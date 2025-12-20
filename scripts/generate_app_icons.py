"""
Utility to generate app icons from the SVG telescope asset.

Outputs:
  - PNGs at multiple sizes
  - ICO for Windows
  - iconset folder for macOS (use iconutil to make .icns)

Usage:
  uv run python scripts/generate_app_icons.py

Prereqs:
  pip install cairosvg pillow

After running:
  macOS: iconutil -c icns dist/icons/app.iconset -o dist/icons/app.icns
  Windows (PyInstaller): use dist/icons/app.ico via --icon
  Linux: install dist/icons/png/app-256.png (and others) to hicolor theme, and set Icon=celestron-nexstar in .desktop
"""

from __future__ import annotations

import itertools
from pathlib import Path

import cairosvg  # type: ignore[import-untyped]
from PIL import Image  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "src" / "celestron_nexstar" / "gui" / "assets" / "icons" / "app.svg"
OUT_ROOT = ROOT / "dist" / "icons"
PNG_DIR = OUT_ROOT / "png"
ICONSET_DIR = OUT_ROOT / "app.iconset"

# Common sizes
PNG_SIZES = [16, 24, 32, 48, 64, 128, 256, 512, 1024]


def ensure_dirs() -> None:
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    ICONSET_DIR.mkdir(parents=True, exist_ok=True)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)


def render_png(size: int, out_path: Path) -> None:
    cairosvg.svg2png(url=str(SVG), write_to=str(out_path), output_width=size, output_height=size, background_color=None)


def generate_pngs() -> None:
    for size in PNG_SIZES:
        render_png(size, PNG_DIR / f"app-{size}.png")


def generate_ico() -> None:
    # ICO expects multiple sizes in one file
    images = []
    for size in [16, 24, 32, 48, 64, 128, 256]:
        png_path = PNG_DIR / f"app-{size}.png"
        if not png_path.exists():
            render_png(size, png_path)
        images.append(Image.open(png_path).convert("RGBA"))
    ico_path = OUT_ROOT / "app.ico"
    images[0].save(ico_path, format="ICO", sizes=[img.size for img in images])


def generate_iconset() -> None:
    # Create macOS iconset folder; user can run iconutil to build .icns
    # Map of required sizes to iconset filenames
    sizes = {
        16: "icon_16x16.png",
        32: "icon_16x16@2x.png",
        32: "icon_32x32.png",
        64: "icon_32x32@2x.png",
        128: "icon_128x128.png",
        256: "icon_128x128@2x.png",
        256: "icon_256x256.png",
        512: "icon_256x256@2x.png",
        512: "icon_512x512.png",
        1024: "icon_512x512@2x.png",
    }
    # above map overrides keys; generate with explicit list instead
    entries = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for size, filename in entries:
        target = ICONSET_DIR / filename
        render_png(size, target)


def main() -> None:
    if not SVG.exists():
        raise SystemExit(f"SVG not found at {SVG}")
    ensure_dirs()
    generate_pngs()
    generate_ico()
    generate_iconset()
    print("Icons generated under dist/icons/")
    print("For macOS, run: iconutil -c icns dist/icons/app.iconset -o dist/icons/app.icns")


if __name__ == "__main__":
    main()

