"""Unit tests for keyboard trigger logic."""

import unittest
from unittest.mock import MagicMock, patch

from config import KEY_NEXT_SLIDE, KEY_PAUSE, KEY_PREV_SLIDE


class TestTriggerKey(unittest.TestCase):
    """Tests for the _trigger_key function."""

    @patch("trigger.shutil.which", return_value=None)
    @patch("trigger.pyautogui.press")
    @patch("trigger._get_active_window_title", return_value="")
    def test_uses_default_key_when_no_app_match(self, mock_title, mock_press, mock_which):
        """Should use default key when no app binding matches."""
        from trigger import _trigger_key

        _trigger_key("next", KEY_NEXT_SLIDE)

        mock_press.assert_called_once_with("right")

    @patch("trigger.shutil.which", return_value=None)
    @patch("trigger.pyautogui.press")
    @patch("trigger._get_active_window_title", return_value="")
    def test_prev_slide_uses_left_key(self, mock_title, mock_press, mock_which):
        """prev_slide should send the left arrow key."""
        from trigger import prev_slide

        prev_slide()

        mock_press.assert_called_once_with("left")

    @patch("trigger.shutil.which", return_value=None)
    @patch("trigger.pyautogui.press")
    @patch("trigger._get_active_window_title", return_value="")
    def test_next_slide_uses_right_key(self, mock_title, mock_press, mock_which):
        """next_slide should send the right arrow key."""
        from trigger import next_slide

        next_slide()

        mock_press.assert_called_once_with("right")

    @patch("trigger.shutil.which", return_value=None)
    @patch("trigger.pyautogui.press")
    @patch("trigger._get_active_window_title", return_value="")
    def test_pause_slide_uses_b_key(self, mock_title, mock_press, mock_which):
        """pause_slide should send the 'b' key."""
        from trigger import pause_slide

        pause_slide()

        mock_press.assert_called_once_with("b")

    @patch("trigger.shutil.which", return_value="/usr/bin/ydotool")
    @patch("trigger.subprocess.run")
    @patch("trigger._get_active_window_title", return_value="")
    def test_ydotool_tried_first(self, mock_title, mock_run, mock_which):
        """Should try ydotool before falling back to pyautogui."""
        from trigger import next_slide

        mock_run.return_value = MagicMock(returncode=0)
        next_slide()

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args[0], "ydotool")
        self.assertEqual(call_args[1], "key")

    @patch("trigger.shutil.which", return_value="/usr/bin/ydotool")
    @patch("trigger.subprocess.run")
    @patch("trigger.pyautogui.press")
    @patch("trigger._get_active_window_title", return_value="")
    def test_fallback_to_pyautogui_on_ydotool_failure(self, mock_title, mock_press, mock_run, mock_which):
        """Should fall back to pyautogui when ydotool fails."""
        from trigger import next_slide

        mock_run.return_value = MagicMock(returncode=1)
        next_slide()

        mock_press.assert_called_once_with("right")

    @patch("trigger.shutil.which", return_value="/usr/bin/ydotool")
    @patch("trigger.subprocess.run")
    @patch("trigger._get_active_window_title", return_value="")
    def test_ydotool_key_format(self, mock_title, mock_run, mock_which):
        """ydotool should receive KEY_ prefixed key names."""
        from trigger import next_slide

        mock_run.return_value = MagicMock(returncode=0)
        next_slide()

        call_args = mock_run.call_args[0][0]
        # Should be KEY_RIGHT for right arrow
        self.assertIn("KEY_RIGHT:1", call_args)
        self.assertIn("KEY_RIGHT:0", call_args)


class TestGetActiveWindowTitle(unittest.TestCase):
    """Tests for _get_active_window_title function."""

    @patch("trigger.shutil.which", return_value=None)
    def test_returns_empty_when_no_tools(self, mock_which):
        """Should return empty string when no window tools available."""
        from trigger import _get_active_window_title

        result = _get_active_window_title()

        self.assertEqual(result, "")

    @patch("trigger.subprocess.run")
    @patch("trigger.shutil.which")
    def test_xdotool_fallback(self, mock_which, mock_run):
        """Should use xdotool when hyprctl is not available."""
        from trigger import _get_active_window_title

        # shutil.which returns None for hyprctl, then path for xdotool
        mock_which.side_effect = lambda cmd: None if cmd == "hyprctl" else "/usr/bin/xdotool"
        mock_run.side_effect = [
            MagicMock(stdout="12345"),  # getactivewindow
            MagicMock(stdout="My Presentation"),  # getwindowname
        ]

        result = _get_active_window_title()

        self.assertEqual(result, "My Presentation")


class TestPerAppBindings(unittest.TestCase):
    """Tests for per-app key binding overrides."""

    @patch("trigger.shutil.which", return_value=None)
    @patch("trigger.pyautogui.press")
    @patch("trigger._get_active_window_title", return_value="google-chrome")
    def test_per_app_binding_overrides_default(self, mock_title, mock_press, mock_which):
        """Should use per-app key binding when window title matches."""
        from trigger import _trigger_key

        with patch("trigger.APP_KEY_BINDINGS", {"google-chrome": {"next": "n"}}):
            _trigger_key("next", KEY_NEXT_SLIDE)

        mock_press.assert_called_once_with("n")

    @patch("trigger.shutil.which", return_value=None)
    @patch("trigger.pyautogui.press")
    @patch("trigger._get_active_window_title", return_value="unknown-app")
    def test_no_match_uses_default(self, mock_title, mock_press, mock_which):
        """Should use default key when no app binding matches."""
        from trigger import _trigger_key

        with patch("trigger.APP_KEY_BINDINGS", {"google-chrome": {"next": "n"}}):
            _trigger_key("next", KEY_NEXT_SLIDE)

        mock_press.assert_called_once_with("right")


if __name__ == "__main__":
    unittest.main()
