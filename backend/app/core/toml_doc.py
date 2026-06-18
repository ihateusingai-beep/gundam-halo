"""Single source of truth for `~/.gundam-halo/config.toml` reads + writes.

**Why this module exists (Sprint 32 P0-2 refactor)**:

Two callers used to maintain their own TOML read/write infrastructure:

- `api/setup.py` used `tomlkit` (lines 195-232) — `_load_toml_doc`,
  `_write_toml_doc`, `_tmp_file_in`. The 8 `_update_*` helpers (lines
  235-300) were ad-hoc per-section mutators that share the same
  "init section if missing" boilerplate.
- `api/voice_ws.py` used **regex** (lines 1221-1282) — `_replace_section_key`.
  Plus 3 more inline regex calls in `put_voice_config`
  (lines 1095-1129) for `wake_phrases`, `strict_wake_phrase`,
  `always_on_mic`. The regex path **did not** handle multiline
  values or escaped strings, while the tomlkit path did.

This module extracts the shared infrastructure and provides a
single API. The `update_section_key` helper auto-creates the
target section (and any intermediate `a.b.c` path) if missing,
replacing the regex path's "append at end of file" fallback.
`tomlkit` preserves comments and structure on round-trip.

**Usage**:

```python
from app.core.toml_doc import read_doc, write_doc, update_section_key

# Read a config (returns empty doc if file is missing)
doc = read_doc(Path("~/.gundam-halo/config.toml"))

# Update a single key (auto-creates the section + any parent tables)
update_section_key(doc, "voice.asr", "backend", "whisper_hf")
update_section_key(doc, "voice.asr", "wake_phrases", ["unicorn", "ntd"])

# Persist atomically (tmp + fsync + os.replace)
write_doc(Path("~/.gundam-halo/config.toml"), doc)
```

**Behaviour preserved vs. the previous regex path**:

- `update_section_key(text, "voice.asr", "backend", '"whisper_hf"')`
  with no `[voice.asr]` section auto-creates one (was: append
  `\\n[voice.asr]\\nbackend = "whisper_hf"\\n` to end of file).
- Comments and quoting style are preserved (tomlkit round-trip).
- Atomic write prevents half-written files on crash.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import tomlkit


def read_doc(path: Path) -> tomlkit.TOMLDocument:
    """Load a TOML document. Returns an empty doc if `path` doesn't exist.

    The empty-doc fallback is the new behaviour that replaces
    `setup.py::_load_toml_doc`'s `(doc, existed)` tuple — callers
    that previously branched on `existed` should now check
    `path.exists()` directly.

    Args:
        path: Absolute or relative path to the TOML file.

    Returns:
        A `tomlkit.TOMLDocument` (empty if file missing).

    Raises:
        OSError: If the file exists but cannot be read.
        tomlkit.TOMLKitError: If the file is not valid TOML.
    """
    if not path.exists():
        return tomlkit.document()
    with open(path, encoding="utf-8") as f:
        return tomlkit.load(f)


def write_doc(path: Path, doc: tomlkit.TOMLDocument) -> None:
    """Atomically write a TOML document to `path`.

    Strategy: write to a temp file in the same directory, fsync,
    then `os.replace` over the target. This is crash-safe —
    a partial write leaves the previous file intact.

    Replaces `setup.py::_write_toml_doc` + `_tmp_file_in` — the
    same atomic write logic, but factored into a reusable helper.

    Args:
        path: Absolute or relative path to the target file.
        doc: The TOML document to persist.

    Raises:
        OSError: If the parent directory cannot be created or the
            temp file cannot be written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=".config.toml.", dir=str(path.parent), text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(tomlkit.dumps(doc))
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # fsync can fail on some filesystems (e.g. /dev/null,
                # FUSE mounts). The atomic-rename still gives us
                # crash safety without an fsync, so swallow the error.
                pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def update_section_key(
    doc: tomlkit.TOMLDocument,
    section: str,
    key: str,
    value: Any,
) -> None:
    """Set `doc[section][key] = value`, auto-creating the section.

    Supports dotted section names like `"voice.asr"` — creates
    nested tables as needed. The previous regex path could only
    edit existing sections; if `[voice.asr]` was missing, the
    fallback appended a new section at the end of the file. This
    helper is **idempotent** and **well-formed**: it creates the
    section in-place at the right nesting level, preserving the
    file's existing structure.

    Args:
        doc: The TOML document to mutate (in place).
        section: Top-level section name OR dotted path
            (e.g. `"voice.asr"`).
        key: The key to set within the (sub-)section.
        value: The value to assign. Lists / dicts are stored as
            TOML arrays / tables respectively (via tomlkit's
            container inference).

    Example:
        >>> doc = tomlkit.document()
        >>> update_section_key(doc, "voice.asr", "backend", "whisper_hf")
        >>> update_section_key(doc, "voice.asr", "wake_phrases",
        ...                     ["unicorn", "ntd"])
        >>> tomlkit.dumps(doc)
        '[voice.asr]\\nbackend = "whisper_hf"\\nwake_phrases = ["unicorn", "ntd"]\\n'
    """
    # Dotted path → walk + create intermediate tables.
    parts = section.split(".")
    table = doc
    for part in parts:
        # `tomlkit.items.Table` is the type for both inline and
        # standard tables. We re-create the sub-table if the
        # existing entry is something else (e.g. a string we
        # wrote by mistake) so the nested path is well-formed.
        from tomlkit.items import Table
        if part not in table or not isinstance(table[part], Table):
            table[part] = tomlkit.table()
        table = table[part]
    table[key] = value


__all__ = [
    "read_doc",
    "update_section_key",
    "write_doc",
]
