"""Unit tests for gesture-to-action remapping."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gesture_map import (
    DEFAULT_GESTURE_MAP,
    VALID_ACTIONS,
    VALID_GESTURES,
    get_action_for_gesture,
    load_gesture_map,
    save_gesture_map,
    validate_gesture_map,
)


class TestGestureMap(unittest.TestCase):
    """Tests for the gesture mapping system."""

    def setUp(self):
        # Use a temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        # Patch the GESTURE_MAP_FILE in the module
        import gesture_map
        self.original_file = gesture_map.GESTURE_MAP_FILE
        gesture_map.GESTURE_MAP_FILE = self.temp_path / "gesture_map.json"

    def tearDown(self):
        # Restore original file path
        import gesture_map
        gesture_map.GESTURE_MAP_FILE = self.original_file
        # Clean up temp directory
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_default_gesture_map(self):
        """Default gesture map should have all valid gestures."""
        for gesture in VALID_GESTURES:
            self.assertIn(gesture, DEFAULT_GESTURE_MAP)
            self.assertIn(DEFAULT_GESTURE_MAP[gesture], VALID_ACTIONS)

    def test_load_gesture_map_returns_default_when_no_file(self):
        """load_gesture_map should return default when no file exists."""
        result = load_gesture_map()
        self.assertEqual(result, DEFAULT_GESTURE_MAP)

    def test_save_and_load_gesture_map(self):
        """save_gesture_map should persist, load_gesture_map should restore."""
        custom_map = {
            "swipe_right": "prev",
            "swipe_left": "next",
            "fist": "pause",
            "double_fist": "last",
            "palm_hold": "first",
        }
        save_gesture_map(custom_map)
        loaded = load_gesture_map()
        self.assertEqual(loaded, custom_map)

    def test_validate_gesture_map_removes_invalid_entries(self):
        """validate_gesture_map should remove invalid gestures and actions."""
        invalid_map = {
            "swipe_right": "next",
            "invalid_gesture": "prev",
            "fist": "invalid_action",
        }
        result = validate_gesture_map(invalid_map)
        self.assertNotIn("invalid_gesture", result)
        self.assertNotIn("invalid_action", result.values())
        self.assertEqual(result["swipe_right"], "next")

    def test_validate_gesture_map_fills_missing_gestures(self):
        """validate_gesture_map should add defaults for missing gestures."""
        partial_map = {"swipe_right": "next"}
        result = validate_gesture_map(partial_map)
        for gesture in VALID_GESTURES:
            self.assertIn(gesture, result)

    def test_get_action_for_gesture(self):
        """get_action_for_gesture should return the mapped action."""
        custom_map = {"swipe_right": "pause"}
        save_gesture_map(custom_map)
        result = get_action_for_gesture("swipe_right")
        self.assertEqual(result, "pause")

    def test_get_action_for_gesture_returns_none_for_unknown(self):
        """get_action_for_gesture should return None for unknown gesture."""
        result = get_action_for_gesture("unknown_gesture")
        self.assertIsNone(result)


class TestGestureMapEndpoints(unittest.TestCase):
    """Tests for the gesture map API endpoints."""

    def setUp(self):
        from runtime import config
        config.reset()

        from web.server import app
        self.app = app.test_client()

    def test_get_gesture_map_returns_mapping(self):
        """GET /api/gestures should return current gesture map."""
        response = self.app.get("/api/gestures")
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertIn("gesture_map", data)
        self.assertIn("valid_gestures", data)
        self.assertIn("valid_actions", data)

    def test_update_gesture_map(self):
        """POST /api/gestures should update the gesture map."""
        new_map = {
            "gesture_map": {
                "swipe_right": "prev",
                "swipe_left": "next",
                "fist": "pause",
                "double_fist": "first",
                "palm_hold": "last",
            }
        }
        response = self.app.post(
            "/api/gestures",
            data=json.dumps(new_map),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "ok")

        # Verify the update persisted
        response = self.app.get("/api/gestures")
        data = json.loads(response.data)
        self.assertEqual(data["gesture_map"]["swipe_right"], "prev")

    def test_update_gesture_map_with_invalid_data(self):
        """POST /api/gestures with invalid data should handle gracefully."""
        invalid_map = {
            "gesture_map": {
                "invalid_gesture": "invalid_action",
            }
        }
        response = self.app.post(
            "/api/gestures",
            data=json.dumps(invalid_map),
            content_type="application/json"
        )

        # Should succeed but with validated (cleaned) data
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
