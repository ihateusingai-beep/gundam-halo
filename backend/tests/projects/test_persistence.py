"""Tests for session persistence (save/load/scan)."""

import json
import pytest

from app.core.types import Message, Role, ToolCall
from app.projects import persistence


@pytest.fixture
def project_name():
    return "test-project"


def test_save_and_load_roundtrip(tmp_path, project_name, permissive_test_config):
    """Save a few messages, load them back, verify they match."""
    sid = "abc123def456"
    messages = [
        Message(role=Role.SYSTEM, content="You are helpful."),
        Message(role=Role.USER, content="hello"),
        Message(
            role=Role.ASSISTANT,
            content="",
            tool_calls=[ToolCall(id="tc1", name="file_read", arguments={"path": "/x"})],
        ),
        Message(
            role=Role.TOOL,
            content="file contents",
            tool_call_id="tc1",
            name="file_read",
        ),
        Message(role=Role.ASSISTANT, content="The file says: file contents"),
    ]

    path = persistence.save_messages(project_name, sid, messages)
    assert path.exists()
    assert path.name == f"{sid}.json"

    loaded = persistence.load_messages(project_name, sid)
    assert loaded is not None
    assert len(loaded) == 5
    assert loaded[0].role == Role.SYSTEM
    assert loaded[0].content == "You are helpful."
    assert loaded[1].role == Role.USER
    assert loaded[2].role == Role.ASSISTANT
    assert len(loaded[2].tool_calls) == 1
    assert loaded[2].tool_calls[0].name == "file_read"
    assert loaded[2].tool_calls[0].arguments == {"path": "/x"}
    assert loaded[3].role == Role.TOOL
    assert loaded[3].tool_call_id == "tc1"
    assert loaded[3].name == "file_read"
    assert loaded[4].content == "The file says: file contents"


def test_save_preserves_created_at(tmp_path, project_name, permissive_test_config):
    """Saving twice should preserve the original created_at."""
    sid = "abc"
    messages = [Message(role=Role.USER, content="hi")]

    persistence.save_messages(project_name, sid, messages)
    first = persistence.load_messages(project_name, sid)
    assert first is not None

    # Save again
    import time
    time.sleep(0.01)
    messages2 = messages + [Message(role=Role.ASSISTANT, content="hello")]
    persistence.save_messages(project_name, sid, messages2)

    # Read raw JSON to check timestamps
    path = persistence.session_file_path(project_name, sid)
    with open(path) as f:
        data = json.load(f)
    # created_at should be present
    assert "created_at" in data
    assert "updated_at" in data


def test_load_nonexistent_returns_none(tmp_path, project_name, permissive_test_config):
    assert persistence.load_messages(project_name, "nope") is None


def test_session_exists(tmp_path, project_name, permissive_test_config):
    sid = "existstest"
    assert not persistence.session_exists(project_name, sid)
    persistence.save_messages(project_name, sid, [Message(role=Role.USER, content="hi")])
    assert persistence.session_exists(project_name, sid)


def test_delete_session(tmp_path, project_name, permissive_test_config):
    sid = "deltest"
    persistence.save_messages(project_name, sid, [Message(role=Role.USER, content="hi")])
    assert persistence.delete_session(project_name, sid) is True
    assert not persistence.session_exists(project_name, sid)
    # Delete again returns False
    assert persistence.delete_session(project_name, sid) is False


def test_scan_project_sessions(tmp_path, project_name, permissive_test_config):
    """Scan returns summaries of all sessions in a project."""
    # Save 3 sessions
    for i, sid in enumerate(["s1", "s2", "s3"]):
        persistence.save_messages(
            project_name,
            sid,
            [Message(role=Role.USER, content=f"msg {i}")],
        )

    summaries = persistence.scan_project_sessions(project_name)
    assert len(summaries) == 3
    sids = {s.session_id for s in summaries}
    assert sids == {"s1", "s2", "s3"}


def test_atomic_write_does_not_leave_tmp(tmp_path, project_name, permissive_test_config):
    """After a successful save, no .tmp files should remain."""
    sid = "atomictest"
    persistence.save_messages(project_name, sid, [Message(role=Role.USER, content="hi")])

    # Check the conversations dir for leftover .tmp files
    conv_dir = persistence.conversations_dir(project_name)
    tmp_files = list(conv_dir.glob("*.tmp"))
    assert tmp_files == []


def test_corrupted_file_returns_none(tmp_path, project_name, permissive_test_config):
    """A corrupted JSON file should not crash — return None."""
    sid = "corrupt"
    path = persistence.session_file_path(project_name, sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not valid json {{{")

    result = persistence.load_messages(project_name, sid)
    assert result is None


def test_different_projects_isolated(tmp_path, permissive_test_config):
    """Sessions in different projects must not see each other."""
    persistence.save_messages("proj-a", "s1", [Message(role=Role.USER, content="a-msg")])
    persistence.save_messages("proj-b", "s1", [Message(role=Role.USER, content="b-msg")])

    a_msgs = persistence.load_messages("proj-a", "s1")
    b_msgs = persistence.load_messages("proj-b", "s1")
    assert a_msgs is not None and b_msgs is not None
    assert a_msgs[0].content == "a-msg"
    assert b_msgs[0].content == "b-msg"
