"""
GDriveSync Main Application Window
Modern Libadwaita window matching the official Google Drive client on Windows/macOS.
Displays account storage quota, live sync status, recent activity feed, and quick controls.
"""

import datetime
import os
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Optional

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio

from gdrive_sync.config import config
from gdrive_sync.engine.rclone_manager import rclone_mgr
from gdrive_sync.engine.stream_service import stream_service
from gdrive_sync.engine.mirror_service import mirror_service
from gdrive_sync.ui.preferences_dialog import PreferencesDialog
from gdrive_sync.ui.oauth_dialog import OAuthDialog


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("Google Drive")
        self.set_default_size(460, 680)
        self.set_resizable(False)

        self.current_speed = 0.0
        self.current_transferring = []

        self._setup_window_actions()
        self._build_ui()
        self._bind_services()
        self.connect("close-request", self._on_close_request)
        self.refresh_state()

    def _build_ui(self):
        self.add_css_class("gdrive-window")

        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        # 1. Top Header Bar
        header = Adw.HeaderBar()
        header.set_show_title(False)

        # App branding title in header
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        logo_img = Gtk.Image.new_from_icon_name("google-drive")
        logo_img.set_pixel_size(24)
        title_lbl = Gtk.Label(label="Google Drive")
        title_lbl.set_css_classes(["title-3", "heading"])
        title_box.append(logo_img)
        title_box.append(title_lbl)
        header.set_title_widget(title_box)

        # Menu Button (Options & Quit)
        menu = Gio.Menu()
        menu.append("Preferences", "win.preferences")
        menu.append("Open Drive Folder", "win.open_folder")
        menu.append("Google Drive on Web", "win.open_web")

        section_exit = Gio.Menu()
        section_exit.append("Hide to Background", "win.hide_window")
        section_exit.append("Quit Google Drive", "win.quit_app")
        menu.append_section(None, section_exit)

        menu_btn = Gtk.MenuButton(icon_name="view-more-symbolic")
        menu_btn.set_menu_model(menu)
        menu_btn.set_tooltip_text("Menu")
        header.pack_end(menu_btn)

        # Gear / Settings button
        gear_btn = Gtk.Button(icon_name="emblem-system-symbolic")
        gear_btn.set_tooltip_text("Google Drive Preferences")
        gear_btn.connect("clicked", self._open_preferences)
        header.pack_end(gear_btn)

        toolbar_view.add_top_bar(header)

        # 2. Main content container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # 2.1 User Profile & Storage Bar Card
        self.profile_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.profile_box.set_css_classes(["gdrive-header"])

        user_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.avatar = Adw.Avatar(size=36, show_initials=True)
        user_row.append(self.avatar)

        name_email_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        name_email_box.set_hexpand(True)
        self.name_lbl = Gtk.Label(label="Google Drive User", xalign=0)
        self.name_lbl.set_css_classes(["heading"])
        self.email_lbl = Gtk.Label(label="user@gmail.com", xalign=0)
        self.email_lbl.set_css_classes(["dim-label", "caption"])
        name_email_box.append(self.name_lbl)
        name_email_box.append(self.email_lbl)
        user_row.append(name_email_box)

        # Account connect / switch button
        self.auth_btn = Gtk.Button(label="Account")
        self.auth_btn.set_css_classes(["flat", "pill"])
        self.auth_btn.connect("clicked", self._open_auth_dialog)
        user_row.append(self.auth_btn)
        self.profile_box.append(user_row)

        # Storage Progress Bar
        quota_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.quota_bar = Gtk.ProgressBar()
        self.quota_bar.set_css_classes(["quota-bar"])
        self.quota_lbl = Gtk.Label(label="Calculating storage...", xalign=0)
        self.quota_lbl.set_css_classes(["caption", "dim-label"])
        quota_box.append(self.quota_bar)
        quota_box.append(self.quota_lbl)
        self.profile_box.append(quota_box)

        main_box.append(self.profile_box)

        # 2.2 Hero Status Card (Everything is up to date / Syncing...)
        self.status_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        self.status_card.set_css_classes(["hero-status-card"])

        self.status_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
        self.status_icon.set_pixel_size(28)
        self.status_card.append(self.status_icon)

        status_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        status_text_box.set_hexpand(True)
        self.status_title = Gtk.Label(label="Everything is up to date", xalign=0)
        self.status_title.set_css_classes(["status-title"])
        self.status_sub = Gtk.Label(label="Stream mode • On-demand virtual mount", xalign=0)
        self.status_sub.set_css_classes(["status-subtitle"])
        status_text_box.append(self.status_title)
        status_text_box.append(self.status_sub)
        self.status_card.append(status_text_box)

        self.mode_badge = Gtk.Label(label="STREAM")
        self.mode_badge.set_css_classes(["mode-badge"])
        self.status_card.append(self.mode_badge)

        main_box.append(self.status_card)

        # 2.3 Stack & Switcher (Activity & Notifications)
        self.stack = Adw.ViewStack()
        
        # Activity Tab
        self.activity_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.activity_list = Gtk.ListBox()
        self.activity_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.activity_list.set_css_classes(["boxed-list-separate"])

        activity_scroll = Gtk.ScrolledWindow()
        activity_scroll.set_vexpand(True)
        activity_scroll.set_child(self.activity_list)
        self.activity_page.append(activity_scroll)

        self.stack.add_titled_with_icon(self.activity_page, "activity", "Activity", "document-open-recent-symbolic")

        # Notifications Tab
        self.notif_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.notif_page.set_margin_top(16)
        self.notif_page.set_margin_start(16)
        self.notif_page.set_margin_end(16)
        self.notif_label = Gtk.Label(label="No new notifications.\nAll files are synced safely to Google Drive.", xalign=0.5)
        self.notif_label.set_justify(Gtk.Justification.CENTER)
        self.notif_label.set_css_classes(["dim-label"])
        self.notif_page.append(self.notif_label)
        self.stack.add_titled_with_icon(self.notif_page, "notifications", "Notifications", "preferences-system-notifications-symbolic")

        view_switcher = Adw.ViewSwitcher(stack=self.stack)
        view_switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        main_box.append(view_switcher)
        main_box.append(self.stack)

        toolbar_view.set_content(main_box)

        # 3. Bottom Action Bar
        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_bar.set_css_classes(["action-bar"])

        # Open Drive Folder Button
        self.open_folder_btn = Gtk.Button()
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        folder_icon = Gtk.Image.new_from_icon_name("folder-symbolic")
        self.open_folder_lbl = Gtk.Label(label="Open Drive Folder")
        btn_box.append(folder_icon)
        btn_box.append(self.open_folder_lbl)
        self.open_folder_btn.set_child(btn_box)
        self.open_folder_btn.set_css_classes(["primary-drive-button"])
        self.open_folder_btn.set_hexpand(True)
        self.open_folder_btn.connect("clicked", self._open_drive_folder)
        action_bar.append(self.open_folder_btn)

        # Google Drive Web Link Button
        web_btn = Gtk.Button(icon_name="web-browser-symbolic")
        web_btn.set_tooltip_text("Open Google Drive in Browser")
        web_btn.connect("clicked", lambda b: webbrowser.open("https://drive.google.com"))
        action_bar.append(web_btn)

        # Pause / Resume Sync Toggle Button
        self.pause_btn = Gtk.Button(icon_name="media-playback-pause-symbolic")
        self.pause_btn.set_tooltip_text("Pause syncing")
        self.pause_btn.connect("clicked", self._toggle_pause_sync)
        action_bar.append(self.pause_btn)

        toolbar_view.add_bottom_bar(action_bar)

    def _bind_services(self):
        # Register callbacks for transfer updates
        stream_service.add_stats_callback(self._on_engine_stats_update)
        mirror_service.add_stats_callback(self._on_engine_stats_update)

    def _on_engine_stats_update(self, stats):
        GLib.idle_add(self._update_stats_ui, stats)

    def _update_stats_ui(self, stats):
        status = stats.get("status", "idle")
        speed = stats.get("speed", 0.0)
        transferring = stats.get("transferring", [])

        if status == "syncing":
            speed_str = f"{speed / (1024 * 1024):.1f} MB/s" if speed > 1024 * 1024 else f"{speed / 1024:.0f} KB/s"
            num_files = len(transferring) or 1
            self.status_title.set_text(f"Syncing {num_files} item{'s' if num_files > 1 else ''}...")
            self.status_sub.set_text(f"Transfer speed: {speed_str}")
            self.status_icon.set_from_icon_name("software-update-available-symbolic")
        elif status == "paused":
            self.status_title.set_text("Syncing is paused")
            self.status_sub.set_text("Click resume to continue synchronization")
            self.status_icon.set_from_icon_name("media-playback-pause-symbolic")
        else:
            mode = config.get("sync_mode", "stream")
            self.status_title.set_text("Everything is up to date")
            if mode == "stream":
                comp_count = len(config.get("other_computers", []))
                if config.get("include_other_computers", True) and comp_count > 0:
                    self.status_sub.set_text(f"Stream mode • My Drive and {comp_count} other computer{'s' if comp_count > 1 else ''}")
                else:
                    self.status_sub.set_text(f"Stream mode • {config.get('stream_mount_path')}")
            else:
                self.status_sub.set_text(f"Mirror mode • {config.get('mirror_local_path')}")
            self.status_icon.set_from_icon_name("emblem-ok-symbolic")

    def refresh_state(self):
        """Update user profile, storage, mode badges, and recent activity feed."""
        # Account info
        email = config.get("account_email")
        name = config.get("account_name") or "Google Drive"
        if email:
            self.name_lbl.set_text(name)
            self.email_lbl.set_text(email)
            self.avatar.set_text(name)
            self.auth_btn.set_label("Account")
        else:
            self.name_lbl.set_text("Not Connected")
            self.email_lbl.set_text("Click to sign in with Google")
            self.avatar.set_text("GD")
            self.auth_btn.set_label("Sign In")

        # Quota
        used = config.get("quota_used_bytes", 0)
        total = config.get("quota_total_bytes", 15 * 1024 * 1024 * 1024)
        fraction = min(1.0, used / max(1, total))
        self.quota_bar.set_fraction(fraction)
        used_gb = used / (1024 ** 3)
        total_gb = total / (1024 ** 3)
        self.quota_lbl.set_text(f"{used_gb:.1f} GB of {total_gb:.1f} GB used ({(fraction * 100):.1f}%)")

        # Mode
        mode = config.get("sync_mode", "stream")
        if mode == "stream":
            self.mode_badge.set_text("STREAM")
            self.open_folder_lbl.set_text("Open Virtual Drive")
            comp_count = len(config.get("other_computers", []))
            if config.get("include_other_computers", True) and comp_count > 0:
                self.status_sub.set_text(f"Stream mode • My Drive and {comp_count} other computer{'s' if comp_count > 1 else ''}")
            else:
                self.status_sub.set_text(f"Stream mode • {config.get('stream_mount_path')}")
        else:
            self.mode_badge.set_text("MIRROR")
            self.open_folder_lbl.set_text("Open Synced Folder")
            self.status_sub.set_text(f"Mirror mode • {config.get('mirror_local_path')}")

        # Pause button
        is_paused = config.get("is_paused", False)
        if is_paused:
            self.pause_btn.set_icon_name("media-playback-start-symbolic")
            self.pause_btn.set_tooltip_text("Resume syncing")
            self.status_title.set_text("Syncing is paused")
        else:
            self.pause_btn.set_icon_name("media-playback-pause-symbolic")
            self.pause_btn.set_tooltip_text("Pause syncing")

        # Refresh Activity list
        self._populate_activity_feed()

    def _populate_activity_feed(self):
        # Clear existing items
        while True:
            row = self.activity_list.get_row_at_index(0)
            if row is None:
                break
            self.activity_list.remove(row)

        items = config.get("recent_activity", [])
        if not items:
            empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            empty_box.set_margin_top(40)
            empty_box.set_margin_bottom(40)
            empty_icon = Gtk.Image.new_from_icon_name("folder-saved-search-symbolic")
            empty_icon.set_pixel_size(48)
            empty_lbl = Gtk.Label(label="No recent file sync activity.")
            empty_lbl.set_css_classes(["dim-label"])
            empty_box.append(empty_icon)
            empty_box.append(empty_lbl)
            self.activity_list.append(empty_box)
            return

        for item in items[:40]:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_css_classes(["activity-row"])

            # File icon based on extension or action
            name = item.get("name", "File")
            action = item.get("action", "sync")
            icon_name = "text-x-generic-symbolic"
            if name.lower().endswith((".pdf", ".doc", ".docx")):
                icon_name = "x-office-document-symbolic"
            elif name.lower().endswith((".xls", ".xlsx", ".csv")):
                icon_name = "x-office-spreadsheet-symbolic"
            elif name.lower().endswith((".png", ".jpg", ".jpeg", ".svg")):
                icon_name = "image-x-generic-symbolic"
            elif name.lower().endswith((".mp4", ".mkv", ".mov")):
                icon_name = "video-x-generic-symbolic"

            file_img = Gtk.Image.new_from_icon_name(icon_name)
            file_img.set_pixel_size(24)
            box.append(file_img)

            # Details
            detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            detail_box.set_hexpand(True)
            name_lbl = Gtk.Label(label=name, xalign=0)
            name_lbl.set_css_classes(["activity-title"])

            ts = item.get("time", int(time.time()))
            time_str = self._format_relative_time(ts)
            size = item.get("size", 0)
            size_str = f"{size / (1024*1024):.1f} MB" if size > 1024*1024 else (f"{size / 1024:.0f} KB" if size > 0 else "")
            action_desc = "Uploaded" if action == "upload" else ("Downloaded" if action == "download" else "Synced")
            meta_str = f"{action_desc} • {time_str}" + (f" • {size_str}" if size_str else "")

            meta_lbl = Gtk.Label(label=meta_str, xalign=0)
            meta_lbl.set_css_classes(["activity-meta"])

            detail_box.append(name_lbl)
            detail_box.append(meta_lbl)
            box.append(detail_box)

            # Action: Open in file manager
            open_item_btn = Gtk.Button(icon_name="document-open-symbolic")
            open_item_btn.set_tooltip_text("Open in folder")
            open_item_btn.set_css_classes(["flat", "circular"])
            rel_path = item.get("path", name)
            open_item_btn.connect("clicked", lambda b, p=rel_path: self._open_item_in_folder(p))
            box.append(open_item_btn)

            row.set_child(box)
            self.activity_list.append(row)

    def _format_relative_time(self, timestamp: int) -> str:
        diff = int(time.time()) - timestamp
        if diff < 60:
            return "just now"
        elif diff < 3600:
            return f"{diff // 60}m ago"
        elif diff < 86400:
            return f"{diff // 3600}h ago"
        else:
            return f"{diff // 86400}d ago"

    def _open_drive_folder(self, btn):
        mode = config.get("sync_mode", "stream")
        folder = config.get("stream_mount_path") if mode == "stream" else config.get("mirror_local_path")
        path = Path(folder).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            print(f"Error opening folder: {e}")

    def _open_item_in_folder(self, rel_path: str):
        mode = config.get("sync_mode", "stream")
        base = config.get("stream_mount_path") if mode == "stream" else config.get("mirror_local_path")
        full_path = (Path(base) / rel_path).resolve()
        parent_dir = full_path.parent if full_path.exists() else Path(base)
        try:
            subprocess.Popen(["xdg-open", str(parent_dir)])
        except Exception:
            pass

    def _toggle_pause_sync(self, btn):
        paused = not config.get("is_paused", False)
        config.set("is_paused", paused)
        self.refresh_state()

    def _open_preferences(self, btn):
        dialog = PreferencesDialog(self, on_settings_changed_callback=self._on_settings_applied)
        dialog.present()

    def _open_auth_dialog(self, btn):
        dialog = OAuthDialog(self, on_auth_complete_callback=lambda d: self.refresh_state())
        dialog.present()

    def _on_settings_applied(self):
        self.refresh_state()
        # Restart or switch active service
        self.get_application().sync_engine_restart()

    def _setup_window_actions(self):
        actions = [
            ("preferences", lambda a, p: self._open_preferences(None)),
            ("open_folder", lambda a, p: self._open_drive_folder(None)),
            ("open_web", lambda a, p: webbrowser.open("https://drive.google.com")),
            ("hide_window", lambda a, p: self.set_visible(False)),
            ("quit_app", lambda a, p: self.get_application().quit_application())
        ]
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    def _on_close_request(self, window):
        if config.get("minimize_to_tray", True):
            self.set_visible(False)
            return True  # Keep application running in background
        return False
