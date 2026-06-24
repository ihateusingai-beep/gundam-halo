"""Channel adapters — telegram, signal.

Sprint 32 P0-1 v2: the prior version of this file was empty
(1-line docstring), which caused a latent cold-start bug —
`app/main.py`'s lifespan calls `manager.start_all()` which
iterates `ChannelRegistry.keys()`, but with no eager import
of `app.channels.telegram` here, the registry was empty in a
clean production cold start. The previous code only worked
because some other code path (test fixtures, smoke scripts)
had already imported `app.channels.telegram`.

The fix mirrors the pattern used by `app/agents/__init__.py`
and `app/voice/{asr,tts,vad}/__init__.py`: eagerly import the
channel modules so the `@ChannelRegistry.register(...)`
decorators fire at package import time. Now any module that
does `import app.channels` (directly or transitively) gets a
populated `ChannelRegistry`.
"""
from __future__ import annotations

# Eager import: trigger @ChannelRegistry.register decorators.
# `app/channels/manager.py::start_all` then iterates
# `ChannelRegistry.keys()` to start every registered channel.
from app.channels import (
    telegram,  # noqa: F401  (registers "telegram" channel)
)