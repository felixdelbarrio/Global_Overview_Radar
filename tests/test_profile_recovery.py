from __future__ import annotations

from pathlib import Path

import pytest


def test_resolve_config_files_recovers_missing_profile_from_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import reputation.config as rep_config

    cfg_dir = tmp_path / "data" / "reputation"
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
