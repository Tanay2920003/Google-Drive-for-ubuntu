"""
GDriveSync - Google Drive Desktop for Linux
Main Application Entry Point (GTK 4 + Libadwaita)
"""

import os
import signal
import sys
from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, Gio, GLib

from gdrive_sync.config import config
from gdrive_sync.engine.rclone_manager import rclone_mgr
from gdrive_sync.engine.stream_service import stream_service
from gdrive_sync.engine.mirror_service import mirror_service
from gdrive_sync.ui.main_window import MainWindow
from gdrive_sync.ui.tray_indicator import TrayIndicator
from gdrive_sync.utils.bookmarks import bookmarks_mgr
from gdrive_sync.utils.desktop_entry import desktop_mgr


class GDriveSyncApplication(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="com.google.GDriveSync",
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        )
        self.window = None
        self.is_held = False
        self.tray_indicator = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        self._load_css()
        self._init_desktop_integration()
        self._setup_signal_handlers()

        # Keep application running in background even when window is closed/hidden
        self.hold()
        self.is_held = True

        # Start tray / status notifier item
        self.tray_indicator = TrayIndicator(on_activate=self._toggle_window_visibility)
        self.tray_indicator.start()

    def do_command_line(self, command_line):
        args = command_line.get_arguments()
        start_hidden = any(arg in args for arg in ["--hidden", "-h", "--background"])

        self._ensure_window_and_engine()

        if not start_hidden:
            self.window.set_visible(True)
            self.window.present()
        else:
            print("[GDriveSync] Running in background (hidden on startup).")
        return 0

    def do_activate(self):
        self._ensure_window_and_engine()
        self.window.set_visible(True)
        self.window.present()

    def _ensure_window_and_engine(self):
        if not self.window:
            if rclone_mgr.is_configured():
                import threading
                def fetch_profile():
                    rclone_mgr.update_user_info_from_drive_api()
                    if self.window:
                        GLib.idle_add(self.window.refresh_state)
                threading.Thread(target=fetch_profile, daemon=True).start()

            self.window = MainWindow(self)
            self.start_sync_engine()

    def _toggle_window_visibility(self):
        self._ensure_window_and_engine()
        if self.window.is_visible():
            self.window.set_visible(False)
        else:
            self.window.set_visible(True)
            self.window.present()

    def quit_application(self):
        self._handle_exit()

    def _load_css(self):
        css_file = Path(__file__).parent / "ui" / "style.css"
        if css_file.exists():
            provider = Gtk.CssProvider()
            provider.load_from_path(str(css_file))
            display = Gdk.Display.get_default()
            if display:
                Gtk.StyleContext.add_provider_for_display(
                    display,
                    provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )

    def _init_desktop_integration(self):
        """Setup Nautilus bookmarks and application launcher."""
        try:
            mode = config.get("sync_mode", "stream")
            path = config.get("stream_mount_path") if mode == "stream" else config.get("mirror_local_path")
            if config.get("bookmark_nautilus", True):
                bookmarks_mgr.update_bookmark(path, f"Google Drive ({mode.capitalize()})")
            
            desktop_mgr.install_application_launcher()
            if config.get("autostart", True):
                desktop_mgr.update_autostart(True)
        except Exception as e:
            print(f"[DesktopIntegration] Warning: {e}")

    def start_sync_engine(self):
        """Start the appropriate sync service based on the configured mode."""
        mode = config.get("sync_mode", "stream")
        print(f"[GDriveSync] Starting sync engine in {mode.upper()} mode...")

        if mode == "stream":
            mirror_service.stop()
            mount_point = config.get("stream_mount_path", str(Path.home() / "GoogleDrive"))
            stream_service.start(mount_point)
        else:
            stream_service.stop()
            local_path = config.get("mirror_local_path", str(Path.home() / "GoogleDrive_Mirror"))
            mirror_service.start(local_path)

    def sync_engine_restart(self):
        """Gracefully switch or restart engines when settings change."""
        self.start_sync_engine()

    def _setup_signal_handlers(self):
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

    def _handle_exit(self, signum=None, frame=None):
        print("\n[GDriveSync] Shutting down cleanly...")
        if hasattr(self, "tray_indicator") and self.tray_indicator:
            self.tray_indicator.stop()
        stream_service.stop()
        mirror_service.stop()
        if getattr(self, "is_held", False):
            self.release()
            self.is_held = False
        sys.exit(0)

    def do_shutdown(self):
        self._handle_exit()
        Adw.Application.do_shutdown(self)


def main():
    app = GDriveSyncApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
