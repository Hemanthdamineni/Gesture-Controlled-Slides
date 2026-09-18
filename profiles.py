"""Sensitivity profile management."""

import json
from pathlib import Path

PROFILES_DIR = Path(__file__).parent / "profiles"
PROFILES_DIR.mkdir(exist_ok=True)

DEFAULT_PROFILE = {
    "name": "default",
    "SWIPE_THRESHOLD": 0.04,
    "SWIPE_WINDOW_SEC": 0.45,
    "SWIPE_MIN_SAMPLES": 4,
    "SWIPE_BUFFER_SIZE": 8,
    "GESTURE_COOLDOWN_SEC": 0.9,
    "FIST_FRAMES_REQUIRED": 3,
    "MIN_DETECTION_CONFIDENCE": 0.5,
    "MIN_TRACKING_CONFIDENCE": 0.4,
    "SWIPE_DEAD_ZONE": 0.01,
    "SWIPE_VELOCITY_THRESHOLD": 0.15,
    "DOUBLE_FIST_WINDOW_SEC": 3.0,
    "PALM_HOLD_FRAMES_REQUIRED": 5,
    "PALM_HOLD_MAX_MOVEMENT": 0.03,
}

PROFILE_KEYS = list(DEFAULT_PROFILE.keys())
PROFILE_KEYS.remove("name")


def get_profile_names():
    """Return list of available profile names."""
    names = ["default"]
    for profile_file in sorted(PROFILES_DIR.glob("*.json")):
        name = profile_file.stem
        if name not in names:
            names.append(name)
    return names


def load_profile(name="default"):
    """Load a profile by name. Returns default if not found."""
    if name == "default":
        return dict(DEFAULT_PROFILE)

    profile_file = PROFILES_DIR / f"{name}.json"
    if profile_file.exists():
        try:
            with open(profile_file, "r") as f:
                data = json.load(f)
            # Merge with defaults to ensure all keys exist
            profile = dict(DEFAULT_PROFILE)
            profile["name"] = name
            for key in PROFILE_KEYS:
                if key in data:
                    profile[key] = data[key]
            return profile
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_PROFILE)


def save_profile(name, settings):
    """Save a profile."""
    profile = {"name": name}
    for key in PROFILE_KEYS:
        if key in settings:
            profile[key] = settings[key]
        else:
            profile[key] = DEFAULT_PROFILE[key]

    profile_file = PROFILES_DIR / f"{name}.json"
    with open(profile_file, "w") as f:
        json.dump(profile, f, indent=2)
    return profile


def delete_profile(name):
    """Delete a profile. Returns True if successful."""
    if name == "default":
        return False
    profile_file = PROFILES_DIR / f"{name}.json"
    if profile_file.exists():
        try:
            profile_file.unlink()
            return True
        except OSError:
            return False
    return False
