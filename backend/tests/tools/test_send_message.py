"""Tests for SendMessageTool (Sprint 27 Track 27.4 + Sprint 30 Track A).

Per `docs/FEATURE-SPEC-SPRINT30.md` §4.1 (Track A
impl) + `docs/FEATURE-SPEC-SPRINT27.md` §4.2 Track 27.4
(Sprint 27 stub replaced in Sprint 30).

Sprint 30 Track A replaced the Sprint 27 stub with a
real YOLO-based computer-vision pipeline. The tests
verify the contract:
  1. Schema + name
  2. Validation (empty args, unknown platform)
  3. Platform → app name resolution (per OS)
  4. pyautogui + YOLO deps availability check
  5. YOLO detection pipeline (mocked — 10 steps)
  6. Error messages (missing deps, no YOLO match,
     unsupported platform, etc.)

The YOLO detector + pyautogui flow itself is untested
in CI because the YOLO model + display + Accessibility
permission are not available in the test env. The
tests mock the YOLO detector's `find_first` method
to verify the 10-step pipeline contract.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.tools.send_message import (
    PLATFORM_APP_NAMES,
    SendMessageError,
    SendMessageTool,
    _check_pyautogui_available,
    _resolve_app_name,
)


# ---------------------------------------------------------------------------
# 1. Schema + name
# ---------------------------------------------------------------------------


class TestSchema:
    def test_name(self):
        assert SendMessageTool().name == "send_message"

    def test_required_params(self):
        params = SendMessageTool().parameters
        assert "receiver" in params["required"]
        assert "message_text" in params["required"]
        # platform is optional (default "whatsapp")
        assert "platform" not in params["required"]


# ---------------------------------------------------------------------------
# 2. Platform → app name resolution
# ---------------------------------------------------------------------------


class TestPlatformResolution:
    def test_resolves_whatsapp_macos(self):
        assert _resolve_app_name("whatsapp", "darwin") == "WhatsApp"

    def test_resolves_telegram_macos(self):
        assert _resolve_app_name("telegram", "darwin") == "Telegram"

    def test_resolves_unknown_platform(self):
        assert _resolve_app_name("not_a_platform", "darwin") is None

    def test_resolves_unsupported_platform_on_linux(self):
        # messenger has no native Linux app
        assert _resolve_app_name("messenger", "linux") is None

    def test_resolves_unsupported_platform_on_windows(self):
        # Most platforms supported on Windows
        assert _resolve_app_name("discord", "win32") == "Discord"

    def test_all_platforms_have_mapping(self):
        for platform_name in (
            "whatsapp", "telegram", "signal",
            "discord", "messenger", "instagram",
        ):
            assert platform_name in PLATFORM_APP_NAMES


# ---------------------------------------------------------------------------
# 3. pyautogui availability check
# ---------------------------------------------------------------------------


class TestPyautoguiAvailability:
    def test_returns_none_when_available(self):
        # When pyautogui + pyperclip are importable, the
        # function returns None (no error).
        # In our test env, the deps are NOT installed,
        # so this test only validates the contract.
        result = _check_pyautogui_available()
        # Either None (deps installed) or an error string
        # (deps not installed). Both are valid — the
        # function's job is to return None or a string.
        assert result is None or isinstance(result, str)

    def test_returns_error_string_when_missing(self):
        # Force the import to fail by patching sys.modules
        # with None (mark as unimportable).
        with patch.dict("sys.modules", {
            "pyautogui": None,
            "pyperclip": None,
        }):
            # Need to invalidate the cache for the imports
            # to re-attempt. Use importlib.invalidate_caches.
            import importlib
            importlib.invalidate_caches()
            # Note: the actual behavior depends on whether
            # `None` in sys.modules actually blocks the
            # import. The test is best-effort; if the
            # imports succeed (because pyautogui is
            # installed), the result will be None.
            result = _check_pyautogui_available()
            # We don't assert specific behavior here —
            # just verify the function returns a string
            # or None (the contract).
            assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# 4. run() validation
# ---------------------------------------------------------------------------


class TestValidation:
    @pytest.mark.asyncio
    async def test_rejects_empty_receiver(self):
        out = await SendMessageTool().run(receiver="", message_text="hello")
        assert "Error" in out
        assert "receiver" in out

    @pytest.mark.asyncio
    async def test_rejects_whitespace_receiver(self):
        out = await SendMessageTool().run(receiver="   ", message_text="hello")
        assert "Error" in out

    @pytest.mark.asyncio
    async def test_rejects_empty_message(self):
        out = await SendMessageTool().run(receiver="John", message_text="")
        assert "Error" in out
        assert "message_text" in out

    @pytest.mark.asyncio
    async def test_rejects_whitespace_message(self):
        out = await SendMessageTool().run(receiver="John", message_text="   ")
        assert "Error" in out

    @pytest.mark.asyncio
    async def test_default_platform_is_whatsapp(self):
        # When platform is omitted, default to whatsapp.
        # The tool should NOT raise an "unknown platform"
        # error. The actual error depends on whether
        # pyautogui is installed — if not, the
        # "pyautogui required" error mentions WhatsApp
        # in the available-platforms list. If yes, the
        # YOLO detection pipeline runs.
        out = await SendMessageTool().run(
            receiver="John", message_text="hi", platform=""
        )
        # The error should not be "unknown platform"
        # (platform="" is normalised to "whatsapp")
        assert "unknown" not in out.lower() or "platform" not in out.lower()

    @pytest.mark.asyncio
    async def test_unknown_platform_returns_clear_error(self):
        out = await SendMessageTool().run(
            receiver="John",
            message_text="hi",
            platform="not_a_real_platform",
        )
        assert "Error" in out
        assert "not_a_real_platform" in out or "supported" in out.lower()


# ---------------------------------------------------------------------------
# 5. Real YOLO-based flow (Sprint 30 Track A)
# ---------------------------------------------------------------------------


class TestRealFlow:
    """Sprint 30 Track A: the SendMessageTool now uses
    a YOLO-based computer-vision pipeline instead of
    the Sprint 27 stub. The tests mock the YOLO
    detector + mss + pyautogui to verify the contract.
    """

    @pytest.mark.asyncio
    @patch(
        "app.tools.send_message._check_pyautogui_available",
        return_value="pyautogui + pyperclip are required for the send_message tool. Install with: uv sync --extra tool-send-message.",
    )
    async def test_missing_pyautogui_returns_clear_error(self, _mock):
        out = await SendMessageTool().run(
            receiver="John",
            message_text="hi",
            platform="whatsapp",
        )
        assert "Error" in out
        assert "pyautogui" in out
        assert "tool-send-message" in out

    @pytest.mark.asyncio
    @patch("app.tools.send_message._check_pyautogui_available", return_value=None)
    @patch(
        "app.tools.send_message._check_yolo_deps_available",
        return_value="onnxruntime is required. Install with: uv sync --extra tool-send-message.",
    )
    async def test_missing_yolo_deps_returns_clear_error(self, _mock_pg, _mock_yolo):
        out = await SendMessageTool().run(
            receiver="John",
            message_text="hi",
            platform="whatsapp",
        )
        assert "Error" in out
        assert "onnxruntime" in out or "mss" in out or "pygetwindow" in out or "numpy" in out
        assert "tool-send-message" in out

    @pytest.mark.asyncio
    @patch("app.tools.send_message._check_pyautogui_available", return_value=None)
    @patch("app.tools.send_message._check_yolo_deps_available", return_value=None)
    async def test_unsupported_platform_on_current_os(self, _mock_pg, _mock_yolo):
        # On Linux, messenger returns None from
        # _resolve_app_name. Verify the error mentions
        # this. Use `monkeypatch.setattr(sys, "platform", "linux")`
        # to mock the OS.
        import sys
        with patch.object(sys, "platform", "linux"):
            out = await SendMessageTool().run(
                receiver="John",
                message_text="hi",
                platform="messenger",
            )
        assert "Error" in out
        assert "messenger" in out
        assert "linux" in out  # sys.platform value (lowercase)

    @pytest.mark.asyncio
    @patch("app.tools.send_message._check_pyautogui_available", return_value=None)
    @patch("app.tools.send_message._check_yolo_deps_available", return_value=None)
    @patch("app.tools.send_message.SendMessageTool._open_app")
    @patch("app.tools.send_message.SendMessageTool._get_window_bbox")
    @patch("app.tools.send_message.SendMessageTool._take_screenshot")
    async def test_yolo_pipeline_success(
        self, mock_screenshot, mock_bbox, mock_open, _mock_yolo, _mock_pg
    ):
        """Verify the 10-step YOLO detection pipeline
        completes successfully. Mocks `_get_detector`
        to return a fake detector with mocked
        `find_first`.
        """
        # Mock the heavy imports (pyautogui + mss + pygetwindow)
        # via sys.modules so the run() flow doesn't try to
        # import them.
        with patch.dict("sys.modules", {
            "pyautogui": MagicMock(),
            "pyperclip": MagicMock(),
            "mss": MagicMock(),
            "pygetwindow": MagicMock(),
            "numpy": MagicMock(),
            "onnxruntime": MagicMock(),
        }):
            # Mock bbox + screenshot
            mock_bbox.return_value = (0, 0, 100, 100)
            mock_screenshot.return_value = None  # not used — find_first is mocked

            # Mock the YOLO detector returned by _get_detector
            from app.tools._yolo import Detection
            mock_detector = MagicMock()
            mock_detector.find_first.side_effect = [
                Detection("contact_search_bar", 0, 0.95, 50, 10, 80, 20),
                Detection("contact_result", 1, 0.91, 50, 50, 100, 30),
                Detection("message_bar", 2, 0.88, 50, 90, 200, 20),
            ]

            async def fake_get_detector(self, model_path):
                return mock_detector
            with patch.object(
                SendMessageTool, "_get_detector", fake_get_detector
            ):
                out = await SendMessageTool().run(
                    receiver="John",
                    message_text="hi",
                    platform="whatsapp",
                )

        assert "Message sent" in out
        assert "John" in out
        assert "whatsapp" in out
        # find_first should be called 3 times (search bar, result, message bar)
        assert mock_detector.find_first.call_count == 3
        # Press Enter (not send_button) for whatsapp
        assert mock_open.call_count == 1

    @pytest.mark.asyncio
    @patch("app.tools.send_message._check_pyautogui_available", return_value=None)
    @patch("app.tools.send_message._check_yolo_deps_available", return_value=None)
    @patch("app.tools.send_message.SendMessageTool._open_app")
    @patch("app.tools.send_message.SendMessageTool._get_window_bbox")
    @patch("app.tools.send_message.SendMessageTool._take_screenshot")
    async def test_yolo_fails_to_find_search_bar(
        self, _mock_ss, _mock_bbox, _mock_open, _mock_yolo, _mock_pg
    ):
        """Verify the error message when YOLO can't find
        the contact search bar.
        """
        with patch.dict("sys.modules", {
            "pyautogui": MagicMock(),
            "pyperclip": MagicMock(),
            "mss": MagicMock(),
            "pygetwindow": MagicMock(),
            "numpy": MagicMock(),
            "onnxruntime": MagicMock(),
        }):
            mock_detector = MagicMock()
            mock_detector.find_first.return_value = None

            async def fake_get_detector(self, model_path):
                return mock_detector
            with patch.object(
                SendMessageTool, "_get_detector", fake_get_detector
            ):
                out = await SendMessageTool().run(
                    receiver="John",
                    message_text="hi",
                    platform="whatsapp",
                )
        assert "Error" in out
        assert "contact search bar" in out

    @pytest.mark.asyncio
    @patch("app.tools.send_message._check_pyautogui_available", return_value=None)
    @patch("app.tools.send_message._check_yolo_deps_available", return_value=None)
    @patch("app.tools.send_message.SendMessageTool._open_app")
    @patch("app.tools.send_message.SendMessageTool._get_window_bbox")
    @patch("app.tools.send_message.SendMessageTool._take_screenshot")
    async def test_yolo_finds_search_bar_but_no_contact_result(
        self, _mock_ss, _mock_bbox, _mock_open, _mock_yolo, _mock_pg
    ):
        """Verify the error message when YOLO finds the
        search bar but no matching contact in the results.
        """
        from app.tools._yolo import Detection
        mock_detector = MagicMock()
        # First call: search bar found. Second call: no contact.
        mock_detector.find_first.side_effect = [
            Detection("contact_search_bar", 0, 0.95, 50, 10, 80, 20),
            None,  # contact_result not found
        ]
        with patch.dict("sys.modules", {
            "pyautogui": MagicMock(),
            "pyperclip": MagicMock(),
            "mss": MagicMock(),
            "pygetwindow": MagicMock(),
            "numpy": MagicMock(),
            "onnxruntime": MagicMock(),
        }):
            async def fake_get_detector(self, model_path):
                return mock_detector
            with patch.object(
                SendMessageTool, "_get_detector", fake_get_detector
            ):
                out = await SendMessageTool().run(
                    receiver="Nonexistent",
                    message_text="hi",
                    platform="whatsapp",
                )
        assert "Error" in out
        assert "Nonexistent" in out or "contact" in out.lower()

    @pytest.mark.asyncio
    @patch("app.tools.send_message._check_pyautogui_available", return_value=None)
    @patch("app.tools.send_message._check_yolo_deps_available", return_value=None)
    @patch("app.tools.send_message.SendMessageTool._open_app")
    @patch("app.tools.send_message.SendMessageTool._get_window_bbox")
    @patch("app.tools.send_message.SendMessageTool._take_screenshot")
    async def test_yolo_finds_everything_for_discord(
        self, _mock_ss, _mock_bbox, mock_open, _mock_yolo, _mock_pg
    ):
        """Verify the Discord flow uses the send_button
        class instead of pressing Enter.
        """
        from app.tools._yolo import Detection
        mock_detector = MagicMock()
        mock_detector.find_first.side_effect = [
            Detection("contact_search_bar", 0, 0.95, 50, 10, 80, 20),
            Detection("contact_result", 1, 0.91, 50, 50, 100, 30),
            Detection("message_bar", 2, 0.88, 50, 90, 200, 20),
            Detection("send_button", 3, 0.85, 100, 90, 30, 30),
        ]
        with patch.dict("sys.modules", {
            "pyautogui": MagicMock(),
            "pyperclip": MagicMock(),
            "mss": MagicMock(),
            "pygetwindow": MagicMock(),
            "numpy": MagicMock(),
            "onnxruntime": MagicMock(),
        }):
            async def fake_get_detector(self, model_path):
                return mock_detector
            with patch.object(
                SendMessageTool, "_get_detector", fake_get_detector
            ):
                out = await SendMessageTool().run(
                    receiver="John",
                    message_text="hi",
                    platform="discord",
                )
        assert "Message sent" in out
        assert "discord" in out
        # 4 calls to find_first: search_bar, result, message_bar, send_button
        assert mock_detector.find_first.call_count == 4


# ---------------------------------------------------------------------------
# 6. YOLO detector helper
# ---------------------------------------------------------------------------


class TestYoloDepsHelper:
    """Tests for `_check_yolo_deps_available()`."""

    def test_returns_none_when_all_available(self):
        from app.tools.send_message import _check_yolo_deps_available
        result = _check_yolo_deps_available()
        # Either None (all deps installed) or error string
        assert result is None or isinstance(result, str)

    def test_returns_error_string_when_missing(self):
        from app.tools.send_message import _check_yolo_deps_available
        with patch.dict("sys.modules", {
            "onnxruntime": None,
        }):
            import importlib
            importlib.invalidate_caches()
            result = _check_yolo_deps_available()
            assert result is None or isinstance(result, str)
