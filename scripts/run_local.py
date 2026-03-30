from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from threading import Lock
from typing import Iterable
from urllib.error import URLError
from urllib.request import urlopen

from app_icon import (
    ASSETS_DIR,
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

ROOT_DIR = Path(__file__).resolve().parent.parent
VENV_PY = ROOT_DIR / ".venv" / "bin" / "python"
FRONT_DIR = ROOT_DIR / "frontend" / "brr-frontend"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run backend + frontend locally and open the UI inside a desktop container window."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--front-port", type=int, default=3000)
    parser.add_argument("--title", default="Global Overview Radar")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--timeout", type=int, default=120)
    return parser.parse_args()


def ensure_local_dependencies() -> None:
    if not VENV_PY.exists():
        raise RuntimeError(
            "No existe .venv. Ejecuta 'make install' antes de usar 'make run'."
        )
    if not (FRONT_DIR / "node_modules").exists():
        raise RuntimeError(
            "No existe frontend/brr-frontend/node_modules. Ejecuta 'make install' antes de usar 'make run'."
        )


def launch_process(
    name: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
) -> subprocess.Popen:
    print(f"==> Arrancando {name}: {' '.join(command)}", flush=True)
    return subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        start_new_session=True,
    )


def wait_for_http(
    name: str,
    url: str,
    processes: list[tuple[str, subprocess.Popen]],
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


def stop_process(process: subprocess.Popen, name: str) -> None:
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


def stop_processes(processes: Iterable[tuple[str, subprocess.Popen]]) -> None:
    for name, process in processes:
        stop_process(process, name)


def main() -> int:
    args = parse_args()
    ensure_local_dependencies()

    backend_url = f"http://{args.host}:{args.api_port}"
    frontend_url = f"http://{args.host}:{args.front_port}"
    processes: list[tuple[str, subprocess.Popen]] = []
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
            origin="local",
            role="wrapper",
            command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
            match_tokens=["run_local.py"],
        )
    )

    try:
        backend_env = os.environ.copy()
        backend_env["PYTHONUNBUFFERED"] = "1"
        backend_command = [
            str(VENV_PY),
            "-m",
            "uvicorn",
            "reputation.api.main:app",
            "--reload",
            "--host",
            args.host,
            "--port",
            str(args.api_port),
        ]
        backend = launch_process(
            name="backend",
            command=backend_command,
            cwd=ROOT_DIR,
            env=backend_env,
        )
        processes.append(("backend", backend))
        registered_processes.append(
            register_child_process(
                origin="local",
                role="backend",
                process=backend,
                command=backend_command,
                match_tokens=["uvicorn", "reputation.api.main:app"],
            )
        )

        frontend_env = os.environ.copy()
        frontend_env["API_PROXY_TARGET"] = backend_url
        frontend_env["NEXT_TELEMETRY_DISABLED"] = "1"
        frontend_command = [
            "npm",
            "run",
            "dev",
            "--",
            "--hostname",
            args.host,
            "--port",
            str(args.front_port),
        ]
        frontend = launch_process(
            name="frontend",
            command=frontend_command,
            cwd=FRONT_DIR,
            env=frontend_env,
        )
        processes.append(("frontend", frontend))
        registered_processes.append(
            register_child_process(
                origin="local",
                role="frontend",
                process=frontend,
                command=frontend_command,
                match_tokens=["npm", "dev"],
            )
        )

        wait_for_http("backend", f"{backend_url}/openapi.json", processes, args.timeout)
        wait_for_http("frontend", frontend_url, processes, args.timeout)

        try:
            import webview
        except ImportError as exc:
            raise RuntimeError(
                "No se pudo importar 'pywebview'. Ejecuta 'make install' para instalar la ventana contenedora."
            ) from exc

        icon_path = runtime_icon_path(ASSETS_DIR)
        apply_macos_app_icon(icon_path)

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
            raise RuntimeError("No se pudo crear la ventana contenedora local.")
        window.events.closing += cleanup
        window.events.closed += cleanup
        webview_icon = linux_webview_icon(ASSETS_DIR)
        if webview_icon:
            webview.start(debug=False, icon=webview_icon)
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
