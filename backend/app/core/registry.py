"""Decorator-based registry for runtime discovery of pluggable components.

Inspired by OpenJarvis (Apache 2.0) — reimplemented under MIT for Gundam Halo.

Each typed subclass gets its own isolated storage so registrations in one
registry never leak into another.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Generic, Tuple, Type, TypeVar

T = TypeVar("T")


class RegistryBase(Generic[T]):
    """Generic registry base class with class-specific entry isolation."""

    @classmethod
    def _entries(cls) -> Dict[str, T]:
        attr_name = f"_registry_entries_{cls.__name__}"
        storage = getattr(cls, attr_name, None)
        if storage is None:
            storage = {}
            setattr(cls, attr_name, storage)
        return storage

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
        """Remove all entries (useful in tests)."""
        cls._entries().clear()


# ---------------------------------------------------------------------------
# Typed subclass registries — one per primitive
# ---------------------------------------------------------------------------


class ModelRegistry(RegistryBase[Any]):
    """Registry for ModelSpec objects."""


class EngineRegistry(RegistryBase[Type[Any]]):
    """Registry for inference engine backends."""


class MemoryRegistry(RegistryBase[Type[Any]]):
    """Registry for memory / retrieval backends."""


class AgentRegistry(RegistryBase[Type[Any]]):
    """Registry for agent implementations."""


class ToolRegistry(RegistryBase[Any]):
    """Registry for tool specifications."""


class ChannelRegistry(RegistryBase[Type[Any]]):
    """Registry for channel implementations."""


class ProjectRegistry(RegistryBase[Any]):
    """Registry for project lifecycle hooks (optional)."""


# Per-subsystem engine registries. Each voice / live2d / inference
# sub-system gets its own typed registry so a backend name in one
# (e.g. "edge" for TTS) doesn't collide with another (e.g. "edge"
# for a hypothetical VAD). Sprint 32 P0-1 adds the 3 voice
# registries; live2d + inference engines share `EngineRegistry`.


class AsrRegistry(RegistryBase[Type[Any]]):
    """Registry for ASR backends (whisper_local, yuesub, whisper_hf)."""


class TtsRegistry(RegistryBase[Type[Any]]):
    """Registry for TTS backends (edge, pyttsx3, azure)."""


class VadRegistry(RegistryBase[Type[Any]]):
    """Registry for VAD backends (silero, fsmn)."""


# ---------------------------------------------------------------------------
# Ergonomic decorator helpers (Sprint 32 P0-1)
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
# the registered key — so a typo like `@register_tool("file_rea")`
# + `name = "file_read"` fails loudly at import time rather than
# silently under-registering.


def register_tool(name: str):
    """Decorator: register a `BaseTool` subclass under `name`."""
    def decorator(cls: type) -> type:
        if hasattr(cls, "name") and cls.name != name:
            raise ValueError(
                f"{cls.__name__}.name = {cls.name!r} does not match "
                f"the registry key {name!r} — fix the decorator or "
                f"the class attribute."
            )
        ToolRegistry.register_value(name, cls)
        return cls
    return decorator


def register_engine(name: str):
    """Decorator: register an `InferenceEngine` subclass under `name`."""
    def decorator(cls: type) -> type:
        EngineRegistry.register_value(name, cls)
        return cls
    return decorator


def register_agent(name: str):
    """Decorator: register a `BaseAgent` subclass under `name`."""
    def decorator(cls: type) -> type:
        AgentRegistry.register_value(name, cls)
        return cls
    return decorator


def register_asr(name: str):
    """Decorator: register an `ASRInterface` subclass under `name`."""
    def decorator(cls: type) -> type:
        AsrRegistry.register_value(name, cls)
        return cls
    return decorator


def register_tts(name: str):
    """Decorator: register a `TTSInterface` subclass under `name`."""
    def decorator(cls: type) -> type:
        TtsRegistry.register_value(name, cls)
        return cls
    return decorator


def register_vad(name: str):
    """Decorator: register a `VADInterface` subclass under `name`."""
    def decorator(cls: type) -> type:
        VadRegistry.register_value(name, cls)
        return cls
    return decorator


__all__ = [
    "AgentRegistry",
    "AsrRegistry",
    "ChannelRegistry",
    "EngineRegistry",
    "MemoryRegistry",
    "ModelRegistry",
    "ProjectRegistry",
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
