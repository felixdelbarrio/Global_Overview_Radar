from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from secrets import compare_digest
from typing import TYPE_CHECKING, Any, Mapping, cast

from fastapi import HTTPException, Request

if TYPE_CHECKING:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token
else:
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
    except Exception:  # pragma: no cover - optional dependency for local tests
        google_requests = None
        google_id_token = None

from reputation.config import settings

logger = logging.getLogger(__name__)
_MIN_MUTATION_KEY_LENGTH = 32
_PROXY_AUTH_HEADER = "x-gor-proxy-auth"
_PROXY_AUTH_CLOUD_RUN = "cloudrun-idtoken"


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


def _extract_token(request: Request) -> str | None:
    token = request.headers.get("x-user-id-token") or request.headers.get("x-user-token")
    if token:
        return token.strip()
    # On Cloud Run, the `Authorization` header is reserved for infrastructure auth
    # (service-to-service invoker ID token). End-user auth must be passed explicitly
    # via `x-user-id-token`.
    if os.environ.get("K_SERVICE"):
        return None
    # When requests are proxied through the Next.js server route, the `Authorization`
    # header is used for Cloud Run service-to-service invocation (ID token), not for
    # end-user auth. Treat it as infrastructure auth and ignore it here.
    if request.headers.get(_PROXY_AUTH_HEADER) == _PROXY_AUTH_CLOUD_RUN:
        return None
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


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
    if allowed_emails and email not in allowed_emails:
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
