"""Tests for the Spotlight wrapper (`app.mac.spotlight`)."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


def _mock_completed_process(returncode=0, stdout="", stderr=""):
    cp = MagicMock()
    cp.returncode = returncode
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


pytestmark = pytest.mark.usefixtures("permissive_test_config")


def test_spotlight_search_basic():
    from app.mac.spotlight import spotlight_search

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(
            stdout="/Users/ken/Documents/notes.md\n/Users/ken/Documents/more.md"
        )
        result = spotlight_search("meeting notes")
    assert result["count"] == 2
    assert "/Users/ken/Documents/notes.md" in result["results"]


def test_spotlight_search_empty_results():
    from app.mac.spotlight import spotlight_search

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="")
        result = spotlight_search("nothing matches xyz")
    assert result["count"] == 0
    assert result["results"] == []


def test_spotlight_search_with_only_in():
    from app.mac.spotlight import spotlight_search

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="/a/x.md")
        spotlight_search("foo", only_in="/a")
    args = mock_run.call_args[0][0]
    # mdfind argv with -onlyin comes first, no -maxresults (post-truncate in Python)
    assert args == ["mdfind", "-onlyin", "/a", "foo"]


def test_spotlight_search_max_results_clamped():
    """max_results above the hard ceiling should be clamped to 500."""
    from app.mac.spotlight import ABSOLUTE_MAX_RESULTS, spotlight_search

    with patch("subprocess.run") as mock_run:
        # Return many lines so we can verify the post-truncate
        lines = [f"/path/{i}" for i in range(1000)]
        mock_run.return_value = _mock_completed_process(stdout="\n".join(lines))
        result = spotlight_search("foo", max_results=99999)
    assert result["max_results"] == ABSOLUTE_MAX_RESULTS == 500
    # argv does NOT include -maxresults — we truncate in Python
    args = mock_run.call_args[0][0]
    assert args == ["mdfind", "foo"]
    # The result list is truncated to 500
    assert len(result["results"]) == 500


def test_spotlight_search_min_clamped_to_1():
    from app.mac.spotlight import spotlight_search

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process()
        result = spotlight_search("foo", max_results=0)
    assert result["max_results"] == 1


def test_spotlight_post_truncate():
    """When mdfind returns more results than max_results, the wrapper truncates."""
    from app.mac.spotlight import spotlight_search

    with patch("subprocess.run") as mock_run:
        lines = [f"/p/{i}" for i in range(50)]
        mock_run.return_value = _mock_completed_process(stdout="\n".join(lines))
        result = spotlight_search("foo", max_results=10)
    assert result["count"] == 10
    assert result["results"] == [f"/p/{i}" for i in range(10)]


def test_spotlight_search_rejects_empty_query():
    from app.mac.spotlight import spotlight_search

    with pytest.raises(ValueError, match="empty"):
        spotlight_search("")


def test_spotlight_search_missing_tool_raises():
    from app.mac.spotlight import spotlight_search

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("mdfind not found")
        with pytest.raises(RuntimeError, match="mdfind"):
            spotlight_search("foo")


def test_spotlight_search_timeout():
    import subprocess
    from app.mac.spotlight import spotlight_search

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["mdfind"], timeout=2)
        result = spotlight_search("foo", timeout=2)
    assert result["exit_code"] == -1
    assert "Timeout" in result["stderr"]


# --- Tool class test ---


def test_spotlight_tool_formats_numbered_list():
    import asyncio
    from app.tools.spotlight import SpotlightTool

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="/a.md\n/b.md")
        result = asyncio.run(SpotlightTool().run(query="kind:pdf"))
    assert "Found 2 result(s)" in result
    assert "1. /a.md" in result
    assert "2. /b.md" in result


def test_spotlight_tool_empty_results():
    import asyncio
    from app.tools.spotlight import SpotlightTool

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="")
        result = asyncio.run(SpotlightTool().run(query="xyz"))
    assert "No results" in result


def test_spotlight_tool_propagates_mdfind_error():
    import asyncio
    from app.tools.spotlight import SpotlightTool

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(
            returncode=1, stderr="index unavailable"
        )
        result = asyncio.run(SpotlightTool().run(query="foo"))
    assert "Error" in result
    assert "index unavailable" in result
