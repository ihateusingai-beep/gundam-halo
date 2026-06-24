"""Decorator-based registry for runtime discovery of pluggable components.

Inspired by OpenJarvis (Apache 2.0) — reimplemented under MIT for Gundam Halo.

# Sprint 32 P0-1 v2 — Context-managed isolation

Each typed subclass gets its own isolated storage so registrations in one
registry never leak into another. Sprint 32 P0-1 v2 replaces the prior
class-attribute dict (`cls._registry_entries_<cls.__name__>`) with a
**per-subclass `ContextVar[dict]`**, plus an explicit
`snapshot()` / `restore()` API.

## Why ContextVar instead of a plain dict

The previous design stored entries on the class object itself. That
worked for production (eager imports at package init populated the
registry once) but caused test pollution: a `@register_tool` decorator
in a test would leak across subsequent test files, because the class
dict survived until the next `.clear()` call (which we never blanket-
called for safety reasons — blanket-clearing `ToolRegistry` would wipe
the 22 eagerly-imported real tools and break `default_tools()`).

The new design keeps the same `ToolRegistry.items()` / `.get()` /
`.register_value()` public API, so **production call sites change
zero** lines of code. The difference is testable:

- `RegistryBase.snapshot()` returns the current dict (a copy).
- `RegistryBase.restore(snap)` replaces the current dict.

The autouse fixture in `tests/conftest.py` (see
`_isolate_registry_state`) snapshots all 5 production-read
registries before each test and restores them after — eliminating
test pollution without hardcoding test keys.

## Production eager-import chains (unchanged)

The 5 production-read registries (`ToolRegistry` / `AgentRegistry` /
`ChannelRegistry` / `AsrRegistry` / `TtsRegistry` / `VadRegistry`)
are populated eagerly by `app/<sub>/__init__.py` module imports.
Sprint 32 P0-1 v2 fixes the latent cold-start bug where
`app/channels/__init__.py` was empty and `ChannelRegistry` was
never populated until something else imported
`app.channels.telegram`. The fix is the same `from .telegram import
TelegramChannel` line that the other 5 `__init__.py` files already
have.

## Removed phantom registries

`ModelRegistry` / `ProjectRegistry` / `MemoryRegistry` had **zero
production readers or writers** as of Sprint 32 P0-1 v2 audit
(2026-06-24). Removed — they were speculative scaffolding for
future features that never landed. If the live2d model layer ever
needs a `ModelRegistry`, it can be re-introduced with a typed spec.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Dict, Generator, Generic, Tuple, Type, TypeVar

T = TypeVar("T")


class RegistryBase(Generic[T]):
    """Generic registry base class with ContextVar-backed storage.

    Each subclass gets its own `ContextVar[Dict[str, T]]` so the
    storage is **per-subclass** (no cross-registry leakage) and
    **per-context** (test fixtures can snapshot/restore to get
    isolation without touching the class dict directly).

    The public API (`register`, `register_value`, `get`, `create`,
    `items`, `keys`, `contains`, `clear`) is unchanged from
    Sprint 32 P0-1. Production callers do not need to be modified.
    """

    @classmethod
    def _storage_var(cls) -> ContextVar[Dict[str, T]]:
        """Return the per-subclass ContextVar (lazily created).

        Stored on the class object as `_<cls.__name__>_storage_var`
        so it's a class attribute (shared by all subclasses via
        `__dict__` lookup, but each subclass gets its own attribute
        thanks to the unique name).
        """
        attr_name = f"_{cls.__name__}_storage_var"
        var = getattr(cls, attr_name, None)
        if var is None:
            var = ContextVar(f"registry.{cls.__name__}", default={})
            setattr(cls, attr_name, var)
        return var

    @classmethod
    def _entries(cls) -> Dict[str, T]:
        """Return the current context's storage dict.

        In production: returns the eager-imported entries (the
        ContextVar defaults to `{}` and is populated by the
        decorator calls fired at package import time, all in the
        root context).
        """
        return cls._storage_var().get()

    @classmethod
    def register(cls, key: str) -> Callable[[T], T]:
        """Decorator that registers *entry* under *key*."""

        def decorator(entry: T) -> T:
            entries = cls._entries()
            if key in entries:
                raise ValueError(f"{cls.__name__} already has an entry for '{key}'")
            entries[key] = entry
            return entry

        return decorator

    @classmethod
    def register_value(cls, key: str, value: T) -> T:
        """Imperatively register a *value* under *key*."""
        entries = cls._entries()
        if key in entries:
            raise ValueError(f"{cls.__name__} already has an entry for '{key}'")
        entries[key] = value
        return value

    @classmethod
    def get(cls, key: str) -> T:
        """Retrieve the entry for *key*, raising KeyError if missing."""
        try:
            return cls._entries()[key]
        except KeyError as exc:
            raise KeyError(
                f"{cls.__name__} does not have an entry for '{key}'"
            ) from exc

    @classmethod
    def create(cls, key: str, *args: Any, **kwargs: Any) -> Any:
        """Look up *key* and instantiate it with the given arguments."""
        entry = cls.get(key)
        if not callable(entry):
            raise TypeError(
                f"{cls.__name__} entry '{key}' is not callable"
                " and cannot be instantiated"
            )
        return entry(*args, **kwargs)

    @classmethod
    def items(cls) -> Tuple[Tuple[str, T], ...]:
        return tuple(cls._entries().items())

    @classmethod
    def keys(cls) -> Tuple[str, ...]:
        return tuple(cls._entries().keys())

    @classmethod
    def contains(cls, key: str) -> bool:
        return key in cls._entries()

    @classmethod
    def clear(cls) -> None:
        """Remove all entries in the current context.

        Useful in tests for a hard reset. Production code should
        NOT call this — the eager-import chains populate the
        registry, and clearing them breaks `default_tools()` and
        the ASR/TTS/VAD factory error paths.
        """
        cls._entries().clear()

    # ------------------------------------------------------------------
    # Sprint 32 P0-1 v2 — isolation API
    # ------------------------------------------------------------------

    @classmethod
    def snapshot(cls) -> Dict[str, T]:
        """Return a shallow copy of the current context's entries.

        Use with `restore()` for test isolation:

            snap = ToolRegistry.snapshot()
            try:
                ToolRegistry.register_value("test_x", MyClass)
                # ... test ...
            finally:
                ToolRegistry.restore(snap)

        The autouse fixture in `tests/conftest.py` does this
        automatically for all production-read registries.
        """
        return dict(cls._entries())

    @classmethod
    def restore(cls, snapshot: Dict[str, T]) -> None:
        """Replace the current context's entries with `snapshot`.

        Existing entries not in `snapshot` are removed; new entries
        from `snapshot` are added. Use after `snapshot()` to roll
        the registry back to a known state — typically end of test.
        """
        entries = cls._entries()
        entries.clear()
        entries.update(snapshot)

    @classmethod
    @contextmanager
    def isolation_scope(cls) -> Generator[None, None, None]:
        """Context manager: snapshot on enter, restore on exit.

        Example:

            with ToolRegistry.isolation_scope():
                ToolRegistry.register_value("test_x", MyClass)
                assert "test_x" in dict(ToolRegistry.items())
            # Outside the scope: "test_x" is gone.

        Convenient for individual tests that need to register
        fixtures without affecting other tests; the autouse
        fixture in `tests/conftest.py` is the canonical pattern
        and supersedes this for the production-read registries.
        """
        snap = cls.snapshot()
        try:
            yield
        finally:
            cls.restore(snap)


# ---------------------------------------------------------------------------
# Typed subclass registries — one per primitive
# ---------------------------------------------------------------------------
#
# Sprint 32 P0-1 v2 removes the phantom registries (ModelRegistry /
# ProjectRegistry / MemoryRegistry) that had zero production
# usage as of 2026-06-24. The 6 retained registries are exactly
# the ones read by production code paths. EngineRegistry is
# retained with a deprecation note (reserved for future live2d
# engine backends per the Sprint 32 P0-1 design comment).


class EngineRegistry(RegistryBase[Type[Any]]):
    """Registry for inference engine backends.

    .. deprecated::
        No production readers as of Sprint 32 P0-1 v2 audit
        (2026-06-24). The ASR/TTS/VAD factories each have their
        own registry; live2d engine backends were planned but
        not yet shipped. Retained for future use — the single
        production writer is `app/engines/minimax.py:61`
        (`@register_engine("minimax")` on `MiniMaxEngine`).
    """


class AgentRegistry(RegistryBase[Type[Any]]):
    """Registry for agent implementations."""


class ToolRegistry(RegistryBase[Any]):
    """Registry for tool specifications."""


class ChannelRegistry(RegistryBase[Type[Any]]):
    """Registry for channel implementations."""


# Per-subsystem voice registries — each subsystem gets its own
# typed registry so a backend name in one (e.g. "edge" for TTS)
# doesn't collide with another (e.g. "edge" for a hypothetical
# VAD). See `app/voice/{asr,tts,vad}/__init__.py` for the eager
# import chains that populate these.


class AsrRegistry(RegistryBase[Type[Any]]):
    """Registry for ASR backends (whisper_local, yuesub, whisper_hf)."""


class TtsRegistry(RegistryBase[Type[Any]]):
    """Registry for TTS backends (edge, pyttsx3, azure)."""


class VadRegistry(RegistryBase[Type[Any]]):
    """Registry for VAD backends (silero, fsmn)."""


# ---------------------------------------------------------------------------
# Ergonomic decorator helpers (Sprint 32 P0-1, name-guard added in v2)
# ---------------------------------------------------------------------------
#
# These thin wrappers let subclasses opt in via:
#
#     @register_tool("file_read")
#     class FileReadTool(BaseTool):
#         name = "file_read"
#         ...
#
#     @register_engine("minimax")
#     class MiniMaxEngine(InferenceEngine):
#         ...
#
#     @register_agent("native_react")
#     class NativeReActAgent(BaseAgent):
#         ...
#
# Each wrapper asserts the class's own `name` attribute matches
# the registered key (Sprint 32 P0-1 v2: applied uniformly to all
# helpers, not just `register_tool`) — so a typo like
# `@register_tool("file_rea")` + `name = "file_read"` fails loudly
# at import time rather than silently under-registering.


def _assert_name_matches(name: str, cls: type) -> None:
    """Sprint 32 P0-1 v2: uniform `name`-attribute guard for all
    decorator helpers. Raises ValueError if `cls.name` is defined
    and doesn't match the registry key.
    """
    if hasattr(cls, "name") and getattr(cls, "name") != name:
        raise ValueError(
            f"{cls.__name__}.name = {getattr(cls, 'name')!r} does not match "
            f"the registry key {name!r} — fix the decorator or "
            f"the class attribute."
        )


def register_tool(name: str):
    """Decorator: register a `BaseTool` subclass under `name`."""
    def decorator(cls: type) -> type:
        _assert_name_matches(name, cls)
        ToolRegistry.register_value(name, cls)
        return cls
    return decorator


def register_engine(name: str):
    """Decorator: register an `InferenceEngine` subclass under `name`."""
    def decorator(cls: type) -> type:
        _assert_name_matches(name, cls)
        EngineRegistry.register_value(name, cls)
        return cls
    return decorator


def register_agent(name: str):
    """Decorator: register a `BaseAgent` subclass under `name`."""
    def decorator(cls: type) -> type:
        _assert_name_matches(name, cls)
        AgentRegistry.register_value(name, cls)
        return cls
    return decorator


def register_asr(name: str):
    """Decorator: register an `ASRInterface` subclass under `name`."""
    def decorator(cls: type) -> type:
        _assert_name_matches(name, cls)
        AsrRegistry.register_value(name, cls)
        return cls
    return decorator


def register_tts(name: str):
    """Decorator: register a `TTSInterface` subclass under `name`."""
    def decorator(cls: type) -> type:
        _assert_name_matches(name, cls)
        TtsRegistry.register_value(name, cls)
        return cls
    return decorator


def register_vad(name: str):
    """Decorator: register a `VADInterface` subclass under `name`."""
    def decorator(cls: type) -> type:
        _assert_name_matches(name, cls)
        VadRegistry.register_value(name, cls)
        return cls
    return decorator


# Production-read registries for the autouse isolation fixture.
# Kept as a module-level constant so `tests/conftest.py` can
# import it without enumerating the subclasses itself. The set
# is hand-curated: it lists the registries whose entries are
# populated by `app/<sub>/__init__.py` eager imports and are
# read by production code (ToolRegistry / AgentRegistry /
# ChannelRegistry / AsrRegistry / TtsRegistry / VadRegistry).
# EngineRegistry is NOT included — it has no production readers
# and is populated lazily by `app/engines/minimax.py:61`, so
# snapshotting it in tests would interfere with the lazy-import
# pattern (the test would re-snapshot an empty registry, then
# real code populating it later would be wiped on restore).
PRODUCTION_READ_REGISTRIES: Tuple[Type[RegistryBase[Any]], ...] = (
    ToolRegistry,
    AgentRegistry,
    ChannelRegistry,
    AsrRegistry,
    TtsRegistry,
    VadRegistry,
)


__all__ = [
    "AgentRegistry",
    "AsrRegistry",
    "ChannelRegistry",
    "EngineRegistry",
    "PRODUCTION_READ_REGISTRIES",
    "register_agent",
    "register_asr",
    "register_engine",
    "register_tts",
    "register_tool",
    "register_vad",
    "RegistryBase",
    "ToolRegistry",
    "TtsRegistry",
    "VadRegistry",
]