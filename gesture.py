"""Camera capture and gesture recognition for slide control."""

import os
import re
import threading
import time
from collections import deque
from contextlib import contextmanager
from glob import glob

import cv2
import mediapipe as mp

from config import (
    CAMERA_PROBE_WARMUP_FRAMES,
    CAMERA_INDEX,
    CAMERA_READ_RETRY_SEC,
    FIST_FRAMES_REQUIRED,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    GESTURE_COOLDOWN_SEC,
    IDLE_SLEEP_SEC,
    MAX_HANDS,
    MIN_DETECTION_CONFIDENCE,
    MIN_TRACKING_CONFIDENCE,
    NO_HAND_RESET_FRAMES,
    SWIPE_BUFFER_SIZE,
    SWIPE_MIN_SAMPLES,
    SWIPE_THRESHOLD,
    SWIPE_WINDOW_SEC,
    TARGET_FPS,
    VISUALIZATION_ACCENT_ACTION,
    VISUALIZATION_ACCENT_NEXT,
    VISUALIZATION_ACCENT_PREV,
    VISUALIZATION_ACCENT_TRACK,
    VISUALIZATION_TEXT_COLOR,
    VISUALIZATION_WINDOW_NAME,
)
from trigger import next_slide, pause_slide, prev_slide


@contextmanager
def _suppress_stderr():
    """Temporarily silence native stderr noise while probing camera devices."""
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(2)
    try:
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(old_stderr, 2)
        os.close(old_stderr)
        os.close(devnull)


