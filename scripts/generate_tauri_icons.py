#!/usr/bin/env python3
"""Generate the Gundam Halo icon set: static bundle + animated frame strip.

Inputs (any one of):
  --video PATH    mp4 video to extract frames from
  --image PATH    single PNG used as both the static icon and the loop base

Outputs:
  icons/icon.png         (1024x1024 master)
  icons/32x32.png
  icons/128x128.png
  icons/128x128@2x.png   (256x256)
  icons/icon.ico         (multi-resolution)
  icons/icon.icns        (macOS, via iconutil)
  icons/anim/frame_001.png ...   (256x256, 15 FPS, seamless loop)

Frame strip is embedded in the Rust binary via include_dir!().
"""
from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "frontend" / "src-tauri" / "icons"
ANIM_DIR = ICONS / "anim"

DEFAULT_VIDEO = Path(
    "/Users/kencheng/Open-LLM-VTuber/matrix-media-1780846959855-bb39d035.mp4"
)
DEFAULT_IMAGE = Path(
    "/Users/kencheng/Open-LLM-VTuber/matrix-media-1780846806383-914bbc60.png"
)

TARGET_FPS = 15
FRAME_SIZE = 256


def extract_frames(video: Path, out_dir: Path) -> list[Path]:
    """Extract 15fps frames at FRAME_SIZE from a video, sorted."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # clean old
    for old in out_dir.glob("frame_*.png"):
        old.unlink()
    pattern = out_dir / "frame_%03d.png"
    cmd = [
        "ffmpeg", "-y", "-i", str(video),
        "-vf", f"fps={TARGET_FPS},scale={FRAME_SIZE}:{FRAME_SIZE}:flags=lanczos",
        "-q:v", "2",
        str(pattern),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"ffmpeg failed: {result.returncode}")
    frames = sorted(out_dir.glob("frame_*.png"))
    print(f"extracted {len(frames)} frames -> {out_dir}")
    return frames


def pick_static_image() -> Path:
    """Use the first frame as the static icon (start of the loop = calm state)."""
    first = ANIM_DIR / "frame_001.png"
    if not first.exists():
        raise SystemExit("no frames extracted; can't pick static")
    return first


def build_static_icons(static: Path) -> None:
    """Build all static bundle icons from a single source PNG."""
    img = Image.open(static).convert("RGBA")
    if img.size != (1024, 1024):
        img = img.resize((1024, 1024), Image.LANCZOS)
    ICONS.mkdir(parents=True, exist_ok=True)
    img.save(ICONS / "icon.png", "PNG", optimize=True)
    print(f"master -> {ICONS / 'icon.png'}")

    for name, size in [
        ("32x32.png", 32),
        ("128x128.png", 128),
        ("128x128@2x.png", 256),
    ]:
        img.resize((size, size), Image.LANCZOS).save(ICONS / name, "PNG", optimize=True)
        print(f"  {name} ({size}x{size})")

    # ICO
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ICONS / "icon.ico", format="ICO", sizes=ico_sizes)
    print(f"  icon.ico ({ico_sizes})")

    # ICNS via iconutil
    iconset = ICONS / "icon.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir()
    for name, size in [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]:
        img.resize((size, size), Image.LANCZOS).save(iconset / name, "PNG", optimize=True)
    icns = ICONS / "icon.icns"
    if icns.exists():
        icns.unlink()
    r = subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(icns)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        raise SystemExit("iconutil failed")
    print(f"  icon.icns ({icns.stat().st_size} bytes)")
    shutil.rmtree(iconset)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--video",
        type=Path,
        default=DEFAULT_VIDEO,
        help="Source video for animated tray (optional; skip with --no-animation).",
    )
    ap.add_argument(
        "--image",
        type=Path,
        default=DEFAULT_IMAGE,
        help="Source image for the static bundle icons (used directly when "
        "--no-animation, otherwise reused as the calm frame base).",
    )
    ap.add_argument(
        "--no-animation",
        action="store_true",
        help="Skip frame extraction. Use --image directly as the static "
        "icon source. The existing icons/anim/ folder is left untouched, "
        "so the Rust binary's embedded animation keeps working.",
    )
    args = ap.parse_args()

    if args.no_animation or not args.video.exists():
        # Static-only path: skip animation entirely.
        if not args.image.exists():
            print(f"image not found: {args.image}", file=sys.stderr)
            return 1
        static_src = args.image
        print(f"[static-only] source: {static_src}")
    else:
        # 1. Extract frames
        extract_frames(args.video, ANIM_DIR)

        # 2. Pick the calm frame (first frame) as the static icon
        static_src = pick_static_image()
        print(f"static source: {static_src}")

    # 3. Build static bundle icons
    build_static_icons(static_src)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
