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
    DOUBLE_FIST_WINDOW_SEC,
    FIST_FRAMES_REQUIRED,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    IDLE_SLEEP_SEC,
    MAX_HANDS,
    PALM_HOLD_FRAMES_REQUIRED,
    PALM_HOLD_MAX_MOVEMENT,
    SWIPE_DEAD_ZONE,
    SWIPE_VELOCITY_THRESHOLD,
    TARGET_FPS,
    VISUALIZATION_ACCENT_ACTION,
    VISUALIZATION_ACCENT_NEXT,
    VISUALIZATION_ACCENT_PREV,
    VISUALIZATION_ACCENT_TRACK,
    VISUALIZATION_TEXT_COLOR,
    VISUALIZATION_WINDOW_NAME,
)
from gesture_map import get_action_for_gesture
from logger import log_gesture
from recorder import record_event
from runtime import config, state, frames
from trigger import exit_presentation, first_slide, last_slide, next_slide, pause_slide, prev_slide, start_presentation




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
        self._wrist_x_buffer = deque(maxlen=int(config.get("SWIPE_BUFFER_SIZE", 8)))
        self._fist_frame_count = 0
        self._last_gesture_time = 0.0
        self._mp_draw = mp.solutions.drawing_utils
        self._mp_hands = mp.solutions.hands
        self._mp_styles = mp.solutions.drawing_styles
        # Double-fist detection (two pause gestures in quick succession = first slide)
        self._last_pause_time = 0.0
        # Palm-hold detection (open hand held still = last slide)
        self._palm_hold_count = 0
        self._palm_hold_wrist_x = None

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
        self._last_pause_time = 0.0
        self._palm_hold_count = 0
        self._palm_hold_wrist_x = None

    def _dispatch_action(self, gesture_name: str, fire_actions: bool = True):
        """Dispatch an action based on the gesture-to-action mapping.

        Returns the action name if dispatched, None otherwise.
        """
        action = get_action_for_gesture(gesture_name)
        if action is None:
            return None

        action_map = {
            "next": next_slide,
            "prev": prev_slide,
            "pause": pause_slide,
            "first": first_slide,
            "last": last_slide,
            "start": start_presentation,
            "exit": exit_presentation,
        }

        func = action_map.get(action)
        if func is None:
            return None

        if fire_actions:
            gesture_start = time.time()
            func()
            latency = (time.time() - gesture_start) * 1000
            state.record_latency(latency)
            log_gesture(action)
            record_event(action, {"gesture": gesture_name})

        return action

    def _prune_stale_swipe_samples(self, now):
        """Keep only recent wrist samples within the swipe time window."""
        while self._wrist_x_buffer and (now - self._wrist_x_buffer[0][0]) > config.get("SWIPE_WINDOW_SEC", 0.45):
            self._wrist_x_buffer.popleft()

    def _swipe_debug_state(self, now):
        """Return swipe debug values derived from the active time window."""
        self._prune_stale_swipe_samples(now)
        buffer_values = [value for _, value in self._wrist_x_buffer]
        buffer_span = 0.0
        buffer_delta = None
        buffer_velocity = None

        if len(self._wrist_x_buffer) >= 2:
            buffer_span = self._wrist_x_buffer[-1][0] - self._wrist_x_buffer[0][0]
            buffer_delta = self._wrist_x_buffer[-1][1] - self._wrist_x_buffer[0][1]
            if buffer_span > 0:
                buffer_velocity = abs(buffer_delta) / buffer_span

        return {
            "buffer_len": len(self._wrist_x_buffer),
            "buffer_values": buffer_values,
            "buffer_span": buffer_span,
            "buffer_delta": buffer_delta,
            "buffer_velocity": buffer_velocity,
        }

    def _snapshot_debug_state(self, now=None):
        """Return the current gesture state for visualization overlays."""
        if now is None:
            now = time.time()

        swipe_state = self._swipe_debug_state(now)
        st = {
            "hand_detected": False,
            "paused": not self.running,
            "action": None,
            "wrist_x": None,
            "buffer_len": swipe_state["buffer_len"],
            "buffer_values": swipe_state["buffer_values"],
            "buffer_delta": swipe_state["buffer_delta"],
            "buffer_span": swipe_state["buffer_span"],
            "min_swipe_samples": min(config.get("SWIPE_BUFFER_SIZE", 8), config.get("SWIPE_MIN_SAMPLES", 4)),
            "fist_detected": False,
            "fist_frame_count": self._fist_frame_count,
            "fist_armed": self._fist_armed,
            "finger_curled": [],
            "cooldown_remaining": max(0.0, config.get("GESTURE_COOLDOWN_SEC", 0.9) - (now - self._last_gesture_time)),
        }
        state.publish(st)
        return st

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
        threshold_px = int(config.get("SWIPE_THRESHOLD", 0.04) * bar_width)
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

        swipe_threshold = config.get("SWIPE_THRESHOLD", 0.04)
        swipe_window = config.get("SWIPE_WINDOW_SEC", 0.45)
        fist_frames_req = config.get("FIST_FRAMES_REQUIRED", 3)

        lines = [
            f"camera={self._camera_index} status={status} hand_detected={debug_info.get('hand_detected', False)}",
            f"wrist_x={wrist_x:.3f}" if wrist_x is not None else "wrist_x=-",
            (
                f"swipe_samples={buffer_len} min={min_swipe_samples} delta={buffer_delta:+.3f}"
                if buffer_delta is not None
                else f"swipe_samples={buffer_len} min={min_swipe_samples} delta=-"
            ),
            f"swipe_threshold={swipe_threshold:.3f} window={buffer_span:.2f}/{swipe_window:.2f}s cooldown={cooldown_remaining:.2f}s",
            f"fist_frames={fist_count}/{fist_frames_req} fist_detected={debug_info.get('fist_detected', False)} armed={debug_info.get('fist_armed', True)}",
            f"curled_fingers={debug_info.get('finger_curled', [])}",
            f"action_now={action} last_action={self._last_action}",
            "Controls: q or Esc closes the visualization window",
        ]

        cv2.rectangle(annotated, (10, 10), (540, 200), (0, 0, 0), -1)
        cv2.rectangle(annotated, (10, 10), (540, 200), (80, 80, 80), 2)
        for idx, line in enumerate(lines):
            color = VISUALIZATION_TEXT_COLOR
            if idx == 2 and buffer_delta is not None:
                if buffer_delta > swipe_threshold:
                    color = VISUALIZATION_ACCENT_NEXT
                elif buffer_delta < -swipe_threshold:
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

    def _candidate_camera_sources(self):
        """Return camera sources to probe, preferring configured index format first."""
        candidates = []
        if isinstance(CAMERA_INDEX, str):
            if CAMERA_INDEX.isdigit():
                candidates.append(f"/dev/video{CAMERA_INDEX}")
                candidates.append(int(CAMERA_INDEX))
            else:
                candidates.append(CAMERA_INDEX)
        else:
            candidates.append(f"/dev/video{CAMERA_INDEX}")
            candidates.append(int(CAMERA_INDEX))

        detected = []
        for path in glob("/dev/video*"):
            detected.append(path)
            match = re.search(r"(\d+)$", path)
            if match:
                detected.append(int(match.group(1)))
                
        # Ensure we don't have dupes but keep ordering
        deduped = []
        seen = set()
        for cand in candidates + detected:
            key = (type(cand), str(cand))
            if key not in seen:
                seen.add(key)
                deduped.append(cand)
        return deduped

    def _open_camera(self):
        """Probe available camera nodes and return the first working capture."""
        candidates = self._candidate_camera_sources()
        print(f"[GestureController] Probing camera sources: {candidates[:15]}...")
        import sys

        for source in candidates:
            if sys.platform.startswith("linux"):
                if isinstance(source, str) and source.startswith("/dev/video"):
                    backends = [cv2.CAP_FFMPEG, cv2.CAP_ANY, cv2.CAP_V4L2]
                elif isinstance(source, int):
                    backends = [cv2.CAP_V4L2]
                else:
                    backends = [cv2.CAP_ANY]
            else:
                backends = [cv2.CAP_ANY]

            for backend in backends:
                cap = cv2.VideoCapture(source, backend)
                
                if not cap.isOpened():
                    cap.release()
                    continue
                    
                found_frame = False
                for _ in range(CAMERA_PROBE_WARMUP_FRAMES):
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        found_frame = True
                        break
                    time.sleep(CAMERA_READ_RETRY_SEC)

                if found_frame:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
                    cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)
                    
                    self._camera_index = source
                    print(f"[GestureController] Using camera {source} with backend {backend}")
                    return cap

                cap.release()

        print(f"[GestureController] Error: Could not open any camera from candidates")
        return None

    def _loop(self):
        self._open_visualization_window()
        hands = self._mp_hands.Hands(
            max_num_hands=MAX_HANDS,
            min_detection_confidence=config.get("MIN_DETECTION_CONFIDENCE", 0.5),
            min_tracking_confidence=config.get("MIN_TRACKING_CONFIDENCE", 0.4),
        )
        cap = None
        consecutive_failures = 0
        max_retry_interval = 30.0

        try:
            while not self._stop_event.is_set():
                if cap is None:
                    cap = self._open_camera()
                    if cap is None:
                        consecutive_failures += 1
                        # Exponential backoff with max cap
                        retry_interval = min(2.0 * (1.5 ** (consecutive_failures - 1)), max_retry_interval)
                        print(f"[GestureController] Camera not available, retry in {retry_interval:.1f}s (attempt {consecutive_failures})")
                        debug_info = self._snapshot_debug_state()
                        debug_info["hand_detected"] = False
                        debug_info["paused"] = True
                        state.publish(debug_info)
                        if self._visualize:
                            import numpy as np
                            frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
                            self._render_visualization(frame, None, debug_info)
                        time.sleep(retry_interval)
                        continue
                    else:
                        consecutive_failures = 0

                frame_started_at = time.perf_counter()
                ret, frame = cap.read()
                if not ret:
                    cap.release()
                    cap = None
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

                frames.put(frame)

                frame_time_budget = 1.0 / TARGET_FPS if TARGET_FPS > 0 else 0.0
                frame_elapsed = time.perf_counter() - frame_started_at
                if frame_time_budget > frame_elapsed:
                    time.sleep(frame_time_budget - frame_elapsed)
        finally:
            self._close_visualization_window()
            hands.close()
            if cap is not None:
                cap.release()
            print("[GestureController] Camera thread exited")

    def _process_landmarks(self, landmarks, fire_actions=True):
        now = time.time()
        wrist_x = landmarks[0].x
        finger_curled = self._finger_curl_states(landmarks)
        fist_detected = all(finger_curled)
        cooldown_remaining = max(0.0, config.get("GESTURE_COOLDOWN_SEC", 0.9) - (now - self._last_gesture_time))
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
            "buffer_velocity": swipe_state["buffer_velocity"],
            "min_swipe_samples": min(config.get("SWIPE_BUFFER_SIZE", 8), config.get("SWIPE_MIN_SAMPLES", 4)),
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
            state.publish(debug_info)
            return debug_info

        if fist_detected:
            self._wrist_x_buffer.clear()
            debug_info["buffer_len"] = 0
            debug_info["buffer_values"] = []
            debug_info["buffer_span"] = 0.0
            debug_info["buffer_delta"] = None
            # Reset palm-hold tracking on fist
            self._palm_hold_count = 0
            self._palm_hold_wrist_x = None
            if self._fist_armed:
                self._fist_frame_count += 1
            debug_info["fist_frame_count"] = self._fist_frame_count
            debug_info["fist_armed"] = self._fist_armed
            if self._fist_armed and self._fist_frame_count >= config.get("FIST_FRAMES_REQUIRED", 3):
                action = self._dispatch_action("fist", fire_actions=fire_actions)
                self._last_gesture_time = now
                self._fist_frame_count = 0
                self._fist_armed = False
                debug_info["action"] = action or "pause"
                debug_info["fist_frame_count"] = 0
                debug_info["fist_armed"] = False
                debug_info["cooldown_remaining"] = config.get("GESTURE_COOLDOWN_SEC", 0.9)
                # Track for double-fist detection (two pause gestures in quick succession)
                if self._last_pause_time > 0 and (now - self._last_pause_time) <= config.get("DOUBLE_FIST_WINDOW_SEC", 3.0):
                    # Double-fist detected!
                    double_action = self._dispatch_action("double_fist", fire_actions=fire_actions)
                    self._last_pause_time = 0.0
                    if double_action:
                        debug_info["action"] = double_action
                        debug_info["cooldown_remaining"] = config.get("GESTURE_COOLDOWN_SEC", 0.9)
                else:
                    self._last_pause_time = now
            state.publish(debug_info)
            return debug_info

        self._fist_frame_count = 0
        self._fist_armed = True
        # Track palm-hold for last slide gesture (open hand held still)
        if self._palm_hold_wrist_x is None:
            self._palm_hold_wrist_x = wrist_x
            self._palm_hold_count = 1
        elif abs(wrist_x - self._palm_hold_wrist_x) <= config.get("PALM_HOLD_MAX_MOVEMENT", 0.03):
            self._palm_hold_count += 1
        else:
            self._palm_hold_wrist_x = wrist_x
            self._palm_hold_count = 1
        self._wrist_x_buffer.append((now, wrist_x))
        swipe_state = self._swipe_debug_state(now)
        debug_info["buffer_len"] = swipe_state["buffer_len"]
        debug_info["buffer_values"] = swipe_state["buffer_values"]
        debug_info["buffer_delta"] = swipe_state["buffer_delta"]
        debug_info["buffer_span"] = swipe_state["buffer_span"]
        debug_info["buffer_velocity"] = swipe_state["buffer_velocity"]
        debug_info["fist_frame_count"] = 0
        debug_info["fist_armed"] = True
        debug_info["palm_hold_count"] = self._palm_hold_count

        swipe_threshold = config.get("SWIPE_THRESHOLD", 0.04)

        if debug_info["buffer_len"] >= debug_info["min_swipe_samples"] and debug_info["buffer_delta"] is not None:
            delta = debug_info["buffer_delta"]
            velocity = debug_info.get("buffer_velocity") or 0.0
            dead_zone = config.get("SWIPE_DEAD_ZONE", 0.01)
            velocity_threshold = config.get("SWIPE_VELOCITY_THRESHOLD", 0.15)
            # Apply dead zone: ignore movements smaller than threshold
            if abs(delta) < dead_zone:
                delta = 0
            # Require minimum velocity for swipe detection
            if delta > swipe_threshold and velocity >= velocity_threshold:
                action = self._dispatch_action("swipe_right", fire_actions=fire_actions)
                self._last_gesture_time = now
                self._wrist_x_buffer.clear()
                debug_info["action"] = action or "next"
                debug_info["buffer_len"] = 0
                debug_info["buffer_values"] = []
                debug_info["buffer_span"] = 0.0
                debug_info["buffer_delta"] = None
                debug_info["cooldown_remaining"] = config.get("GESTURE_COOLDOWN_SEC", 0.9)
            elif delta < -swipe_threshold and velocity >= velocity_threshold:
                action = self._dispatch_action("swipe_left", fire_actions=fire_actions)
                self._last_gesture_time = now
                self._wrist_x_buffer.clear()
                debug_info["action"] = action or "prev"
                debug_info["buffer_len"] = 0
                debug_info["buffer_values"] = []
                debug_info["buffer_span"] = 0.0
                debug_info["buffer_delta"] = None
                debug_info["cooldown_remaining"] = config.get("GESTURE_COOLDOWN_SEC", 0.9)
                self._palm_hold_count = 0
                self._palm_hold_wrist_x = None

        # Check for palm-hold (last slide) - open hand held still
        if self._palm_hold_count >= config.get("PALM_HOLD_FRAMES_REQUIRED", 5):
            action = self._dispatch_action("palm_hold", fire_actions=fire_actions)
            self._last_gesture_time = now
            debug_info["action"] = action or "last"
            debug_info["cooldown_remaining"] = config.get("GESTURE_COOLDOWN_SEC", 0.9)
            self._palm_hold_count = 0
            self._palm_hold_wrist_x = None

        state.publish(debug_info)
        return debug_info

    @staticmethod
    def _finger_curl_states(landmarks):
        tip_ids = [8, 12, 16, 20]
        pip_ids = [6, 10, 14, 18]
        return [landmarks[tip_id].y > landmarks[pip_id].y for tip_id, pip_id in zip(tip_ids, pip_ids)]

