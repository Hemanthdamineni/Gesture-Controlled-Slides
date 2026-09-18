"""Shared configuration for the GestureSlides app."""

# --- Camera ---
CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
TARGET_FPS = 30
CAMERA_PROBE_WARMUP_FRAMES = 5
CAMERA_READ_RETRY_SEC = 0.05

# --- MediaPipe ---
MAX_HANDS = 1
MIN_DETECTION_CONFIDENCE = 0.5
MIN_TRACKING_CONFIDENCE = 0.4

# --- Gesture: Swipe ---
SWIPE_BUFFER_SIZE = 8
SWIPE_THRESHOLD = 0.04
SWIPE_WINDOW_SEC = 0.45
SWIPE_MIN_SAMPLES = 4
SWIPE_DEAD_ZONE = 0.01
SWIPE_VELOCITY_THRESHOLD = 0.15

# --- Gesture: Tracking ---
FIST_FRAMES_REQUIRED = 3
NO_HAND_RESET_FRAMES = 3
DOUBLE_FIST_WINDOW_SEC = 3.0
PALM_HOLD_FRAMES_REQUIRED = 5
PALM_HOLD_MAX_MOVEMENT = 0.03

# --- Cooldown ---
GESTURE_COOLDOWN_SEC = 0.9
IDLE_SLEEP_SEC = 0.05
APP_POLL_INTERVAL_SEC = 0.5

# --- Performance ---
LATENCY_WARNING_THRESHOLD_MS = 100

# --- Keyboard keys ---
KEY_NEXT_SLIDE = 'right'
KEY_PREV_SLIDE = 'left'
KEY_PAUSE = 'b'
KEY_FIRST_SLIDE = 'home'
KEY_LAST_SLIDE = 'end'
KEY_START_PRESENTATION = 'f5'
KEY_EXIT_PRESENTATION = 'escape'

# --- Visualization ---
VISUALIZATION_WINDOW_NAME = "GestureSlides Visualization"
VISUALIZATION_TEXT_COLOR = (240, 240, 240)
VISUALIZATION_ACCENT_NEXT = (34, 197, 94)
VISUALIZATION_ACCENT_PREV = (59, 130, 246)
VISUALIZATION_ACCENT_ACTION = (239, 68, 68)
VISUALIZATION_ACCENT_TRACK = (245, 158, 11)

# --- Tray ---
ICON_SIZE = 64
TRAY_ICON_MARGIN = 8
ICON_COLOR_ACTIVE = (34, 197, 94)
ICON_COLOR_PAUSED = (107, 114, 128)
ICON_COLOR_BG = (0, 0, 0, 0)
APP_NAME = "GestureSlides"

# --- Web dashboard ---
WEB_SERVER_HOST = "127.0.0.1"
WEB_SERVER_PORT = 7474
ENABLE_CAMERA_PREVIEW = True   # stream MJPEG frames to the dashboard

# --- Per-app key overrides ---
# Map window-title substrings (case-insensitive) to action→key dicts.
# The first matching pattern wins; fall back to KEY_* constants above.
# Add your own patterns to customize keys for specific apps.
APP_KEY_BINDINGS: dict[str, dict[str, str]] = {
    "google-chrome": {"next": "right", "prev": "left", "pause": "b"},
    "libreoffice": {"next": "right", "prev": "left", "pause": "b"},
    "powerpoint": {"next": "right", "prev": "left", "pause": "b"},
    "keynote": {"next": "right", "prev": "left", "pause": "b"},
}
