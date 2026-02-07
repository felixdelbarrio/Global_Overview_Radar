from __future__ import annotations

import logging
import time
from dataclasses import dataclass
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
    if allowed_emails:
        _enforce_allowed(email, allowed_emails, "email")

    allowed_domains = _split_list(settings.auth_allowed_domains)
    if allowed_domains:
        domain = email.split("@")[-1] if "@" in email else ""
        _enforce_allowed(domain, allowed_domains, "domain")

    allowed_groups = _split_list(settings.auth_allowed_groups)
    if allowed_groups:
        _enforce_allowed_groups(email, allowed_groups)

    logger.info("auth ok email=%s path=%s", email, request.url.path)
    return AuthUser(
        email=email,
        name=str(payload.get("name") or "") or None,
        picture=str(payload.get("picture") or "") or None,
        subject=str(payload.get("sub") or "") or None,
    )
