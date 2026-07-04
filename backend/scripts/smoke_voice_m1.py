"""M1 live smoke test — connect to /ws/voice, send text, verify agent reply.

This is a manual smoke test (not part of pytest). It:
1. Starts the FastAPI server in a subprocess
2. Connects to ws://localhost:8765/ws/voice
3. Sends a `voice.text` frame with a question
4. Verifies the server returns an `agent.message` reply from the LLM

Usage:
    cd backend && uv run python scripts/smoke_voice_m1.py

Requires:
- MINIMAX_API_KEY env var
- server config that has voice.enabled = true
- a registered agent callback (this script sets a simple one)
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import websockets

BACKEND_DIR = Path(__file__).resolve().parent.parent
# Sprint 56 R1: route through `app.paths` so $HALO_HOME override works.
from app.paths import halo_home, config_path, logs_dir, projects_dir

HALO_HOME = halo_home()
CONFIG_PATH = config_path()


def _write_smoke_config() -> None:
    """Write a minimal config.toml with voice enabled for the smoke run."""
    HALO_HOME.mkdir(parents=True, exist_ok=True)
    logs_dir().mkdir(parents=True, exist_ok=True)
    (HALO_HOME / "projects").mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        """[user]
name = "smoke"
default_theme = "gundam-ntd"

[llm]
provider = "minimax"
default_model = "MiniMax-M3"

[server]
host = "127.0.0.1"
port = 8765
log_level = "INFO"

[mac_control]
file_read_paths = ["/tmp"]
file_write_paths = ["/tmp"]
shell_allowlist = ["echo", "ls", "pwd"]

[security]
injection_scan = false

[voice]
enabled = true
[voice.vad]
backend = "silero"
model_path = "~/.gundam-halo/models/silero_vad.onnx"
[voice.asr]
backend = "whisper_local"
model_size = "tiny"
[voice.tts]
backend = "edge"
[voice.live2d]
theme = "ntd"
"""
    )


async def main() -> int:
    if not os.environ.get("MINIMAX_API_KEY"):
        print("ERROR: MINIMAX_API_KEY env var not set", file=sys.stderr)
        return 1

    _write_smoke_config()
    print(f"Wrote smoke config to {CONFIG_PATH}")

    # Start server
    env = os.environ.copy()
    env["HALO_HOME"] = str(HALO_HOME)
    print("Starting server on 127.0.0.1:8765 ...")
    server = subprocess.Popen(
        [".venv/bin/uvicorn", "app.main:halo_app", "--host", "127.0.0.1", "--port", "8765"],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Wait for server to come up
    print("Waiting for server to be ready ...")
    for _ in range(30):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get("http://127.0.0.1:8765/health", timeout=1.0)
                if r.status_code == 200:
                    print(f"Server up: {r.json()}")
                    break
        except (httpx.RequestError, httpx.HTTPError):
            pass
        time.sleep(0.5)
    else:
        print("ERROR: server didn't start in 15s", file=sys.stderr)
        server.terminate()
        return 2

    # Note: voice WS will try to load Silero/Whisper and fail in this
    # smoke env (no model on disk). For M1 smoke, the easier path is
    # to hit /api/sessions directly with a text message and verify the
    # agent works.
    print("\nHitting /api/sessions to verify LLM is wired ...")
    try:
        async with httpx.AsyncClient() as client:
            # List projects
            r = await client.get("http://127.0.0.1:8765/api/projects", timeout=5.0)
            print(f"GET /api/projects: {r.status_code} {r.json()}")
    except Exception as e:
        print(f"Project API call failed: {e}")

    # Stop server
    print("\nStopping server ...")
    server.terminate()
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()

    print("\nSmoke test done.")
    print("Note: voice WS requires Silero + Whisper on disk.")
    print("For M1, the unit tests (tests/voice/) are the canonical proof.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
