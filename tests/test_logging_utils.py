"""Tests for logging utilities."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from bugresolutionradar import logging_utils


class DummySettings:
    def __init__(
        self,
        *,
        log_enabled: bool,
        log_to_file: bool,
        log_file_name: str = "test.log",
        log_debug: bool = False,
    ) -> None:
        self.log_enabled = log_enabled
        self.log_to_file = log_to_file
        self.log_file_name = log_file_name
        self.log_debug = log_debug


def _reset_logging_state() -> None:
    logging_utils._stop_listener()
    logging_utils._last_signature = None
    logging_utils._last_mtime = None
    logging_utils._last_check = None


def test_configure_logging_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_logging_state()
    monkeypatch.setattr(
        logging_utils,
        "Settings",
        lambda: DummySettings(log_enabled=False, log_to_file=False),
    )
    logging_utils.configure_logging(force=True)
    logger = logging.getLogger("bugresolutionradar")
    assert logger.disabled is True
    assert any(isinstance(h, logging.NullHandler) for h in logger.handlers)


def test_configure_logging_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_logging_state()
    monkeypatch.setattr(
        logging_utils,
        "Settings",
        lambda: DummySettings(log_enabled=True, log_to_file=False, log_debug=True),
    )
    logging_utils.configure_logging(force=True)
    logger = logging.getLogger("bugresolutionradar")
    assert logger.disabled is False
    assert logger.level == logging.DEBUG
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)


def test_configure_logging_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_logging_state()
    log_path = tmp_path / "app.log"
    monkeypatch.setattr(
        logging_utils,
        "Settings",
        lambda: DummySettings(log_enabled=True, log_to_file=True, log_file_name="app.log"),
    )
    monkeypatch.setattr(logging_utils, "_resolve_path", lambda _: log_path)

    logging_utils.configure_logging(force=True)
    logger = logging.getLogger("bugresolutionradar")
    logger.info("hello")
    logging_utils._stop_listener()

    assert log_path.parent.exists()
