"""Unit tests for latency monitoring."""

import json
import unittest

from runtime import StateStore


class TestLatencyStats(unittest.TestCase):
    """Tests for latency tracking in StateStore."""

    def setUp(self):
        self.store = StateStore()

    def test_record_latency(self):
        """record_latency should store latency measurements."""
        self.store.record_latency(50.0)
        self.store.record_latency(75.0)
        self.store.record_latency(100.0)

        stats = self.store.get_latency_stats()
        self.assertEqual(stats["count"], 3)
        self.assertAlmostEqual(stats["avg_ms"], 75.0)
        self.assertAlmostEqual(stats["min_ms"], 50.0)
        self.assertAlmostEqual(stats["max_ms"], 100.0)

    def test_latency_stats_empty(self):
        """get_latency_stats should return zeros when no data."""
        stats = self.store.get_latency_stats()
        self.assertEqual(stats["count"], 0)
        self.assertEqual(stats["avg_ms"], 0)

    def test_latency_recent_entries(self):
        """get_latency_stats should include recent entries."""
        for i in range(15):
            self.store.record_latency(float(i * 10))

        stats = self.store.get_latency_stats()
        self.assertEqual(stats["count"], 15)
        # Should have last 10 entries
        self.assertEqual(len(stats["recent"]), 10)


class TestLatencyEndpoint(unittest.TestCase):
    """Tests for the latency API endpoint."""

    def setUp(self):
        from runtime import config
        config.reset()

        from web.server import app
        self.app = app.test_client()

    def test_get_latency_stats(self):
        """GET /api/latency should return latency statistics."""
        response = self.app.get("/api/latency")
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertIn("count", data)
        self.assertIn("avg_ms", data)
        self.assertIn("min_ms", data)
        self.assertIn("max_ms", data)
        self.assertIn("recent", data)


if __name__ == "__main__":
    unittest.main()
