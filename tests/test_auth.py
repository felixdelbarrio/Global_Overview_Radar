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
    monkeypatch.setattr(settings, "google_cloud_login_requested", False, raising=False)
    with pytest.raises(HTTPException) as exc:
        auth.require_google_user(_make_request({}))
    assert exc.value.status_code == 401


def test_require_google_user_ignores_cloud_run_proxy_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "google_cloud_login_requested", False, raising=False)
    with pytest.raises(HTTPException) as exc:
        auth.require_google_user(
            _make_request(
                {
                    "authorization": "Bearer cloud-run-id-token",
                    "x-gor-proxy-auth": "cloudrun-idtoken",
                }
            )
        )
    assert exc.value.status_code == 401
    assert exc.value.detail == "missing auth token"


def test_require_google_user_domain_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "google_cloud_login_requested", False, raising=False)
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
    monkeypatch.setattr(settings, "google_cloud_login_requested", False, raising=False)
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


def test_require_google_user_bypass_uses_first_allowed_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "google_cloud_login_requested", True, raising=False)
    monkeypatch.setattr(
        settings,
        "auth_allowed_emails",
        "felixdelbarriocebrian@gmail.com,alescribano@gmail.com",
        raising=False,
    )

    user = auth.require_google_user(_make_request({}))
    assert user.email == "felixdelbarriocebrian@gmail.com"
    assert user.subject == "cloudrun-bypass"


def test_require_google_user_bypass_needs_allowed_emails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "google_cloud_login_requested", True, raising=False)
    monkeypatch.setattr(settings, "auth_allowed_emails", "", raising=False)

    with pytest.raises(HTTPException) as exc:
        auth.require_google_user(_make_request({}))
    assert exc.value.status_code == 500


def test_require_mutation_access_allows_when_bypass_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "google_cloud_login_requested", False, raising=False)

    # Should pass-through without requiring admin key when bypass is disabled.
    auth.require_mutation_access(_make_request({}))


def test_require_mutation_access_blocks_when_bypass_mutations_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "google_cloud_login_requested", True, raising=False)
    monkeypatch.setattr(settings, "auth_bypass_allow_mutations", False, raising=False)
    monkeypatch.setattr(
        settings,
        "auth_bypass_mutation_key",
        "32chars-minimum-admin-key-12345678",
        raising=False,
    )

    with pytest.raises(HTTPException) as exc:
        auth.require_mutation_access(_make_request({}))
    assert exc.value.status_code == 403


def test_require_mutation_access_requires_key_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "google_cloud_login_requested", True, raising=False)
    monkeypatch.setattr(settings, "auth_bypass_allow_mutations", True, raising=False)
    monkeypatch.setattr(
        settings,
        "auth_bypass_mutation_key",
        "32chars-minimum-admin-key-12345678",
        raising=False,
    )

    with pytest.raises(HTTPException) as exc:
        auth.require_mutation_access(_make_request({}))
    assert exc.value.status_code == 403


def test_require_mutation_access_500_when_key_missing_in_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "google_cloud_login_requested", True, raising=False)
    monkeypatch.setattr(settings, "auth_bypass_allow_mutations", True, raising=False)
    monkeypatch.setattr(settings, "auth_bypass_mutation_key", "", raising=False)

    with pytest.raises(HTTPException) as exc:
        auth.require_mutation_access(_make_request({"x-gor-admin-key": "anything"}))
    assert exc.value.status_code == 500


def test_require_mutation_access_500_when_key_too_short(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "google_cloud_login_requested", True, raising=False)
    monkeypatch.setattr(settings, "auth_bypass_allow_mutations", True, raising=False)
    monkeypatch.setattr(settings, "auth_bypass_mutation_key", "short", raising=False)

    with pytest.raises(HTTPException) as exc:
        auth.require_mutation_access(_make_request({"x-gor-admin-key": "short"}))
    assert exc.value.status_code == 500


def test_require_mutation_access_rejects_invalid_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "google_cloud_login_requested", True, raising=False)
    monkeypatch.setattr(settings, "auth_bypass_allow_mutations", True, raising=False)
    monkeypatch.setattr(
        settings,
        "auth_bypass_mutation_key",
        "32chars-minimum-admin-key-12345678",
        raising=False,
    )

    with pytest.raises(HTTPException) as exc:
        auth.require_mutation_access(_make_request({"x-gor-admin-key": "wrong"}))
    assert exc.value.status_code == 403


def test_require_mutation_access_accepts_valid_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "google_cloud_login_requested", True, raising=False)
    monkeypatch.setattr(settings, "auth_bypass_allow_mutations", True, raising=False)
    monkeypatch.setattr(
        settings,
        "auth_bypass_mutation_key",
        "32chars-minimum-admin-key-12345678",
        raising=False,
    )

    auth.require_mutation_access(
        _make_request({"x-gor-admin-key": "32chars-minimum-admin-key-12345678"})
    )
