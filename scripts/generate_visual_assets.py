#!/usr/bin/env python3
"""Generate Gundam Halo visual showpiece assets.

Takes the master peak-state Gundam head image (1024²) and produces
multiple derivative sizes for README, social cards, and profile PFPs.
The wide compositions (README banner 1280×320, social preview 1280×640)
must be generated separately via `matrix_generate_image` since the
square source doesn't crop well to wide aspect ratios — the script
just resizes whatever you provide for those slots.

Re-run this script whenever you regenerate the peak-state master or
the matrix-generated wide compositions.

Outputs (all paths relative to repo root):
  docs/assets/og-card-1280x640.png      — Open Graph / GitHub social preview
  docs/assets/readme-banner-1280x320.png — README top banner
  docs/assets/profile-pfp-800x800.png   — High-res square PFP
  docs/assets/profile-pfp-400x400.png   — Medium square PFP
  .github/social-preview.png            — Same as og-card (GitHub convention)
"""
from __future__ import annotations
import argparse
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "assets"
GITHUB = ROOT / ".github"

# Default sources. Override via CLI flags.
DEFAULT_PFP_SOURCE = (
    ROOT / "frontend" / "src-tauri" / "icons" / "icon.png"
)
DEFAULT_OG_SOURCE = Path(
    "/Users/kencheng/Open-LLM-VTuber/matrix-media-1780853936217-a9268d20.png"
)
DEFAULT_BANNER_SOURCE = Path(
    "/Users/kencheng/Open-LLM-VTuber/matrix-media-1780853888111-a2f295bd.png"
)


def resize_to(img: Image.Image, w: int, h: int) -> Image.Image:
    """LANCZOS resize to exact w×h. Preserves aspect via crop-then-fit if needed.

    For square→square, straight resize. For wide→wide, also straight
    resize (the source is already the right aspect ratio). For any
    mismatch, we crop-center to fit.
    """
    src_w, src_h = img.size
    src_ratio = src_w / src_h
    dst_ratio = w / h

    if abs(src_ratio - dst_ratio) < 0.02:
        # Close enough — straight resize
        return img.resize((w, h), Image.LANCZOS)

    # Different aspect: crop-center then resize
    if src_ratio > dst_ratio:
        # Source is wider than target — crop sides
        new_w = int(src_h * dst_ratio)
        left = (src_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, src_h))
    else:
        # Source is taller than target — crop top/bottom
        new_h = int(src_w / dst_ratio)
        top = (src_h - new_h) // 2
        img = img.crop((0, top, src_w, top + new_h))
    return img.resize((w, h), Image.LANCZOS)


def process_square(src: Path, out_800: Path, out_400: Path) -> None:
    """Square PFP at 800² and 400²."""
    img = Image.open(src).convert("RGBA")
    print(f"  PFP source: {src.name} {img.size} → {out_800.name} (800) + {out_400.name} (400)")
    img.resize((800, 800), Image.LANCZOS).save(out_800, "PNG", optimize=True)
    img.resize((400, 400), Image.LANCZOS).save(out_400, "PNG", optimize=True)


def process_wide(src: Path, out: Path, w: int, h: int) -> None:
    """Wide banner / social card at the exact size."""
    img = Image.open(src).convert("RGBA")
    print(f"  Wide source: {src.name} {img.size} → {out.name} ({w}×{h})")
    img = resize_to(img, w, h)
    img.save(out, "PNG", optimize=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--pfp-source",
        type=Path,
        default=DEFAULT_PFP_SOURCE,
        help="Square source (default: tray animation frame_001.png)",
    )
    ap.add_argument(
        "--og-source",
        type=Path,
        default=DEFAULT_OG_SOURCE,
        help="1280×640 social preview source (matrix-generated)",
    )
    ap.add_argument(
        "--banner-source",
        type=Path,
        default=DEFAULT_BANNER_SOURCE,
        help="1280×320 README banner source (matrix-generated)",
    )
    args = ap.parse_args()

    ASSETS.mkdir(parents=True, exist_ok=True)
    GITHUB.mkdir(parents=True, exist_ok=True)

    # 1. Open Graph / GitHub social preview (1280×640)
    if args.og_source.exists():
        og_out = ASSETS / "og-card-1280x640.png"
        process_wide(args.og_source, og_out, 1280, 640)
        # GitHub convention: also write to .github/social-preview.png
        shutil.copyfile(og_out, GITHUB / "social-preview.png")
        print(f"  Copied to {GITHUB / 'social-preview.png'}")
    else:
        print(f"WARNING: og source missing: {args.og_source}", file=sys.stderr)

    # 2. README banner (1280×320)
    if args.banner_source.exists():
        banner_out = ASSETS / "readme-banner-1280x320.png"
        process_wide(args.banner_source, banner_out, 1280, 320)
    else:
        print(
            f"WARNING: banner source missing: {args.banner_source}",
            file=sys.stderr,
        )

    # 3. PFP (800² + 400²)
    if args.pfp_source.exists():
        process_square(
            args.pfp_source,
            ASSETS / "profile-pfp-800x800.png",
            ASSETS / "profile-pfp-400x400.png",
        )
    else:
        print(
            f"WARNING: PFP source missing: {args.pfp_source}",
            file=sys.stderr,
        )

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
