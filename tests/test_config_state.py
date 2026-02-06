from __future__ import annotations

from pathlib import Path

from reputation import config as rep_config


def test_profile_state_roundtrip(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / "profile_state.json"
    monkeypatch.setattr(rep_config, "PROFILE_STATE_PATH", state_path)

    rep_config._save_profile_state("samples", ["alpha", "beta"])
    data = rep_config._load_profile_state()

    assert data["source"] == "samples"
    assert data["profiles"] == ["alpha", "beta"]


def test_profile_state_invalid_payload(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / "profile_state.json"
    monkeypatch.setattr(rep_config, "PROFILE_STATE_PATH", state_path)

    state_path.write_text("[]", encoding="utf-8")
    assert rep_config._load_profile_state() == {}

    state_path.write_text("{", encoding="utf-8")
    assert rep_config._load_profile_state() == {}


def test_apply_profile_path_template(tmp_path: Path) -> None:
    default_value = tmp_path / "reputation_cache.json"

    templated = rep_config._apply_profile_path_template(
        Path("/tmp/cache__{profile_key}.json"),
        default_value,
        "reputation_cache__profile.json",
        "alpha__beta",
    )
    assert str(templated).endswith("cache__alpha__beta.json")

    replaced_default = rep_config._apply_profile_path_template(
        default_value,
        default_value,
        "reputation_cache__alpha.json",
        "alpha",
    )
    assert replaced_default.name == "reputation_cache__alpha.json"


def test_resolve_paths_for_source() -> None:
    cfg_path, llm_path = rep_config._resolve_paths_for_source("samples")
    assert cfg_path == rep_config.DEFAULT_SAMPLE_CONFIG_PATH
    assert llm_path == rep_config.DEFAULT_SAMPLE_LLM_CONFIG_PATH

    cfg_path, llm_path = rep_config._resolve_paths_for_source("default")
    assert cfg_path == rep_config.BASE_CONFIG_PATH
    assert llm_path == rep_config.BASE_LLM_CONFIG_PATH
