from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet

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


def _set_env_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path]:
    env_path = tmp_path / ".env.reputation"
    example_path = tmp_path / ".env.reputation.example"
    advanced_env_path = tmp_path / ".env.reputation.advanced"
    advanced_example_path = tmp_path / ".env.reputation.advanced.example"
    monkeypatch.setattr(user_settings, "REPUTATION_ENV_PATH", env_path, raising=False)
    monkeypatch.setattr(
        user_settings, "REPUTATION_ENV_EXAMPLE", example_path, raising=False
    )
    monkeypatch.setattr(
        user_settings, "REPUTATION_ADVANCED_ENV_PATH", advanced_env_path, raising=False
    )
    monkeypatch.setattr(
        user_settings,
        "REPUTATION_ADVANCED_ENV_EXAMPLE",
        advanced_example_path,
        raising=False,
    )
    return env_path, example_path, advanced_env_path, advanced_example_path


def _set_env_crypto_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "REPUTATION_ENV_CRYPTO_KEY", Fernet.generate_key().decode("utf-8")
    )


def test_settings_snapshot_redacts_secret_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path, _, advanced_env_path, _ = _set_env_paths(monkeypatch, tmp_path)
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=super-secret-openai",
                "GEMINI_API_KEY=super-secret-gemini",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    advanced_env_path.write_text(
        "\n".join(
            [
                "CUSTOM_TIMEOUT=15",
                "CUSTOM_SECRET_TOKEN=hidden-value",
            ]
        )
        + "\n",
        encoding="utf-8",
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
    _set_env_crypto_key(monkeypatch)
    env_path, _, _, _ = _set_env_paths(monkeypatch, tmp_path)
    env_path.write_text("OPENAI_API_KEY=super-secret-openai\n", encoding="utf-8")

    user_settings.update_user_settings({"llm.openai_key": "********"})
    updated = user_settings._parse_env_file(env_path)
    assert updated["OPENAI_API_KEY"] == "super-secret-openai"


def test_update_settings_encrypts_secret_values_at_rest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _set_env_crypto_key(monkeypatch)
    env_path, _, _, _ = _set_env_paths(monkeypatch, tmp_path)
    env_path.write_text("LLM_ENABLED=true\nOPENAI_API_KEY=\n", encoding="utf-8")

    user_settings.update_user_settings({"llm.openai_key": "super-secret-openai"})

    raw_content = env_path.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=super-secret-openai" not in raw_content
    assert "OPENAI_API_KEY=enc:v1:" in raw_content
    parsed = user_settings._parse_env_file(env_path)
    assert parsed["OPENAI_API_KEY"] == "super-secret-openai"


def test_settings_snapshot_forces_llm_disabled_without_selected_provider_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path, _, _, _ = _set_env_paths(monkeypatch, tmp_path)
    env_path.write_text(
        "LLM_ENABLED=true\nLLM_PROVIDER=openai\nOPENAI_API_KEY=\nGEMINI_API_KEY=gemini-secret\n",
        encoding="utf-8",
    )

    snapshot = user_settings.get_user_settings_snapshot()
    fields = _collect_fields(snapshot)

    assert fields["llm.enabled"]["value"] is False


def test_update_settings_forces_llm_disabled_when_selected_provider_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path, _, _, _ = _set_env_paths(monkeypatch, tmp_path)
    env_path.write_text(
        "LLM_ENABLED=true\nLLM_PROVIDER=gemini\nOPENAI_API_KEY=openai-secret\nGEMINI_API_KEY=\n",
        encoding="utf-8",
    )

    user_settings.update_user_settings({"llm.enabled": True})
    updated = user_settings._parse_env_file(env_path)

    assert updated["LLM_ENABLED"] == "false"


def test_update_settings_keeps_llm_choice_when_selected_provider_key_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path, _, _, _ = _set_env_paths(monkeypatch, tmp_path)
    env_path.write_text(
        "LLM_ENABLED=false\nLLM_PROVIDER=gemini\nGEMINI_API_KEY=gemini-secret\n",
        encoding="utf-8",
    )

    user_settings.update_user_settings({"llm.enabled": True})
    updated = user_settings._parse_env_file(env_path)

    assert updated["LLM_ENABLED"] == "true"


def test_update_settings_rejects_cloudrun_only_keys(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path, _, _, _ = _set_env_paths(monkeypatch, tmp_path)
    env_path.write_text("LLM_ENABLED=false\n", encoding="utf-8")

    with pytest.raises(ValueError, match="cloudrun.env"):
        user_settings.update_user_settings(
            {"advanced.AUTH_GOOGLE_CLIENT_ID": "abc.apps.googleusercontent.com"}
        )


def test_settings_snapshot_hides_advanced_group_on_cloud_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path, _, advanced_env_path, _ = _set_env_paths(monkeypatch, tmp_path)
    env_path.write_text("LLM_ENABLED=false\n", encoding="utf-8")
    advanced_env_path.write_text(
        "\n".join(
            [
                "REPUTATION_LOG_ENABLED=true",
                "REPUTATION_LOG_TO_FILE=true",
                "REPUTATION_LOG_FILE_NAME=reputation.log",
                "REPUTATION_LOG_DEBUG=true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("K_SERVICE", "gor-backend")

    snapshot = user_settings.get_user_settings_snapshot()
    group_ids = {group.get("id") for group in snapshot.get("groups", [])}
    assert "advanced" not in group_ids
    assert snapshot.get("advanced_options") == []


def test_enable_advanced_settings_creates_advanced_file_from_example(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path, _, advanced_env_path, advanced_example_path = _set_env_paths(
        monkeypatch, tmp_path
    )
    env_path.write_text("LLM_ENABLED=false\n", encoding="utf-8")
    advanced_example_path.write_text(
        "REPUTATION_LOG_ENABLED=true\nREPUTATION_LOG_TO_FILE=true\nCUSTOM_ADVANCED=42\n",
        encoding="utf-8",
    )
    assert not advanced_env_path.exists()

    snapshot = user_settings.enable_advanced_settings()

    assert advanced_env_path.exists()
    advanced_values = user_settings._parse_env_file(advanced_env_path)
    assert advanced_values["REPUTATION_LOG_ENABLED"] == "true"
    assert advanced_values["REPUTATION_LOG_TO_FILE"] == "true"
    assert advanced_values["CUSTOM_ADVANCED"] == "42"
    assert snapshot.get("advanced_env_exists") is True


def test_update_settings_persists_advanced_values_in_advanced_file_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path, _, advanced_env_path, advanced_example_path = _set_env_paths(
        monkeypatch, tmp_path
    )
    env_path.write_text(
        "NEWS_LANG=es\nNEWSAPI_LANGUAGE=es\nLLM_ENABLED=false\n", encoding="utf-8"
    )
    advanced_example_path.write_text(
        "REPUTATION_LOG_ENABLED=false\nREPUTATION_LOG_TO_FILE=false\nREPUTATION_LOG_FILE_NAME=reputation.log\nREPUTATION_LOG_DEBUG=false\n",
        encoding="utf-8",
    )
    advanced_env_path.write_text(
        "REPUTATION_LOG_ENABLED=false\nREPUTATION_LOG_TO_FILE=false\nREPUTATION_LOG_FILE_NAME=reputation.log\nREPUTATION_LOG_DEBUG=false\n",
        encoding="utf-8",
    )

    user_settings.update_user_settings(
        {
            "advanced.log_enabled": True,
            "advanced.REPUTATION_HTTP_CACHE_TTL_SEC": "90",
            "language.preference": "en",
        }
    )

    base_values = user_settings._parse_env_file(env_path)
    advanced_values = user_settings._parse_env_file(advanced_env_path)

    assert "REPUTATION_LOG_ENABLED" not in base_values
    assert "REPUTATION_HTTP_CACHE_TTL_SEC" not in base_values
    assert "NEWS_LANG" not in base_values
    assert advanced_values["NEWS_LANG"] == "en"
    assert advanced_values["REPUTATION_LOG_ENABLED"] == "true"
    assert advanced_values["REPUTATION_HTTP_CACHE_TTL_SEC"] == "90"


def test_settings_endpoint_allows_read_without_admin_key_in_auth_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import reputation.config as rep_config
    from reputation.api.routers import reputation as reputation_router

    key = "32chars-minimum-admin-key-12345678"

    monkeypatch.setattr(
        rep_config.settings, "google_cloud_login_requested", False, raising=False
    )
    monkeypatch.setattr(
        rep_config.settings, "auth_allowed_emails", "owner@example.com", raising=False
    )
    monkeypatch.setattr(
        rep_config.settings, "auth_bypass_mutation_key", key, raising=False
    )

    app = create_app()
    app.dependency_overrides[reputation_router._refresh_settings] = lambda: None
    client = TestClient(app)

    read_snapshot = client.get("/reputation/settings")
    assert read_snapshot.status_code == 200


def test_settings_update_endpoint_allows_without_admin_key_in_auth_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import reputation.config as rep_config
    from reputation.api.routers import reputation as reputation_router

    key = "32chars-minimum-admin-key-12345678"

    monkeypatch.setattr(
        rep_config.settings, "google_cloud_login_requested", False, raising=False
    )
    monkeypatch.setattr(
        rep_config.settings, "auth_allowed_emails", "owner@example.com", raising=False
    )
    monkeypatch.setattr(
        rep_config.settings, "auth_bypass_mutation_key", key, raising=False
    )

    app = create_app()
    app.dependency_overrides[reputation_router._refresh_settings] = lambda: None
    client = TestClient(app)

    allowed = client.post(
        "/reputation/settings", json={"values": {"llm.enabled": True}}
    )
    assert allowed.status_code == 200
