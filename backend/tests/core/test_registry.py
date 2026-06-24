"""Tests for the registry system.

Sprint 32 P0-1 v2: the autouse `_isolate_registry_state` fixture
uses the new `RegistryBase.snapshot()` / `restore()` API
(ContextVar-backed storage) to give every test a clean slate
without hardcoding test-polluted keys.

Strategy:
- The 6 production-read registries (`ToolRegistry` /
  `AgentRegistry` / `ChannelRegistry` / `AsrRegistry` /
  `TtsRegistry` / `VadRegistry`) are snapshotted before each
  test and restored after — so test fixtures registered via
  `@register_tool` / `@register_engine` / `@register_agent`
  decorators (or any other registration pattern) get
  auto-cleaned without explicit per-test teardown.
- `EngineRegistry` is **cleared** before each test (and
  restored after, but it has no production readers so
  restoring an empty dict is a no-op). The lazy-import
  pattern for `app/engines/minimax.py` means an earlier
  test in the suite might have imported it and registered
  `minimax` — clearing before each test gives us a clean
  scratch surface for the generic registry-machinery tests
  (which need strict equality assertions like
  `assert keys() == {'a', 'b'}`). The snapshot/restore
  pattern wouldn't work here because `minimax` is a
  legitimate registration from the production lazy import
  that we want to disappear for the duration of these tests.
"""
import pytest

from app.core.registry import (
    PRODUCTION_READ_REGISTRIES,
    AgentRegistry,
    ChannelRegistry,
    EngineRegistry,
    ToolRegistry,
)


@pytest.fixture(autouse=True)
def _isolate_registry_state():
    """Snapshot production-read registries + clear EngineRegistry.

    EngineRegistry has no production readers (it's reserved
    for future live2d backends per the Sprint 32 P0-1
    design comment) so clearing it is safe — it doesn't
    affect production code paths. The generic registry-
    machinery tests use it as scratch space and need strict
    equality assertions, which only work if the registry is
    empty at test entry.
    """
    # Snapshot production-read registries BEFORE any test
    # mutation (and before EngineRegistry.clear() wipes it).
    snapshots = {r: r.snapshot() for r in PRODUCTION_READ_REGISTRIES}
    engine_snap = EngineRegistry.snapshot()
    # EngineRegistry is the scratch surface; clear it so the
    # generic tests get a deterministic empty baseline.
    EngineRegistry.clear()
    try:
        yield
    finally:
        EngineRegistry.restore(engine_snap)
        for r, snap in snapshots.items():
            r.restore(snap)


def test_register_and_get():
    @EngineRegistry.register("test-model")
    class _Dummy:
        pass

    assert EngineRegistry.get("test-model") is _Dummy


def test_register_value():
    EngineRegistry.register_value("val", 42)
    assert EngineRegistry.get("val") == 42


def test_duplicate_register_raises():
    EngineRegistry.register_value("dup", 1)
    with pytest.raises(ValueError, match="already has an entry"):
        EngineRegistry.register_value("dup", 2)


def test_get_missing_raises():
    with pytest.raises(KeyError, match="does not have an entry"):
        EngineRegistry.get("nonexistent")


def test_create_instantiates():
    @EngineRegistry.register("factory")
    class _Cls:
        def __init__(self, x):
            self.x = x

    obj = EngineRegistry.create("factory", 7)
    assert obj.x == 7


def test_isolation_between_registries():
    """Entries in EngineRegistry must not leak into ChannelRegistry."""
    EngineRegistry.register_value("shared-key", "engine")
    with pytest.raises(KeyError):
        ChannelRegistry.get("shared-key")


def test_keys_and_contains():
    EngineRegistry.register_value("a", 1)
    EngineRegistry.register_value("b", 2)
    assert set(EngineRegistry.keys()) == {"a", "b"}
    assert EngineRegistry.contains("a")
    assert not EngineRegistry.contains("z")


def test_clear_empties_registry():
    EngineRegistry.register_value("x", 1)
    EngineRegistry.clear()
    assert EngineRegistry.keys() == ()


def test_snapshot_returns_independent_copy():
    """Mutating the registry after snapshot must not affect the snapshot.

    This guards the autouse fixture's contract: if `snapshot()`
    returned a reference (not a copy), the fixture's restore()
    would silently keep test-fixture entries.
    """
    EngineRegistry.register_value("orig", "before")
    snap = EngineRegistry.snapshot()
    EngineRegistry.register_value("after-snap", "after")
    assert "after-snap" not in snap
    assert "orig" in snap


def test_restore_replaces_state():
    """`restore(snap)` makes the registry equal to `snap`.

    Verifies the inverse direction of the autouse fixture's
    cleanup: after restore, both pre-existing entries and
    additions during the test should be reflected in the
    post-restore state.
    """
    EngineRegistry.register_value("a", 1)
    snap = EngineRegistry.snapshot()
    EngineRegistry.register_value("b", 2)  # during-test addition
    EngineRegistry.restore(snap)
    assert EngineRegistry.keys() == ("a",)
    assert not EngineRegistry.contains("b")


def test_isolation_scope_context_manager():
    """`isolation_scope()` snapshots on enter, restores on exit."""
    EngineRegistry.register_value("permanent", "p")
    with EngineRegistry.isolation_scope():
        EngineRegistry.register_value("scoped", "s")
        assert EngineRegistry.contains("scoped")
        assert EngineRegistry.contains("permanent")
    # Outside the scope, the "scoped" entry is gone but "permanent"
    # (which existed before the scope) is restored too.
    assert not EngineRegistry.contains("scoped")
    assert EngineRegistry.contains("permanent")


# ---------------------------------------------------------------------------
# Sprint 32 P0-1: thin decorator wrappers (register_tool /
# register_engine / register_agent / register_asr / register_tts /
# register_vad)
# ---------------------------------------------------------------------------


def test_register_tool_decorator_registers_and_sets_name():
    from app.core.registry import register_tool

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
    from app.core.registry import register_engine

    @register_engine("test_engine_decorator")
    class _DummyEngine:
        pass

    assert EngineRegistry.get("test_engine_decorator") is _DummyEngine


def test_register_engine_mismatched_name_raises():
    """Sprint 32 P0-1 v2: name-guard now applies to all decorator helpers,
    not just register_tool."""
    from app.core.registry import register_engine

    with pytest.raises(ValueError, match="does not match the registry key"):

        @register_engine("engine-key")
        class _BadEngine:
            name = "different"


def test_register_agent_decorator_registers():
    from app.core.registry import register_agent

    @register_agent("test_agent_decorator")
    class _DummyAgent:
        pass

    assert AgentRegistry.get("test_agent_decorator") is _DummyAgent


def test_register_agent_mismatched_name_raises():
    """Sprint 32 P0-1 v2: uniform name-guard."""
    from app.core.registry import register_agent

    with pytest.raises(ValueError, match="does not match the registry key"):

        @register_agent("agent-key")
        class _BadAgent:
            name = "different"