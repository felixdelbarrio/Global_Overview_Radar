from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

APP_RUNTIME_ID = "GlobalOverviewRadar"
PROCESS_REGISTRY_NAME = "processes"
KILL_TIMEOUT_SECONDS = 10.0


def process_registry_dir() -> Path:
    override = os.environ.get("GOR_PROCESS_REGISTRY_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    if sys.platform == "darwin":
        base_dir = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if appdata:
            base_dir = Path(appdata).expanduser().resolve()
        else:
            base_dir = Path.home() / "AppData" / "Local"
    else:
        xdg_state_home = os.environ.get("XDG_STATE_HOME", "").strip()
        if xdg_state_home:
            base_dir = Path(xdg_state_home).expanduser().resolve()
        else:
            base_dir = Path.home() / ".local" / "state"

    return base_dir / APP_RUNTIME_ID / PROCESS_REGISTRY_NAME


def _slug(value: str) -> str:
    return (
        "".join(character if character.isalnum() else "-" for character in value).strip(
            "-"
        )
        or "unknown"
    )


def _record_path(origin: str, role: str, pid: int) -> Path:
    filename = f"{_slug(origin)}-{_slug(role)}-{pid}.json"
    return process_registry_dir() / filename


def _command_list(command: Iterable[str] | None) -> list[str]:
    if command is None:
        return []
    return [str(part) for part in command if str(part)]


def register_process(
    *,
    origin: str,
    role: str,
    pid: int,
    scope: str,
    command: Iterable[str] | None = None,
    pgid: int | None = None,
    match_tokens: Iterable[str] | None = None,
) -> Path:
    registry_dir = process_registry_dir()
    registry_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "origin": origin,
        "role": role,
        "pid": pid,
        "pgid": pgid,
        "scope": scope,
        "command": _command_list(command),
        "match_tokens": [str(token) for token in match_tokens or []],
    }
    record_path = _record_path(origin, role, pid)
    record_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return record_path


def register_current_process(
    *,
    origin: str,
    role: str,
    command: Iterable[str] | None = None,
    match_tokens: Iterable[str] | None = None,
) -> Path:
    return register_process(
        origin=origin,
        role=role,
        pid=os.getpid(),
        scope="pid",
        command=command or sys.argv,
        match_tokens=match_tokens,
    )


def register_child_process(
    *,
    origin: str,
    role: str,
    process: subprocess.Popen[Any],
    command: Iterable[str] | None = None,
    match_tokens: Iterable[str] | None = None,
) -> Path:
    scope = "pid"
    pgid: int | None = None
    if os.name != "nt":
        scope = "process_group"
        try:
            pgid = os.getpgid(process.pid)
        except ProcessLookupError:
            pgid = None

    return register_process(
        origin=origin,
        role=role,
        pid=process.pid,
        pgid=pgid,
        scope=scope,
        command=command,
        match_tokens=match_tokens,
    )


def clear_registered_processes(record_paths: Iterable[Path]) -> None:
    for record_path in record_paths:
        try:
            record_path.unlink(missing_ok=True)
        except OSError:
            continue


def install_cleanup_signal_handlers(cleanup: Callable[[], None]) -> None:
    def handle_signal(signum: int, _frame: Any) -> None:
        signal_name = signal.Signals(signum).name
        print(f"==> Señal {signal_name}: cerrando procesos activos...", flush=True)
        cleanup()
        raise SystemExit(128 + signum)

    for signal_name in ("SIGINT", "SIGTERM", "SIGHUP", "SIGQUIT"):
        signum = getattr(signal, signal_name, None)
        if signum is None:
            continue
        signal.signal(signum, handle_signal)


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _process_group_exists(pgid: int) -> bool:
    if os.name == "nt":
        return False
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _target_is_alive(record: dict[str, Any]) -> bool:
    pid = int(record.get("pid", 0))
    if pid <= 0:
        return False
    if (
        record.get("scope") == "process_group"
        and record.get("pgid") is not None
        and os.name != "nt"
    ):
        return _process_group_exists(int(record["pgid"]))
    return _pid_exists(pid)


def _wait_until_gone(record: dict[str, Any], timeout_seconds: float) -> bool:
    import time

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _target_is_alive(record):
            return True
        time.sleep(0.2)
    return not _target_is_alive(record)


def _terminate_record(record: dict[str, Any], *, force: bool) -> None:
    pid = int(record.get("pid", 0))
    if pid <= 0:
        return

    if os.name == "nt":
        command = ["taskkill", "/PID", str(pid), "/T"]
        if force:
            command.append("/F")
        subprocess.run(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
        )
        return

    sig = signal.SIGKILL if force else signal.SIGTERM
    if record.get("scope") == "process_group" and record.get("pgid") is not None:
        try:
            os.killpg(int(record["pgid"]), sig)
        except ProcessLookupError:
            return
        return

    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return


def _load_record(record_path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        try:
            record_path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def record_description(record: dict[str, Any]) -> str:
    role = str(record.get("role", "unknown"))
    origin = str(record.get("origin", "unknown"))
    pid = int(record.get("pid", 0))
    scope = str(record.get("scope", "pid"))
    if scope == "process_group" and record.get("pgid") is not None:
        return f"{origin}:{role} (pid={pid}, pgid={record['pgid']})"
    return f"{origin}:{role} (pid={pid})"


def _kill_priority(record: dict[str, Any]) -> tuple[int, int]:
    role_order = {"wrapper": 0, "frontend": 1, "backend": 2}
    return (role_order.get(str(record.get("role", "")), 99), int(record.get("pid", 0)))


def kill_registered_processes() -> list[tuple[str, dict[str, Any]]]:
    results: list[tuple[str, dict[str, Any]]] = []
    registry_dir = process_registry_dir()
    if not registry_dir.exists():
        return results

    records: list[tuple[Path, dict[str, Any]]] = []
    for record_path in sorted(registry_dir.glob("*.json")):
        record = _load_record(record_path)
        if record is None:
            continue
        records.append((record_path, record))

    for record_path, record in sorted(
        records, key=lambda item: _kill_priority(item[1])
    ):
        if not _target_is_alive(record):
            clear_registered_processes([record_path])
            results.append(("stale", record))
            continue

        _terminate_record(record, force=False)
        if not _wait_until_gone(record, KILL_TIMEOUT_SECONDS):
            _terminate_record(record, force=True)
            _wait_until_gone(record, 2.0)

        clear_registered_processes([record_path])
        results.append(("killed", record))

    return results
