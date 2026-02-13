from __future__ import annotations

from pathlib import Path

import pytest


def test_resolve_config_files_recovers_missing_profile_from_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import reputation.config as rep_config

    cfg_dir = tmp_path / "data" / "reputation"
    sample_cfg_dir = tmp_path / "data" / "reputation_samples"
    sample_cfg_dir.mkdir(parents=True, exist_ok=True)
    (sample_cfg_dir / "banking_bbva_empresas.json").write_text("{}", encoding="utf-8")
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "banking_bbva_retail.json").write_text("{}", encoding="utf-8")

    def _fake_sync_from_state(
        local_path: Path, *, key: str | None = None, repo_root: Path | None = None
    ) -> bool:
        del key, repo_root
        if local_path.name != "banking_bbva_empresas.json":
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text("{}", encoding="utf-8")
        return True

    monkeypatch.setattr(rep_config, "state_store_enabled", lambda: True)
    monkeypatch.setattr(rep_config, "sync_from_state", _fake_sync_from_state)
    monkeypatch.setattr(rep_config, "DEFAULT_SAMPLE_CONFIG_PATH", sample_cfg_dir)

    files = rep_config._resolve_config_files(cfg_dir, ["banking_bbva_empresas"])

    assert [file.stem for file in files] == ["banking_bbva_empresas"]
    assert (cfg_dir / "banking_bbva_empresas.json").exists()


