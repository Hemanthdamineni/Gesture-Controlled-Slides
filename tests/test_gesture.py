"""Unit tests for gesture recognition logic."""

import time
import unittest
from collections import namedtuple

from gesture import GestureController
from runtime import config

Landmark = namedtuple("Landmark", ["x", "y"])

class TestGestureController(unittest.TestCase):
    def setUp(self):
        # We start the controller but don't call start() so no camera thread
        self.controller = GestureController()
        # Ensure we have clean default configs
        config.reset()

    def test_swipe_right(self):
        # fast swipe right (x increases)
        landmarks = [Landmark(x=i * 0.05, y=0.5) for i in range(10)]
        for lm in landmarks:
            # We must pass 21 landmarks for hand, only wrist [0], pip and tips are used.
            # 0=wrist, tips=8, 12, 16, 20. pips=6, 10, 14, 18.
            # Uncurled fingers: tip.y < pip.y
            full_lms = [Landmark(0, 0)] * 21
            full_lms[0] = lm
            for tip, pip in zip([8, 12, 16, 20], [6, 10, 14, 18]):
                full_lms[tip] = Landmark(lm.x, 0.2)
                full_lms[pip] = Landmark(lm.x, 0.5)
            
            res = self.controller._process_landmarks(full_lms, fire_actions=False)
            if res.get("action") == "next":
                break
        
        self.assertEqual(res.get("action"), "next")

    def test_swipe_left(self):
        self.controller._last_gesture_time = 0
        # fast swipe left (x decreases)
        landmarks = [Landmark(x=1.0 - (i * 0.05), y=0.5) for i in range(10)]
        for lm in landmarks:
            full_lms = [Landmark(0, 0)] * 21
            full_lms[0] = lm
            for tip, pip in zip([8, 12, 16, 20], [6, 10, 14, 18]):
                full_lms[tip] = Landmark(lm.x, 0.2)
                full_lms[pip] = Landmark(lm.x, 0.5)
            
            res = self.controller._process_landmarks(full_lms, fire_actions=False)
            if res.get("action") == "prev":
                break
        
        self.assertEqual(res.get("action"), "prev")

    def test_fist(self):
        self.controller._last_gesture_time = 0
        res = None
        for _ in range(config.get("FIST_FRAMES_REQUIRED", 3) + 1):
            full_lms = [Landmark(0, 0)] * 21
            full_lms[0] = Landmark(0.5, 0.5)
            # Curled fingers: tip.y > pip.y
            for tip, pip in zip([8, 12, 16, 20], [6, 10, 14, 18]):
                full_lms[tip] = Landmark(0.5, 0.8)
                full_lms[pip] = Landmark(0.5, 0.5)
            
            res = self.controller._process_landmarks(full_lms, fire_actions=False)
            if res.get("action") == "pause":
                break
        
        self.assertEqual(res.get("action"), "pause")


if __name__ == "__main__":
    unittest.main()
