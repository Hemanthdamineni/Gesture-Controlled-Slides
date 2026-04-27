"""Keyboard trigger helpers for slide navigation with Wayland/ydotool support and per-app bindings."""

import json
import os
import shutil
import subprocess

import pyautogui

from config import APP_KEY_BINDINGS, KEY_NEXT_SLIDE, KEY_PAUSE, KEY_PREV_SLIDE

pyautogui.FAILSAFE = False

def _get_active_window_title() -> str:
    """Attempt to get the title of the active window for per-app bindings."""
    # Try Hyprland first
    if shutil.which("hyprctl"):
        try:
            res = subprocess.run(
                ["hyprctl", "activewindow", "-j"], capture_output=True, text=True, timeout=1
            )
            data = json.loads(res.stdout)
            # Combine class and title to give patterns more to match against
            return f"{data.get('class', '')} {data.get('title', '')}"
        except Exception:
            pass

    # Try xdotool for X11 / XWayland
    if shutil.which("xdotool"):
        try:
            win_id = subprocess.run(
                ["xdotool", "getactivewindow"], capture_output=True, text=True, timeout=1
            ).stdout.strip()
            if win_id:
                title = subprocess.run(
                    ["xdotool", "getwindowname", win_id], capture_output=True, text=True, timeout=1
                ).stdout.strip()
                return title
        except Exception:
            pass

    return ""


def _trigger_key(action_name: str, default_key: str):
    """
    Look up the key for the current app, then send it.
    Tries ydotool first (for Wayland), falls back to pyautogui.
    """
    title = _get_active_window_title().lower()
    key_to_press = default_key

    if title:
        for pattern, bindings in APP_KEY_BINDINGS.items():
            if pattern.lower() in title:
                # We found a matching app; override if the action exists
                if action_name in bindings:
                    key_to_press = bindings[action_name]
                break

    print(f"[TRIGGER] → {action_name.capitalize()} (Key: {key_to_press})")

    # Try ydotool first for native Wayland support
    if shutil.which("ydotool"):
        try:
            # ydotool uses slightly different key names sometimes, but basic ones work
            # mapping 'right' -> 'KEY_RIGHT' if needed, but ydotool often accepts 'right'
            # We'll use ydotool key <key_to_press>
            # Actually, ydotool expects KEY_RIGHT, etc., but it also accepts string literals
            # if they match evdev key names. PyAutoGUI names are standard ('right', 'left', 'b').
            # Common conversions for ydotool:
            ydo_key = key_to_press.upper()
            if ydo_key in ("RIGHT", "LEFT", "UP", "DOWN", "ENTER", "SPACE", "ESC", "B"):
                if len(ydo_key) == 1:
                    ydo_key = f"KEY_{ydo_key}"
                else:
                    ydo_key = f"KEY_{ydo_key}"
            
            res = subprocess.run(
                ["ydotool", "key", f"{ydo_key}:1", f"{ydo_key}:0"],
                capture_output=True,
                timeout=1
            )
            if res.returncode == 0:
                return
        except Exception as e:
            print(f"[TRIGGER] ydotool failed: {e}")

    # Fallback to pyautogui
    try:
        pyautogui.press(key_to_press)
    except Exception as e:
        print(f"[TRIGGER] pyautogui failed: {e}")


def next_slide():
    """Press key to advance to the next slide."""
    _trigger_key("next", KEY_NEXT_SLIDE)


def prev_slide():
    """Press key to go to the previous slide."""
    _trigger_key("prev", KEY_PREV_SLIDE)


def pause_slide():
    """Press key to pause or black out the presentation."""
    _trigger_key("pause", KEY_PAUSE)
