"""Keyboard trigger helpers for slide navigation."""

import pyautogui

from config import KEY_NEXT_SLIDE, KEY_PAUSE, KEY_PREV_SLIDE

pyautogui.FAILSAFE = False


def next_slide():
    """Press key to advance to the next slide."""
    pyautogui.press(KEY_NEXT_SLIDE)
    print("[TRIGGER] → Next Slide")


def prev_slide():
    """Press key to go to the previous slide."""
    pyautogui.press(KEY_PREV_SLIDE)
    print("[TRIGGER] → Previous Slide")


def pause_slide():
    """Press key to pause or black out the presentation."""
    pyautogui.press(KEY_PAUSE)
    print("[TRIGGER] → Pause")
