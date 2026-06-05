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
def _clear_registries():
    """Clear all registries before each test to avoid leakage."""
    for reg in [AgentRegistry, ChannelRegistry, EngineRegistry, ModelRegistry, ToolRegistry]:
        reg.clear()
    yield
    for reg in [AgentRegistry, ChannelRegistry, EngineRegistry, ModelRegistry, ToolRegistry]:
        reg.clear()


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
