from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Iterable

from fastapi import HTTPException, Request
from google.auth.transport import requests
from google.oauth2 import id_token

from reputation.config import settings


logger = logging.getLogger(__name__)

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


def _verify_google_token(token: str) -> dict[str, object]:
    client_id = settings.auth_google_client_id.strip()
    if not client_id:
        raise HTTPException(status_code=500, detail="auth misconfigured (missing client id)")
    try:
        return id_token.verify_oauth2_token(token, requests.Request(), audience=client_id)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid auth token") from exc


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

    logger.info("auth ok email=%s path=%s", email, request.url.path)
    return AuthUser(
        email=email,
        name=str(payload.get("name") or "") or None,
        picture=str(payload.get("picture") or "") or None,
        subject=str(payload.get("sub") or "") or None,
    )
