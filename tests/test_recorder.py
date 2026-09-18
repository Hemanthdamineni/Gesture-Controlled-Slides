"""Unit tests for gesture recording and playback."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from recorder import (
    RECORDINGS_DIR,
    delete_recording,
    get_recording_names,
    is_recording,
    load_recording,
    record_event,
    save_recording,
    start_recording,
    stop_recording,
)


class TestRecorder(unittest.TestCase):
    """Tests for the gesture recorder."""

    def setUp(self):
        # Use a temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        # Patch the RECORDINGS_DIR in the module
        import recorder
        self.original_dir = recorder.RECORDINGS_DIR
        recorder.RECORDINGS_DIR = self.temp_path

    def tearDown(self):
        # Restore original directory
        import recorder
        recorder.RECORDINGS_DIR = self.original_dir
        # Clean up temp directory
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_start_and_stop_recording(self):
        """start_recording should activate, stop_recording should deactivate."""
        start_recording()
        self.assertTrue(is_recording())
        stop_recording()
        self.assertFalse(is_recording())

    def test_record_event_while_recording(self):
        """record_event should capture events while recording."""
        start_recording()
        record_event("next")
        record_event("prev")
        events = stop_recording()

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["action"], "next")
        self.assertEqual(events[1]["action"], "prev")

    def test_record_event_while_not_recording(self):
        """record_event should not capture events when not recording."""
        record_event("next")
        self.assertFalse(is_recording())

    def test_save_and_load_recording(self):
        """save_recording should persist, load_recording should restore."""
        events = [
            {"time": 0.1, "action": "next"},
            {"time": 0.5, "action": "prev"},
        ]
        save_recording("test_recording", events)

        loaded = load_recording("test_recording")
        self.assertEqual(loaded, events)

    def test_get_recording_names(self):
        """get_recording_names should return saved recording names."""
        save_recording("recording1", [])
        save_recording("recording2", [])

        names = get_recording_names()
        self.assertIn("recording1", names)
        self.assertIn("recording2", names)

    def test_delete_recording(self):
        """delete_recording should remove a saved recording."""
        save_recording("to_delete", [])
        self.assertTrue(delete_recording("to_delete"))
        self.assertFalse(delete_recording("to_delete"))  # Already deleted

    def test_load_nonexistent_recording(self):
        """Loading a nonexistent recording should return empty list."""
        result = load_recording("nonexistent")
        self.assertEqual(result, [])


class TestRecordingEndpoints(unittest.TestCase):
    """Tests for the recording API endpoints."""

    def setUp(self):
        from runtime import config
        config.reset()

        from web.server import app
        self.app = app.test_client()

    def test_get_recordings(self):
        """GET /api/recordings should return list of recordings."""
        response = self.app.get("/api/recordings")
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertIn("recordings", data)
        self.assertIsInstance(data["recordings"], list)

    def test_start_recording(self):
        """POST /api/recordings with 'start' should start recording."""
        response = self.app.post(
            "/api/recordings",
            data=json.dumps({"action": "start"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["recording"])

    def test_stop_recording(self):
        """POST /api/recordings with 'stop' should stop recording."""
        # Start recording first
        self.app.post(
            "/api/recordings",
            data=json.dumps({"action": "start"}),
            content_type="application/json"
        )

        response = self.app.post(
            "/api/recordings",
            data=json.dumps({"action": "stop"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertFalse(data["recording"])
        self.assertIn("events", data)

    def test_save_recording(self):
        """POST /api/recordings/<name> should save a recording."""
        events = [{"time": 0.1, "action": "next"}]
        response = self.app.post(
            "/api/recordings/test_save",
            data=json.dumps({"events": events}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)

        # Verify it was saved
        response = self.app.get("/api/recordings/test_save")
        data = json.loads(response.data)
        self.assertEqual(data["events"], events)

    def test_delete_recording_endpoint(self):
        """DELETE /api/recordings/<name> should delete a recording."""
        # Create a recording first
        self.app.post(
            "/api/recordings/to_delete",
            data=json.dumps({"events": []}),
            content_type="application/json"
        )

        response = self.app.delete("/api/recordings/to_delete")
        self.assertEqual(response.status_code, 200)

        # Verify it's gone
        response = self.app.get("/api/recordings/to_delete")
        data = json.loads(response.data)
        self.assertEqual(data["events"], [])


if __name__ == "__main__":
    unittest.main()
