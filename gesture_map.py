"""Gesture-to-action remapping configuration."""

import json
from pathlib import Path

GESTURE_MAP_FILE = Path(__file__).parent / "gesture_map.json"

DEFAULT_GESTURE_MAP = {
    "swipe_right": "next",
    "swipe_left": "prev",
    "fist": "pause",
    "double_fist": "first",
    "palm_hold": "last",
}

VALID_ACTIONS = {"next", "prev", "pause", "first", "last", "start", "exit"}
VALID_GESTURES = {"swipe_right", "swipe_left", "fist", "double_fist", "palm_hold"}


def load_gesture_map():
    """Load gesture map from file, or return default."""
    if GESTURE_MAP_FILE.exists():
        try:
            with open(GESTURE_MAP_FILE, "r") as f:
                data = json.load(f)
            # Validate the loaded map
            return validate_gesture_map(data)
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_GESTURE_MAP)


def save_gesture_map(gesture_map):
    """Save gesture map to file after validation."""
    validated = validate_gesture_map(gesture_map)
    with open(GESTURE_MAP_FILE, "w") as f:
        json.dump(validated, f, indent=2)
    return validated


def validate_gesture_map(gesture_map):
    """Validate and clean a gesture map."""
    cleaned = {}
    for gesture, action in gesture_map.items():
        if gesture in VALID_GESTURES and action in VALID_ACTIONS:
            cleaned[gesture] = action
    # Ensure all valid gestures have a mapping
    for gesture in VALID_GESTURES:
        if gesture not in cleaned:
            cleaned[gesture] = DEFAULT_GESTURE_MAP.get(gesture, "next")
    return cleaned


def get_action_for_gesture(gesture_name):
    """Get the action mapped to a gesture."""
    gesture_map = load_gesture_map()
    return gesture_map.get(gesture_name)
