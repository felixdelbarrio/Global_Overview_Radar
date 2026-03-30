from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from threading import Lock
from typing import Iterable, Literal
from urllib.error import URLError
from urllib.request import urlopen

from app_icon import (
    WINDOW_BACKGROUND_COLOR,
    WINDOW_MIN_SIZE,
    apply_macos_app_icon,
    linux_webview_icon,
    runtime_icon_path,
)
from process_registry import (
    clear_registered_processes,
    install_cleanup_signal_handlers,
    register_child_process,
    register_current_process,
)

APP_NAME = "Global Overview Radar"
ROOT_DIR = Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root(bundle_root: str | None = None) -> Path:
    if bundle_root:
        return Path(bundle_root).expanduser().resolve()
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return ROOT_DIR


def app_data_root() -> Path:
    override = os.environ.get("GOR_APP_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "GlobalOverviewRadar"
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "GlobalOverviewRadar"
        return Path.home() / "AppData" / "Roaming" / "GlobalOverviewRadar"
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / "GlobalOverviewRadar"
    return Path.home() / ".local" / "share" / "GlobalOverviewRadar"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the packaged desktop version of Global Overview Radar."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--front-port", type=int, default=3000)
    parser.add_argument("--title", default=APP_NAME)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--backend-only", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--bundle-root", default="")
    return parser.parse_args()


def copy_missing_file(source: Path, destination: Path) -> None:
    if not source.exists() or destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_missing_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        target = destination / entry.name
        if entry.is_dir():
            copy_missing_tree(entry, target)
        else:
            copy_missing_file(entry, target)


def seed_runtime_workspace(seed_root: Path, runtime_root: Path) -> None:
    runtime_root.mkdir(parents=True, exist_ok=True)
    copy_missing_tree(
        seed_root / "backend" / "reputation", runtime_root / "backend" / "reputation"
    )
    copy_missing_tree(
        seed_root / "data" / "reputation", runtime_root / "data" / "reputation"
    )
    copy_missing_tree(
        seed_root / "data" / "reputation_llm", runtime_root / "data" / "reputation_llm"
    )
    copy_missing_tree(
        seed_root / "data" / "reputation_samples",
        runtime_root / "data" / "reputation_samples",
    )
    copy_missing_tree(
        seed_root / "data" / "reputation_llm_samples",
        runtime_root / "data" / "reputation_llm_samples",
    )
    copy_missing_tree(seed_root / "data" / "cache", runtime_root / "data" / "cache")
    (runtime_root / "logs").mkdir(parents=True, exist_ok=True)


def prefer_port(host: str, preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, preferred))
        except OSError:
            sock.bind((host, 0))
        return int(sock.getsockname()[1])


def wait_for_http(
    name: str,
    url: str,
    processes: list[tuple[str, subprocess.Popen[bytes]]],
    timeout_seconds: int,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        for process_name, process in processes:
            return_code = process.poll()
            if return_code is not None:
                raise RuntimeError(
                    f"El proceso '{process_name}' terminó antes de estar listo (exit code {return_code})."
                )

        try:
            with urlopen(url, timeout=2) as response:
                status = getattr(response, "status", 200)
                if 200 <= status < 500:
                    print(f"==> {name} listo en {url}", flush=True)
                    return
        except URLError as exc:
            last_error = exc
        except OSError as exc:
            last_error = exc

        time.sleep(1)

    raise RuntimeError(f"Timeout esperando a {name} en {url}: {last_error}")


def launch_process(
    name: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
) -> subprocess.Popen[bytes]:
    print(f"==> Arrancando {name}: {' '.join(command)}", flush=True)
    if os.name == "nt":
        return subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    return subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        start_new_session=True,
    )


def stop_process(process: subprocess.Popen[bytes], name: str) -> None:
    if process.poll() is not None:
        return

    print(f"==> Cerrando {name}...", flush=True)
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def stop_processes(processes: Iterable[tuple[str, subprocess.Popen[bytes]]]) -> None:
    for name, process in processes:
        stop_process(process, name)


def backend_command(args: argparse.Namespace) -> list[str]:
    if is_frozen():
        return [
            sys.executable,
            "--backend-only",
            "--host",
            args.host,
            "--api-port",
            str(args.api_port),
        ]
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "--backend-only",
        "--host",
        args.host,
        "--api-port",
        str(args.api_port),
    ]


def run_backend_only(args: argparse.Namespace) -> int:
    import uvicorn

    from reputation.api.main import app

    uvicorn.run(app, host=args.host, port=args.api_port, reload=False)
    return 0


def webview_gui() -> Literal["qt"] | None:
    if sys.platform.startswith("linux"):
        return "qt"
    return None


