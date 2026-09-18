"""Keyboard trigger helpers for slide navigation with Wayland/ydotool support and per-app bindings."""

import json
import os
import platform
import shutil
import subprocess

import pyautogui

from config import APP_KEY_BINDINGS, KEY_EXIT_PRESENTATION, KEY_FIRST_SLIDE, KEY_LAST_SLIDE, KEY_NEXT_SLIDE, KEY_PAUSE, KEY_PREV_SLIDE, KEY_START_PRESENTATION

pyautogui.FAILSAFE = False

IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"
IS_WINDOWS = platform.system() == "Windows"

def _get_active_window_title() -> str:
    """Attempt to get the title of the active window for per-app bindings."""
    if IS_LINUX:
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

    if IS_MACOS:
        # Use AppleScript to get frontmost app name
        try:
            result = subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to get name of first application process whose frontmost is true'],
                capture_output=True, text=True, timeout=1
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

    if IS_WINDOWS:
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
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

    # Platform-specific key dispatch
    if IS_LINUX:
        # Try ydotool first for native Wayland support
        if shutil.which("ydotool"):
            try:
                # ydotool expects KEY_* evdev names; convert pyautogui names
                ydo_key = key_to_press.upper()
                if ydo_key in ("RIGHT", "LEFT", "UP", "DOWN", "ENTER", "SPACE", "ESC", "B"):
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

    if IS_MACOS:
        # Try osascript for macOS key dispatch
        try:
            # Map pyautogui key names to AppleScript key codes
            key_code_map = {
                "right": "124",
                "left": "123",
                "up": "126",
                "down": "125",
                "return": "36",
                "enter": "36",
                "space": "49",
                "escape": "53",
                "b": "11",
                "home": "115",
                "end": "119",
                "f5": "96",
            }
            key_code = key_code_map.get(key_to_press.lower())
            if key_code:
                subprocess.run(
                    ["osascript", "-e", f'tell application "System Events" to key code {key_code}'],
                    capture_output=True,
                    timeout=1
                )
                return
        except Exception as e:
            print(f"[TRIGGER] osascript failed: {e}")

    if IS_WINDOWS:
        # Use Windows SendKeys via ctypes
        try:
            import ctypes
            # Map pyautogui key names to Windows virtual key codes
            vk_map = {
                "right": 0x27,
                "left": 0x25,
                "up": 0x26,
                "down": 0x28,
                "return": 0x0D,
                "enter": 0x0D,
                "space": 0x20,
                "escape": 0x1B,
                "b": 0x42,
                "home": 0x24,
                "end": 0x23,
                "f5": 0x74,
            }
            vk_code = vk_map.get(key_to_press.lower())
            if vk_code:
                ctypes.windll.user32.keybd_event(0, 0, 0, 0)
                ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
                ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)
                return
        except Exception as e:
            print(f"[TRIGGER] Windows key event failed: {e}")

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


def first_slide():
    """Press key to jump to the first slide."""
    _trigger_key("first", KEY_FIRST_SLIDE)


def last_slide():
    """Press key to jump to the last slide."""
    _trigger_key("last", KEY_LAST_SLIDE)


def start_presentation():
    """Press key to start presentation mode (F5)."""
    _trigger_key("start", KEY_START_PRESENTATION)


def exit_presentation():
    """Press key to exit presentation mode (Escape)."""
    _trigger_key("exit", KEY_EXIT_PRESENTATION)
