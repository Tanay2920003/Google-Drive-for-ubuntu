"""
GDriveSync Preferences Dialog
Directly mirrors the Google Drive Preferences window on Windows/macOS.
Allows toggling between 'Stream files' and 'Mirror files', setting folders,
managing account, and configuring advanced options.
"""

import webbrowser
from pathlib import Path
from typing import Callable, Optional

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

from gdrive_sync.config import config
from gdrive_sync.engine.rclone_manager import rclone_mgr
from gdrive_sync.utils.bookmarks import bookmarks_mgr
from gdrive_sync.utils.desktop_entry import desktop_mgr


class PreferencesDialog(Adw.PreferencesWindow):
    def __init__(self, parent_window, on_settings_changed_callback: Optional[Callable] = None):
        super().__init__(transient_for=parent_window, modal=True)
        self.set_title("Google Drive Preferences")
        self.set_default_size(680, 600)
        self.on_settings_changed_callback = on_settings_changed_callback
        self.computer_rows = []

        self._build_pages()

    def _build_pages(self):
        # 1. Google Drive Sync Mode Page
        self.page_drive = Adw.PreferencesPage(title="Google Drive", icon_name="folder-remote-symbolic")
        self.add(self.page_drive)
        self._build_sync_mode_section()

        # 2. Other Computers Page
        self.page_computers = Adw.PreferencesPage(title="Computers", icon_name="computer-symbolic")
        self.add(self.page_computers)
        self._build_computers_section()

        # 3. Account Page
        self.page_account = Adw.PreferencesPage(title="Account", icon_name="avatar-default-symbolic")
        self.add(self.page_account)
        self._build_account_section()

        # 4. Settings & Advanced Page
        self.page_settings = Adw.PreferencesPage(title="Settings", icon_name="emblem-system-symbolic")
        self.add(self.page_settings)
        self._build_advanced_section()

    def _build_sync_mode_section(self):
        group = Adw.PreferencesGroup()
        group.set_title("My Drive Sync Options")
        group.set_description("Choose how files in your Google Drive appear and sync on this computer.")
        self.page_drive.add(group)

        current_mode = config.get("sync_mode", "stream")

        # STREAM FILES CARD
        self.stream_row = Adw.ActionRow(
            title="Stream files (Virtual Drive)",
            subtitle="Store files in the cloud only. Access on demand from your computer.\n• Saves local hard drive space\n• Files open and cache seamlessly"
        )
        self.stream_check = Gtk.CheckButton()
        self.stream_check.set_active(current_mode == "stream")
        self.stream_row.add_prefix(self.stream_check)
        self.stream_row.set_activatable_widget(self.stream_check)
        group.add(self.stream_row)

        # Stream folder setting
        self.stream_folder_row = Adw.EntryRow(title="Virtual Mount Folder")
        self.stream_folder_row.set_text(config.get("stream_mount_path", str(Path.home() / "GoogleDrive")))
        browse_stream_btn = Gtk.Button(icon_name="document-open-symbolic")
        browse_stream_btn.set_tooltip_text("Browse folder...")
        browse_stream_btn.connect("clicked", lambda b: self._browse_folder(self.stream_folder_row))
        self.stream_folder_row.add_suffix(browse_stream_btn)
        group.add(self.stream_folder_row)

        # Cache size row
        self.cache_spin = Adw.SpinRow.new_with_range(1, 100, 1)
        self.cache_spin.set_title("VFS Local Cache Limit (GB)")
        self.cache_spin.set_subtitle("Maximum disk space used for temporarily caching streamed files")
        self.cache_spin.set_value(config.get("cache_max_size_gb", 10))
        group.add(self.cache_spin)

        # MIRROR FILES CARD
        self.mirror_row = Adw.ActionRow(
            title="Mirror files (Two-Way Offline Sync)",
            subtitle="Store files both in the cloud and locally on this computer.\n• All files available offline\n• Changes sync automatically in both directions"
        )
        self.mirror_check = Gtk.CheckButton()
        self.mirror_check.set_group(self.stream_check)
        self.mirror_check.set_active(current_mode == "mirror")
        self.mirror_row.add_prefix(self.mirror_check)
        self.mirror_row.set_activatable_widget(self.mirror_check)
        group.add(self.mirror_row)

        # Mirror folder setting
        self.mirror_folder_row = Adw.EntryRow(title="Local Mirror Folder")
        self.mirror_folder_row.set_text(config.get("mirror_local_path", str(Path.home() / "GoogleDrive_Mirror")))
        browse_mirror_btn = Gtk.Button(icon_name="document-open-symbolic")
        browse_mirror_btn.set_tooltip_text("Browse folder...")
        browse_mirror_btn.connect("clicked", lambda b: self._browse_folder(self.mirror_folder_row))
        self.mirror_folder_row.add_suffix(browse_mirror_btn)
        group.add(self.mirror_folder_row)

        # Connect radio changes
        self.stream_check.connect("toggled", self._on_mode_toggled)

        # Save Button group
        save_group = Adw.PreferencesGroup()
        save_btn = Gtk.Button(label="Apply Changes")
        save_btn.set_css_classes(["suggested-action", "pill"])
        save_btn.set_halign(Gtk.Align.END)
        save_btn.connect("clicked", self._on_apply_clicked)
        save_group.add(save_btn)
        self.page_drive.add(save_group)

    def _build_computers_section(self):
        group_opt = Adw.PreferencesGroup()
        group_opt.set_title("Other Computers in Virtual Drive")
        group_opt.set_description(
            "Access folders backed up from your other PCs and Macs inside the virtual drive, "
            "matching the 'Other computers' folder structure in Google Drive on Windows."
        )
        self.page_computers.add(group_opt)

        self.include_comp_switch = Adw.SwitchRow(
            title="Include Other Computers in Virtual Drive",
            subtitle="Organize virtual drive as 'My Drive' and 'Other computers' folders"
        )
        self.include_comp_switch.set_active(config.get("include_other_computers", True))
        self.include_comp_switch.connect("notify::active", self._on_include_computers_toggled)
        group_opt.add(self.include_comp_switch)

        self.group_comp_list = Adw.PreferencesGroup()
        self.group_comp_list.set_title("Linked Synced Computers")
        self.group_comp_list.set_description(
            "Each linked computer appears as a folder under 'Other computers' in your virtual drive."
        )

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header_box.set_margin_bottom(8)

        add_comp_btn = Gtk.Button(label="Add Other Computer")
        add_comp_btn.set_icon_name("list-add-symbolic")
        add_comp_btn.set_css_classes(["suggested-action", "pill"])
        add_comp_btn.connect("clicked", self._open_add_computer_dialog)
        header_box.append(add_comp_btn)

        open_web_btn = Gtk.Button(label="Find Computers on Web")
        open_web_btn.set_icon_name("web-browser-symbolic")
        open_web_btn.set_css_classes(["flat", "pill"])
        open_web_btn.connect("clicked", lambda b: webbrowser.open("https://drive.google.com/drive/computers"))
        header_box.append(open_web_btn)

        self.group_comp_list.add(header_box)
        self.page_computers.add(self.group_comp_list)

        self._refresh_computers_list()

    def _refresh_computers_list(self):
        for row in self.computer_rows:
            self.group_comp_list.remove(row)
        self.computer_rows = []

        computers = config.get("other_computers", [])
        if not computers:
            empty_row = Adw.ActionRow(
                title="No other computers linked yet",
                subtitle="Click 'Add Other Computer' above to link a computer from Google Drive."
            )
            empty_row.set_sensitive(False)
            self.group_comp_list.add(empty_row)
            self.computer_rows.append(empty_row)
            return

        for comp in computers:
            row = Adw.ActionRow(
                title=comp.get("name", "Computer"),
                subtitle=f"Folder ID: {comp.get('folder_id', 'Unknown')}"
            )
            icon = Gtk.Image.new_from_icon_name("computer-symbolic")
            row.add_prefix(icon)

            del_btn = Gtk.Button(icon_name="user-trash-symbolic")
            del_btn.set_tooltip_text("Remove this computer")
            del_btn.set_css_classes(["flat", "destructive-action", "circular"])
            del_btn.set_valign(Gtk.Align.CENTER)
            comp_id = comp.get("id")
            del_btn.connect("clicked", lambda b, cid=comp_id: self._remove_computer(cid))
            row.add_suffix(del_btn)

            self.group_comp_list.add(row)
            self.computer_rows.append(row)

    def _remove_computer(self, comp_id: str):
        config.remove_other_computer(comp_id)
        rclone_mgr.rebuild_config()
        self._refresh_computers_list()
        if self.on_settings_changed_callback:
            self.on_settings_changed_callback()

    def _on_include_computers_toggled(self, row, param):
        enabled = row.get_active()
        config.set("include_other_computers", enabled)
        rclone_mgr.rebuild_config()
        if self.on_settings_changed_callback:
            self.on_settings_changed_callback()

    def _open_add_computer_dialog(self, btn):
        dialog = Adw.Window(transient_for=self, modal=True)
        dialog.set_title("Add Other Computer")
        dialog.set_default_size(440, 320)

        toolbar = Adw.ToolbarView()
        dialog.set_content(toolbar)
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(20)
        box.set_margin_end(20)

        group = Adw.PreferencesGroup()
        group.set_title("Computer Details")
        group.set_description("Enter the computer name and its Google Drive folder link.")

        name_entry = Adw.EntryRow(title="Computer Name")
        name_entry.set_text("Work Laptop")
        group.add(name_entry)

        link_entry = Adw.EntryRow(title="Folder URL or ID")
        group.add(link_entry)

        helper_lbl = Gtk.Label(
            label="Tip: In Google Drive Web (drive.google.com/drive/computers),\n"
                  "click on the computer and copy the URL from the browser address bar."
        )
        helper_lbl.set_css_classes(["dim-label", "caption"])
        helper_lbl.set_justify(Gtk.Justification.CENTER)
        box.append(group)
        box.append(helper_lbl)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda b: dialog.close())
        add_btn = Gtk.Button(label="Add Computer")
        add_btn.set_css_classes(["suggested-action", "pill"])

        def on_add(b):
            cname = name_entry.get_text().strip()
            clink = link_entry.get_text().strip()
            if not cname:
                return
            if not clink:
                clink = "root"
            config.add_other_computer(cname, clink)
            rclone_mgr.rebuild_config()
            self._refresh_computers_list()
            if self.on_settings_changed_callback:
                self.on_settings_changed_callback()
            dialog.close()

        add_btn.connect("clicked", on_add)
        btn_box.append(cancel_btn)
        btn_box.append(add_btn)
        box.append(btn_box)

        toolbar.set_content(box)
        dialog.present()

    def _build_account_section(self):
        group = Adw.PreferencesGroup(title="Google Account")
        self.page_account.add(group)

        email = config.get("account_email") or "Not connected"
        name = config.get("account_name") or "Google Drive"

        self.account_row = Adw.ActionRow(title=name, subtitle=email)
        avatar = Adw.Avatar(size=40, text=name, show_initials=True)
        self.account_row.add_prefix(avatar)

        self.disconnect_btn = Gtk.Button(label="Disconnect")
        self.disconnect_btn.set_css_classes(["destructive-action"])
        self.disconnect_btn.set_valign(Gtk.Align.CENTER)
        self.disconnect_btn.connect("clicked", self._on_disconnect_clicked)
        self.account_row.add_suffix(self.disconnect_btn)

        group.add(self.account_row)

        # Storage quota breakdown
        quota_group = Adw.PreferencesGroup(title="Google Drive Storage")
        self.page_account.add(quota_group)

        used_bytes = config.get("quota_used_bytes", 0)
        total_bytes = config.get("quota_total_bytes", 15 * 1024 * 1024 * 1024)
        used_gb = used_bytes / (1024 ** 3)
        total_gb = total_bytes / (1024 ** 3)

        self.quota_row = Adw.ActionRow(
            title=f"{used_gb:.1f} GB of {total_gb:.1f} GB used",
            subtitle=f"{((used_bytes / max(1, total_bytes)) * 100):.1f}% storage consumed"
        )
        quota_group.add(self.quota_row)

        # Refresh quota button
        refresh_btn = Gtk.Button(label="Refresh Storage Quota")
        refresh_btn.set_halign(Gtk.Align.START)
        refresh_btn.connect("clicked", self._on_refresh_quota)
        quota_group.add(refresh_btn)

    def _build_advanced_section(self):
        group = Adw.PreferencesGroup(title="General Preferences")
        self.page_settings.add(group)

        # Autostart switch
        self.autostart_row = Adw.SwitchRow(
            title="Launch Google Drive on system startup",
            subtitle="Automatically start GDriveSync when you log in"
        )
        self.autostart_row.set_active(config.get("autostart", True))
        self.autostart_row.connect("notify::active", self._on_autostart_toggled)
        group.add(self.autostart_row)

        # Start hidden switch
        self.start_hidden_row = Adw.SwitchRow(
            title="Start hidden on startup",
            subtitle="Start quietly in the background without opening the window"
        )
        self.start_hidden_row.set_active(config.get("start_hidden", True))
        self.start_hidden_row.connect("notify::active", lambda r, p: config.set("start_hidden", r.get_active()))
        group.add(self.start_hidden_row)

        # Run in background when closed switch
        self.minimize_row = Adw.SwitchRow(
            title="Run in background when closed",
            subtitle="Keep syncing in the background instead of exiting when closing the window"
        )
        self.minimize_row.set_active(config.get("minimize_to_tray", True))
        self.minimize_row.connect("notify::active", lambda r, p: config.set("minimize_to_tray", r.get_active()))
        group.add(self.minimize_row)

        # Bookmark in Nautilus switch
        self.bookmark_row = Adw.SwitchRow(
            title="Show in File Manager sidebar",
            subtitle="Add a direct bookmark to Google Drive in GNOME Files (Nautilus)"
        )
        self.bookmark_row.set_active(config.get("bookmark_nautilus", True))
        self.bookmark_row.connect("notify::active", self._on_bookmark_toggled)
        group.add(self.bookmark_row)

        # Bandwidth Group
        bw_group = Adw.PreferencesGroup(title="Bandwidth and Sync Frequency")
        self.page_settings.add(bw_group)

        self.poll_spin = Adw.SpinRow.new_with_range(10, 300, 5)
        self.poll_spin.set_title("Cloud Check Interval (Seconds)")
        self.poll_spin.set_subtitle("How often to check for remote changes in Mirror mode")
        self.poll_spin.set_value(config.get("poll_interval_sec", 30))
        bw_group.add(self.poll_spin)

        self.bw_spin = Adw.SpinRow.new_with_range(0, 100000, 256)
        self.bw_spin.set_title("Bandwidth Limit (KB/s)")
        self.bw_spin.set_subtitle("0 = Unlimited upload/download speed")
        self.bw_spin.set_value(config.get("bandwidth_limit_kbps", 0))
        bw_group.add(self.bw_spin)

    def _browse_folder(self, entry_row):
        dialog = Gtk.FileDialog(title="Select Google Drive Folder")
        def on_open_finish(d, res):
            try:
                folder = d.select_folder_finish(res)
                if folder:
                    entry_row.set_text(folder.get_path())
            except Exception:
                pass
        dialog.select_folder(self, None, on_open_finish)

    def _on_mode_toggled(self, check):
        # UI updates can happen live
        pass

    def _on_apply_clicked(self, btn):
        mode = "stream" if self.stream_check.get_active() else "mirror"
        stream_path = self.stream_folder_row.get_text().strip()
        mirror_path = self.mirror_folder_row.get_text().strip()
        cache_gb = int(self.cache_spin.get_value())
        poll_sec = int(self.poll_spin.get_value())
        bw_limit = int(self.bw_spin.get_value())

        config.set("sync_mode", mode)
        config.set("stream_mount_path", stream_path)
        config.set("mirror_local_path", mirror_path)
        config.set("cache_max_size_gb", cache_gb)
        config.set("poll_interval_sec", poll_sec)
        config.set("bandwidth_limit_kbps", bw_limit)

        # Rebuild configuration with current layout & computers
        rclone_mgr.rebuild_config()

        # Update bookmarks
        active_path = stream_path if mode == "stream" else mirror_path
        if config.get("bookmark_nautilus", True):
            bookmarks_mgr.update_bookmark(active_path, f"Google Drive ({mode.capitalize()})")

        if self.on_settings_changed_callback:
            self.on_settings_changed_callback()

        self.close()

    def _on_disconnect_clicked(self, btn):
        config.set("account_email", "")
        config.set("account_name", "")
        config.set("account_avatar_url", "")
        if config.rclone_config_file.exists():
            try:
                config.rclone_config_file.unlink()
            except Exception:
                pass
        self.account_row.set_title("Not connected")
        self.account_row.set_subtitle("Sign in to connect Google Drive")
        self.disconnect_btn.set_sensitive(False)

        if self.on_settings_changed_callback:
            self.on_settings_changed_callback()

    def _on_refresh_quota(self, btn):
        btn.set_sensitive(False)
        def fetch():
            quota = rclone_mgr.get_storage_quota()
            def update_ui():
                used_gb = quota["used"] / (1024 ** 3)
                total_gb = quota["total"] / (1024 ** 3)
                self.quota_row.set_title(f"{used_gb:.1f} GB of {total_gb:.1f} GB used")
                self.quota_row.set_subtitle(f"{((quota['used'] / max(1, quota['total'])) * 100):.1f}% storage consumed")
                btn.set_sensitive(True)
            GLib.idle_add(update_ui)
        import threading
        threading.Thread(target=fetch, daemon=True).start()

    def _on_autostart_toggled(self, row, param):
        enabled = row.get_active()
        config.set("autostart", enabled)
        desktop_mgr.update_autostart(enabled)

    def _on_bookmark_toggled(self, row, param):
        enabled = row.get_active()
        config.set("bookmark_nautilus", enabled)
        mode = config.get("sync_mode", "stream")
        path = config.get("stream_mount_path") if mode == "stream" else config.get("mirror_local_path")
        if enabled:
            bookmarks_mgr.update_bookmark(path, f"Google Drive ({mode.capitalize()})")
        else:
            bookmarks_mgr.remove_bookmark()
