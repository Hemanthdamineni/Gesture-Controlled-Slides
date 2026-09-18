"""Gesture recording and playback for debugging."""

import json
import time
from pathlib import Path
from threading import Lock

RECORDINGS_DIR = Path(__file__).parent / "recordings"
RECORDINGS_DIR.mkdir(exist_ok=True)

_recording = False
_recorded_events = []
_recording_lock = Lock()
_recording_start_time = 0.0


def start_recording():
    """Start recording gesture events."""
    global _recording, _recorded_events, _recording_start_time
    with _recording_lock:
        _recording = True
        _recorded_events = []
        _recording_start_time = time.time()


def stop_recording():
    """Stop recording and return the recorded events."""
    global _recording
    with _recording_lock:
        _recording = False
        return list(_recorded_events)


def is_recording():
    """Check if currently recording."""
    return _recording


def record_event(action, details=None):
    """Record a gesture event if recording is active."""
    if not _recording:
        return
    with _recording_lock:
        elapsed = time.time() - _recording_start_time
        event = {
            "time": elapsed,
            "action": action,
        }
        if details:
            event["details"] = details
        _recorded_events.append(event)


def save_recording(name, events=None):
    """Save a recording to file."""
    if events is None:
        events = _recorded_events
    recording_file = RECORDINGS_DIR / f"{name}.json"
    with open(recording_file, "w") as f:
        json.dump({"events": events}, f, indent=2)
    return events


def load_recording(name):
    """Load a recording from file."""
    recording_file = RECORDINGS_DIR / f"{name}.json"
    if recording_file.exists():
        try:
            with open(recording_file, "r") as f:
                data = json.load(f)
            return data.get("events", [])
        except (json.JSONDecodeError, OSError):
            return []
    return []


def get_recording_names():
    """Return list of available recording names."""
    names = []
    for recording_file in sorted(RECORDINGS_DIR.glob("*.json")):
        names.append(recording_file.stem)
    return names


def delete_recording(name):
    """Delete a recording."""
    recording_file = RECORDINGS_DIR / f"{name}.json"
    if recording_file.exists():
        try:
            recording_file.unlink()
            return True
        except OSError:
            return False
    return False
