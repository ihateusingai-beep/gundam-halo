"""Tools — file_read, file_write, shell_exec, open_app, etc.

Each tool:
- implements `to_spec()` → OpenAI-compatible function spec
- implements `run(**kwargs) → str` → execution, returns observation text
- is registered in `ToolRegistry` (defined in `core/registry.py`)
  via the `@register_tool("name")` class decorator on each
  tool class. This module eagerly imports every tool module so
  the decorators fire at import time and `ToolRegistry.items()`
  returns the full set of 22 tools (Sprint 32 P0-1 refactor).
"""
from __future__ import annotations

# Eager import: trigger @register_tool decorators on each tool class.
# `builder.py::default_tools` then iterates `ToolRegistry.items()`
# instead of hardcoding 22 imports + 22 instance creations.
from app.tools import (
    a11y,                 # noqa: F401  (registers A11yTool)
    apple_script,         # noqa: F401
    bluetooth,            # noqa: F401
    brightness,           # noqa: F401
    clipboard,            # noqa: F401
    file_read,            # noqa: F401
    file_write,           # noqa: F401
    flight_finder,        # noqa: F401
    mavis_delegate,       # noqa: F401
    memory,               # noqa: F401  (registers MemoryReadTool + MemoryWriteTool)
    notify,               # noqa: F401
    open_app,             # noqa: F401
    screenshot,           # noqa: F401
    send_message,         # noqa: F401
    shell_exec,           # noqa: F401
    spotlight,            # noqa: F401
    system_settings,      # noqa: F401
    weather,              # noqa: F401
    web_fetch,            # noqa: F401
    web_search,           # noqa: F401
    youtube_summarize,    # noqa: F401
)

