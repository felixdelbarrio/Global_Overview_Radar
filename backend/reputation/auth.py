from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from secrets import compare_digest
from typing import TYPE_CHECKING, Any, Iterable, Mapping, cast

from fastapi import HTTPException, Request

if TYPE_CHECKING:
    from google.auth import default as google_auth_default
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token
else:
    try:
        from google.auth import default as google_auth_default
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
    except Exception:  # pragma: no cover - optional dependency for local tests
        google_auth_default = None
        google_requests = None
        google_id_token = None

from reputation.config import settings

logger = logging.getLogger(__name__)
_MIN_MUTATION_KEY_LENGTH = 32
_PROXY_AUTH_HEADER = "x-gor-proxy-auth"
_PROXY_AUTH_CLOUD_RUN = "cloudrun-idtoken"

_GROUP_SCOPE = "https://www.googleapis.com/auth/cloud-identity.groups.readonly"
_GROUP_LOOKUP_URL = "https://cloudidentity.googleapis.com/v1/groups:lookup"
_GROUP_MEMBERSHIP_LOOKUP_URL = (
    "https://cloudidentity.googleapis.com/v1/{group_name}/memberships:lookup"
)
_group_name_cache: dict[str, tuple[str, float]] = {}
_group_member_cache: dict[tuple[str, str], tuple[bool, float]] = {}


@dataclass(frozen=True)
class AuthUser:
    email: str
    name: str | None = None
    picture: str | None = None
    subject: str | None = None


def _split_list(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _first_csv_item(value: str | None) -> str | None:
    if not value:
        return None
    for item in value.split(","):
        cleaned = item.strip().lower()
        if cleaned:
            return cleaned
    return None


def _cloud_bypass_user() -> AuthUser:
    email = _first_csv_item(settings.auth_allowed_emails)
    if not email:
        raise HTTPException(
            status_code=500,
            detail="auth bypass misconfigured (missing AUTH_ALLOWED_EMAILS)",
        )
    return AuthUser(
        email=email,
        name="Cloud Run bypass",
        subject="cloudrun-bypass",
    )


def _is_auth_bypass_active() -> bool:
    # When GOOGLE_CLOUD_LOGIN_REQUESTED=false, the system runs in "bypass" mode:
    # requests are authenticated at the infrastructure layer (Cloud Run invoker),
    # and the app does not require an end-user Google ID token.
    return settings.auth_enabled and not settings.google_cloud_login_requested


def _cache_get(cache: dict[Any, tuple[Any, float]], key: Any) -> Any | None:
    cached = cache.get(key)
    if not cached:
        return None
    value, expires_at = cached
    if expires_at <= time.time():
        cache.pop(key, None)
        return None
    return value


def _cache_set(cache: dict[Any, tuple[Any, float]], key: Any, value: Any, ttl: int) -> None:
    if ttl <= 0:
        return
    cache[key] = (value, time.time() + ttl)


def _extract_token(request: Request) -> str | None:
    token = request.headers.get("x-user-id-token") or request.headers.get("x-user-token")
    if token:
        return token.strip()
    # When requests are proxied through the Next.js server route, the `Authorization`
    # header is used for Cloud Run service-to-service invocation (ID token), not for
    # end-user auth. Treat it as infrastructure auth and ignore it here.
    if request.headers.get(_PROXY_AUTH_HEADER) == _PROXY_AUTH_CLOUD_RUN:
        return None
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _enforce_allowed(email: str, allowed: Iterable[str], label: str) -> None:
    if not allowed:
        return
    if email.lower() not in {item.lower() for item in allowed}:
        raise HTTPException(status_code=403, detail=f"{label} not allowed")


def _verify_google_token(token: str) -> Mapping[str, Any]:
    client_id = settings.auth_google_client_id.strip()
    if not client_id:
        raise HTTPException(status_code=500, detail="auth misconfigured (missing client id)")
    try:
        if google_id_token is None or google_requests is None:
            raise HTTPException(status_code=500, detail="auth dependency missing")
        requests_mod = cast(Any, google_requests)
        id_token_mod = cast(Any, google_id_token)
        payload = id_token_mod.verify_oauth2_token(
            token,
            requests_mod.Request(),
            audience=client_id,
        )
        return cast(Mapping[str, Any], payload)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid auth token") from exc


def _get_group_session() -> Any:
    if google_auth_default is None or google_requests is None:
        raise HTTPException(status_code=500, detail="auth dependency missing")
    creds, _ = google_auth_default(scopes=[_GROUP_SCOPE])
    requests_mod = cast(Any, google_requests)
    return requests_mod.AuthorizedSession(creds)


def _resolve_group_name(session: Any, group_key: str, ttl: int) -> str:
    if group_key.startswith("groups/"):
        return group_key
    cached = _cache_get(_group_name_cache, group_key)
    if isinstance(cached, str):
        return cached
    response = session.get(_GROUP_LOOKUP_URL, params={"groupKey.id": group_key})
    if response.status_code == 404:
        raise HTTPException(status_code=500, detail="auth group not found")
    if response.status_code >= 400:
        raise HTTPException(status_code=500, detail="auth group lookup failed")
    payload = response.json()
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=500, detail="auth group lookup missing name")
    _cache_set(_group_name_cache, group_key, name, ttl)
    return name


