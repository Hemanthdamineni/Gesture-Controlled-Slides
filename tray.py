"""Tray backends for GestureSlides across desktop environments."""

import threading
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw
import pystray

from config import (
    APP_NAME,
    ICON_COLOR_ACTIVE,
    ICON_COLOR_BG,
    ICON_COLOR_PAUSED,
    ICON_SIZE,
    TRAY_ICON_MARGIN,
)


def _make_icon_image(color: tuple) -> Image.Image:
    """Create a circular tray icon image using the given RGB color."""
    image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), ICON_COLOR_BG)
    draw = ImageDraw.Draw(image)
    draw.ellipse(
        (TRAY_ICON_MARGIN, TRAY_ICON_MARGIN, ICON_SIZE - TRAY_ICON_MARGIN, ICON_SIZE - TRAY_ICON_MARGIN),
        fill=(*color, 255),
    )
    return image


def _icon_title(status: str, ascii_only: bool = False) -> str:
    separator = "-" if ascii_only else "—"
    return f"{APP_NAME} {separator} {status}"


def build_tray(controller) -> pystray.Icon:
    """Build and return the tray icon for the gesture controller."""
    state = {"paused": False}
    state_lock = threading.Lock()

    def set_title(icon, status: str):
        try:
            icon.title = _icon_title(status)
        except UnicodeEncodeError:
            icon.title = _icon_title(status, ascii_only=True)

    def toggle(icon, item):
        with state_lock:
            if state["paused"] is True:
                controller.resume()
                state["paused"] = False
                icon.icon = _make_icon_image(ICON_COLOR_ACTIVE)
                set_title(icon, "Active")
            else:
                controller.pause()
                state["paused"] = True
                icon.icon = _make_icon_image(ICON_COLOR_PAUSED)
                set_title(icon, "Paused")

    def quit_app(icon, item):
        controller.stop()
        icon.stop()
        sys.exit(0)

    def toggle_label(item) -> str:
        with state_lock:
            return "Resume" if state["paused"] else "Pause"

    menu = pystray.Menu(
        pystray.MenuItem(toggle_label, toggle, default=True),
        pystray.MenuItem("Quit", quit_app),
    )

    try:
        icon = pystray.Icon(
            name=APP_NAME,
            icon=_make_icon_image(ICON_COLOR_ACTIVE),
            title=_icon_title("Active"),
            menu=menu,
        )
    except UnicodeEncodeError:
        icon = pystray.Icon(
            name=APP_NAME,
            icon=_make_icon_image(ICON_COLOR_ACTIVE),
            title=_icon_title("Active", ascii_only=True),
            menu=menu,
        )
    return icon


class _GtkTrayIcon:
    """GTK tray adapter that prefers AppIndicator and falls back to StatusIcon."""

    def __init__(self, controller):
        import dbus
        import gi

        dbus.SessionBus()
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        self._Gtk = Gtk
        self._controller = controller
        self._state = {"paused": False}
        self._state_lock = threading.Lock()
        self._temp_dir = TemporaryDirectory(prefix="gestureslides-tray-")
        self._cleanup_done = False
        self._toggle_item = Gtk.MenuItem(label="Pause")
        self._toggle_item.connect("activate", self._toggle)
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self._quit)

        self._menu = Gtk.Menu()
        self._menu.append(self._toggle_item)
        self._menu.append(quit_item)
        self._menu.show_all()
        self._icon_paths = {
            "active": self._write_icon("active", ICON_COLOR_ACTIVE),
            "paused": self._write_icon("paused", ICON_COLOR_PAUSED),
        }
        self._backend_name = None
        self._indicator = None
        self._status_icon = None
        self._build_backend()

    def _write_icon(self, stem: str, color: tuple) -> str:
        path = Path(self._temp_dir.name) / f"{stem}.png"
        _make_icon_image(color).save(path)
        return str(path)

    def _build_backend(self):
        appindicator_error = None
        try:
            self._build_appindicator()
            return
        except Exception as exc:
            appindicator_error = exc

        try:
            self._build_status_icon()
            return
        except Exception as exc:
            raise RuntimeError(
                "AppIndicator and GTK StatusIcon backends are unavailable "
                f"({appindicator_error}; {exc})"
            ) from exc

    def _build_appindicator(self):
        import gi

        appindicator_module = None
        last_error = None
        for namespace in ("AyatanaAppIndicator3", "AppIndicator3"):
            try:
                gi.require_version(namespace, "0.1")
                if namespace == "AyatanaAppIndicator3":
                    from gi.repository import AyatanaAppIndicator3 as appindicator_module
                else:
                    from gi.repository import AppIndicator3 as appindicator_module
                break
            except Exception as exc:
                last_error = exc

        if appindicator_module is None:
            raise RuntimeError(f"no AppIndicator module found: {last_error}")

        self._indicator = appindicator_module.Indicator.new(
            APP_NAME,
            self._icon_paths["active"],
            appindicator_module.IndicatorCategory.APPLICATION_STATUS,
        )
        self._indicator.set_status(appindicator_module.IndicatorStatus.ACTIVE)
        self._indicator.set_menu(self._menu)
        self._indicator.set_icon_full(self._icon_paths["active"], APP_NAME)
        if hasattr(self._indicator, "set_title"):
            self._indicator.set_title(APP_NAME)
        self._backend_name = "appindicator"

    def _build_status_icon(self):
        self._status_icon = self._Gtk.StatusIcon.new_from_file(self._icon_paths["active"])
        self._status_icon.set_visible(True)
        if hasattr(self._status_icon, "set_title"):
            self._status_icon.set_title(APP_NAME)
        self._status_icon.connect("activate", self._toggle)
        self._status_icon.connect("popup-menu", self._show_menu)
        self._backend_name = "gtk-statusicon"

    def _show_menu(self, icon, button, activate_time):
        self._menu.popup(None, None, None, None, button, activate_time)

    def _set_icon(self, key: str):
        if self._indicator is not None:
            self._indicator.set_icon_full(self._icon_paths[key], APP_NAME)
        if self._status_icon is not None:
            self._status_icon.set_from_file(self._icon_paths[key])

    def _toggle(self, *args):
        with self._state_lock:
            paused = not self._state["paused"]
            self._state["paused"] = paused
            self._toggle_item.set_label("Resume" if paused else "Pause")
            if paused:
                self._controller.pause()
                self._set_icon("paused")
            else:
                self._controller.resume()
                self._set_icon("active")

    def _quit(self, *args):
        self._controller.stop()
        self.stop()

    def run(self):
        self._Gtk.main()

    def stop(self):
        if self._status_icon is not None:
            self._status_icon.set_visible(False)
        if self._Gtk.main_level():
            self._Gtk.main_quit()
        if not self._cleanup_done:
            self._cleanup_done = True
            self._temp_dir.cleanup()


def build_gtk_tray(controller):
    """Build and return the GTK/AppIndicator tray backend."""
    return _GtkTrayIcon(controller)
