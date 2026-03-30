from __future__ import annotations

import sys
from pathlib import Path

APP_ICON_SOURCE_NAME = "global-overview-radar.png"
APP_ICON_SLUG = "global-overview-radar"
WINDOW_BACKGROUND_COLOR = "#2D1056"
WINDOW_MIN_SIZE = (1080, 720)

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
GENERATED_ASSETS_DIR = ASSETS_DIR / "generated"


def source_icon_path(assets_dir: Path = ASSETS_DIR) -> Path:
    return assets_dir / APP_ICON_SOURCE_NAME


def generated_png_dir(assets_dir: Path = ASSETS_DIR) -> Path:
    return assets_dir / "generated" / "png"


def generated_macos_icon_path(assets_dir: Path = ASSETS_DIR) -> Path:
    return assets_dir / "generated" / "macos" / f"{APP_ICON_SLUG}.icns"


def generated_windows_icon_path(assets_dir: Path = ASSETS_DIR) -> Path:
    return assets_dir / "generated" / "windows" / f"{APP_ICON_SLUG}.ico"


def runtime_icon_path(assets_dir: Path = ASSETS_DIR) -> Path:
    candidate = generated_png_dir(assets_dir) / f"{APP_ICON_SLUG}-512.png"
    if candidate.exists():
        return candidate
    return source_icon_path(assets_dir)


def linux_webview_icon(assets_dir: Path = ASSETS_DIR) -> str | None:
    if not sys.platform.startswith("linux"):
        return None
    icon_path = runtime_icon_path(assets_dir)
    if not icon_path.exists():
        return None
    return str(icon_path)


def apply_macos_app_icon(icon_path: Path) -> None:
    if sys.platform != "darwin" or not icon_path.exists():
        return

    try:
        from AppKit import NSApplication, NSImage
    except Exception:
        return

    app = NSApplication.sharedApplication()
    image = NSImage.alloc().initWithContentsOfFile_(str(icon_path))
    if image is not None:
        app.setApplicationIconImage_(image)
