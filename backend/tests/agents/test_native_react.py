"""Tests for the native_react agent.

Most of these tests use a stub engine to avoid actually calling the LLM.
For full integration tests, mark as `@pytest.mark.live`.
"""

import pytest

from app.agents.native_react import NativeReActAgent
from app.core.types import (
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
    import asyncio
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
    import asyncio
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
    import asyncio
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
    import asyncio
    result = asyncio.run(agent.run("test"))
    assert not result.success
    assert result.error == "max_turns_exceeded"
