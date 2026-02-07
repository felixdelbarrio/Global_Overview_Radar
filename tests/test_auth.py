from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from reputation import auth
from reputation.config import settings


def _make_request(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "scheme": "http",
        "path": "/",
        "server": ("testserver", 80),
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


def test_verify_google_token_missing_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_google_client_id", "", raising=False)
    with pytest.raises(HTTPException) as exc:
        auth._verify_google_token("token")
    assert exc.value.status_code == 500


def test_require_google_user_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    with pytest.raises(HTTPException) as exc:
        auth.require_google_user(_make_request({}))
    assert exc.value.status_code == 401


def test_require_google_user_domain_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auth_allowed_emails", "", raising=False)
    monkeypatch.setattr(settings, "auth_allowed_domains", "bbva.com", raising=False)
    monkeypatch.setattr(settings, "auth_allowed_groups", "", raising=False)

    def fake_verify(_: str) -> dict[str, Any]:
        return {"email": "user@gmail.com", "email_verified": True}

    monkeypatch.setattr(auth, "_verify_google_token", fake_verify)

    with pytest.raises(HTTPException) as exc:
        auth.require_google_user(_make_request({"x-user-id-token": "token"}))
    assert exc.value.status_code == 403


def test_require_google_user_allows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auth_allowed_emails", "", raising=False)
    monkeypatch.setattr(settings, "auth_allowed_domains", "", raising=False)
    monkeypatch.setattr(settings, "auth_allowed_groups", "", raising=False)

    def fake_verify(_: str) -> dict[str, Any]:
        return {
            "email": "felix.delbarrio@bbva.com",
            "email_verified": True,
            "name": "Felix",
            "picture": "pic",
            "sub": "123",
        }

    monkeypatch.setattr(auth, "_verify_google_token", fake_verify)

    user = auth.require_google_user(_make_request({"x-user-id-token": "token"}))
    assert user.email == "felix.delbarrio@bbva.com"
