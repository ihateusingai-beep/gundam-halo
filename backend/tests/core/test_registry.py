"""Tests for the registry system."""
import pytest

from app.core.registry import (
    ChannelRegistry,
    EngineRegistry,
    ModelRegistry,
)


@pytest.fixture(autouse=True)
def _clear_model_registry():
    """Clear ModelRegistry before + after each test.

    `test_registry.py` only writes to `ModelRegistry`
    (the only registry it actually populates with test
    fixtures like `_Dummy` via `@ModelRegistry.register`).
    The other 7 registries — ToolRegistry / AgentRegistry /
    ChannelRegistry / EngineRegistry / AsrRegistry /
    TtsRegistry / VadRegistry — are populated by
    `app.<sub>.__init__.py` eager imports during Sprint 32
    P0-1. Clearing them here would wipe those eager-imported
    entries and break downstream tests (e.g. test_smoke's
    `agent_type: "simple"` lookup in AgentRegistry, or
    `default_tools()` lookup in ToolRegistry).

    Note: `test_isolation_between_registries` reads from
    `EngineRegistry` without writing to it — so we don't
    need to clear EngineRegistry either.

    Before-clear: ensures each `test_register_and_get`
    variant starts with a clean `ModelRegistry` (no leakage
    from the previous test in this file).
    After-clear: removes the `_Dummy` classes registered
    by this file's tests so the module-level state doesn't
    accumulate test fixtures across reruns (mitigates
    `test_register_and_get` → `test_create_instantiates`
    pollution if a future test runs them out of order).
    """
    ModelRegistry.clear()
    yield
    ModelRegistry.clear()


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
