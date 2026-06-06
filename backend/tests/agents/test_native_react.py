"""Tests for the native_react agent.

Most of these tests use a stub engine to avoid actually calling the LLM.
For full integration tests, mark as `@pytest.mark.live`.
"""

import asyncio

import pytest

from app.agents.native_react import NativeReActAgent
from app.core.events import EventType, get_event_bus, reset_event_bus
from app.core.types import (
    AgentContext,
    AgentResult,
    Message,
    Role,
    ToolCall,
    ToolResult,
)


# Agent tests need permissive policy for file_read/file_write tools
pytestmark = pytest.mark.usefixtures("permissive_test_config")


class StubEngine:
    """Stub engine that returns scripted responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def chat(self, messages, *, tools=None, **kwargs):
        self.calls.append({"messages": list(messages), "tools": tools})
        return self.responses.pop(0) if self.responses else Message(role=Role.ASSISTANT, content="(no more scripted responses)")


@pytest.fixture
def file_read_tool():
    """A simple stub file_read tool that returns a fixed string."""
    from app.tools.file_read import FileReadTool
    return FileReadTool()


def _make_final_answer(text: str = "All done.") -> Message:
    return Message(role=Role.ASSISTANT, content=text)


def _make_tool_call(name: str, args: dict, id: str = "tc1") -> Message:
    return Message(
        role=Role.ASSISTANT,
        content="",
        tool_calls=[ToolCall(id=id, name=name, arguments=args)],
    )


def test_simple_run_no_tools():
    """If LLM gives a direct answer, return it."""
    engine = StubEngine([_make_final_answer("The answer is 42.")])
    agent = NativeReActAgent(engine=engine, model="test", tools=[])
    result = asyncio.run(agent.run("What is the meaning of life?"))
    assert result.success
    assert "42" in result.output
    assert result.tool_calls_made == 0


def test_run_with_tool_call(file_read_tool):
    """Agent should execute the tool and continue."""
    engine = StubEngine([
        _make_tool_call("file_read", {"path": "/some/file.txt"}, "tc1"),
        _make_final_answer("File says: hello"),
    ])
    agent = NativeReActAgent(
        engine=engine, model="test", tools=[file_read_tool],
    )
    result = asyncio.run(agent.run("read /some/file.txt"))
    assert result.success
    assert "hello" in result.output
    assert result.tool_calls_made == 1


def test_run_with_unknown_tool():
    """Unknown tool name should produce an error observation, not crash."""
    engine = StubEngine([
        _make_tool_call("nonexistent_tool", {}, "tc1"),
        _make_final_answer("OK, I tried"),
    ])
    agent = NativeReActAgent(engine=engine, model="test", tools=[])
    result = asyncio.run(agent.run("test"))
    assert result.success
    assert result.tool_calls_made == 1
    # The observation should mention "not found"
    tool_messages = [m for m in result.messages if m.role == Role.TOOL]
    assert any("not found" in m.content for m in tool_messages)


def test_max_turns_exceeded():
    """If LLM keeps calling tools without answering, hit max_turns."""
    responses = [
        _make_tool_call("file_read", {"path": "/x"}, f"tc{i}")
        for i in range(15)  # more than default max_turns=10
    ]
    engine = StubEngine(responses)
    agent = NativeReActAgent(engine=engine, model="test", tools=[])
    result = asyncio.run(agent.run("test"))
    assert not result.success
    assert result.error == "max_turns_exceeded"


# ---------------------------------------------------------------------------
# Tool call event emission (TOOL_CALL_START / TOOL_CALL_END on the EventBus)
# ---------------------------------------------------------------------------


def test_tool_call_start_and_end_events_published(file_read_tool):
    """Agent must publish TOOL_CALL_START before executing and TOOL_CALL_END after."""
    reset_event_bus()
    bus = get_event_bus(record_history=True)

    engine = StubEngine([
        _make_tool_call("file_read", {"path": "/some/file.txt"}, "call-abc"),
        _make_final_answer("Done"),
    ])
    agent = NativeReActAgent(engine=engine, model="test", tools=[file_read_tool])

    ctx = AgentContext(project_id="test-proj", session_id="sess-1", channel="web")
    asyncio.run(agent.run("read the file", context=ctx))

    # Filter history for tool call events
    starts = [e for e in bus.history if e.event_type == EventType.TOOL_CALL_START]
    ends = [e for e in bus.history if e.event_type == EventType.TOOL_CALL_END]

    assert len(starts) == 1
    assert len(ends) == 1

    s = starts[0]
    assert s.data["call_id"] == "call-abc"
    assert s.data["tool"] == "file_read"
    assert s.data["session_id"] == "sess-1"
    assert s.data["project"] == "test-proj"
    assert s.data["args"] == {"path": "/some/file.txt"}

    e = ends[0]
    assert e.data["call_id"] == "call-abc"
    assert e.data["tool"] == "file_read"
    assert e.data["ok"] is True
    assert e.data["session_id"] == "sess-1"
    assert "duration_ms" in e.data
    assert e.data["duration_ms"] >= 0


def test_tool_call_end_marks_failure_on_exception():
    """If a tool raises, the TOOL_CALL_END event should have ok=False."""
    reset_event_bus()
    bus = get_event_bus(record_history=True)

    # A tool that always raises
    class BoomTool:
        name = "boom"
        async def run(self, **_):
            raise RuntimeError("kaboom")
        def to_spec(self):
            return {"type": "function", "function": {"name": "boom"}}

    engine = StubEngine([
        _make_tool_call("boom", {}, "call-boom"),
        _make_final_answer("I tried"),
    ])
    agent = NativeReActAgent(engine=engine, model="test", tools=[BoomTool()])
    asyncio.run(agent.run("boom"))

    ends = [e for e in bus.history if e.event_type == EventType.TOOL_CALL_END]
    assert len(ends) == 1
    assert ends[0].data["ok"] is False
    assert "kaboom" in ends[0].data["result_preview"]


def test_tool_call_event_includes_call_id_for_unknown_tool():
    """Unknown tool: TOOL_CALL_END still fires with ok=False and a call_id."""
    reset_event_bus()
    bus = get_event_bus(record_history=True)

    engine = StubEngine([
        _make_tool_call("nope", {}, "call-missing"),
        _make_final_answer("done"),
    ])
    agent = NativeReActAgent(engine=engine, model="test", tools=[])
    asyncio.run(agent.run("go"))

    ends = [e for e in bus.history if e.event_type == EventType.TOOL_CALL_END]
    assert len(ends) == 1
    assert ends[0].data["call_id"] == "call-missing"
    assert ends[0].data["ok"] is False
