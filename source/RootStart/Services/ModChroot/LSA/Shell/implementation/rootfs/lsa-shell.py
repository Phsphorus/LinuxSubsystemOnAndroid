#!/usr/bin/env python3
"""LSA's first Debian-side X11 phone shell."""

from __future__ import annotations

import configparser
import datetime
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

try:
    from Xlib import X, XK, display, protocol
    from Xlib.ext import xtest
except ImportError:
    X = XK = display = protocol = xtest = None


TOP, BOTTOM = 52, 86
WM_CLASS, WM_INSTANCE = "LSAShell", "lsa-shell"
SHELL_ROOT = "/usr/local/lib/lsa/shell"
WALLPAPER = SHELL_ROOT + "/assets/lsa-wallpaper-v1.png"
CSS = b"""
window.surface { background: transparent; color: #f8fbff; font-family: Sans; }
window.tasksurface, window.librarysurface { background: #111827; color: #f8fbff; font-family: Sans; }
.top, .bottom { background-color: rgba(5, 9, 20, 0.92); border-color: rgba(255, 255, 255, 0.18); border-style: solid; }
.top { border-bottom-width: 1px; } .bottom { border-top-width: 1px; }
.status { color: #f8fbff; font-size: 13px; font-weight: bold; padding: 0 9px; }
.title { color: #f8fbff; font-size: 29px; font-weight: bold; }
.detail, .notice { color: #c7d2e5; font-size: 14px; }
button.app { background-color: transparent; background-image: none; border: none; box-shadow: none; outline: none; border-radius: 16px; color: #f8fbff; font-size: 13px; font-weight: bold; min-height: 108px; padding: 4px; }
button.app:hover, button.app:active { background-image: none; border: none; box-shadow: none; outline: none; background-color: rgba(255, 255, 255, 0.16); }
button.app:focus { background-image: none; border: none; box-shadow: none; outline: none; background-color: transparent; }
.icon { color: #fff; font-size: 26px; font-weight: bold; border-radius: 19px; min-width: 68px; min-height: 68px; }
.terminal { background: linear-gradient(145deg, #243759, #121a2b); }
.firefox { background: linear-gradient(145deg, #ef7841, #b63272); }
.files { background: linear-gradient(145deg, #4b9aec, #2759b5); }
.tasks { background: linear-gradient(145deg, #725ee8, #3d318f); }
.camera { background: linear-gradient(145deg, #3eaf9e, #1b6f70); }
.record { background: linear-gradient(145deg, #e96172, #a82545); }
.settings { background: linear-gradient(145deg, #78859e, #37435b); }
.add { background-color: rgba(10, 17, 35, 0.56); border: 1px dashed rgba(255, 255, 255, 0.75); }
.user { background: linear-gradient(145deg, #58657f, #263042); }
.app-label { color: #f8fbff; font-size: 13px; font-weight: bold; padding-top: 5px; text-shadow: 0 1px 2px #000; }
button.status-control { background-color: transparent; background-image: none; border: 0; box-shadow: none; outline: none; color: #f8fbff; font-size: 13px; font-weight: bold; padding: 0 9px; }
button.status-control:hover { background-color: rgba(255, 255, 255, 0.08); }
button.status-control:focus, button.status-control:active { background-color: transparent; background-image: none; border: 0; box-shadow: none; outline: none; }
button.nav { background-color: transparent; background-image: none; border: 0; box-shadow: none; color: #f8fbff; font-size: 14px; font-weight: bold; min-height: 72px; }
button.nav:hover, button.nav:active { background-color: rgba(255, 255, 255, 0.13); }
button.nav:focus { background-color: transparent; background-image: none; border: 0; box-shadow: none; outline: none; }
button.task { background: #f8fbff; border: 0; border-radius: 12px; color: #111827; font-size: 16px; min-height: 84px; }
button.close { background: #f8fbff; border: 0; border-radius: 10px; color: #111827; font-size: 20px; font-weight: bold; min-height: 48px; min-width: 48px; }
button.library-add, button.library-home { background: #273a62; border: 0; border-radius: 10px; color: #f8fbff; font-size: 13px; font-weight: bold; min-height: 40px; padding: 4px 12px; }
button.library-add:hover, button.library-home:hover { background: #385184; }
.library-card { background: #1b273d; border-radius: 14px; padding: 12px; }
.library-name { color: #f8fbff; font-size: 15px; font-weight: bold; }
.library-detail { color: #b7c5dd; font-size: 12px; }
menu { background-color: #111827; color: #f8fbff; border: 1px solid rgba(255, 255, 255, 0.22); }
menuitem { color: #f8fbff; padding: 10px 18px; }
menuitem:hover { background-color: #385184; }
"""


