"""Unit tests for the Flask web dashboard."""

import json
import unittest
from unittest.mock import MagicMock, patch

from config import ENABLE_CAMERA_PREVIEW


class TestConfigRoutes(unittest.TestCase):
    """Tests for /api/config endpoints."""

    def setUp(self):
        # Reset runtime config before each test
        from runtime import config
        config.reset()

        from web.server import app
        self.app = app.test_client()

    def test_get_config_returns_snapshot(self):
        """GET /api/config should return current config snapshot."""
        response = self.app.get("/api/config")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("SWIPE_THRESHOLD", data)
        self.assertIn("SWIPE_BUFFER_SIZE", data)

    def test_update_config_modifies_values(self):
        """POST /api/config should update config values."""
        response = self.app.post(
            "/api/config",
            data=json.dumps({"SWIPE_THRESHOLD": 0.1}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertAlmostEqual(data["SWIPE_THRESHOLD"], 0.1)

    def test_update_config_ignores_invalid_keys(self):
        """POST /api/config should ignore non-mutable keys."""
        response = self.app.post(
            "/api/config",
            data=json.dumps({"INVALID_KEY": "value"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertNotIn("INVALID_KEY", data)

    def test_update_config_persists(self):
        """Config updates should persist across requests."""
        self.app.post(
            "/api/config",
            data=json.dumps({"SWIPE_THRESHOLD": 0.15}),
            content_type="application/json"
        )

        response = self.app.get("/api/config")
        data = json.loads(response.data)
        self.assertAlmostEqual(data["SWIPE_THRESHOLD"], 0.15)


class TestStateStream(unittest.TestCase):
    """Tests for the SSE state stream endpoint."""

    def setUp(self):
        from runtime import config
        config.reset()

        from web.server import app
        self.app = app.test_client()

    def test_state_stream_returns_event_stream(self):
        """GET /api/state/stream should return text/event-stream."""
        # Note: Testing SSE streams fully requires more setup
        # This verifies the endpoint exists and returns correct content type
        from runtime import state
        state.publish({"test": True})

        response = self.app.get("/api/state/stream")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.content_type)


class TestVideoFeed(unittest.TestCase):
    """Tests for the MJPEG video feed endpoint."""

    def setUp(self):
        from runtime import config
        config.reset()

        from web.server import app
        self.app = app.test_client()

    @patch("web.server.ENABLE_CAMERA_PREVIEW", True)
    def test_video_feed_enabled(self):
        """GET /video_feed should return multipart stream when enabled."""
        import numpy as np
        from runtime import frames

        # Put a test frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frames.put(frame)

        response = self.app.get("/video_feed")
        self.assertEqual(response.status_code, 200)
        self.assertIn("multipart/x-mixed-replace", response.content_type)

    @patch("web.server.ENABLE_CAMERA_PREVIEW", False)
    def test_video_feed_disabled(self):
        """GET /video_feed should return 403 when disabled."""
        response = self.app.get("/video_feed")
        self.assertEqual(response.status_code, 403)


class TestIndexRoute(unittest.TestCase):
    """Tests for the main index route."""

    def setUp(self):
        from runtime import config
        config.reset()

        from web.server import app
        self.app = app.test_client()

    def test_index_returns_200(self):
        """GET / should return 200."""
        response = self.app.get("/")
        self.assertEqual(response.status_code, 200)

    def test_index_returns_html(self):
        """GET / should return HTML content."""
        response = self.app.get("/")
        self.assertIn("text/html", response.content_type)


class TestRemoteAction(unittest.TestCase):
    """Tests for the /api/action remote control endpoint."""

    def setUp(self):
        from runtime import config
        config.reset()

        from web.server import app
        self.app = app.test_client()

    @patch("web.server.next_slide")
    def test_action_next(self, mock_next):
        """POST /api/action with 'next' should call next_slide."""
        response = self.app.post(
            "/api/action",
            data=json.dumps({"action": "next"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["action"], "next")
        mock_next.assert_called_once()

    @patch("web.server.prev_slide")
    def test_action_prev(self, mock_prev):
        """POST /api/action with 'prev' should call prev_slide."""
        response = self.app.post(
            "/api/action",
            data=json.dumps({"action": "prev"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        mock_prev.assert_called_once()

    @patch("web.server.pause_slide")
    def test_action_pause(self, mock_pause):
        """POST /api/action with 'pause' should call pause_slide."""
        response = self.app.post(
            "/api/action",
            data=json.dumps({"action": "pause"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        mock_pause.assert_called_once()

    @patch("web.server.first_slide")
    def test_action_first(self, mock_first):
        """POST /api/action with 'first' should call first_slide."""
        response = self.app.post(
            "/api/action",
            data=json.dumps({"action": "first"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        mock_first.assert_called_once()

    @patch("web.server.last_slide")
    def test_action_last(self, mock_last):
        """POST /api/action with 'last' should call last_slide."""
        response = self.app.post(
            "/api/action",
            data=json.dumps({"action": "last"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        mock_last.assert_called_once()

    def test_action_unknown_returns_400(self):
        """POST /api/action with unknown action should return 400."""
        response = self.app.post(
            "/api/action",
            data=json.dumps({"action": "unknown"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn("error", data)

    def test_action_empty_body_returns_400(self):
        """POST /api/action with empty body should return 400."""
        response = self.app.post(
            "/api/action",
            data=json.dumps({}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)

    @patch("web.server.start_presentation")
    def test_action_start(self, mock_start):
        """POST /api/action with 'start' should call start_presentation."""
        response = self.app.post(
            "/api/action",
            data=json.dumps({"action": "start"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        mock_start.assert_called_once()

    @patch("web.server.exit_presentation")
    def test_action_exit(self, mock_exit):
        """POST /api/action with 'exit' should call exit_presentation."""
        response = self.app.post(
            "/api/action",
            data=json.dumps({"action": "exit"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        mock_exit.assert_called_once()


class TestStatusEndpoint(unittest.TestCase):
    """Tests for the system status endpoint."""

    def setUp(self):
        from runtime import config
        config.reset()

        from web.server import app
        self.app = app.test_client()

    def test_get_status(self):
        """GET /api/status should return system status."""
        response = self.app.get("/api/status")
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertEqual(data["status"], "running")
        self.assertIn("uptime", data)
        self.assertIn("hand_detected", data)


class TestHealthEndpoint(unittest.TestCase):
    """Tests for the health check endpoint."""

    def setUp(self):
        from runtime import config
        config.reset()

        from web.server import app
        self.app = app.test_client()

    def test_get_health(self):
        """GET /api/health should return health status."""
        response = self.app.get("/api/health")
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertIn("status", data)
        self.assertIn("camera", data)
        self.assertIn("uptime", data)
        self.assertIn(data["status"], ["healthy", "degraded"])


if __name__ == "__main__":
    unittest.main()
