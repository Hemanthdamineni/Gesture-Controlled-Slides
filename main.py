"""Application entry point for the GestureSlides background service."""

import argparse
import os
import time

from config import APP_POLL_INTERVAL_SEC


def parse_args():
    """Parse command-line flags for the app."""
    parser = argparse.ArgumentParser(description="Run GestureSlides in the background.")
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="Open an OpenCV window with MediaPipe landmarks and gesture-state overlays.",
    )
    return parser.parse_args()


def _tray_builders():
    """Return tray backends in the preferred order for the current desktop."""
    from tray import build_gtk_tray, build_tray

    desktop = " ".join(
        filter(
            None,
            (
                os.environ.get("XDG_CURRENT_DESKTOP"),
                os.environ.get("XDG_SESSION_DESKTOP"),
            ),
        )
    ).lower()
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") or "hyprland" in desktop:
        return (
            ("gtk/appindicator", build_gtk_tray),
            ("pystray", build_tray),
        )
    return (
        ("pystray", build_tray),
        ("gtk/appindicator", build_gtk_tray),
    )


def main():
    args = parse_args()
    from gesture import GestureController

    controller = GestureController(visualize=args.visualize)
    controller.start()

    if args.visualize:
        print(
            "[main] Visualization requested. "
            "Running in foreground without tray; press q or Esc in the OpenCV window to close it."
        )
        try:
            while controller._thread and controller._thread.is_alive():
                time.sleep(APP_POLL_INTERVAL_SEC)
        except KeyboardInterrupt:
            controller.stop()
        print("[main] Exited.")
        return

    for backend_name, builder in _tray_builders():
        try:
            icon = builder(controller)
        except Exception as exc:
            print(f"[main] Tray backend unavailable ({backend_name}): {exc}")
            continue

        print(f"[main] App running in background with {backend_name}. Check system tray.")
        try:
            icon.run()
        except KeyboardInterrupt:
            if hasattr(icon, "stop"):
                icon.stop()
        finally:
            if controller._thread and controller._thread.is_alive():
                controller.stop()
        print("[main] Exited.")
        return

    print(
        "[main] No tray available on this desktop.\n"
        f"Use Ctrl+C to quit, or send SIGTERM to PID {os.getpid()}"
    )
    try:
        while controller._thread and controller._thread.is_alive():
            time.sleep(APP_POLL_INTERVAL_SEC)
    except KeyboardInterrupt:
        controller.stop()

    print("[main] Exited.")


if __name__ == "__main__":
    main()
