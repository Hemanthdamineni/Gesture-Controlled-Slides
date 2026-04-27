"""Shared runtime state: mutable config, gesture state store, SSE publisher, frame buffer."""

import json
import queue
import threading
import time
from collections import deque

from config import (
    FIST_FRAMES_REQUIRED,
    GESTURE_COOLDOWN_SEC,
    MIN_DETECTION_CONFIDENCE,
    MIN_TRACKING_CONFIDENCE,
    SWIPE_BUFFER_SIZE,
    SWIPE_MIN_SAMPLES,
    SWIPE_THRESHOLD,
    SWIPE_WINDOW_SEC,
)

# ---------------------------------------------------------------------------
# RuntimeConfig — mutable overlay on top of config.py constants
# ---------------------------------------------------------------------------

_DEFAULTS: dict = {
    "SWIPE_THRESHOLD": SWIPE_THRESHOLD,
    "SWIPE_WINDOW_SEC": SWIPE_WINDOW_SEC,
    "SWIPE_MIN_SAMPLES": SWIPE_MIN_SAMPLES,
    "SWIPE_BUFFER_SIZE": SWIPE_BUFFER_SIZE,
    "GESTURE_COOLDOWN_SEC": GESTURE_COOLDOWN_SEC,
    "FIST_FRAMES_REQUIRED": FIST_FRAMES_REQUIRED,
    "MIN_DETECTION_CONFIDENCE": MIN_DETECTION_CONFIDENCE,
    "MIN_TRACKING_CONFIDENCE": MIN_TRACKING_CONFIDENCE,
}

_FLOAT_KEYS = {
    "SWIPE_THRESHOLD",
    "SWIPE_WINDOW_SEC",
    "GESTURE_COOLDOWN_SEC",
    "MIN_DETECTION_CONFIDENCE",
    "MIN_TRACKING_CONFIDENCE",
}
_INT_KEYS = {"SWIPE_MIN_SAMPLES", "SWIPE_BUFFER_SIZE", "FIST_FRAMES_REQUIRED"}
_MUTABLE_KEYS = _FLOAT_KEYS | _INT_KEYS


class RuntimeConfig:
    """Thread-safe mutable overlay on top of config.py constants.

    Gesture processing reads values through :meth:`get` so that live edits
    from the web dashboard take effect on the next frame without a restart.
    """

    def __init__(self) -> None:
        self._overrides: dict = {}
        self._lock = threading.RLock()

    def get(self, key: str, default):
        """Return the runtime override for *key*, falling back to *default*."""
        with self._lock:
            return self._overrides.get(key, default)

    def update(self, updates: dict) -> None:
        """Apply validated updates from the web API."""
        with self._lock:
            for key, value in updates.items():
                if key not in _MUTABLE_KEYS:
                    continue
                try:
                    if key in _FLOAT_KEYS:
                        self._overrides[key] = float(value)
                    elif key in _INT_KEYS:
                        self._overrides[key] = int(value)
                except (TypeError, ValueError):
                    pass

    def snapshot(self) -> dict:
        """Return a merged dict of defaults + current overrides."""
        with self._lock:
            result = dict(_DEFAULTS)
            result.update(self._overrides)
            return result

    def reset(self) -> None:
        """Clear all overrides, restoring config.py defaults."""
        with self._lock:
            self._overrides.clear()


# ---------------------------------------------------------------------------
# StateStore — gesture state + SSE fan-out publisher
# ---------------------------------------------------------------------------


class StateStore:
    """Thread-safe gesture state store with SSE subscriber support.

    The gesture controller calls :meth:`publish` after each frame.
    SSE clients subscribe via :meth:`subscribe` and receive JSON payloads.
    """

    def __init__(self) -> None:
        self._state: dict = {}
        self._state_lock = threading.Lock()
        self._subscribers: list[queue.Queue] = []
        self._subscribers_lock = threading.Lock()
        self._history: deque = deque(maxlen=150)
        self._start_time = time.time()

    # --- producer side ---

    def publish(self, state: dict) -> None:
        """Push a new gesture state snapshot and fan-out to all SSE clients."""
        with self._state_lock:
            self._state = state
            action = state.get("action")
            if action:
                self._history.appendleft(
                    {
                        "action": action,
                        "ts": time.time(),
                    }
                )

        envelope = {
            "type": "state",
            "data": state,
            "uptime": time.time() - self._start_time,
        }
        payload = json.dumps(envelope)

        dead = []
        with self._subscribers_lock:
            for q in self._subscribers:
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self._subscribers.remove(q)

    # --- consumer side ---

    def subscribe(self) -> queue.Queue:
        """Return a new queue that receives all future state payloads."""
        q: queue.Queue = queue.Queue(maxsize=64)
        with self._subscribers_lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        """Remove a subscriber queue."""
        with self._subscribers_lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def get_state(self) -> dict:
        with self._state_lock:
            return dict(self._state)

    def get_history(self) -> list:
        with self._state_lock:
            return list(self._history)

    def uptime(self) -> float:
        return time.time() - self._start_time


# ---------------------------------------------------------------------------
# FrameBuffer — latest camera frame for MJPEG preview
# ---------------------------------------------------------------------------


class FrameBuffer:
    """Thread-safe holder for the most recent camera frame."""

    def __init__(self) -> None:
        self._frame = None
        self._lock = threading.Lock()

    def put(self, frame) -> None:
        with self._lock:
            self._frame = frame.copy() if frame is not None else None

    def get(self):
        with self._lock:
            return self._frame


# ---------------------------------------------------------------------------
# Module-level singletons shared across all threads
# ---------------------------------------------------------------------------

config = RuntimeConfig()
state = StateStore()
frames = FrameBuffer()
