"""Tests for the default_tools() builder."""
from app.tools.builder import default_tools
from app.tools._stubs import BaseTool


def test_default_tools_returns_list():
    tools = default_tools()
    assert isinstance(tools, list)
    assert len(tools) > 0


def test_all_tools_are_base_tool():
    tools = default_tools()
    for tool in tools:
        assert isinstance(tool, BaseTool)


def test_default_tool_names():
    tools = default_tools()
    names = {t.name for t in tools}
    assert "file_read" in names
    assert "file_write" in names
    assert "shell_exec" in names
    assert "open_app" in names


def test_all_tools_have_unique_names():
    tools = default_tools()
    names = [t.name for t in tools]
    assert len(names) == len(set(names))


def test_all_tools_have_valid_specs():
    """Each tool's spec should have the OpenAI function-calling format."""
    for tool in default_tools():
        spec = tool.to_spec()
        assert spec["type"] == "function"
        assert "name" in spec["function"]
        assert "description" in spec["function"]
        assert "parameters" in spec["function"]
        params = spec["function"]["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
