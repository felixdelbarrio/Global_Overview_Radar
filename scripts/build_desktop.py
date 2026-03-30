from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PyInstaller import __main__ as pyinstaller
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

from app_icon import (
    ASSETS_DIR,
    generated_macos_icon_path,
    generated_windows_icon_path,
)

APP_NAME = "GlobalOverviewRadar"
ARCHIVE_PREFIX = "global-overview-radar"
APPLE_BUNDLE_IDENTIFIER = "com.felixdelbarrio.globaloverviewradar"
ROOT_DIR = Path(__file__).resolve().parent.parent
FRONT_DIR = ROOT_DIR / "frontend" / "brr-frontend"
BUILD_ROOT = ROOT_DIR / "build" / "desktop"
DIST_ROOT = ROOT_DIR / "dist"


@dataclass(frozen=True)
class AppleDistributionConfig:
    mode: str
    sign_identity: str | None
    notary_profile: str | None


def parse_args() -> argparse.Namespace:
    apple_distribution_default = (
        os.environ.get("APPLE_DISTRIBUTION", "auto").strip().lower()
    )
    if apple_distribution_default not in {"auto", "required", "off"}:
        apple_distribution_default = "auto"

    parser = argparse.ArgumentParser(
        description="Build desktop artifacts for Global Overview Radar."
    )
    parser.add_argument("--skip-smoke-test", action="store_true")
    parser.add_argument(
        "--apple-distribution",
        choices=("auto", "required", "off"),
        default=apple_distribution_default,
        help=(
            "Controla la distribución Apple en macOS. "
            "auto: intenta firmar/notarizar si hay credenciales, "
            "required: exige credenciales y falla si falta algo, "
            "off: omite firma/notarización."
        ),
    )
    return parser.parse_args()


def platform_slug() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    if os.name == "nt":
        return "windows"
    raise RuntimeError(f"Sistema operativo no soportado para build: {sys.platform}")


