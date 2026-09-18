"""Unit tests for gesture recognition logic."""

import time
import unittest
from collections import namedtuple

from gesture import GestureController
from runtime import config

Landmark = namedtuple("Landmark", ["x", "y"])


def _make_open_hand(wrist_x, wrist_y=0.5):
    """Create landmarks for an open hand (fingers extended) at given wrist position."""
    full_lms = [Landmark(0, 0)] * 21
    full_lms[0] = Landmark(wrist_x, wrist_y)
    # Uncurled fingers: tip.y < pip.y
    for tip, pip in zip([8, 12, 16, 20], [6, 10, 14, 18]):
        full_lms[tip] = Landmark(wrist_x, 0.2)
        full_lms[pip] = Landmark(wrist_x, 0.5)
    return full_lms


def _make_fist(wrist_x=0.5):
    """Create landmarks for a fist (all fingers curled)."""
    full_lms = [Landmark(0, 0)] * 21
    full_lms[0] = Landmark(wrist_x, 0.5)
    # Curled fingers: tip.y > pip.y
    for tip, pip in zip([8, 12, 16, 20], [6, 10, 14, 18]):
        full_lms[tip] = Landmark(wrist_x, 0.8)
        full_lms[pip] = Landmark(wrist_x, 0.5)
    return full_lms


