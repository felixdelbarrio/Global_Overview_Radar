from __future__ import annotations

from pathlib import Path

import pytest

from reputation import config as rep_config


def _write(path: Path, name: str) -> Path:
    file_path = path / name
    file_path.write_text("{}", encoding="utf-8")
    return file_path


def test_parse_profile_selector() -> None:
    assert rep_config._parse_profile_selector("") == []
    assert rep_config._parse_profile_selector("  ") == []
    assert rep_config._parse_profile_selector("all") == []
    assert rep_config._parse_profile_selector("*") == []
    assert rep_config._parse_profile_selector("todos") == []
    assert rep_config._parse_profile_selector("banking, retail.json") == [
        "banking",
        "retail",
    ]


def test_sorted_config_files(tmp_path: Path) -> None:
    _write(tmp_path, "b.json")
    _write(tmp_path, "config.json")
    _write(tmp_path, "a.json")

    files = rep_config._sorted_config_files(tmp_path)
    assert [f.name for f in files] == ["config.json", "a.json", "b.json"]


def test_filter_profile_files_missing(tmp_path: Path) -> None:
    _write(tmp_path, "alpha.json")
    files = rep_config._sorted_config_files(tmp_path)
    with pytest.raises(FileNotFoundError):
        rep_config._filter_profile_files(files, ["beta"])


def test_resolve_config_files_dir_and_file(tmp_path: Path) -> None:
    _write(tmp_path, "config.json")
    _write(tmp_path, "alpha.json")
    _write(tmp_path, "beta.json")

    files = rep_config._resolve_config_files(tmp_path, ["beta", "alpha"])
    assert [f.stem for f in files] == ["alpha", "beta"]

    alpha_file = tmp_path / "alpha.json"
    files = rep_config._resolve_config_files(alpha_file, ["alpha"])
    assert files == [alpha_file]

    with pytest.raises(FileNotFoundError):
        rep_config._resolve_config_files(alpha_file, ["beta"])


def test_profile_key_from_files(tmp_path: Path) -> None:
    a = _write(tmp_path, "a.json")
    b = _write(tmp_path, "b.json")
    key = rep_config._profile_key_from_files([b, a])
    assert key == "a__b"
