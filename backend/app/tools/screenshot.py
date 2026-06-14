"""screenshot tool — capture screen / window / region to a PNG file.

Wraps the macOS `screencapture` CLI (built into the OS, no install
needed). Three ops:

  - `full` — captures the main display. Default path is
    `~/Desktop/screenshot_<timestamp>.png` if not specified.
  - `window` — captures a specific window by name (the user passes
    the window title or app name).
  - `region` — captures a sub-rectangle of the main display. The
    user passes x, y, width, height in points.

Notes:
  - `-x` flag silences the camera-shutter sound (important when
    capturing repeatedly during automation).
  - `-o` flag hides the drop-shadow that macOS otherwise adds
    around windows (we want clean output).
  - File extension is forced to .png regardless of user input —
    `screencapture` only writes PNG.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

from app.tools._stubs import BaseTool

logger = logging.getLogger(__name__)

DEFAULT_DIR = Path.home() / "Desktop"


def _default_path() -> Path:
    ts = time.strftime("%Y%m%d-%H%M%S")
    return DEFAULT_DIR / f"screenshot_{ts}.png"


class ScreenshotTool(BaseTool):
    name = "screenshot"
    description = (
        "Capture the macOS screen to a PNG file. Operations: 'full' "
        "captures the main display; 'window' captures a specific window "
        "by name (the user passes the window title or owning app name); "
        "'region' captures a sub-rectangle (user passes x, y, width, "
        "height in points). The output path defaults to "
        "~/Desktop/screenshot_<timestamp>.png; the user can override "
        "with `output_path`. The camera-shutter sound is silenced and "
        "the window drop-shadow is hidden for clean output. Use sparingly "
        "— captures are silent but macOS may pop a 'screenshot taken' "
        "notification the first few times."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["full", "window", "region"],
                "description": "Which capture mode to use.",
            },
            "output_path": {
                "type": "string",
                "description": (
                    "Optional absolute or ~-prefixed output path. Must "
                    "end in .png. Defaults to ~/Desktop/screenshot_"
                    "<timestamp>.png. Parent directory is created if "
                    "needed."
                ),
            },
            "window_name": {
                "type": "string",
                "description": "Window title or owning app name (operation='window').",
            },
            "x": {"type": "integer", "description": "Top-left X (operation='region')."},
            "y": {"type": "integer", "description": "Top-left Y (operation='region')."},
            "width": {"type": "integer", "description": "Width in points (operation='region')."},
            "height": {"type": "integer", "description": "Height in points (operation='region')."},
        },
        "required": ["operation"],
    }

    async def run(
        self,
        operation: str,
        output_path: Optional[str] = None,
        window_name: Optional[str] = None,
        x: int = -1,
        y: int = -1,
        width: int = -1,
        height: int = -1,
        **kwargs: Any,
    ) -> str:
        # Resolve the output path
        if output_path:
            p = Path(os.path.expanduser(output_path))
        else:
            p = _default_path()
        if p.suffix.lower() != ".png":
            return f"Error: output path must end in .png, got {p}"
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return f"Error: cannot create parent dir for {p}: {e}"

        # Build the screencapture args
        args = ["-x", "-o", p]  # -x: no sound, -o: no shadow
        if operation == "full":
            # `-l` selects display number; default is main, which is
            # what we want.
            pass
        elif operation == "window":
            if not window_name:
                return "Error: 'window_name' is required for operation='window'"
            args = ["-x", "-o", "-l", window_name, p]
        elif operation == "region":
            if any(v < 0 for v in (x, y, width, height)):
                return (
                    "Error: 'x', 'y', 'width', 'height' are all required "
                    "and must be non-negative for operation='region'"
                )
            args = ["-x", "-o", "-R", f"{x},{y},{width},{height}", p]
        else:
            return f"Error: unknown operation {operation!r}"

        try:
            result = subprocess.run(
                ["screencapture", *args],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return f"Error: screencapture timed out for {p}"
        except FileNotFoundError:
            return (
                "Error: `screencapture` not found — this tool only runs on macOS"
            )
        except Exception as e:
            logger.error(f"screenshot error: {e}")
            return f"Error: {e}"

        if result.returncode != 0:
            return (
                f"Error: screencapture failed (exit {result.returncode}): "
                f"{result.stderr.strip()}"
            )
        if not p.exists() or p.stat().st_size == 0:
            return f"Error: screencapture produced no file at {p}"
        return f"OK: saved {p} ({p.stat().st_size} bytes)"


__all__ = ["ScreenshotTool"]