def _is_group_member(session: Any, group_name: str, email: str, ttl: int) -> bool:
    cache_key = (group_name, email)
    cached = _cache_get(_group_member_cache, cache_key)
    if isinstance(cached, bool):
        return cached
    url = _GROUP_MEMBERSHIP_LOOKUP_URL.format(group_name=group_name)
    response = session.get(url, params={"memberKey.id": email})
    if response.status_code == 200:
        _cache_set(_group_member_cache, cache_key, True, ttl)
        return True
    if response.status_code == 404:
        _cache_set(_group_member_cache, cache_key, False, ttl)
        return False
    raise HTTPException(status_code=500, detail="auth group membership lookup failed")


def _enforce_allowed_groups(email: str, groups: Iterable[str]) -> None:
    group_list = [group for group in groups if group]
    if not group_list:
        return
    ttl = settings.auth_groups_cache_ttl
    session = _get_group_session()
    for group in group_list:
        group_name = _resolve_group_name(session, group, ttl)
        if _is_group_member(session, group_name, email, ttl):
            return
    raise HTTPException(status_code=403, detail="group not allowed")


def require_google_user(request: Request) -> AuthUser:
    if not settings.auth_enabled:
        return AuthUser(email="anonymous")

    # When GOOGLE_CLOUD_LOGIN_REQUESTED=false, interactive login is bypassed.
    if _is_auth_bypass_active():
        user = _cloud_bypass_user()
        logger.warning("auth bypass active email=%s path=%s", user.email, request.url.path)
        return user

    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="missing auth token")

    payload = _verify_google_token(token)

    email = str(payload.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=403, detail="missing email")

    if payload.get("email_verified") is False:
        raise HTTPException(status_code=403, detail="email not verified")

    allowed_emails = _split_list(settings.auth_allowed_emails)
    allowlisted = bool(allowed_emails) and email.lower() in allowed_emails

    allowed_domains = _split_list(settings.auth_allowed_domains)
    allowed_groups = _split_list(settings.auth_allowed_groups)

    if not allowlisted:
        if allowed_domains:
            domain = email.split("@")[-1] if "@" in email else ""
            _enforce_allowed(domain, allowed_domains, "domain")
        if allowed_groups:
            _enforce_allowed_groups(email, allowed_groups)
        if allowed_emails and not allowed_domains and not allowed_groups:
            raise HTTPException(status_code=403, detail="email not allowed")

    logger.info("auth ok email=%s path=%s", email, request.url.path)
    return AuthUser(
        email=email,
        name=str(payload.get("name") or "") or None,
        picture=str(payload.get("picture") or "") or None,
        subject=str(payload.get("sub") or "") or None,
    )


def require_mutation_access(request: Request) -> None:
    """Hardens state-changing endpoints when auth bypass is active."""
    if not _is_auth_bypass_active():
        return
    if not settings.auth_bypass_allow_mutations:
        raise HTTPException(
            status_code=403,
            detail="mutations disabled while auth bypass is active",
        )
    expected = settings.auth_bypass_mutation_key.strip()
    if not expected:
        raise HTTPException(
            status_code=500,
            detail="auth bypass misconfigured (missing AUTH_BYPASS_MUTATION_KEY)",
        )
    if len(expected) < _MIN_MUTATION_KEY_LENGTH:
        raise HTTPException(
            status_code=500,
            detail="auth bypass misconfigured (AUTH_BYPASS_MUTATION_KEY too short)",
        )
    provided = (request.headers.get("x-gor-admin-key") or "").strip()
    if not provided or not compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="admin key required")