def architecture_slug() -> str:
    machine = platform.machine().lower()
    aliases = {
        "amd64": "x64",
        "x86_64": "x64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    return aliases.get(machine, machine or "unknown")


def add_data_arg(source: Path, destination: str) -> str:
    separator = ";" if os.name == "nt" else ":"
    return f"{source}{separator}{destination}"


def run(
    command: list[str], cwd: Path | None = None, env: dict[str, str] | None = None
) -> None:
    print(f"==> {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def command_output(command: list[str]) -> str:
    return subprocess.check_output(command, text=True).strip()


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def copy_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    shutil.copytree(source, destination, dirs_exist_ok=True)


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def installed_node_version() -> str:
    version = command_output(["node", "-p", "process.version"])
    if not version.startswith("v"):
        raise RuntimeError(f"Versión de Node inesperada: {version}")
    return version


def node_distribution() -> tuple[str, str, str]:
    version = installed_node_version()
    arch = architecture_slug()
    if os.name == "nt":
        if arch not in {"x64", "arm64"}:
            raise RuntimeError(f"Arquitectura Windows no soportada para Node: {arch}")
        filename = f"node-{version}-win-{arch}.zip"
        binary_relpath = f"node-{version}-win-{arch}/node.exe"
    elif sys.platform == "darwin":
        if arch not in {"x64", "arm64"}:
            raise RuntimeError(f"Arquitectura macOS no soportada para Node: {arch}")
        filename = f"node-{version}-darwin-{arch}.tar.gz"
        binary_relpath = f"node-{version}-darwin-{arch}/bin/node"
    elif sys.platform.startswith("linux"):
        if arch not in {"x64", "arm64"}:
            raise RuntimeError(f"Arquitectura Linux no soportada para Node: {arch}")
        filename = f"node-{version}-linux-{arch}.tar.xz"
        binary_relpath = f"node-{version}-linux-{arch}/bin/node"
    else:
        raise RuntimeError(f"Sistema operativo no soportado para Node: {sys.platform}")

    url = f"https://nodejs.org/dist/{version}/{filename}"
    return url, filename, binary_relpath


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"==> Descargando {url}", flush=True)
    request = urllib.request.Request(
        url, headers={"User-Agent": "GlobalOverviewRadar build"}
    )
    with urllib.request.urlopen(request) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def extract_archive(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(destination)
        return
    with tarfile.open(archive_path, "r:*") as archive:
        archive.extractall(destination)


def stage_frontend(stage_root: Path) -> Path:
    frontend_stage = stage_root / "app" / "frontend"
    frontend_stage.parent.mkdir(parents=True, exist_ok=True)

    standalone_dir = FRONT_DIR / ".next" / "standalone"
    static_dir = FRONT_DIR / ".next" / "static"
    public_dir = FRONT_DIR / "public"

    if not (standalone_dir / "server.js").exists():
        raise RuntimeError(
            "No existe frontend/brr-frontend/.next/standalone/server.js. Revisa la build del frontend."
        )

    copy_tree(standalone_dir, frontend_stage)
    if static_dir.exists():
        copy_tree(static_dir, frontend_stage / ".next" / "static")
    if public_dir.exists():
        copy_tree(public_dir, frontend_stage / "public")
    return frontend_stage


def stage_seed(stage_root: Path) -> Path:
    seed_root = stage_root / "app" / "seed"
    copy_tree(ROOT_DIR / "data" / "reputation", seed_root / "data" / "reputation")
    copy_tree(
        ROOT_DIR / "data" / "reputation_llm", seed_root / "data" / "reputation_llm"
    )
    copy_tree(
        ROOT_DIR / "data" / "reputation_samples",
        seed_root / "data" / "reputation_samples",
    )
    copy_tree(
        ROOT_DIR / "data" / "reputation_llm_samples",
        seed_root / "data" / "reputation_llm_samples",
    )
    copy_tree(ROOT_DIR / "data" / "cache", seed_root / "data" / "cache")

    backend_env_dir = ROOT_DIR / "backend" / "reputation"
    for filename in (
        ".env.reputation",
        ".env.reputation.example",
        ".env.reputation.advanced",
        ".env.reputation.advanced.example",
    ):
        source = backend_env_dir / filename
        if source.exists():
            copy_file(source, seed_root / "backend" / "reputation" / filename)
    return seed_root


def stage_assets(stage_root: Path) -> Path:
    assets_stage = stage_root / "app" / "assets"
    copy_tree(ROOT_DIR / "assets", assets_stage)
    return assets_stage


def stage_node_runtime(stage_root: Path) -> Path:
    if not shutil.which("node"):
        raise RuntimeError("No se encontró 'node' en PATH.")
    url, filename, binary_relpath = node_distribution()
    downloads_root = BUILD_ROOT / "downloads"
    archive_path = downloads_root / filename
    extract_root = downloads_root / "unpacked"
    if not archive_path.exists():
        download_file(url, archive_path)
    shutil.rmtree(extract_root, ignore_errors=True)
    extract_archive(archive_path, extract_root)
    resolved_node = extract_root / binary_relpath
    if not resolved_node.exists():
        raise RuntimeError(
            f"No se encontró el binario de Node extraído en {resolved_node}"
        )
    runtime_root = stage_root / "app" / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    node_name = "node.exe" if os.name == "nt" else "node"
    destination = runtime_root / node_name
    copy_file(resolved_node, destination)
    destination.chmod(destination.stat().st_mode | 0o111)
    return destination


def artifact_executable_path() -> Path:
    if sys.platform == "darwin":
        return DIST_ROOT / f"{APP_NAME}.app" / "Contents" / "MacOS" / APP_NAME
    binary_name = f"{APP_NAME}.exe" if os.name == "nt" else APP_NAME
    return DIST_ROOT / APP_NAME / binary_name


def archive_target_path() -> Path:
    if sys.platform == "darwin":
        return DIST_ROOT / f"{APP_NAME}.app"
    return DIST_ROOT / APP_NAME


def build_archive_name() -> str:
    return f"{ARCHIVE_PREFIX}-{platform_slug()}-{architecture_slug()}"


def create_archive(target_path: Path) -> Path:
    archive_base = DIST_ROOT / build_archive_name()
    archive_path = shutil.make_archive(
        str(archive_base),
        "zip",
        root_dir=target_path.parent,
        base_dir=target_path.name,
    )
    return Path(archive_path)


def run_smoke_test(executable: Path) -> None:
    print(f"==> Smoke test: {executable}", flush=True)
    subprocess.run([str(executable), "--smoke-test", "--timeout", "180"], check=True)


def pyinstaller_icon_path() -> Path | None:
    if sys.platform == "darwin":
        icon_path = generated_macos_icon_path(ASSETS_DIR)
        return icon_path if icon_path.exists() else None
    if os.name == "nt":
        icon_path = generated_windows_icon_path(ASSETS_DIR)
        return icon_path if icon_path.exists() else None
    return None


def env_value(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value if value else None


def apple_distribution_config(mode: str) -> AppleDistributionConfig:
    return AppleDistributionConfig(
        mode=mode,
        sign_identity=env_value("APPLE_SIGN_IDENTITY"),
        notary_profile=env_value("APPLE_NOTARY_PROFILE"),
    )


def create_notary_submission_archive(app_bundle: Path) -> Path:
    archive_base = BUILD_ROOT / "apple-notary-submission"
    archive_path = Path(f"{archive_base}.zip")
    if archive_path.exists():
        archive_path.unlink()
    generated = shutil.make_archive(
        str(archive_base),
        "zip",
        root_dir=app_bundle.parent,
        base_dir=app_bundle.name,
    )
    return Path(generated)


def _run_optional_apple_step(
    command: list[str], description: str, *, required: bool
) -> bool:
    try:
        run(command)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        if required:
            raise RuntimeError(
                f"Fallo en paso Apple '{description}': {error}"
            ) from error
        print(
            f"==> WARN: Se omite '{description}' por error no bloqueante: {error}",
            flush=True,
        )
        return False


def maybe_apply_apple_distribution(app_bundle: Path, mode: str) -> None:
    if sys.platform != "darwin":
        return

    config = apple_distribution_config(mode)
    if config.mode == "off":
        print(
            "==> Distribución Apple desactivada (APPLE_DISTRIBUTION=off).",
            flush=True,
        )
        return

    required = config.mode == "required"
    if not config.sign_identity:
        message = "APPLE_SIGN_IDENTITY no informado; se genera build macOS sin firma."
        if required:
            raise RuntimeError(message)
        print(f"==> {message}", flush=True)
        return

    if not command_exists("codesign"):
        message = "No se encontró 'codesign' en PATH."
        if required:
            raise RuntimeError(message)
        print(f"==> WARN: {message} Se omite firma Apple.", flush=True)
        return

    if not _run_optional_apple_step(
        [
            "codesign",
            "--force",
            "--deep",
            "--options",
            "runtime",
            "--timestamp",
            "--sign",
            config.sign_identity,
            str(app_bundle),
        ],
        "codesign",
        required=required,
    ):
        return

    _run_optional_apple_step(
        ["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app_bundle)],
        "codesign-verify",
        required=required,
    )
    print("==> Firma macOS completada.", flush=True)

    if not config.notary_profile:
        message = (
            "APPLE_NOTARY_PROFILE no informado; se omite notarización y stapling."
        )
        if required:
            raise RuntimeError(message)
        print(f"==> {message}", flush=True)
        return

    if not command_exists("xcrun"):
        message = "No se encontró 'xcrun' en PATH para notarización."
        if required:
            raise RuntimeError(message)
        print(f"==> WARN: {message}", flush=True)
        return

    submission_archive = create_notary_submission_archive(app_bundle)
    if not _run_optional_apple_step(
        [
            "xcrun",
            "notarytool",
            "submit",
            str(submission_archive),
            "--keychain-profile",
            config.notary_profile,
            "--wait",
        ],
        "notarytool-submit",
        required=required,
    ):
        return

    if not _run_optional_apple_step(
        ["xcrun", "stapler", "staple", str(app_bundle)],
        "stapler-staple",
        required=required,
    ):
        return

    _run_optional_apple_step(
        ["xcrun", "stapler", "validate", str(app_bundle)],
        "stapler-validate",
        required=required,
    )
    print("==> Notarización macOS completada.", flush=True)


def main() -> int:
    args = parse_args()
    if not (FRONT_DIR / "node_modules").exists():
        raise RuntimeError(
            "No existe frontend/brr-frontend/node_modules. Ejecuta 'make install'."
        )

    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    DIST_ROOT.mkdir(parents=True, exist_ok=True)
    stage_root = BUILD_ROOT / "staging"
    pyinstaller_work = BUILD_ROOT / "pyinstaller"
    pyinstaller_spec = BUILD_ROOT / "spec"

    shutil.rmtree(stage_root, ignore_errors=True)
    shutil.rmtree(pyinstaller_work, ignore_errors=True)
    shutil.rmtree(pyinstaller_spec, ignore_errors=True)
    shutil.rmtree(DIST_ROOT / APP_NAME, ignore_errors=True)
    shutil.rmtree(DIST_ROOT / f"{APP_NAME}.app", ignore_errors=True)

    run([sys.executable, str(ROOT_DIR / "scripts" / "generate_app_icons.py")])

    build_env = os.environ.copy()
    build_env["NEXT_TELEMETRY_DISABLED"] = "1"
    run(["npm", "run", "build"], cwd=FRONT_DIR, env=build_env)

    frontend_stage = stage_frontend(stage_root)
    seed_stage = stage_seed(stage_root)
    assets_stage = stage_assets(stage_root)
    node_stage = stage_node_runtime(stage_root)

    pyinstaller_args = [
        str(ROOT_DIR / "scripts" / "desktop_app.py"),
        "--name",
        APP_NAME,
        "--onedir",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(DIST_ROOT),
        "--workpath",
        str(pyinstaller_work),
        "--specpath",
        str(pyinstaller_spec),
        "--paths",
        str(ROOT_DIR / "backend"),
        "--add-data",
        add_data_arg(frontend_stage, "app/frontend"),
        "--add-data",
        add_data_arg(seed_stage, "app/seed"),
        "--add-data",
        add_data_arg(assets_stage, "app/assets"),
        "--add-data",
        add_data_arg(node_stage, "app/runtime"),
    ]
    pyinstaller_args.append("--windowed")
    icon_path = pyinstaller_icon_path()
    if icon_path is not None:
        pyinstaller_args.extend(["--icon", str(icon_path)])
    if sys.platform == "darwin":
        pyinstaller_args.extend(["--osx-bundle-identifier", APPLE_BUNDLE_IDENTIFIER])

    for hidden_import in sorted(set(collect_submodules("webview"))):
        pyinstaller_args.extend(["--hidden-import", hidden_import])

    for source, destination in collect_data_files("webview"):
        pyinstaller_args.extend(["--add-data", add_data_arg(Path(source), destination)])

    pyinstaller.run(pyinstaller_args)

    executable = artifact_executable_path()
    if not executable.exists():
        raise RuntimeError(f"No se encontró el ejecutable generado en {executable}")

    if not args.skip_smoke_test:
        run_smoke_test(executable)

    maybe_apply_apple_distribution(archive_target_path(), args.apple_distribution)

    archive_path = create_archive(archive_target_path())
    print(f"==> Build OK: {archive_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
