"""Tests for the registry system."""
import pytest

from app.core.registry import (
    AgentRegistry,
    ChannelRegistry,
    EngineRegistry,
    ModelRegistry,
    ToolRegistry,
)


@pytest.fixture(autouse=True)
def _isolate_registry_state():
    """Clear ModelRegistry + surgically clean test-polluted
    keys from ToolRegistry / EngineRegistry / AgentRegistry
    before + after each test.

    History:
      Sprint 32 P0-1 fixture only cleared ModelRegistry.
      `test_register_tool_decorator_registers_and_sets_name`
      + `test_register_engine_decorator_registers` +
      `test_register_agent_decorator_registers` register
      `_DummyTool` / `_DummyEngine` / `_DummyAgent` classes
      under well-known test keys (`test_tool_decorator_class`
      / `test_engine_decorator` / `test_agent_decorator`).
      Without cleanup, these survive into subsequent test
      files and pollute `default_tools()` (which iterates
      `ToolRegistry.items()`) — causing 11 false failures in
      `tests/tools/test_builder.py` +
      `tests/tools/test_builder_conditional.py`.

    Why surgical (not blanket `.clear()`):
      The other 6 registries (Tool / Agent / Channel /
      Engine / Asr / Tts / Vad) are populated by
      `app.<sub>.__init__.py` eager imports during Sprint 32
      P0-1. Blanket-clearing them here would wipe the real
      eager-imported entries and break downstream tests
      (`default_tools()` would return []; agent_type
      lookups in test_smoke would KeyError). Surgical pop
      of only the test-polluted keys preserves the real
      entries and removes only what these tests added.

    Note: `test_isolation_between_registries` reads from
    EngineRegistry without writing to it — the surgical
    pop is a no-op for it (key absent).

    Before-clear: ensures each `test_register_and_get`
    variant starts with a clean ModelRegistry (no leakage
    from the previous test in this file).
    After-clear: removes the `_Dummy` classes registered
    by this file's tests so the module-level state doesn't
    accumulate test fixtures across reruns.
    """
    # Test-polluted keys added by this file's tests. Keep
    # in sync with the 3 decorator tests below.
    _TOOL_TEST_KEY = "test_tool_decorator_class"
    _ENGINE_TEST_KEY = "test_engine_decorator"
    _AGENT_TEST_KEY = "test_agent_decorator"

    def _surgical_clear() -> None:
        """Remove only the keys this file's tests registered.

        The `_entries()` dict is shared across all
        `ToolRegistry` / `EngineRegistry` / `AgentRegistry`
        subclasses (per-subclass key), so we `pop()` with
        `None` default to avoid KeyError when a previous
        test in this file already cleaned up after itself.
        """
        ToolRegistry._entries().pop(_TOOL_TEST_KEY, None)
        EngineRegistry._entries().pop(_ENGINE_TEST_KEY, None)
        AgentRegistry._entries().pop(_AGENT_TEST_KEY, None)

    ModelRegistry.clear()
    _surgical_clear()
    yield
    ModelRegistry.clear()
    _surgical_clear()


def test_register_and_get():
    @ModelRegistry.register("test-model")
    class _Dummy:
        pass

    assert ModelRegistry.get("test-model") is _Dummy


def test_register_value():
    ModelRegistry.register_value("val", 42)
    assert ModelRegistry.get("val") == 42


def test_duplicate_register_raises():
    ModelRegistry.register_value("dup", 1)
    with pytest.raises(ValueError, match="already has an entry"):
        ModelRegistry.register_value("dup", 2)


def test_get_missing_raises():
    with pytest.raises(KeyError, match="does not have an entry"):
        ModelRegistry.get("nonexistent")


def test_create_instantiates():
    @ModelRegistry.register("factory")
    class _Cls:
        def __init__(self, x):
            self.x = x

    obj = ModelRegistry.create("factory", 7)
    assert obj.x == 7


def test_isolation_between_registries():
    """Entries in ModelRegistry must not leak into EngineRegistry."""
    ModelRegistry.register_value("shared-key", "model")
    with pytest.raises(KeyError):
        EngineRegistry.get("shared-key")


def test_keys_and_contains():
    ModelRegistry.register_value("a", 1)
    ModelRegistry.register_value("b", 2)
    assert set(ModelRegistry.keys()) == {"a", "b"}
    assert ModelRegistry.contains("a")
    assert not ModelRegistry.contains("z")


# ---------------------------------------------------------------------------
# Sprint 32 P0-1: thin decorator wrappers (register_tool /
# register_engine / register_agent / register_asr / register_tts /
# register_vad)
# ---------------------------------------------------------------------------


def test_register_tool_decorator_registers_and_sets_name():
    from app.core.registry import ToolRegistry, register_tool

    @register_tool("test_tool_decorator_class")
    class _DummyTool:
        name = "test_tool_decorator_class"

    assert ToolRegistry.get("test_tool_decorator_class") is _DummyTool


def test_register_tool_mismatched_name_raises():
    from app.core.registry import register_tool

    with pytest.raises(ValueError, match="does not match the registry key"):

        @register_tool("expected-name")
        class _Mismatched:
            name = "different-name"


def test_register_engine_decorator_registers():
    from app.core.registry import EngineRegistry, register_engine

    @register_engine("test_engine_decorator")
    class _DummyEngine:
        pass

    assert EngineRegistry.get("test_engine_decorator") is _DummyEngine


def test_register_agent_decorator_registers():
    from app.core.registry import AgentRegistry, register_agent

    @register_agent("test_agent_decorator")
    class _DummyAgent:
        pass

    assert AgentRegistry.get("test_agent_decorator") is _DummyAgent
