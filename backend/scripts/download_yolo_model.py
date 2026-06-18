#!/usr/bin/env python3
"""Download the bundled YOLO model for SendMessageTool
(Sprint 30 Track A).

Per `docs/FEATURE-SPEC-SPRINT30.md` §4.1.

The YOLO model is a fine-tuned YOLOv8n ONNX model
trained on messaging app screenshots (WhatsApp,
Telegram, Signal, Discord). It is bundled with
Gundam Halo at
`~/.gundam-halo/models/yolov8n-messaging.onnx`
(~50MB). The download is one-time — the model is
cached after first use.

**4 YOLO classes** (per spec §4.1):
  - 0: contact_search_bar
  - 1: contact_result
  - 2: message_bar
  - 3: send_button

**Usage**:
    python scripts/download_yolo_model.py

**What it does**:
  1. Creates the target directory
     (`~/.gundam-halo/models/`).
  2. Downloads the model from Gundam Halo's
     model hub (~50MB).
  3. Verifies the file size + ONNX header
     (`onnx` magic bytes).
  4. Prints a clear success message + the
     YOLO classes.

**Re-running**: the script is idempotent. If the
model is already present, it prompts the user
to confirm re-download (overwrite).

**Why a separate script (not in-line auto-download)**:
the SendMessageTool's in-line auto-download flow
has no hard-coded URL (to avoid breaking when the
URL changes). The user runs this script manually
to get the real URL + the actual download.

**NOTE — URL TBD**: the actual model hub URL is
TBD. This script ships with a placeholder URL
that points at Gundam Halo's GitHub releases
page. The user can override the URL via the
`GUNDAM_HALO_YOLO_MODEL_URL` environment variable
or by editing the `DEFAULT_MODEL_URL` constant
below.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Default model URL. Override with
# GUNDAM_HALO_YOLO_MODEL_URL env var.
# NOTE: this URL is a placeholder. The actual
# model hub URL is TBD — see the script docstring
# for details. The user must either:
#   1. Set GUNDAM_HALO_YOLO_MODEL_URL=https://...
#      before running the script.
#   2. Edit DEFAULT_MODEL_URL below.
#   3. Manually download the model from
#      https://github.com/<gundam-halo>/releases
#      and place it at the target path.
DEFAULT_MODEL_URL = os.environ.get(
    "GUNDAM_HALO_YOLO_MODEL_URL",
    "https://github.com/ihateusingai-beep/gundam-halo/releases/download/v0.1.4/yolov8n-messaging.onnx",
)
DEFAULT_MODEL_PATH = Path.home() / ".gundam-halo" / "models" / "yolov8n-messaging.onnx"
EXPECTED_MODEL_SIZE_MB = 50


def _check_httpx_available() -> None:
    """Verify httpx is importable. If not, exit with
    a clear error message pointing at the install
    command.
    """
    try:
        import httpx  # type: ignore  # noqa: F401
    except ImportError as e:
        print(
            f"Error: httpx is required to download the YOLO "
            f"model. Install with: "
            f"uv add httpx. ({e})",
            file=sys.stderr,
        )
        sys.exit(1)


def _verify_onnx_file(path: Path) -> bool:
    """Verify the file at `path` is a valid ONNX file.
    Returns True if the file starts with the ONNX
    magic bytes ('onnx' as a 4-byte string in the
    first 4 bytes of the file), False otherwise.
    """
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
        return magic == b"onnx"
    except OSError:
        return False


def download_model(
    url: str = DEFAULT_MODEL_URL,
    target_path: Path = DEFAULT_MODEL_PATH,
    overwrite: bool = False,
) -> None:
    """Download the YOLO model from `url` to
    `target_path`. If `overwrite` is False and the
    file exists, prompts the user to confirm
    re-download.
    """
    import httpx

    # Check if the file already exists
    if target_path.exists() and not overwrite:
        existing_size_mb = target_path.stat().st_size / (1024 * 1024)
        print(
            f"Model already exists at {target_path} "
            f"({existing_size_mb:.1f} MB)."
        )
        if not _prompt_yes_no("Re-download and overwrite?"):
            print("Skipped. Using existing model.")
            return

    # Create the target directory
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Download with streaming (50MB files need streaming
    # to avoid loading the whole file into memory).
    print(f"Downloading YOLO model from {url}...")
    print(f"Target: {target_path}")
    try:
        with httpx.stream("GET", url, timeout=60.0, follow_redirects=True) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            with open(target_path, "wb") as f:
                downloaded = 0
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = (downloaded / total) * 100
                        print(
                            f"\r  {downloaded / (1024 * 1024):.1f} / "
                            f"{total / (1024 * 1024):.1f} MB "
                            f"({pct:.0f}%)",
                            end="",
                            flush=True,
                        )
                print()  # newline
    except httpx.HTTPError as e:
        print(
            f"\nError: download failed — {e}",
            file=sys.stderr,
        )
        # Clean up partial download
        if target_path.exists():
            target_path.unlink()
        sys.exit(1)

    # Verify the file size is reasonable
    actual_size_mb = target_path.stat().st_size / (1024 * 1024)
    if actual_size_mb < 1:
        print(
            f"Error: downloaded file is suspiciously small "
            f"({actual_size_mb:.1f} MB). The model should be "
            f"~{EXPECTED_MODEL_SIZE_MB} MB. The download may "
            f"have been truncated.",
            file=sys.stderr,
        )
        target_path.unlink()
        sys.exit(1)

    # Verify the ONNX header
    if not _verify_onnx_file(target_path):
        print(
            f"Error: downloaded file is not a valid ONNX "
            f"model (missing 'onnx' magic bytes). The URL "
            f"may be wrong or the file may be corrupted.",
            file=sys.stderr,
        )
        target_path.unlink()
        sys.exit(1)

    print(
        f"\n✓ Downloaded YOLO model to {target_path} "
        f"({actual_size_mb:.1f} MB)."
    )
    print("\nYOLO classes (4 classes, per spec §4.1):")
    print("  0: contact_search_bar")
    print("  1: contact_result")
    print("  2: message_bar")
    print("  3: send_button")
    print(
        f"\nTo enable the SendMessageTool, set "
        f"`tools.send_message.enabled = true` in "
        f"`~/.gundam-halo/config.toml` and grant macOS "
        f"Accessibility permission."
    )


def _prompt_yes_no(question: str) -> bool:
    """Prompt the user for a yes/no answer. Returns
    True for yes, False for no.
    """
    while True:
        answer = input(f"{question} [y/N] ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no", ""):
            return False
        print("Please answer 'y' or 'n'.")


def main() -> None:
    """Entry point for `python scripts/download_yolo_model.py`."""
    _check_httpx_available()
    download_model()


if __name__ == "__main__":
    main()