@dataclass(frozen=True)
class Client:
    xid: int
    title: str
    wm_class: str


class WindowController:
    def __init__(self) -> None:
        self.dpy = self.root = None
        self.atom: dict[str, int] = {}
        if display is None:
            return
        try:
            self.dpy = display.Display()
            self.root = self.dpy.screen().root
            for name in ("_NET_CLIENT_LIST", "_NET_ACTIVE_WINDOW", "_NET_WM_NAME",
                         "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_DOCK",
                         "_NET_WM_WINDOW_TYPE_DESKTOP", "WM_PROTOCOLS", "WM_DELETE_WINDOW"):
                self.atom[name] = self.dpy.intern_atom(name, only_if_exists=False)
        except Exception:
            self.dpy = self.root = None

    @property
    def available(self) -> bool:
        return self.dpy is not None and self.root is not None

    def prop(self, window, name: str):
        if not self.available:
            return None
        try:
            return window.get_full_property(self.atom[name], X.AnyPropertyType)
        except Exception:
            return None

    def clients(self) -> list[Client]:
        prop = self.prop(self.root, "_NET_CLIENT_LIST") if self.available else None
        if prop is None:
            return []
        result: list[Client] = []
        ignored = {self.atom["_NET_WM_WINDOW_TYPE_DOCK"], self.atom["_NET_WM_WINDOW_TYPE_DESKTOP"]}
        for xid in prop.value:
            try:
                window = self.dpy.create_resource_object("window", int(xid))
                if WM_CLASS in (window.get_wm_class() or ()):
                    continue
                types = self.prop(window, "_NET_WM_WINDOW_TYPE")
                if types is not None and set(int(x) for x in types.value) & ignored:
                    continue
                title = self.prop(window, "_NET_WM_NAME")
                title = bytes(title.value).decode("utf-8", "replace").rstrip("\0") if title else ""
                wm_class = " / ".join(filter(None, window.get_wm_class() or ())) or "X11 app"
                result.append(Client(int(xid), title or window.get_wm_name() or wm_class, wm_class))
            except Exception:
                continue
        return result

    def active(self) -> Optional[int]:
        prop = self.prop(self.root, "_NET_ACTIVE_WINDOW") if self.available else None
        return int(prop.value[0]) if prop is not None and len(prop.value) else None

    def focus(self, xid: int) -> bool:
        if not self.available:
            return False
        try:
            window = self.dpy.create_resource_object("window", xid)
            event = protocol.event.ClientMessage(window=window, client_type=self.atom["_NET_ACTIVE_WINDOW"],
                data=(32, [2, X.CurrentTime, 0, 0, 0]))
            self.root.send_event(event, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
            self.dpy.flush()
            return True
        except Exception:
            return False

    def close(self, xid: int) -> bool:
        if not self.available:
            return False
        try:
            window = self.dpy.create_resource_object("window", xid)
            event = protocol.event.ClientMessage(window=window, client_type=self.atom["WM_PROTOCOLS"],
                data=(32, [self.atom["WM_DELETE_WINDOW"], X.CurrentTime, 0, 0, 0]))
            window.send_event(event, event_mask=0)
            self.dpy.flush()
            return True
        except Exception:
            return False

    def alt_left(self) -> bool:
        """Send the standard browser-style Back shortcut to the focused app."""
        if not self.available or xtest is None or XK is None:
            return False
        try:
            alt = self.dpy.keysym_to_keycode(XK.string_to_keysym("Alt_L"))
            left = self.dpy.keysym_to_keycode(XK.string_to_keysym("Left"))
            if not alt or not left:
                return False
            xtest.fake_input(self.dpy, X.KeyPress, alt)
            xtest.fake_input(self.dpy, X.KeyPress, left)
            xtest.fake_input(self.dpy, X.KeyRelease, left)
            xtest.fake_input(self.dpy, X.KeyRelease, alt)
            self.dpy.sync()
            return True
        except Exception:
            return False


class Shell:
    def __init__(self) -> None:
        self.screen = Gdk.Screen.get_default()
        if self.screen is None:
            raise RuntimeError("no X11 screen is available")
        self.width, self.height = self.screen.get_width(), self.screen.get_height()
        # Termux:X11 can initially report a transient surface while Android is
        # attaching or rotating the activity.  This shell owns fixed-position
        # phone chrome, so retaining that first geometry leaves the home view
        # and navigator clipped after the real surface arrives.  Re-exec once
        # the display size settles; existing applications remain untouched.
        self.display_geometry = (self.width, self.height)
        self.geometry_restart_id: Optional[int] = None
        self.screen.connect("size-changed", self.screen_size_changed)
        self.app_columns = 4 if self.width >= 420 else 3
        self.control = WindowController()
        self.snapshots: dict[int, object] = {}
        self.back_target: Optional[int] = None
        config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        self.pinned_path = config_root / "lsa-shell" / "pinned-apps.json"
        self.desktop_apps = self.load_desktop_apps()
        self.pins = self.load_pins()
        self.pin_hold_timer = None
        self.pin_hold_app_id: Optional[str] = None

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            self.screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.home = self.make_home()
        self.overview = self.make_overview()
        self.library = self.make_library()
        self.top, self.bottom = self.make_top(), self.make_bottom()
        for window in (self.top, self.bottom):
            window.show_all()
            window.set_keep_above(True)
        self.show_home()
        GLib.timeout_add_seconds(1, self.tick)

    def window(self, hint, style: str) -> Gtk.Window:
        window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        window.set_wmclass(WM_INSTANCE, WM_CLASS)
        window.set_type_hint(hint)
        window.set_decorated(False)
        window.set_resizable(False)
        window.set_skip_taskbar_hint(True)
        window.set_skip_pager_hint(True)
        window.get_style_context().add_class(style)
        window.connect("delete-event", self.hide)
        return window

    @staticmethod
    def hide(window, _event) -> bool:
        window.hide()
        return True

    def screen_size_changed(self, _screen) -> None:
        """Recreate the fixed phone layout after a real X11 size change."""
        width, height = self.screen.get_width(), self.screen.get_height()
        if width <= 0 or height <= 0 or (width, height) == self.display_geometry:
            return
        if self.geometry_restart_id is not None:
            GLib.source_remove(self.geometry_restart_id)
        # Android may emit more than one resize while its X11 activity settles.
        # Waiting briefly makes one clean replacement at the final geometry.
        self.geometry_restart_id = GLib.timeout_add(350, self.restart_for_geometry)

    def restart_for_geometry(self) -> bool:
        self.geometry_restart_id = None
        width, height = self.screen.get_width(), self.screen.get_height()
        if width > 0 and height > 0 and (width, height) != self.display_geometry:
            os.execv(sys.executable, [sys.executable, *sys.argv])
        return False

    @staticmethod
    def text(text: str, style: str) -> Gtk.Label:
        label = Gtk.Label(label=text)
        label.set_xalign(0)
        label.get_style_context().add_class(style)
        return label

    @staticmethod
    def desktop_command(value: str, terminal: bool) -> tuple[str, ...]:
        try:
            parsed = shlex.split(value)
        except ValueError:
            return ()
        command = []
        for part in parsed:
            for field in ("%f", "%F", "%u", "%U", "%d", "%D", "%n", "%N",
                          "%i", "%c", "%k", "%v", "%m"):
                part = part.replace(field, "")
            if part:
                command.append(part)
        if not command:
            return ()
        if terminal:
            return ("lxterminal", "-e", " ".join(shlex.quote(part) for part in command))
        return tuple(command)

    def load_desktop_apps(self) -> dict[str, dict[str, object]]:
        # Later directories override distro entries with a user-installed
        # launcher of the same desktop-file id.
        roots = (
            Path("/usr/share/applications"),
            Path("/usr/local/share/applications"),
            Path.home() / ".local/share/applications",
        )
        apps: dict[str, dict[str, object]] = {}
        for root in roots:
            if not root.is_dir():
                continue
            for file in sorted(root.glob("*.desktop")):
                parser = configparser.ConfigParser(interpolation=None)
                parser.optionxform = str
                try:
                    parser.read(file, encoding="utf-8")
                except (OSError, configparser.Error):
                    continue
                if not parser.has_section("Desktop Entry"):
                    continue
                entry = parser["Desktop Entry"]
                if entry.get("Type", "Application") != "Application":
                    continue
                if entry.get("Hidden", "").casefold() == "true":
                    continue
                command = self.desktop_command(
                    entry.get("Exec", ""), entry.get("Terminal", "").casefold() == "true")
                if not command:
                    continue
                app_id = file.stem
                apps[app_id] = {
                    "name": entry.get("Name", app_id).strip() or app_id,
                    "icon": entry.get("Icon", "").strip(),
                    "command": command,
                    "source": str(file),
                }
        return dict(sorted(apps.items(), key=lambda item: (
            str(item[1]["name"]).casefold(), item[0])))

    def load_pins(self) -> list[str]:
        try:
            payload = json.loads(self.pinned_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(payload, list):
            return []
        pins: list[str] = []
        for app_id in payload:
            if isinstance(app_id, str) and app_id in self.desktop_apps and app_id not in pins:
                pins.append(app_id)
        return pins

    def save_pins(self) -> None:
        self.pinned_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.pinned_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.pins, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.pinned_path)

    @staticmethod
    def desktop_icon(icon_reference: object, size: int = 42) -> Gtk.Image:
        """Resolve a desktop-entry icon, including direct pixmap paths."""
        icon_name = str(icon_reference or "").strip()
        candidates = [Path(icon_name)] if icon_name else []
        if icon_name and not Path(icon_name).is_absolute():
            candidates.extend(
                Path("/usr/share/pixmaps") / (icon_name + suffix)
                for suffix in ("", ".png", ".svg", ".xpm")
            )
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                return Gtk.Image.new_from_pixbuf(
                    GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        str(candidate), size, size, True))
            except Exception:
                continue

        theme = Gtk.IconTheme.get_default()
        selected = icon_name if theme is not None and theme.has_icon(icon_name) else "application-x-executable"
        image = Gtk.Image.new_from_icon_name(selected, Gtk.IconSize.DIALOG)
        image.set_pixel_size(size)
        return image

    def make_top(self) -> Gtk.Window:
        window = self.window(Gdk.WindowTypeHint.DOCK, "top")
        window.set_size_request(self.width, TOP)
        window.move(0, 0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        home = Gtk.Button(label="LSA")
        home.get_style_context().add_class("status-control")
        home.connect("clicked", self.home_click)
        row.pack_start(home, True, True, 0)
        for value in ("LTE", "Wi-Fi", "Battery —"):
            row.pack_start(self.text(value, "status"), False, False, 0)
        self.clock = self.text("", "status")
        row.pack_start(self.clock, False, False, 0)
        window.add(row)
        return window

    def make_bottom(self) -> Gtk.Window:
        window = self.window(Gdk.WindowTypeHint.DOCK, "bottom")
        window.set_size_request(self.width, BOTTOM)
        window.move(0, self.height - BOTTOM)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        for label, callback in (("‹\nBack", self.back), ("○\nHome", self.home_click),
                                ("▣\nApps", self.apps_click)):
            button = Gtk.Button(label=label)
            button.get_style_context().add_class("nav")
            button.set_hexpand(True)
            button.connect("clicked", callback)
            row.pack_start(button, True, True, 0)
        window.add(row)
        return window

    def raise_chrome(self) -> bool:
        """Keep the status and navigation docks above each changing view."""
        for window in (self.top, self.bottom):
            window.show_all()
            window.set_keep_above(True)
            gdk_window = window.get_window()
            if gdk_window is not None:
                gdk_window.raise_()
        return False

    def make_home(self) -> Gtk.Window:
        window = self.window(Gdk.WindowTypeHint.NORMAL, "surface")
        window.set_title("LSA Home")
        content_height = self.height - TOP - BOTTOM
        window.set_size_request(self.width, content_height)
        window.move(0, TOP)

        overlay = Gtk.Overlay()
        overlay.add(self.wallpaper(content_height))
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        outer.set_border_width(16)
        self.notice = self.text("", "notice")
        self.notice.set_halign(Gtk.Align.CENTER)
        outer.pack_start(Gtk.Box(), True, True, 0)
        outer.pack_start(self.notice, False, False, 0)
        self.home_grid = Gtk.Grid(column_homogeneous=True, column_spacing=4, row_spacing=18)
        outer.pack_start(self.home_grid, False, False, 6)
        outer.pack_start(Gtk.Box(), True, True, 0)
        overlay.add_overlay(outer)
        window.add(overlay)
        self.refresh_home_grid()
        return window

    def wallpaper(self, height: int) -> Gtk.Image:
        try:
            image = Gtk.Image.new_from_pixbuf(
                GdkPixbuf.Pixbuf.new_from_file_at_scale(WALLPAPER, self.width, height, False))
        except Exception:
            image = Gtk.Image.new()
        image.set_hexpand(True)
        image.set_vexpand(True)
        return image

    def home_entries(self):
        entries = [
            ("Terminal", ">_", "terminal", ("lxterminal", "-e", "/bin/bash -l"), None, None),
            ("Firefox", "◉", "firefox", ("firefox",), None, None),
            ("Files", "▰", "files", ("pcmanfm",), None, None),
            ("Tasks", "▦", "tasks", None, self.apps_click, None),
            ("Camera", "◉", "camera",
             ("ffplay", "-loglevel", "warning", "-fflags", "nobuffer",
              "-flags", "low_delay", "-framedrop",
              "http://127.0.0.1:8765/camera.mjpg"), None, None),
            ("Recorder", "●", "record",
             ("lxterminal", "-e", "/usr/local/bin/lsa-record-video"), None, None),
            ("Settings", "⚙", "settings", ("lxappearance",), None, None),
            ("App library", "+", "add", None, self.show_library, None),
        ]
        for app_id in self.pins:
            app = self.desktop_apps.get(app_id)
            if app is None:
                continue
            entries.append((str(app["name"]), "▣", "user", tuple(app["command"]), None, app_id))
        return entries

    def refresh_home_grid(self) -> None:
        for child in self.home_grid.get_children():
            self.home_grid.remove(child)
        for index, (name, glyph, icon_style, command, callback, pinned_app_id) in enumerate(self.home_entries()):
            button = self.launcher_button(
                name, glyph, icon_style, command, callback, pinned_app_id)
            self.home_grid.attach(button, index % self.app_columns,
                                  index // self.app_columns, 1, 1)
        self.home_grid.show_all()

    def launcher_button(self, name: str, glyph: str, icon_style: str,
                        command: Optional[tuple[str, ...]], callback=None,
                        pinned_app_id: Optional[str] = None) -> Gtk.Button:
        button = Gtk.Button()
        button.get_style_context().add_class("app")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        icon = Gtk.Label(label=glyph)
        icon.set_size_request(68, 68)
        icon.set_halign(Gtk.Align.CENTER)
        icon.get_style_context().add_class("icon")
        icon.get_style_context().add_class(icon_style)
        label = Gtk.Label(label=name)
        label.set_halign(Gtk.Align.CENTER)
        label.set_ellipsize(3)
        label.get_style_context().add_class("app-label")
        content.pack_start(icon, False, False, 0)
        content.pack_start(label, False, False, 0)
        button.add(content)
        if pinned_app_id is not None and command:
            button.connect("button-press-event", self.pinned_button_press, pinned_app_id)
            button.connect("button-release-event", self.pinned_button_release, pinned_app_id)
            button.connect("clicked", self.launch_pinned, command, name, pinned_app_id)
        elif callback is not None:
            button.connect("clicked", callback)
        elif command:
            button.connect("clicked", self.launch, command, name)
        return button

    def pinned_button_press(self, button, event, app_id: str) -> bool:
        if event.button == 3:
            self.show_pinned_menu(button, app_id)
            return True
        if event.button != 1:
            return False
        if self.pin_hold_timer is not None:
            GLib.source_remove(self.pin_hold_timer)
        self.pin_hold_app_id = None
        self.pin_hold_timer = GLib.timeout_add(650, self.mark_pinned_hold, app_id)
        return False

    def mark_pinned_hold(self, app_id: str) -> bool:
        self.pin_hold_timer = None
        self.pin_hold_app_id = app_id
        return False

    def pinned_button_release(self, _button, event, app_id: str) -> bool:
        if event.button != 1:
            return False
        if self.pin_hold_timer is not None:
            GLib.source_remove(self.pin_hold_timer)
            self.pin_hold_timer = None
        if self.pin_hold_app_id == app_id:
            # The mouse/touch release that ends a hold also dismisses a GTK
            # menu opened during the press.  Open it on the following idle
            # turn so it remains available for the user to choose from.
            GLib.idle_add(self.show_pinned_menu, _button, app_id)
            return True
        return False

    def show_pinned_menu(self, button: Gtk.Button, app_id: str) -> bool:
        menu = Gtk.Menu()
        remove = Gtk.MenuItem.new_with_label("Remove from Home")
        remove.connect("activate", self.remove_pinned, app_id)
        remove.connect("button-release-event", self.remove_pinned_release, app_id)
        menu.append(remove)
        menu.connect("deactivate", lambda widget: widget.destroy())
        menu.show_all()
        if hasattr(menu, "popup_at_widget"):
            menu.popup_at_widget(button, Gdk.Gravity.SOUTH, Gdk.Gravity.NORTH, None)
        else:
            menu.popup(None, None, None, None, 0, Gtk.get_current_event_time())
        return False

    def remove_pinned_release(self, item, event, app_id: str) -> bool:
        # A touch release on a Gtk.MenuItem can deactivate its parent menu
        # before Gtk emits activate.  Remove immediately on that release too.
        if event.button == 1:
            parent = item.get_parent()
            if isinstance(parent, Gtk.Menu):
                parent.popdown()
            self.remove_pinned(item, app_id)
            return True
        return False

    def launch_pinned(self, button, command: tuple[str, ...], name: str, app_id: str) -> None:
        if self.pin_hold_app_id == app_id:
            self.pin_hold_app_id = None
            return
        self.launch(button, command, name)

    def remove_pinned(self, _item, app_id: str) -> None:
        app = self.desktop_apps.get(app_id)
        if app is None or app_id not in self.pins:
            return
        self.pins.remove(app_id)
        try:
            self.save_pins()
        except OSError as error:
            self.notice.set_text("Could not remove " + str(app["name"]) + ": " + str(error))
            return
        self.refresh_home_grid()
        self.refresh_library()
        self.show_home(message=str(app["name"]) + " removed from Home.")

    def make_overview(self) -> Gtk.Window:
        window = self.window(Gdk.WindowTypeHint.NORMAL, "tasksurface")
        window.set_title("LSA task view")
        window.set_size_request(self.width, self.height - TOP - BOTTOM)
        window.move(0, TOP)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.set_border_width(22)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.pack_start(self.text("Open apps", "title"), True, True, 0)
        home = Gtk.Button(label="Home")
        home.get_style_context().add_class("library-home")
        home.connect("clicked", self.home_click)
        header.pack_end(home, False, False, 0)
        outer.pack_start(header, False, False, 0)
        outer.pack_start(self.text(
            "Last-seen previews are captured when task view opens.", "detail"),
            False, False, 0)
        scroll = Gtk.ScrolledWindow()
        self.tasks = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        scroll.add(self.tasks)
        outer.pack_start(scroll, True, True, 0)
        window.add(outer)
        return window

    def make_library(self) -> Gtk.Window:
        window = self.window(Gdk.WindowTypeHint.NORMAL, "librarysurface")
        window.set_title("LSA App Library")
        window.set_size_request(self.width, self.height - TOP - BOTTOM)
        window.move(0, TOP)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.set_border_width(16)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        home = Gtk.Button(label="Home")
        home.get_style_context().add_class("library-home")
        home.connect("clicked", self.home_click)
        header.pack_start(home, False, False, 0)
        heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        heading.pack_start(self.text("App library", "title"), False, False, 0)
        heading.pack_start(self.text(
            "Choose an installed Debian application to add it to Home.",
            "detail"), False, False, 0)
        header.pack_start(heading, True, True, 0)
        outer.pack_start(header, False, False, 0)
        self.library_notice = self.text("", "notice")
        self.library_notice.set_halign(Gtk.Align.CENTER)
        outer.pack_start(self.library_notice, False, False, 0)
        self.library_query = ""
        search = Gtk.SearchEntry()
        search.set_placeholder_text("Search installed applications")
        search.connect("search-changed", self.filter_library)
        outer.pack_start(search, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.library_grid = Gtk.FlowBox()
        self.library_grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self.library_grid.set_max_children_per_line(2 if self.width >= 420 else 1)
        self.library_grid.set_row_spacing(10)
        self.library_grid.set_column_spacing(10)
        self.library_grid.set_valign(Gtk.Align.START)
        scroll.add(self.library_grid)
        outer.pack_start(scroll, True, True, 0)
        window.add(outer)
        self.refresh_library()
        return window

    def refresh_library(self) -> None:
        for child in self.library_grid.get_children():
            self.library_grid.remove(child)
        for app_id, app in self.desktop_apps.items():
            haystack = " ".join((app_id, str(app["name"]), str(app["source"]))).casefold()
            if self.library_query and self.library_query not in haystack:
                continue
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            card.get_style_context().add_class("library-card")
            card.set_size_request(max(190, (self.width - 58) // 2), -1)
            card.set_valign(Gtk.Align.START)
            card.set_vexpand(False)
            heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            icon = self.desktop_icon(app.get("icon"), 42)
            icon.set_valign(Gtk.Align.START)
            heading.pack_start(icon, False, False, 0)
            details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            name = self.text(str(app["name"]), "library-name")
            name.set_ellipsize(3)
            details.pack_start(name, False, False, 0)
            source = self.text(Path(str(app["source"])).name, "library-detail")
            source.set_ellipsize(3)
            details.pack_start(source, False, False, 0)
            heading.pack_start(details, True, True, 0)
            card.pack_start(heading, False, False, 0)
            add = Gtk.Button(label="Add to Home" if app_id not in self.pins else "Already on Home")
            add.get_style_context().add_class("library-add")
            add.connect("clicked", self.add_pinned, app_id)
            card.pack_start(add, False, False, 0)
            self.library_grid.add(card)
        self.library_grid.show_all()

    def filter_library(self, entry) -> None:
        self.library_query = entry.get_text().strip().casefold()
        self.refresh_library()

    def add_pinned(self, _button, app_id: str) -> None:
        app = self.desktop_apps.get(app_id)
        if app is None:
            return
        if app_id in self.pins:
            self.show_home(message=str(app["name"]) + " is already on Home.")
            return
        self.pins.append(app_id)
        try:
            self.save_pins()
        except OSError as error:
            self.library_notice.set_text("Could not save Home: " + str(error))
            return
        self.refresh_home_grid()
        self.refresh_library()
        self.show_home(message=str(app["name"]) + " added to Home.")

    def tick(self) -> bool:
        self.clock.set_text(datetime.datetime.now().strftime("%H:%M"))
        return True

    def clear_notice(self) -> bool:
        self.notice.set_text("")
        return False

    def show_home(self, _button=None, message: str = "") -> None:
        self.overview.hide()
        self.library.hide()
        self.notice.set_text(message)
        self.home.show_all()
        self.home.present()
        GLib.idle_add(self.raise_chrome)
        if message:
            GLib.timeout_add(2200, self.clear_notice)

    def home_click(self, _button) -> None:
        self.show_home()

    def show_library(self, _button) -> None:
        # Debian packages can add or replace .desktop files while the shell is
        # already running.  Read them when the library opens so there is no
        # need to restart the phone shell after an apt install.
        self.desktop_apps = self.load_desktop_apps()
        self.refresh_home_grid()
        self.refresh_library()
        self.home.hide()
        self.overview.hide()
        self.library_notice.set_text("")
        self.library.show_all()
        self.library.present()
        GLib.idle_add(self.raise_chrome)

    def apps_click(self, _button) -> None:
        self.home.hide()
        self.library.hide()
        GLib.timeout_add(120, self.show_overview_after_capture)

    def show_overview_after_capture(self) -> bool:
        self.capture_active()
        self.refresh()
        self.overview.show_all()
        self.overview.present()
        GLib.idle_add(self.raise_chrome)
        return False

    def capture_active(self) -> None:
        active = self.control.active()
        if active is None or active not in {client.xid for client in self.control.clients()}:
            return
        try:
            pixbuf = Gdk.pixbuf_get_from_window(
                self.screen.get_root_window(), 0, TOP, self.width, self.height - TOP - BOTTOM)
            if pixbuf is None:
                return
            scale = min(1.0, 180 / pixbuf.get_width(), 300 / pixbuf.get_height())
            preview = pixbuf.scale_simple(
                max(1, int(pixbuf.get_width() * scale)),
                max(1, int(pixbuf.get_height() * scale)),
                GdkPixbuf.InterpType.BILINEAR,
            )
            self.snapshots[active] = preview
        except Exception:
            return

    def launch(self, _button, command: tuple[str, ...], name: str) -> None:
        if shutil.which(command[0]) is None:
            self.notice.set_text(name + " is not installed in this Debian rootfs.")
            return
        try:
            subprocess.Popen(command, start_new_session=True, env=os.environ.copy())
            self.home.hide()
            self.library.hide()
        except OSError as error:
            self.notice.set_text("Could not launch " + name + ": " + str(error))

    def refresh(self) -> None:
        for child in self.tasks.get_children():
            self.tasks.remove(child)
        if not self.control.available:
            self.tasks.pack_start(self.text(
                "Task controls need python3-xlib. Home and app launch are ready.",
                "notice"), False, False, 4)
        else:
            clients = self.control.clients()
            if not clients:
                self.tasks.pack_start(
                    self.text("No application windows are open.", "notice"),
                    False, False, 4)
            for client in clients:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                task = Gtk.Button(label=client.title + "\n" + client.wm_class)
                task.get_style_context().add_class("task")
                preview = self.snapshots.get(client.xid)
                if preview is not None:
                    task.set_image(Gtk.Image.new_from_pixbuf(preview))
                    task.set_always_show_image(True)
                    task.set_image_position(Gtk.PositionType.LEFT)
                task.set_hexpand(True)
                task.connect("clicked", self.activate, client.xid)
                close = Gtk.Button(label="×")
                close.get_style_context().add_class("close")
                close.connect("clicked", self.close, client.xid)
                row.pack_start(task, True, True, 0)
                row.pack_end(close, False, False, 0)
                self.tasks.pack_start(row, False, False, 0)
        self.tasks.show_all()

    def activate(self, _button, xid: int) -> None:
        if self.control.focus(xid):
            self.overview.hide()

    def close(self, _button, xid: int) -> None:
        if self.control.close(xid):
            self.snapshots.pop(xid, None)
            GLib.timeout_add(200, self.close_refresh)

    def close_refresh(self) -> bool:
        self.refresh()
        return False

    # Kept for the upcoming gesture layer: Back maps to the normal
    # browser-style Alt+Left shortcut once an invisible gesture surface exists.
    def back(self, _button=None) -> None:
        active = self.control.active()
        clients = {client.xid for client in self.control.clients()}
        if active is None or active not in clients:
            self.show_home()
            return
        if not self.control.focus(active):
            return
        self.back_target = active
        GLib.timeout_add(80, self.send_back)

    def send_back(self) -> bool:
        target, self.back_target = self.back_target, None
        if target is not None:
            self.control.alt_left()
        return False

    def run(self) -> None:
        Gtk.main()

def main() -> int:
    try:
        Gtk.init([])
        Shell().run()
    except Exception as error:
        print("lsa-shell: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
