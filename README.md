# GestureSlides

GestureSlides is a Python app that watches a single camera feed, detects hand gestures with MediaPipe, and sends keyboard shortcuts to control presentation slides.

## Status

The app currently supports:

- swipe right: next slide
- swipe left: previous slide
- fist: pause or black screen
- Pixi-based environment management
- tray mode when the desktop provides a usable tray backend
- foreground visualization mode for debugging landmarks and gesture state

The project now lives directly in the repository root. There is no nested `gesture-slides/` source directory anymore.

## Project files

- `main.py`: app entry point and runtime mode selection
- `gesture.py`: camera probing, MediaPipe processing, gesture detection, visualization overlay
- `trigger.py`: keyboard actions sent to the presentation app
- `tray.py`: `pystray` and GTK/AppIndicator tray backends
- `config.py`: gesture, camera, tray, and visualization settings
- `requirements.txt`: Python package pins
- `start_linux.sh`: background launcher with log output
- `start_mac.sh`: background launcher without terminal attachment
- `start_windows.bat`: Windows launcher

## Environment

This project uses Pixi. Do not create a `venv`.

Check the environment:

```bash
pixi run python --version
```

Install Python dependencies:

```bash
pixi run pip install -r requirements.txt
```

## Omarchy / Arch Linux setup

On Omarchy / Arch Linux, install the desktop packages needed for GTK/AppIndicator tray support:

```bash
sudo pacman -S gtk3 libayatana-appindicator gobject-introspection-runtime
```

The app has been tuned around a setup where the usable camera arrives on `/dev/video42` through a `libcamera -> GStreamer -> v4l2sink` pipeline. It does not hardcode that index. Instead, it probes `/dev/video*` nodes and picks the first stream that actually returns frames.

## Running

Normal run:

```bash
pixi run python main.py
```

Visualization run:

```bash
pixi run python main.py --visualize
```

`--visualize` runs in the foreground without the tray backend and opens an OpenCV window with:

- MediaPipe landmarks
- swipe history and threshold markers
- cooldown state
- fist detection progress
- current and last action

Controls in visualization mode:

- `q`: close the visualization window
- `Esc`: close the visualization window
- `Ctrl+C`: stop the app from the terminal

Background launchers:

```bash
./start_linux.sh
./start_mac.sh
start_windows.bat
```

## Tray behavior

Tray startup is desktop-dependent:

- KDE / XFCE / GNOME with tray support: tries `pystray` first
- Hyprland / Waybar: prefers GTK/AppIndicator first
- no usable tray backend: keeps gesture detection running without crashing

When no tray backend is available, `main.py` prints:

```text
[main] No tray available on this desktop.
Use Ctrl+C to quit, or send SIGTERM to PID <pid>
```

## Gesture tuning

The current working defaults in `config.py` are:

- `MIN_DETECTION_CONFIDENCE = 0.5`
- `MIN_TRACKING_CONFIDENCE = 0.4`
- `SWIPE_BUFFER_SIZE = 8`
- `SWIPE_THRESHOLD = 0.04`
- `SWIPE_WINDOW_SEC = 0.45`
- `SWIPE_MIN_SAMPLES = 4`
- `FIST_FRAMES_REQUIRED = 3`
- `GESTURE_COOLDOWN_SEC = 0.9`
- `NO_HAND_RESET_FRAMES = 3`

These values were adjusted to tolerate brief hand dropouts and slower real-world movement better than the original fixed-frame-only approach.

## How it works

1. `main.py` starts the `GestureController`.
2. `gesture.py` probes available camera indices and opens the first device that returns real frames.
3. MediaPipe tracks a single hand and reports landmarks.
4. Wrist motion across a short time window is used for swipe detection.
5. Curled finger tips relative to PIP joints are used for fist detection.
6. `trigger.py` sends `right`, `left`, or `b` through `pyautogui`.

## Stopping the app

If the app is attached to your terminal:

```bash
Ctrl+C
```

Or stop it by PID or pattern:

```bash
pkill -f 'pixi run python main.py'
```

## Known limitations

- Tray support still depends on the desktop exposing a tray host.
- On pure Hyprland setups, tray behavior depends on Waybar tray support plus the GTK/AppIndicator stack being available.
- OpenCV may still print non-fatal Qt or MediaPipe startup messages in visualization mode. The noisy OpenCV camera probe warnings for bad indices are already suppressed.
- `pyautogui` requires access to the active desktop session to send real keypresses.
