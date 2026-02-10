from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reputation import user_settings
from reputation.api.main import create_app


def _collect_fields(snapshot: dict) -> dict[str, dict]:
    fields: dict[str, dict] = {}
    for group in snapshot.get("groups", []):
        for field in group.get("fields", []):
            key = field.get("key")
            if isinstance(key, str):
                fields[key] = field
    return fields


def test_settings_snapshot_redacts_secret_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env.reputation"
    example_path = tmp_path / ".env.reputation.example"
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=super-secret-openai",
                "GEMINI_API_KEY=super-secret-gemini",
                "CUSTOM_TIMEOUT=15",
                "CUSTOM_SECRET_TOKEN=hidden-value",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(user_settings, "REPUTATION_ENV_PATH", env_path, raising=False)
    monkeypatch.setattr(
        user_settings, "REPUTATION_ENV_EXAMPLE", example_path, raising=False
    )

    snapshot = user_settings.get_user_settings_snapshot()
    fields = _collect_fields(snapshot)

    assert fields["llm.openai_key"]["type"] == "secret"
    assert fields["llm.openai_key"]["value"] == "********"
    assert fields["llm.openai_key"]["configured"] is True

    assert fields["llm.gemini_key"]["type"] == "secret"
    assert fields["llm.gemini_key"]["value"] == "********"
    assert fields["llm.gemini_key"]["configured"] is True

    assert fields["advanced.CUSTOM_SECRET_TOKEN"]["type"] == "secret"
    assert fields["advanced.CUSTOM_SECRET_TOKEN"]["value"] == "********"
    assert fields["advanced.CUSTOM_SECRET_TOKEN"]["configured"] is True

    assert fields["advanced.CUSTOM_TIMEOUT"]["type"] == "string"
    assert fields["advanced.CUSTOM_TIMEOUT"]["value"] == "15"


def test_update_settings_ignores_secret_mask_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env.reputation"
    example_path = tmp_path / ".env.reputation.example"
    env_path.write_text("OPENAI_API_KEY=super-secret-openai\n", encoding="utf-8")

    monkeypatch.setattr(user_settings, "REPUTATION_ENV_PATH", env_path, raising=False)
    monkeypatch.setattr(
        user_settings, "REPUTATION_ENV_EXAMPLE", example_path, raising=False
    )

    user_settings.update_user_settings({"llm.openai_key": "********"})
    updated = user_settings._parse_env_file(env_path)
    assert updated["OPENAI_API_KEY"] == "super-secret-openai"


def test_settings_endpoint_requires_admin_key_in_auth_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import reputation.config as rep_config
    from reputation.api.routers import reputation as reputation_router

    key = "32chars-minimum-admin-key-12345678"

    monkeypatch.setattr(rep_config.settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(
        rep_config.settings, "google_cloud_login_requested", True, raising=False
    )
    monkeypatch.setattr(
        rep_config.settings, "auth_allowed_emails", "owner@example.com", raising=False
    )
    monkeypatch.setattr(
        rep_config.settings, "auth_bypass_allow_mutations", True, raising=False
    )
    monkeypatch.setattr(
        rep_config.settings, "auth_bypass_mutation_key", key, raising=False
    )

    app = create_app()
    app.dependency_overrides[reputation_router._refresh_settings] = lambda: None
    client = TestClient(app)

    denied = client.get("/reputation/settings")
    assert denied.status_code == 403

    allowed = client.get("/reputation/settings", headers={"x-gor-admin-key": key})
    assert allowed.status_code == 200
