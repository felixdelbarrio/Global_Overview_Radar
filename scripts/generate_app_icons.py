from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageFilter

from app_icon import (
    APP_ICON_SLUG,
    ASSETS_DIR,
    source_icon_path,
)

SOURCE_SIZE = 1024
INNER_CROP_RATIO = 0.9
PNG_SIZES = (16, 20, 24, 32, 40, 48, 64, 72, 96, 128, 256, 512, 1024)
LINUX_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
WINDOWS_ICO_SIZES = [
    (16, 16),
    (24, 24),
    (32, 32),
    (48, 48),
    (64, 64),
    (128, 128),
    (256, 256),
]
MAC_ICONSET_SIZES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate desktop icon derivatives.")
    parser.add_argument("--assets-dir", default=str(ASSETS_DIR))
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def open_master(source_path: Path) -> Image.Image:
    image = Image.open(source_path).convert("RGBA")
    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    squared = image.crop((left, top, left + side, top + side))
    crop_side = int(side * INNER_CROP_RATIO)
    crop_side -= crop_side % 2
    offset = (side - crop_side) // 2
    cropped = squared.crop((offset, offset, offset + crop_side, offset + crop_side))
    return cropped.resize((SOURCE_SIZE, SOURCE_SIZE), Image.Resampling.LANCZOS)


def render_png(master: Image.Image, size: int) -> Image.Image:
    rendered = master.resize((size, size), Image.Resampling.LANCZOS)
    if size <= 128:
        rendered = rendered.filter(
            ImageFilter.UnsharpMask(radius=1.1, percent=110, threshold=3)
        )
    return rendered


def write_pngs(master: Image.Image, assets_dir: Path) -> None:
    png_dir = assets_dir / "generated" / "png"
    png_dir.mkdir(parents=True, exist_ok=True)
    for size in PNG_SIZES:
        rendered = render_png(master, size)
        rendered.save(png_dir / f"{APP_ICON_SLUG}-{size}.png")


def write_linux_icons(assets_dir: Path) -> None:
    png_dir = assets_dir / "generated" / "png"
    linux_root = assets_dir / "generated" / "linux" / "hicolor"
    for size in LINUX_SIZES:
        target_dir = linux_root / f"{size}x{size}" / "apps"
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            png_dir / f"{APP_ICON_SLUG}-{size}.png",
            target_dir / f"{APP_ICON_SLUG}.png",
        )


def write_windows_icon(master: Image.Image, assets_dir: Path) -> None:
    windows_dir = assets_dir / "generated" / "windows"
    windows_dir.mkdir(parents=True, exist_ok=True)
    master.save(
        windows_dir / f"{APP_ICON_SLUG}.ico",
        format="ICO",
        sizes=WINDOWS_ICO_SIZES,
    )


def write_macos_iconset(assets_dir: Path) -> Path:
    png_dir = assets_dir / "generated" / "png"
    iconset_dir = assets_dir / "generated" / "macos" / "AppIcon.iconset"
    shutil.rmtree(iconset_dir, ignore_errors=True)
    iconset_dir.mkdir(parents=True, exist_ok=True)
    for filename, size in MAC_ICONSET_SIZES.items():
        shutil.copy2(png_dir / f"{APP_ICON_SLUG}-{size}.png", iconset_dir / filename)
    return iconset_dir


def write_macos_icns(assets_dir: Path) -> None:
    iconset_dir = write_macos_iconset(assets_dir)
    if sys.platform != "darwin":
        return
    if not shutil.which("iconutil"):
        raise RuntimeError("iconutil no está disponible para generar el icono macOS.")

    macos_dir = assets_dir / "generated" / "macos"
    icns_path = macos_dir / f"{APP_ICON_SLUG}.icns"
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
        check=True,
    )


def main() -> int:
    args = parse_args()
    assets_dir = Path(args.assets_dir).expanduser().resolve()
    source_path = source_icon_path(assets_dir)
    if not source_path.exists():
        raise RuntimeError(f"No se encontró el icono fuente en {source_path}")

    generated_dir = assets_dir / "generated"
    if args.clean:
        shutil.rmtree(generated_dir, ignore_errors=True)

    master = open_master(source_path)
    generated_dir.mkdir(parents=True, exist_ok=True)
    master.save(generated_dir / f"{APP_ICON_SLUG}-master.png")
    write_pngs(master, assets_dir)
    write_linux_icons(assets_dir)
    write_windows_icon(master, assets_dir)
    write_macos_icns(assets_dir)
    print(f"==> Iconos generados en {generated_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