def test_resolve_config_files_seeds_default_from_samples(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import reputation.config as rep_config

    base_cfg_dir = tmp_path / "data" / "reputation"
    base_llm_dir = tmp_path / "data" / "reputation_llm"
    sample_cfg_dir = tmp_path / "data" / "reputation_samples"
    sample_llm_dir = tmp_path / "data" / "reputation_llm_samples"
    sample_cfg_dir.mkdir(parents=True, exist_ok=True)
    sample_llm_dir.mkdir(parents=True, exist_ok=True)
    (sample_cfg_dir / "banking_bbva_empresas.json").write_text("{}", encoding="utf-8")
    (sample_llm_dir / "banking_bbva_empresas_llm.json").write_text(
        "{}", encoding="utf-8"
    )

    monkeypatch.setattr(rep_config, "state_store_enabled", lambda: False)
    monkeypatch.setattr(rep_config, "BASE_CONFIG_PATH", base_cfg_dir)
    monkeypatch.setattr(rep_config, "BASE_LLM_CONFIG_PATH", base_llm_dir)
    monkeypatch.setattr(rep_config, "DEFAULT_SAMPLE_CONFIG_PATH", sample_cfg_dir)
    monkeypatch.setattr(rep_config, "DEFAULT_SAMPLE_LLM_CONFIG_PATH", sample_llm_dir)

    files = rep_config._resolve_config_files(base_cfg_dir, ["banking_bbva_empresas"])

    assert [file.stem for file in files] == ["banking_bbva_empresas"]
    assert (base_cfg_dir / "banking_bbva_empresas.json").exists()
    assert (base_llm_dir / "banking_bbva_empresas_llm.json").exists()


def test_resolve_llm_config_files_recovers_missing_llm_from_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import reputation.config as rep_config

    llm_dir = tmp_path / "data" / "reputation_llm"
    cfg_file = tmp_path / "data" / "reputation" / "banking_bbva_empresas.json"
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text("{}", encoding="utf-8")

    def _fake_sync_from_state(
        local_path: Path, *, key: str | None = None, repo_root: Path | None = None
    ) -> bool:
        del key, repo_root
        if local_path.name != "banking_bbva_empresas_llm.json":
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text("{}", encoding="utf-8")
        return True

    monkeypatch.setattr(rep_config, "state_store_enabled", lambda: True)
    monkeypatch.setattr(rep_config, "sync_from_state", _fake_sync_from_state)

    files = rep_config._resolve_llm_config_files([cfg_file], llm_dir)

    assert [file.name for file in files] == ["banking_bbva_empresas_llm.json"]
    assert (llm_dir / "banking_bbva_empresas_llm.json").exists()


def test_resolve_default_workspace_paths_avoids_sample_directories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import reputation.config as rep_config

    sample_cfg_dir = tmp_path / "backend" / "data" / "reputation_samples"
    sample_llm_dir = tmp_path / "backend" / "data" / "reputation_llm_samples"
    default_cfg_dir = tmp_path / "data" / "reputation"
    default_llm_dir = tmp_path / "data" / "reputation_llm"
    sample_cfg_dir.mkdir(parents=True, exist_ok=True)
    sample_llm_dir.mkdir(parents=True, exist_ok=True)
    default_cfg_dir.mkdir(parents=True, exist_ok=True)
    default_llm_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(rep_config, "DEFAULT_SAMPLE_CONFIG_PATH", sample_cfg_dir)
    monkeypatch.setattr(rep_config, "DEFAULT_SAMPLE_LLM_CONFIG_PATH", sample_llm_dir)
    monkeypatch.setattr(rep_config, "DEFAULT_CONFIG_PATH", default_cfg_dir)
    monkeypatch.setattr(rep_config, "DEFAULT_LLM_CONFIG_PATH", default_llm_dir)
    monkeypatch.setattr(rep_config, "BASE_CONFIG_PATH", sample_cfg_dir)
    monkeypatch.setattr(rep_config, "BASE_LLM_CONFIG_PATH", sample_llm_dir)

    cfg_path, llm_path = rep_config._resolve_default_workspace_paths()

    assert cfg_path == default_cfg_dir
    assert llm_path == default_llm_dir


def test_apply_samples_does_not_mutate_sample_catalog_when_default_is_misconfigured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import reputation.config as rep_config

    sample_cfg_dir = tmp_path / "backend" / "data" / "reputation_samples"
    sample_llm_dir = tmp_path / "backend" / "data" / "reputation_llm_samples"
    default_cfg_dir = tmp_path / "data" / "reputation"
    default_llm_dir = tmp_path / "data" / "reputation_llm"
    profile_state_path = tmp_path / "data" / "cache" / "reputation_profile.json"
    sample_cfg_dir.mkdir(parents=True, exist_ok=True)
    sample_llm_dir.mkdir(parents=True, exist_ok=True)
    default_cfg_dir.mkdir(parents=True, exist_ok=True)
    default_llm_dir.mkdir(parents=True, exist_ok=True)

    (sample_cfg_dir / "banking_bbva_empresas.json").write_text("{}", encoding="utf-8")
    (sample_cfg_dir / "banking_bbva_retail.json").write_text("{}", encoding="utf-8")
    (sample_llm_dir / "banking_bbva_empresas_llm.json").write_text(
        "{}", encoding="utf-8"
    )
    (sample_llm_dir / "banking_bbva_retail_llm.json").write_text("{}", encoding="utf-8")

    # Existing workspace files should be replaced.
    (default_cfg_dir / "obsolete.json").write_text("{}", encoding="utf-8")
    (default_llm_dir / "obsolete_llm.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(rep_config, "state_store_enabled", lambda: False)
    monkeypatch.setattr(rep_config, "DEFAULT_SAMPLE_CONFIG_PATH", sample_cfg_dir)
    monkeypatch.setattr(rep_config, "DEFAULT_SAMPLE_LLM_CONFIG_PATH", sample_llm_dir)
    monkeypatch.setattr(rep_config, "DEFAULT_CONFIG_PATH", default_cfg_dir)
    monkeypatch.setattr(rep_config, "DEFAULT_LLM_CONFIG_PATH", default_llm_dir)
    monkeypatch.setattr(rep_config, "BASE_CONFIG_PATH", sample_cfg_dir)
    monkeypatch.setattr(rep_config, "BASE_LLM_CONFIG_PATH", sample_llm_dir)
    monkeypatch.setattr(rep_config, "PROFILE_STATE_PATH", profile_state_path)

    result = rep_config.apply_sample_profiles_to_default(["banking_bbva_retail"])

    assert sorted(p.name for p in sample_cfg_dir.glob("*.json")) == [
        "banking_bbva_empresas.json",
        "banking_bbva_retail.json",
    ]
    assert sorted(p.name for p in sample_llm_dir.glob("*.json")) == [
        "banking_bbva_empresas_llm.json",
        "banking_bbva_retail_llm.json",
    ]
    assert sorted(p.name for p in default_cfg_dir.glob("*.json")) == [
        "banking_bbva_retail.json"
    ]
    assert sorted(p.name for p in default_llm_dir.glob("*.json")) == [
        "banking_bbva_retail_llm.json"
    ]
    assert result["active"]["source"] == "default"
    assert result["active"]["profiles"] == ["banking_bbva_retail"]


def test_set_profile_state_rejects_path_like_profile_name() -> None:
    import reputation.config as rep_config

    with pytest.raises(ValueError, match="Invalid profile name"):
        rep_config.set_profile_state("samples", ["../etc/passwd"])


def test_set_profile_state_rejects_unknown_profile() -> None:
    import reputation.config as rep_config

    with pytest.raises(FileNotFoundError, match="not found"):
        rep_config.set_profile_state("samples", ["perfil_inexistente"])