class GestureController:
    """Run MediaPipe hand tracking and translate gestures into slide actions."""

    def __init__(self, visualize=False):
        self.running = False
        self._stop_event = threading.Event()
        self._thread = None
        self._camera_index = None
        self._fist_armed = True
        self._missing_hand_frames = 0
        self._last_action = "-"
        self._visualize = visualize
        self._visualization_window_open = False
        self._wrist_x_buffer = deque(maxlen=SWIPE_BUFFER_SIZE)
        self._fist_frame_count = 0
        self._last_gesture_time = 0.0
        self._mp_draw = mp.solutions.drawing_utils
        self._mp_hands = mp.solutions.hands
        self._mp_styles = mp.solutions.drawing_styles

    def start(self):
        """Start the camera + detection thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self.running = True
        self._thread = threading.Thread(target=self._loop, name="gesture-controller", daemon=True)
        self._thread.start()
        print("[GestureController] Started")

    def stop(self):
        """Stop the camera + detection thread cleanly."""
        if self._thread is None:
            self.running = False
            return
        self._stop_event.set()
        self.running = False
        self._thread.join(timeout=3.0)
        self._thread = None
        print("[GestureController] Stopped")

    def pause(self):
        """Pause gesture detection."""
        self.running = False
        print("[GestureController] Paused")

    def resume(self):
        """Resume gesture detection."""
        self.running = True
        self._wrist_x_buffer.clear()
        self._fist_frame_count = 0
        self._fist_armed = True
        self._missing_hand_frames = 0
        print("[GestureController] Resumed")

    def _reset_tracking_state(self):
        """Clear swipe/fist state when the hand is lost."""
        self._wrist_x_buffer.clear()
        self._fist_frame_count = 0
        self._fist_armed = True
        self._missing_hand_frames = 0

    def _prune_stale_swipe_samples(self, now):
        """Keep only recent wrist samples within the swipe time window."""
        while self._wrist_x_buffer and (now - self._wrist_x_buffer[0][0]) > SWIPE_WINDOW_SEC:
            self._wrist_x_buffer.popleft()

    def _swipe_debug_state(self, now):
        """Return swipe debug values derived from the active time window."""
        self._prune_stale_swipe_samples(now)
        buffer_values = [value for _, value in self._wrist_x_buffer]
        buffer_span = 0.0
        buffer_delta = None

        if len(self._wrist_x_buffer) >= 2:
            buffer_span = self._wrist_x_buffer[-1][0] - self._wrist_x_buffer[0][0]
            buffer_delta = self._wrist_x_buffer[-1][1] - self._wrist_x_buffer[0][1]

        return {
            "buffer_len": len(self._wrist_x_buffer),
            "buffer_values": buffer_values,
            "buffer_span": buffer_span,
            "buffer_delta": buffer_delta,
        }

    def _snapshot_debug_state(self, now=None):
        """Return the current gesture state for visualization overlays."""
        if now is None:
            now = time.time()

        swipe_state = self._swipe_debug_state(now)
        return {
            "hand_detected": False,
            "paused": not self.running,
            "action": None,
            "wrist_x": None,
            "buffer_len": swipe_state["buffer_len"],
            "buffer_values": swipe_state["buffer_values"],
            "buffer_delta": swipe_state["buffer_delta"],
            "buffer_span": swipe_state["buffer_span"],
            "min_swipe_samples": min(SWIPE_BUFFER_SIZE, SWIPE_MIN_SAMPLES),
            "fist_detected": False,
            "fist_frame_count": self._fist_frame_count,
            "fist_armed": self._fist_armed,
            "finger_curled": [],
            "cooldown_remaining": max(0.0, GESTURE_COOLDOWN_SEC - (now - self._last_gesture_time)),
        }

    def _open_visualization_window(self):
        """Create the visualization window when requested."""
        if not self._visualize or self._visualization_window_open:
            return

        try:
            cv2.namedWindow(VISUALIZATION_WINDOW_NAME, cv2.WINDOW_NORMAL)
            self._visualization_window_open = True
            print(
                "[GestureController] Visualization enabled. "
                "Press q or Esc in the OpenCV window to close it."
            )
        except cv2.error as exc:
            self._visualize = False
            print(f"[GestureController] Visualization unavailable: {exc}")

    def _close_visualization_window(self, disable=False):
        """Destroy the visualization window and optionally disable future updates."""
        if self._visualization_window_open:
            try:
                cv2.destroyWindow(VISUALIZATION_WINDOW_NAME)
            except cv2.error:
                pass
        self._visualization_window_open = False
        if disable and self._visualize:
            self._visualize = False
            print("[GestureController] Visualization window closed; gestures continue running.")

    @staticmethod
    def _put_overlay_line(frame, text, line_index, color=VISUALIZATION_TEXT_COLOR, scale=0.55):
        """Draw a line of status text into the visualization overlay."""
        y = 28 + (line_index * 22)
        cv2.putText(frame, text, (18, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)

    def _draw_swipe_bar(self, frame, buffer_values, delta):
        """Draw the live swipe buffer and threshold markers."""
        height, width = frame.shape[:2]
        left = 20
        right = width - 20
        top = height - 58
        bottom = height - 24
        mid_y = (top + bottom) // 2
        bar_width = right - left

        cv2.rectangle(frame, (left, top), (right, bottom), (40, 40, 40), 2)
        cv2.line(frame, (left, mid_y), (right, mid_y), (70, 70, 70), 1)

        if not buffer_values:
            return

        start_x = left + int(buffer_values[0] * bar_width)
        threshold_px = int(SWIPE_THRESHOLD * bar_width)
        cv2.line(frame, (start_x + threshold_px, top), (start_x + threshold_px, bottom), VISUALIZATION_ACCENT_NEXT, 1)
        cv2.line(frame, (start_x - threshold_px, top), (start_x - threshold_px, bottom), VISUALIZATION_ACCENT_PREV, 1)

        points = []
        for value in buffer_values:
            x = left + int(value * bar_width)
            point = (x, mid_y)
            points.append(point)
            cv2.circle(frame, point, 4, VISUALIZATION_ACCENT_TRACK, -1)

        for start, end in zip(points, points[1:]):
            cv2.line(frame, start, end, VISUALIZATION_ACCENT_TRACK, 2)

        if delta is not None and points:
            end_x = points[-1][0]
            color = VISUALIZATION_ACCENT_NEXT if delta > 0 else VISUALIZATION_ACCENT_PREV
            cv2.line(frame, (start_x, top - 8), (end_x, top - 8), color, 3)

    def _render_visualization(self, frame, hand_landmarks, debug_info):
        """Render the annotated OpenCV visualization frame."""
        self._open_visualization_window()
        if not self._visualization_window_open:
            return

        annotated = frame.copy()
        if hand_landmarks is not None:
            self._mp_draw.draw_landmarks(
                annotated,
                hand_landmarks,
                self._mp_hands.HAND_CONNECTIONS,
                self._mp_styles.get_default_hand_landmarks_style(),
                self._mp_styles.get_default_hand_connections_style(),
            )

        action = debug_info.get("action") or "-"
        wrist_x = debug_info.get("wrist_x")
        buffer_len = debug_info.get("buffer_len", 0)
        buffer_delta = debug_info.get("buffer_delta")
        buffer_span = debug_info.get("buffer_span", 0.0)
        min_swipe_samples = debug_info.get("min_swipe_samples", 0)
        fist_count = debug_info.get("fist_frame_count", 0)
        cooldown_remaining = debug_info.get("cooldown_remaining", 0.0)
        status = "paused" if debug_info.get("paused") else "active"

        lines = [
            f"camera={self._camera_index} status={status} hand_detected={debug_info.get('hand_detected', False)}",
            f"wrist_x={wrist_x:.3f}" if wrist_x is not None else "wrist_x=-",
            (
                f"swipe_samples={buffer_len} min={min_swipe_samples} delta={buffer_delta:+.3f}"
                if buffer_delta is not None
                else f"swipe_samples={buffer_len} min={min_swipe_samples} delta=-"
            ),
            f"swipe_threshold={SWIPE_THRESHOLD:.3f} window={buffer_span:.2f}/{SWIPE_WINDOW_SEC:.2f}s cooldown={cooldown_remaining:.2f}s",
            f"fist_frames={fist_count}/{FIST_FRAMES_REQUIRED} fist_detected={debug_info.get('fist_detected', False)} armed={debug_info.get('fist_armed', True)}",
            f"curled_fingers={debug_info.get('finger_curled', [])}",
            f"action_now={action} last_action={self._last_action}",
            "Controls: q or Esc closes the visualization window",
        ]

        cv2.rectangle(annotated, (10, 10), (540, 200), (0, 0, 0), -1)
        cv2.rectangle(annotated, (10, 10), (540, 200), (80, 80, 80), 2)
        for idx, line in enumerate(lines):
            color = VISUALIZATION_TEXT_COLOR
            if idx == 2 and buffer_delta is not None:
                if buffer_delta > SWIPE_THRESHOLD:
                    color = VISUALIZATION_ACCENT_NEXT
                elif buffer_delta < -SWIPE_THRESHOLD:
                    color = VISUALIZATION_ACCENT_PREV
            if idx == 4 and debug_info.get("fist_detected"):
                color = VISUALIZATION_ACCENT_TRACK
            if idx == 6 and action != "-":
                color = VISUALIZATION_ACCENT_ACTION
            self._put_overlay_line(annotated, line, idx, color=color)

        self._draw_swipe_bar(annotated, debug_info.get("buffer_values", []), buffer_delta)

        if action != "-":
            cv2.rectangle(annotated, (10, 210), (260, 250), (20, 20, 20), -1)
            cv2.rectangle(annotated, (10, 210), (260, 250), VISUALIZATION_ACCENT_ACTION, 2)
            cv2.putText(
                annotated,
                f"ACTION: {action.upper()}",
                (20, 238),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                VISUALIZATION_ACCENT_ACTION,
                2,
                cv2.LINE_AA,
            )

        cv2.imshow(VISUALIZATION_WINDOW_NAME, annotated)
        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q")):
            self._close_visualization_window(disable=True)
            return

        try:
            if cv2.getWindowProperty(VISUALIZATION_WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                self._close_visualization_window(disable=True)
        except cv2.error:
            self._close_visualization_window(disable=True)

    def _candidate_camera_indices(self):
        """Return camera indices to probe, preferring the configured index first."""
        detected_indices = []
        for path in glob("/dev/video*"):
            match = re.search(r"(\d+)$", path)
            if match:
                detected_indices.append(int(match.group(1)))

        if not detected_indices:
            return [CAMERA_INDEX]

        ordered = []
        seen = set()

        def add(index):
            if index not in seen:
                ordered.append(index)
                seen.add(index)

        add(CAMERA_INDEX)
        for index in sorted((idx for idx in detected_indices if idx > CAMERA_INDEX), reverse=True):
            add(index)
        for index in sorted((idx for idx in detected_indices if idx < CAMERA_INDEX)):
            add(index)
        return ordered

    def _open_camera(self):
        """Probe available camera nodes and return the first working capture."""
        candidates = self._candidate_camera_indices()
        print(f"[GestureController] Probing camera indices: {candidates}")

        for index in candidates:
            with _suppress_stderr():
                cap = cv2.VideoCapture(index)
                is_opened = cap.isOpened()

            if not is_opened:
                cap.release()
                continue

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
            cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)

            for _ in range(CAMERA_PROBE_WARMUP_FRAMES):
                ret, frame = cap.read()
                if ret and frame is not None:
                    self._camera_index = index
                    print(f"[GestureController] Using camera index {index}")
                    return cap
                time.sleep(CAMERA_READ_RETRY_SEC)

            cap.release()

        print(f"[GestureController] Error: Could not open any camera from {candidates}")
        return None

    def _loop(self):
        cap = self._open_camera()
        if cap is None:
            return

        self._open_visualization_window()
        hands = self._mp_hands.Hands(
            max_num_hands=MAX_HANDS,
            min_detection_confidence=MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=MIN_TRACKING_CONFIDENCE,
        )

        try:
            while not self._stop_event.is_set():
                frame_started_at = time.perf_counter()
                ret, frame = cap.read()
                if not ret:
                    time.sleep(IDLE_SLEEP_SEC)
                    continue

                debug_info = None
                hand_landmarks = None
                if not self.running:
                    if self._visualize:
                        debug_info = self._snapshot_debug_state()
                        self._render_visualization(frame, None, debug_info)
                    time.sleep(IDLE_SLEEP_SEC)
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                results = hands.process(rgb)
                rgb.flags.writeable = True

                if results.multi_hand_landmarks:
                    self._missing_hand_frames = 0
                    hand_landmarks = results.multi_hand_landmarks[0]
                    debug_info = self._process_landmarks(hand_landmarks.landmark)
                    debug_info["hand_detected"] = True
                    debug_info["paused"] = False
                    if debug_info["action"]:
                        self._last_action = debug_info["action"]
                else:
                    self._missing_hand_frames += 1
                    if self._missing_hand_frames >= NO_HAND_RESET_FRAMES:
                        self._reset_tracking_state()
                    if self._visualize:
                        debug_info = self._snapshot_debug_state()

                if self._visualize:
                    if debug_info is None:
                        debug_info = self._snapshot_debug_state()
                    self._render_visualization(frame, hand_landmarks, debug_info)

                frame_time_budget = 1.0 / TARGET_FPS if TARGET_FPS > 0 else 0.0
                frame_elapsed = time.perf_counter() - frame_started_at
                if frame_time_budget > frame_elapsed:
                    time.sleep(frame_time_budget - frame_elapsed)
        finally:
            self._close_visualization_window()
            hands.close()
            cap.release()
            print("[GestureController] Camera released")

    def _process_landmarks(self, landmarks, fire_actions=True):
        now = time.time()
        wrist_x = landmarks[0].x
        finger_curled = self._finger_curl_states(landmarks)
        fist_detected = all(finger_curled)
        cooldown_remaining = max(0.0, GESTURE_COOLDOWN_SEC - (now - self._last_gesture_time))
        swipe_state = self._swipe_debug_state(now)

        debug_info = {
            "action": None,
            "hand_detected": False,
            "paused": not self.running,
            "wrist_x": wrist_x,
            "buffer_len": swipe_state["buffer_len"],
            "buffer_values": swipe_state["buffer_values"],
            "buffer_delta": swipe_state["buffer_delta"],
            "buffer_span": swipe_state["buffer_span"],
            "min_swipe_samples": min(SWIPE_BUFFER_SIZE, SWIPE_MIN_SAMPLES),
            "fist_detected": fist_detected,
            "fist_frame_count": self._fist_frame_count,
            "fist_armed": self._fist_armed,
            "finger_curled": finger_curled,
            "cooldown_remaining": cooldown_remaining,
        }

        if cooldown_remaining > 0:
            if not fist_detected:
                self._fist_armed = True
                debug_info["fist_armed"] = True
            return debug_info

        if fist_detected:
            self._wrist_x_buffer.clear()
            debug_info["buffer_len"] = 0
            debug_info["buffer_values"] = []
            debug_info["buffer_span"] = 0.0
            debug_info["buffer_delta"] = None
            if self._fist_armed:
                self._fist_frame_count += 1
            debug_info["fist_frame_count"] = self._fist_frame_count
            debug_info["fist_armed"] = self._fist_armed
            if self._fist_armed and self._fist_frame_count >= FIST_FRAMES_REQUIRED:
                if fire_actions:
                    pause_slide()
                self._last_gesture_time = now
                self._fist_frame_count = 0
                self._fist_armed = False
                debug_info["action"] = "pause"
                debug_info["fist_frame_count"] = 0
                debug_info["fist_armed"] = False
                debug_info["cooldown_remaining"] = GESTURE_COOLDOWN_SEC
            return debug_info

        self._fist_frame_count = 0
        self._fist_armed = True
        self._wrist_x_buffer.append((now, wrist_x))
        swipe_state = self._swipe_debug_state(now)
        debug_info["buffer_len"] = swipe_state["buffer_len"]
        debug_info["buffer_values"] = swipe_state["buffer_values"]
        debug_info["buffer_delta"] = swipe_state["buffer_delta"]
        debug_info["buffer_span"] = swipe_state["buffer_span"]
        debug_info["fist_frame_count"] = 0
        debug_info["fist_armed"] = True
        if debug_info["buffer_len"] >= debug_info["min_swipe_samples"] and debug_info["buffer_delta"] is not None:
            delta = debug_info["buffer_delta"]
            if delta > SWIPE_THRESHOLD:
                if fire_actions:
                    next_slide()
                self._last_gesture_time = now
                self._wrist_x_buffer.clear()
                debug_info["action"] = "next"
                debug_info["buffer_len"] = 0
                debug_info["buffer_values"] = []
                debug_info["buffer_span"] = 0.0
                debug_info["buffer_delta"] = None
                debug_info["cooldown_remaining"] = GESTURE_COOLDOWN_SEC
            elif delta < -SWIPE_THRESHOLD:
                if fire_actions:
                    prev_slide()
                self._last_gesture_time = now
                self._wrist_x_buffer.clear()
                debug_info["action"] = "prev"
                debug_info["buffer_len"] = 0
                debug_info["buffer_values"] = []
                debug_info["buffer_span"] = 0.0
                debug_info["buffer_delta"] = None
                debug_info["cooldown_remaining"] = GESTURE_COOLDOWN_SEC

        return debug_info

    @staticmethod
    def _finger_curl_states(landmarks):
        tip_ids = [8, 12, 16, 20]
        pip_ids = [6, 10, 14, 18]
        return [landmarks[tip_id].y > landmarks[pip_id].y for tip_id, pip_id in zip(tip_ids, pip_ids)]

    @staticmethod
    def _is_fist(landmarks):
        return all(GestureController._finger_curl_states(landmarks))
