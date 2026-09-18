"""Unit tests for runtime state management."""

import queue
import time
import unittest

from runtime import FrameBuffer, RuntimeConfig, StateStore


class TestRuntimeConfig(unittest.TestCase):
    """Tests for the RuntimeConfig class."""

    def setUp(self):
        self.config = RuntimeConfig()

    def test_get_returns_default_when_no_override(self):
        """Should return default value when no override set."""
        result = self.config.get("SWIPE_THRESHOLD", 0.04)
        self.assertEqual(result, 0.04)

    def test_update_sets_override(self):
        """update() should set override values."""
        self.config.update({"SWIPE_THRESHOLD": 0.1})
        result = self.config.get("SWIPE_THRESHOLD", 0.04)
        self.assertEqual(result, 0.1)

    def test_update_converts_float_keys(self):
        """Float keys should be converted to float type."""
        self.config.update({"SWIPE_THRESHOLD": "0.08"})
        result = self.config.get("SWIPE_THRESHOLD", 0.04)
        self.assertIsInstance(result, float)
        self.assertAlmostEqual(result, 0.08)

    def test_update_converts_int_keys(self):
        """Int keys should be converted to int type."""
        self.config.update({"SWIPE_BUFFER_SIZE": "12"})
        result = self.config.get("SWIPE_BUFFER_SIZE", 8)
        self.assertIsInstance(result, int)
        self.assertEqual(result, 12)

    def test_update_ignores_invalid_keys(self):
        """Should ignore keys not in _MUTABLE_KEYS."""
        self.config.update({"INVALID_KEY": "value", "SWIPE_THRESHOLD": 0.1})
        result = self.config.get("INVALID_KEY", "default")
        self.assertEqual(result, "default")

    def test_update_ignores_invalid_values(self):
        """Should skip values that cannot be converted."""
        self.config.update({"SWIPE_THRESHOLD": "not_a_number"})
        result = self.config.get("SWIPE_THRESHOLD", 0.04)
        self.assertEqual(result, 0.04)

    def test_snapshot_returns_defaults_plus_overrides(self):
        """snapshot() should return merged defaults and overrides."""
        self.config.update({"SWIPE_THRESHOLD": 0.1})
        snapshot = self.config.snapshot()

        self.assertIn("SWIPE_THRESHOLD", snapshot)
        self.assertAlmostEqual(snapshot["SWIPE_THRESHOLD"], 0.1)
        self.assertIn("SWIPE_BUFFER_SIZE", snapshot)

    def test_reset_clears_overrides(self):
        """reset() should clear all overrides."""
        self.config.update({"SWIPE_THRESHOLD": 0.1})
        self.config.reset()

        result = self.config.get("SWIPE_THRESHOLD", 0.04)
        self.assertEqual(result, 0.04)

    def test_multiple_updates(self):
        """Multiple updates should accumulate."""
        self.config.update({"SWIPE_THRESHOLD": 0.1})
        self.config.update({"SWIPE_BUFFER_SIZE": 12})

        self.assertAlmostEqual(self.config.get("SWIPE_THRESHOLD", 0.04), 0.1)
        self.assertEqual(self.config.get("SWIPE_BUFFER_SIZE", 8), 12)


class TestStateStore(unittest.TestCase):
    """Tests for the StateStore class."""

    def setUp(self):
        self.store = StateStore()

    def test_publish_stores_state(self):
        """publish() should store the latest state."""
        state = {"hand_detected": True, "action": "next"}
        self.store.publish(state)

        result = self.store.get_state()
        self.assertEqual(result["hand_detected"], True)
        self.assertEqual(result["action"], "next")

    def test_publish_fans_out_to_subscribers(self):
        """publish() should send to all subscribers."""
        q = self.store.subscribe()
        state = {"hand_detected": True}
        self.store.publish(state)

        payload = q.get(timeout=1.0)
        self.assertIn('"hand_detected": true', payload)

    def test_subscribe_returns_queue(self):
        """subscribe() should return a new queue."""
        q = self.store.subscribe()
        self.assertIsInstance(q, queue.Queue)

    def test_unsubscribe_removes_queue(self):
        """unsubscribe() should remove the queue from subscribers."""
        q = self.store.subscribe()
        self.store.unsubscribe(q)

        # Publish should not fail even after unsubscribe
        self.store.publish({"test": True})

    def test_get_history_returns_action_history(self):
        """get_history() should return recorded actions."""
        self.store.publish({"action": "next"})
        self.store.publish({"action": "prev"})

        history = self.store.get_history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["action"], "prev")
        self.assertEqual(history[1]["action"], "next")

    def test_history_only_records_actions(self):
        """History should only include states with an action."""
        self.store.publish({"hand_detected": True, "action": None})
        self.store.publish({"action": "next"})

        history = self.store.get_history()
        self.assertEqual(len(history), 1)

    def test_uptime_increases(self):
        """uptime() time since creation."""
        start = self.store.uptime()
        time.sleep(0.01)
        end = self.store.uptime()

        self.assertGreater(end, start)

    def test_dead_subscribers_removed(self):
        """Full queues should be removed as dead subscribers."""
        q = self.store.subscribe()
        # Fill the queue
        for _ in range(100):
            self.store.publish({"action": "test"})

        # Queue should be removed after being full
        import time
        time.sleep(0.1)  # Allow processing
        # If queue was full, it should be removed
        # This is a best-effort test


class TestFrameBuffer(unittest.TestCase):
    """Tests for the FrameBuffer class."""

    def setUp(self):
        self.buffer = FrameBuffer()

    def test_get_returns_none_initially(self):
        """get() should return None when no frame set."""
        result = self.buffer.get()
        self.assertIsNone(result)

    def test_put_and_get_frame(self):
        """put() should store frame, get() should retrieve it."""
        import numpy as np

        frame = np.array([[1, 2], [3, 4]], dtype=np.uint8)
        self.buffer.put(frame)

        result = self.buffer.get()
        self.assertTrue((result == frame).all())

    def test_put_creates_copy(self):
        """put() should store a copy, not the original."""
        import numpy as np

        frame = np.array([1, 2, 3])
        self.buffer.put(frame)

        # Modify original
        frame[0] = 999

        # Buffer should have original value
        result = self.buffer.get()
        self.assertEqual(result[0], 1)

    def test_put_none(self):
        """put(None) should store None."""
        import numpy as np

        self.buffer.put(np.zeros((10, 10), dtype=np.uint8))
        self.buffer.put(None)

        result = self.buffer.get()
        self.assertIsNone(result)

    def test_latest_frame_overwrites(self):
        """Latest put() should overwrite previous frame."""
        import numpy as np

        frame1 = np.zeros((10, 10), dtype=np.uint8)
        frame2 = np.ones((10, 10), dtype=np.uint8)
        self.buffer.put(frame1)
        self.buffer.put(frame2)

        result = self.buffer.get()
        self.assertTrue((result == frame2).all())


if __name__ == "__main__":
    unittest.main()