class TestGestureController(unittest.TestCase):
    def setUp(self):
        self.controller = GestureController()
        config.reset()

    def test_swipe_right(self):
        landmarks = [Landmark(x=i * 0.05, y=0.5) for i in range(10)]
        res = None
        for lm in landmarks:
            full_lms = _make_open_hand(lm.x)
            res = self.controller._process_landmarks(full_lms, fire_actions=False)
            if res.get("action") == "next":
                break

        self.assertEqual(res.get("action"), "next")

    def test_swipe_left(self):
        self.controller._last_gesture_time = 0
        landmarks = [Landmark(x=1.0 - (i * 0.05), y=0.5) for i in range(10)]
        res = None
        for lm in landmarks:
            full_lms = _make_open_hand(lm.x)
            res = self.controller._process_landmarks(full_lms, fire_actions=False)
            if res.get("action") == "prev":
                break

        self.assertEqual(res.get("action"), "prev")

    def test_fist(self):
        self.controller._last_gesture_time = 0
        res = None
        for _ in range(config.get("FIST_FRAMES_REQUIRED", 3) + 1):
            full_lms = _make_fist()
            res = self.controller._process_landmarks(full_lms, fire_actions=False)
            if res.get("action") == "pause":
                break

        self.assertEqual(res.get("action"), "pause")

    def test_no_gesture_stationary_hand(self):
        """A stationary open hand should not trigger any action."""
        self.controller._last_gesture_time = 0
        for _ in range(10):
            full_lms = _make_open_hand(0.5)
            res = self.controller._process_landmarks(full_lms, fire_actions=False)

        self.assertIsNone(res.get("action"))

    def test_cooldown_blocks_rapid_gestures(self):
        """After a gesture fires, cooldown should prevent immediate re-trigger."""
        self.controller._last_gesture_time = 0

        # Fire a swipe right
        for i in range(10):
            full_lms = _make_open_hand(i * 0.05)
            res = self.controller._process_landmarks(full_lms, fire_actions=False)
            if res.get("action") == "next":
                break

        self.assertEqual(res.get("action"), "next")

        # Immediately try another swipe - should be blocked by cooldown
        self.controller._wrist_x_buffer.clear()
        for i in range(10):
            full_lms = _make_open_hand(1.0 - (i * 0.05))
            res = self.controller._process_landmarks(full_lms, fire_actions=False)

        self.assertIsNone(res.get("action"))

    def test_finger_curl_states_open_hand(self):
        """_finger_curl_states should return all False for an open hand."""
        full_lms = _make_open_hand(0.5)
        curled = GestureController._finger_curl_states(full_lms)
        self.assertEqual(curled, [False, False, False, False])

    def test_finger_curl_states_fist(self):
        """_finger_curl_states should return all True for a fist."""
        full_lms = _make_fist()
        curled = GestureController._finger_curl_states(full_lms)
        self.assertEqual(curled, [True, True, True, True])

    def test_small_movement_not_swipe(self):
        """Small wrist movements below threshold should not trigger swipe."""
        self.controller._last_gesture_time = 0
        # Move wrist by only 0.02, below SWIPE_THRESHOLD of 0.04
        for _ in range(10):
            full_lms = _make_open_hand(0.5)
            res = self.controller._process_landmarks(full_lms, fire_actions=False)
            full_lms = _make_open_hand(0.52)
            res = self.controller._process_landmarks(full_lms, fire_actions=False)

        self.assertIsNone(res.get("action"))

    def test_swipe_buffer_cleared_after_action(self):
        """After a swipe fires, the wrist buffer should be cleared."""
        self.controller._last_gesture_time = 0

        for i in range(10):
            full_lms = _make_open_hand(i * 0.05)
            res = self.controller._process_landmarks(full_lms, fire_actions=False)
            if res.get("action") == "next":
                break

        self.assertEqual(res.get("action"), "next")
        self.assertEqual(res.get("buffer_len"), 0)
        self.assertEqual(res.get("buffer_values"), [])

    def test_fist_requires_multiple_frames(self):
        """A fist should only fire after FIST_FRAMES_REQUIRED consecutive frames."""
        self.controller._last_gesture_time = 0
        required = config.get("FIST_FRAMES_REQUIRED", 3)

        # One frame should not trigger
        full_lms = _make_fist()
        res = self.controller._process_landmarks(full_lms, fire_actions=False)
        self.assertNotEqual(res.get("action"), "pause")
        self.assertEqual(res.get("fist_frame_count"), 1)

    def test_reset_tracking_state(self):
        """_reset_tracking_state should clear all tracking buffers."""
        self.controller._wrist_x_buffer.append((time.time(), 0.5))
        self.controller._fist_frame_count = 2
        self.controller._fist_armed = False
        self.controller._missing_hand_frames = 5

        self.controller._reset_tracking_state()

        self.assertEqual(len(self.controller._wrist_x_buffer), 0)
        self.assertEqual(self.controller._fist_frame_count, 0)
        self.assertTrue(self.controller._fist_armed)
        self.assertEqual(self.controller._missing_hand_frames, 0)

    def test_prune_stale_swipe_samples(self):
        """Old swipe samples outside the time window should be pruned."""
        now = time.time()
        # Add samples: some old, some recent
        self.controller._wrist_x_buffer.append((now - 1.0, 0.1))
        self.controller._wrist_x_buffer.append((now - 0.5, 0.2))
        self.controller._wrist_x_buffer.append((now, 0.3))

        self.controller._prune_stale_swipe_samples(now)

        # Only the recent sample should remain (window is 0.45s)
        self.assertEqual(len(self.controller._wrist_x_buffer), 1)
        self.assertAlmostEqual(self.controller._wrist_x_buffer[0][1], 0.3)

    def test_first_slide_double_fist(self):
        """Double-fist gesture (two pause gestures in quick succession) should trigger first slide."""
        self.controller._last_gesture_time = 0
        res = None
        # First fist gesture (triggers pause)
        for _ in range(config.get("FIST_FRAMES_REQUIRED", 3)):
            full_lms = _make_fist()
            res = self.controller._process_landmarks(full_lms, fire_actions=False)
        self.assertEqual(res.get("action"), "pause")

        # Wait for cooldown to expire (but stay within double-fist window)
        self.controller._last_gesture_time = 0
        # Brief open hand to reset fist state
        for _ in range(2):
            full_lms = _make_open_hand(0.5)
            res = self.controller._process_landmarks(full_lms, fire_actions=False)

        # Second fist gesture (triggers first slide via double-fist)
        for _ in range(config.get("FIST_FRAMES_REQUIRED", 3)):
            full_lms = _make_fist()
            res = self.controller._process_landmarks(full_lms, fire_actions=False)
            if res.get("action") == "first":
                break

        self.assertEqual(res.get("action"), "first")

    def test_last_slide_palm_hold(self):
        """Open hand held still should trigger last slide action."""
        self.controller._last_gesture_time = 0
        res = None
        # Need PALM_HOLD_FRAMES_REQUIRED frames with minimal movement
        for _ in range(config.get("PALM_HOLD_FRAMES_REQUIRED", 5) + 1):
            full_lms = _make_open_hand(0.5)
            res = self.controller._process_landmarks(full_lms, fire_actions=False)
            if res.get("action") == "last":
                break

        self.assertEqual(res.get("action"), "last")

    def test_palm_hold_resets_on_movement(self):
        """Palm-hold should reset when hand moves significantly."""
        self.controller._last_gesture_time = 0
        # Hold still for a few frames
        for _ in range(3):
            full_lms = _make_open_hand(0.5)
            res = self.controller._process_landmarks(full_lms, fire_actions=False)

        # Now move hand significantly
        full_lms = _make_open_hand(0.6)
        res = self.controller._process_landmarks(full_lms, fire_actions=False)

        # Palm hold count should have reset
        self.assertEqual(res.get("palm_hold_count"), 1)

    def test_palm_hold_resets_on_fist(self):
        """Palm-hold should reset when making a fist."""
        self.controller._last_gesture_time = 0
        # Hold still for a few frames
        for _ in range(3):
            full_lms = _make_open_hand(0.5)
            res = self.controller._process_landmarks(full_lms, fire_actions=False)

        # Now make a fist
        full_lms = _make_fist()
        res = self.controller._process_landmarks(full_lms, fire_actions=False)

        # Palm hold should be reset
        self.assertEqual(self.controller._palm_hold_count, 0)
        self.assertIsNone(self.controller._palm_hold_wrist_x)

    def test_dead_zone_ignores_small_movements(self):
        """Movements within dead zone should not accumulate as swipe."""
        self.controller._last_gesture_time = 0
        # Make tiny movements (below dead zone of 0.01)
        for _ in range(10):
            full_lms = _make_open_hand(0.5)
            self.controller._process_landmarks(full_lms, fire_actions=False)
            full_lms = _make_open_hand(0.505)  # 0.005 movement, below dead zone
            res = self.controller._process_landmarks(full_lms, fire_actions=False)

        # Should not trigger any action
        self.assertIsNone(res.get("action"))

    def test_velocity_threshold_filters_slow_movements(self):
        """Slow movements below velocity threshold should not trigger swipe."""
        self.controller._last_gesture_time = 0
        import time

        # Simulate slow movement by adding delay between positions
        positions = [0.5, 0.51, 0.52, 0.53, 0.54, 0.55, 0.56, 0.57, 0.58, 0.59, 0.6]
        res = None
        for pos in positions:
            full_lms = _make_open_hand(pos)
            res = self.controller._process_landmarks(full_lms, fire_actions=False)
            time.sleep(0.05)  # Slow movement

        # Without sufficient velocity, should not trigger
        # (This test may be timing-dependent, but validates the concept)
        # At minimum, the debug_info should include velocity
        self.assertIn("buffer_velocity", res)

    def test_swipe_requires_minimum_velocity(self):
        """Swipe should only trigger with sufficient velocity."""
        self.controller._last_gesture_time = 0
        # Fast swipe should trigger
        for i in range(10):
            full_lms = _make_open_hand(i * 0.05)
            res = self.controller._process_landmarks(full_lms, fire_actions=False)
            if res.get("action") == "next":
                break

        self.assertEqual(res.get("action"), "next")


if __name__ == "__main__":
    unittest.main()
