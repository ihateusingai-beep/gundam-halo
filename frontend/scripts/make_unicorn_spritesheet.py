"""Generate a horizontal sprite sheet from the 88 Unicorn Gundam animation
frames. Single PNG, 88 columns × 1 row, 256x256 per frame = 22528x256 px.

Output: frontend/public/gundam-assets/avatars/unicorn-spritesheet.png
"""
from pathlib import Path
from PIL import Image

SRC_DIR = Path("/Users/kencheng/workspace/working/gundam-halo/frontend/src-tauri/icons/anim")
OUT = Path("/Users/kencheng/workspace/working/gundam-halo/frontend/public/gundam-assets/avatars/unicorn-spritesheet.png")
OUT.parent.mkdir(parents=True, exist_ok=True)

frames = sorted(SRC_DIR.glob("frame_*.png"))
print(f"Found {len(frames)} frames")
assert len(frames) == 88, f"expected 88, got {len(frames)}"

# Each frame is 256x256 → final sheet is 22528x256
fw, fh = 256, 256
sheet_w = fw * len(frames)
sheet = Image.new("RGBA", (sheet_w, fh), (0, 0, 0, 0))

for i, p in enumerate(frames):
    img = Image.open(p).convert("RGBA")
    if img.size != (fw, fh):
        img = img.resize((fw, fh), Image.LANCZOS)
    sheet.paste(img, (i * fw, 0), img)

sheet.save(OUT, optimize=True)
print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB, {sheet_w}x{fh})")
