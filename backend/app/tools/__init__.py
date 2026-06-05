"""Tools — file_read, file_write, shell_exec, open_app, etc.

Each tool:
- implements `to_spec()` → OpenAI-compatible function spec
- implements `run(**kwargs) → str` → execution, returns observation text
- is registered in `ToolRegistry` (defined in `core/registry.py`)
"""
