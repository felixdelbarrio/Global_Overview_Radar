"""Configuracion de logging para reputation."""

from __future__ import annotations

import atexit
import logging
import time
from contextlib import suppress
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path
from queue import Queue
from threading import Lock
from types import TracebackType
from typing import Mapping, Optional

from reputation.config import REPO_ROOT, REPUTATION_ENV_PATH, ReputationSettings

_DISABLED_LEVEL = logging.CRITICAL + 10
_BASE_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_DEBUG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_last_signature: Optional[tuple[bool, bool, str, bool]] = None
_last_mtime: Optional[float] = None
_last_check: Optional[float] = None
_listener: Optional[QueueListener] = None
_listener_handlers: list[logging.Handler] = []
_config_lock = Lock()
_CHECK_INTERVAL_SEC = 0.5
_atexit_registered = False


def _resolve_path(file_name: str | Path) -> Path:
    name = str(file_name).strip() or "reputation.log"
    path = Path(name)
    if path.is_absolute():
        return path
    return (REPO_ROOT / "logs" / path).resolve()


def _env_mtime() -> Optional[float]:
    try:
        return REPUTATION_ENV_PATH.stat().st_mtime
    except FileNotFoundError:
        return None


def _stop_listener() -> None:
    global _listener, _listener_handlers
    if not _listener:
        return
    _listener.stop()
    for handler in _listener_handlers:
        with suppress(Exception):
            handler.close()
    _listener = None
    _listener_handlers = []


def _should_check() -> bool:
    global _last_check
    now = time.monotonic()
    if _last_check is None or (now - _last_check) >= _CHECK_INTERVAL_SEC:
        _last_check = now
        return True
    return False


def configure_logging(force: bool = False) -> None:
    """Configura logging leyendo la config actual desde .env.reputation."""
    global _last_signature, _last_mtime, _listener, _listener_handlers, _atexit_registered

    if not force and _last_signature is not None and not _should_check():
        return

    mtime = _env_mtime()
    if not force and _last_signature is not None and _last_mtime == mtime:
        return

    with _config_lock:
        mtime = _env_mtime()
        if not force and _last_signature is not None and _last_mtime == mtime:
            return
        _last_mtime = mtime

        cfg = ReputationSettings()
        file_path = str(_resolve_path(cfg.log_file_name)) if cfg.log_to_file else ""
        signature = (
            cfg.log_enabled,
            cfg.log_to_file,
            file_path,
            cfg.log_debug,
        )
        if not force and _last_signature == signature:
            return
        _last_signature = signature

    logger = logging.getLogger("reputation")
    _stop_listener()
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        with suppress(Exception):
            handler.close()

    if not cfg.log_enabled:
        logger.disabled = True
        logger.setLevel(_DISABLED_LEVEL)
        logger.propagate = False
        logger.addHandler(logging.NullHandler())
        return

    level = logging.DEBUG if cfg.log_debug else logging.INFO
    logger.disabled = False
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(
        _DEBUG_FORMAT if cfg.log_debug else _BASE_FORMAT,
        _DATE_FORMAT,
    )
    handlers: list[logging.Handler] = []

    if cfg.log_to_file:
        log_path = _resolve_path(cfg.log_file_name)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8", delay=True)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        queue: Queue[logging.LogRecord] = Queue(-1)
        queue_handler = QueueHandler(queue)
        queue_handler.setLevel(level)
        handlers.append(queue_handler)
        listener = QueueListener(queue, file_handler, respect_handler_level=True)
        listener.start()
        _listener_handlers = [file_handler]
        _listener = listener
        if not _atexit_registered:
            atexit.register(_stop_listener)
            _atexit_registered = True
    else:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(level)
        stream_handler.setFormatter(formatter)
        handlers.append(stream_handler)

    for handler in handlers:
        logger.addHandler(handler)


class _HotReloadingLoggerAdapter(logging.LoggerAdapter):
    def isEnabledFor(self, level: int) -> bool:  # noqa: N802
        configure_logging()
        return self.logger.isEnabledFor(level)

    def log(
        self,
        level: int,
        msg: object,
        *args: object,
        exc_info: bool
        | tuple[type[BaseException], BaseException, TracebackType | None]
        | tuple[None, None, None]
        | BaseException
        | None = None,
        stack_info: bool = False,
        stacklevel: int = 1,
        extra: Mapping[str, object] | None = None,
        **kwargs: object,
    ) -> None:
        configure_logging()
        super().log(
            level,
            msg,
            *args,
            exc_info=exc_info,
            stack_info=stack_info,
            stacklevel=stacklevel,
            extra=extra,
            **kwargs,
        )


def get_logger(name: str | None = None) -> logging.LoggerAdapter[logging.Logger]:
    """Devuelve un logger configurado para el paquete."""
    configure_logging()
    return _HotReloadingLoggerAdapter(logging.getLogger(name or "reputation"), {})
