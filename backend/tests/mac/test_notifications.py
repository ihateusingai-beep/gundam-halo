"""Tests for the notifications wrapper (`app.mac.notifications`)."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


def _mock_completed_process(returncode=0, stderr=""):
    cp = MagicMock()
    cp.returncode = returncode
    cp.stderr = stderr
    return cp


pytestmark = pytest.mark.usefixtures("permissive_test_config")


def test_send_notification_constructs_correct_script():
    from app.mac.notifications import send_notification

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process()
        result = send_notification(
            text="Task complete", title="Build OK", subtitle="3.2s"
        )

    args = mock_run.call_args[0][0]
    assert args[0] == "osascript"
    assert args[1] == "-e"
    # The composed AppleScript should contain all three parts
    script = args[2]
    assert "display notification" in script
    assert 'with title "Build OK"' in script
    assert 'subtitle "3.2s"' in script
    # Text is quoted — verify it survives the escape
    assert '"Task complete"' in script
    assert result["exit_code"] == 0


def test_send_notification_optional_title_and_subtitle():
    from app.mac.notifications import send_notification

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process()
        send_notification(text="Bare notification")
    script = mock_run.call_args[0][0][2]
    assert "display notification" in script
    # Without title/subtitle, no with/subtitle clauses
    assert "with title" not in script
    assert "subtitle " not in script


def test_send_notification_escapes_quotes():
    """Quotes in the notification text should be backslash-escaped."""
    from app.mac.notifications import send_notification

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process()
        send_notification(text='He said "hi"', title='My "Title"')
    script = mock_run.call_args[0][0][2]
    # Backslash-escaped quotes should be present
    assert '\\"hi\\"' in script
    assert '\\"Title\\"' in script


def test_send_notification_rejects_empty():
    from app.mac.notifications import send_notification

    with pytest.raises(ValueError, match="empty"):
        send_notification(text="")


def test_send_notification_disabled_raises():
    from app.core import config as _config_module
    from app.mac.notifications import send_notification

    cfg = _config_module.get_config()
    cfg.mac.notifications_enabled = False
    try:
        with pytest.raises(PermissionError, match="disabled"):
            send_notification(text="hi")
    finally:
        cfg.mac.notifications_enabled = True


def test_send_notification_timeout():
    import subprocess
    from app.mac.notifications import send_notification

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["osascript"], timeout=2)
        result = send_notification(text="hi", timeout=2)
    assert result["exit_code"] == -1
    assert "Timeout" in result["stderr"]


# --- Tool class test ---


def test_notify_tool_sends_banner():
    import asyncio
    from app.tools.notify import NotifyTool

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process()
        result = asyncio.run(NotifyTool().run(text="Build done"))
    assert "OK" in result
    assert "notification sent" in result


def test_notify_tool_surfaces_disabled():
    import asyncio
    from app.core import config as _config_module
    from app.tools.notify import NotifyTool

    cfg = _config_module.get_config()
    cfg.mac.notifications_enabled = False
    try:
        result = asyncio.run(NotifyTool().run(text="hi"))
    finally:
        cfg.mac.notifications_enabled = True
    assert "Error" in result
    assert "disabled" in result
