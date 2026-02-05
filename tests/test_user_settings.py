"""Tests for bugresolutionradar user settings utilities."""

from __future__ import annotations

from pathlib import Path

import pytest

from bugresolutionradar import user_settings


def _setup_env_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    env_path = tmp_path / ".env"
    example_path = tmp_path / ".env.example"
    monkeypatch.setattr(user_settings, "BUG_ENV_PATH", env_path)
    monkeypatch.setattr(user_settings, "BUG_ENV_EXAMPLE", example_path)
    monkeypatch.setattr(user_settings, "reload_bugresolutionradar_settings", lambda: None)
    return env_path, example_path


def _write_env(path: Path, content: str) -> None:
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _flatten_groups(snapshot: dict[str, object]) -> dict[str, object]:
    groups = snapshot.get("groups", [])
    flat: dict[str, object] = {}
    for group in groups:
        for field in group.get("fields", []):
            flat[field["key"]] = field["value"]
    return flat


def test_get_user_settings_snapshot_includes_groups_and_advanced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path, _ = _setup_env_paths(tmp_path, monkeypatch)
    _write_env(
        env_path,
        """
APP_NAME=Test App
TZ=UTC
SOURCES=filesystem_json,jira
INCIDENTS_UI_ENABLED=true
JIRA_BASE_URL=https://jira.example
JIRA_USER_EMAIL=user@example.com
JIRA_API_TOKEN=token
JIRA_JQL=project = ABC
EXTRA_FOO=bar
""",
    )

    snapshot = user_settings.get_user_settings_snapshot()
    flat = _flatten_groups(snapshot)

    assert flat["sources.jira"] is True
    assert flat["jira.base_url"] == "https://jira.example"
    assert flat["jira.user_email"] == "user@example.com"
    assert flat["jira.jql"] == "project = ABC"
    assert "EXTRA_FOO" in snapshot["advanced_options"]


def test_update_user_settings_persists_sources_and_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path, _ = _setup_env_paths(tmp_path, monkeypatch)
    _write_env(env_path, "SOURCES=filesystem_json\nINCIDENTS_UI_ENABLED=true\n")

    snapshot = user_settings.update_user_settings(
        {
            "sources.jira": True,
            "jira.base_url": "https://jira.example",
            "jira.user_email": "user@example.com",
            "jira.api_token": "token",
            "jira.jql": "project = ABC",
        }
    )

    content = env_path.read_text(encoding="utf-8")
    assert "SOURCES=filesystem_json,jira" in content
    assert "JIRA_BASE_URL=https://jira.example" in content
    assert "JIRA_USER_EMAIL=user@example.com" in content
    assert "JIRA_API_TOKEN=token" in content
    assert "JIRA_JQL=project = ABC" in content
    assert "JIRA_AUTH_MODE=auto" in content

    flat = _flatten_groups(snapshot)
    assert flat["sources.jira"] is True


def test_update_user_settings_requires_jql_or_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path, _ = _setup_env_paths(tmp_path, monkeypatch)
    _write_env(env_path, "SOURCES=\nINCIDENTS_UI_ENABLED=true\n")

    with pytest.raises(ValueError):
        user_settings.update_user_settings(
            {
                "sources.jira": True,
                "jira.base_url": "https://jira.example",
                "jira.user_email": "user@example.com",
                "jira.api_token": "token",
            }
        )