def main() -> int:
    args = parse_args()
    if args.backend_only:
        return run_backend_only(args)

    resources = resource_root(args.bundle_root or None)
    app_resources = resources / "app"
    assets_dir = app_resources / "assets"
    frontend_dir = app_resources / "frontend"
    node_name = "node.exe" if os.name == "nt" else "node"
    node_path = app_resources / "runtime" / node_name
    seed_root = app_resources / "seed"

    if not frontend_dir.exists():
        raise RuntimeError(f"No se encontró el frontend empaquetado en {frontend_dir}")
    if not node_path.exists():
        raise RuntimeError(
            f"No se encontró el runtime de Node empaquetado en {node_path}"
        )

    runtime_root = app_data_root()
    seed_runtime_workspace(seed_root, runtime_root)
    icon_path = runtime_icon_path(assets_dir)
    apply_macos_app_icon(icon_path)

    args.api_port = prefer_port(args.host, args.api_port)
    args.front_port = prefer_port(args.host, args.front_port)
    backend_url = f"http://{args.host}:{args.api_port}"
    frontend_url = f"http://{args.host}:{args.front_port}"

    processes: list[tuple[str, subprocess.Popen[bytes]]] = []
    registered_processes: list[Path] = []
    cleanup_lock = Lock()
    cleaned_up = False

    def cleanup() -> None:
        nonlocal cleaned_up
        with cleanup_lock:
            if cleaned_up:
                return
            cleaned_up = True
        stop_processes(reversed(processes))
        clear_registered_processes(registered_processes)

    install_cleanup_signal_handlers(cleanup)
    registered_processes.append(
        register_current_process(
            origin="packaged",
            role="wrapper",
            command=[sys.executable, *sys.argv[1:]],
            match_tokens=[Path(sys.executable).name],
        )
    )

    try:
        backend_env = os.environ.copy()
        backend_env["PYTHONUNBUFFERED"] = "1"
        backend_env["REPUTATION_WORKSPACE_ROOT"] = str(runtime_root)
        backend_env["REPUTATION_RUNTIME_ENV_DIR"] = str(
            runtime_root / "backend" / "reputation"
        )
        backend_env["REPUTATION_CONFIG_PATH"] = str(
            runtime_root / "data" / "reputation"
        )
        backend_env["REPUTATION_LLM_CONFIG_PATH"] = str(
            runtime_root / "data" / "reputation_llm"
        )
        backend_env["REPUTATION_CACHE_PATH"] = str(
            runtime_root / "data" / "cache" / "reputation_cache.json"
        )
        backend_env["REPUTATION_OVERRIDES_PATH"] = str(
            runtime_root / "data" / "cache" / "reputation_overrides.json"
        )
        backend_cmd = backend_command(args)
        backend = launch_process(
            name="backend",
            command=backend_cmd,
            cwd=runtime_root,
            env=backend_env,
        )
        processes.append(("backend", backend))
        registered_processes.append(
            register_child_process(
                origin="packaged",
                role="backend",
                process=backend,
                command=backend_cmd,
                match_tokens=["--backend-only"],
            )
        )

        frontend_env = os.environ.copy()
        frontend_env["API_PROXY_TARGET"] = backend_url
        frontend_env["NEXT_TELEMETRY_DISABLED"] = "1"
        frontend_env["NODE_ENV"] = "production"
        frontend_env["HOSTNAME"] = args.host
        frontend_env["PORT"] = str(args.front_port)
        frontend_env["GOR_RUNTIME_ROOT"] = str(runtime_root)
        frontend_cmd = [str(node_path), str(frontend_dir / "server.js")]
        frontend = launch_process(
            name="frontend",
            command=frontend_cmd,
            cwd=frontend_dir,
            env=frontend_env,
        )
        processes.append(("frontend", frontend))
        registered_processes.append(
            register_child_process(
                origin="packaged",
                role="frontend",
                process=frontend,
                command=frontend_cmd,
                match_tokens=["server.js"],
            )
        )

        wait_for_http("backend", f"{backend_url}/openapi.json", processes, args.timeout)
        wait_for_http("frontend", frontend_url, processes, args.timeout)

        if args.smoke_test:
            print("==> Smoke test OK.", flush=True)
            return 0

        import webview

        gui = webview_gui()
        window = webview.create_window(
            args.title,
            frontend_url,
            width=args.width,
            height=args.height,
            min_size=WINDOW_MIN_SIZE,
            resizable=True,
            background_color=WINDOW_BACKGROUND_COLOR,
        )
        if window is None:
            raise RuntimeError("No se pudo crear la ventana contenedora.")
        window.events.closing += cleanup
        window.events.closed += cleanup
        if gui:
            webview.start(
                gui=gui,
                debug=False,
                icon=linux_webview_icon(assets_dir),
            )
        else:
            webview.start(debug=False)
        return 0
    except KeyboardInterrupt:
        print("==> Cierre solicitado.", flush=True)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
