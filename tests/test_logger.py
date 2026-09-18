"""Unit tests for session logging."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from logger import LOG_DIR, log_gesture, get_recent_logs, get_log_dates


class TestLogger(unittest.TestCase):
    """Tests for the gesture logger."""

    def setUp(self):
        # Use a temporary directory for test logs
        self.original_log_dir = LOG_DIR
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        # Patch the LOG_DIR in the logger module
        import logger
        logger.LOG_DIR = self.temp_path
        logger.LOG_DIR.mkdir(exist_ok=True)

    def tearDown(self):
        # Restore original LOG_DIR
        import logger
        logger.LOG_DIR = self.original_log_dir
        # Clean up temp directory
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_log_gesture_creates_entry(self):
        """log_gesture should create a JSONL entry."""
        log_gesture("next")

        log_files = list(self.temp_path.glob("gestures-*.jsonl"))
        self.assertEqual(len(log_files), 1)

        with open(log_files[0], "r") as f:
            entry = json.loads(f.readline())

        self.assertEqual(entry["action"], "next")
        self.assertIn("timestamp", entry)

    def test_log_gesture_with_details(self):
        """log_gesture should include optional details."""
        log_gesture("swipe", {"direction": "right", "delta": 0.05})

        log_files = list(self.temp_path.glob("gestures-*.jsonl"))
        with open(log_files[0], "r") as f:
            entry = json.loads(f.readline())

        self.assertEqual(entry["action"], "swipe")
        self.assertEqual(entry["details"]["direction"], "right")

    def test_get_recent_logs(self):
        """get_recent_logs should return entries in reverse chronological order."""
        log_gesture("next")
        log_gesture("prev")
        log_gesture("pause")

        logs = get_recent_logs(limit=10)
        self.assertEqual(len(logs), 3)
        # Most recent first
        self.assertEqual(logs[-1]["action"], "pause")
        self.assertEqual(logs[0]["action"], "next")

    def test_get_recent_logs_with_limit(self):
        """get_recent_logs should respect the limit parameter."""
        for _ in range(10):
            log_gesture("next")

        logs = get_recent_logs(limit=5)
        self.assertEqual(len(logs), 5)

    def test_get_log_dates(self):
        """get_log_dates should return dates with log files."""
        log_gesture("next")

        dates = get_log_dates()
        self.assertGreaterEqual(len(dates), 1)

    def test_log_rotation_removes_old_files(self):
        """Old log files should be removed during rotation."""
        import time

        # Create a log file with an old timestamp
        old_file = self.temp_path / "gestures-2020-01-01.jsonl"
        old_file.write_text('{"action": "test"}\n')

        # Make sure it's old enough
        old_time = time.time() - (10 * 86400)  # 10 days ago
        os.utime(old_file, (old_time, old_time))

        # Trigger rotation by logging
        log_gesture("next")

        # Old file should be removed
        self.assertFalse(old_file.exists())


class TestLogEndpoints(unittest.TestCase):
    """Tests for the log API endpoints."""

    def setUp(self):
        from runtime import config
        config.reset()

        from web.server import app
        self.app = app.test_client()

    def test_get_logs_returns_json(self):
        """GET /api/logs should return JSON with logs array."""
        response = self.app.get("/api/logs")
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertIn("logs", data)
        self.assertIsInstance(data["logs"], list)

    def test_get_logs_with_limit(self):
        """GET /api/logs?limit=N should respect limit parameter."""
        response = self.app.get("/api/logs?limit=5")
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertLessEqual(len(data["logs"]), 5)

    def test_get_log_dates_returns_json(self):
        """GET /api/logs/dates should return JSON with dates array."""
        response = self.app.get("/api/logs/dates")
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertIn("dates", data)
        self.assertIsInstance(data["dates"], list)


if __name__ == "__main__":
    unittest.main()
