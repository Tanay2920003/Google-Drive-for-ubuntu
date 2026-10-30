"""
GDriveSync OAuth Setup & Login Dialog
Provides guided Google Account authentication and demo mode.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

from gdrive_sync.config import config
from gdrive_sync.engine.oauth import oauth_mgr


class OAuthDialog(Adw.Window):
    def __init__(self, parent_window, on_auth_complete_callback=None):
        super().__init__(transient_for=parent_window, modal=True)
        self.set_title("Connect Google Drive")
        self.set_default_size(440, 520)
        self.on_auth_complete_callback = on_auth_complete_callback

        self._build_ui()

    def _build_ui(self):
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        # Header bar
        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        # Content container
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)

        # App Icon & Title
        icon_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        icon_box.set_halign(Gtk.Align.CENTER)

        # Large icon
        icon_image = Gtk.Image.new_from_icon_name("folder-remote-symbolic")
        icon_image.set_pixel_size(64)
        icon_box.append(icon_image)

        title_label = Gtk.Label(label="Sign in to Google Drive")
        title_label.set_css_classes(["title-1"])
        icon_box.append(title_label)

        desc_label = Gtk.Label(
            label="Connect your Google account to mount as a virtual\nfolder or mirror your files locally."
        )
        desc_label.set_justify(Gtk.Justification.CENTER)
        desc_label.set_css_classes(["dim-label"])
        icon_box.append(desc_label)

        box.append(icon_box)

        # Status / Feedback area
        self.status_banner = Adw.Banner()
        self.status_banner.set_revealed(False)
        box.append(self.status_banner)

        self.spinner = Gtk.Spinner()
        self.spinner.set_halign(Gtk.Align.CENTER)
        self.spinner.set_size_request(32, 32)
        box.append(self.spinner)

        # Primary Sign In Button
        self.signin_btn = Gtk.Button(label="Sign in with Google (Browser)")
        self.signin_btn.set_css_classes(["suggested-action", "pill"])
        self.signin_btn.set_halign(Gtk.Align.CENTER)
        self.signin_btn.connect("clicked", self._on_signin_clicked)
        box.append(self.signin_btn)

        # Demo Mode Button
        demo_btn = Gtk.Button(label="Use Offline Demo Account (Quick Test)")
        demo_btn.set_css_classes(["flat", "pill"])
        demo_btn.set_halign(Gtk.Align.CENTER)
        demo_btn.connect("clicked", self._on_demo_clicked)
        box.append(demo_btn)

        # Advanced Settings (Client ID / Secret) Expander
        expander = Adw.ExpanderRow(title="Advanced API Credentials (Optional)")
        expander.set_subtitle("Use your own Google Cloud Client ID and Secret")

        self.client_id_entry = Adw.EntryRow(title="Client ID")
        self.client_secret_entry = Adw.PasswordEntryRow(title="Client Secret")

        expander.add_row(self.client_id_entry)
        expander.add_row(self.client_secret_entry)

        pref_group = Adw.PreferencesGroup()
        pref_group.add(expander)
        box.append(pref_group)

        # Scroll wrapper
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(box)
        toolbar_view.set_content(scrolled)

    def _on_signin_clicked(self, btn):
        self.signin_btn.set_sensitive(False)
        self.spinner.start()
        self.status_banner.set_title("Opening browser... Please authorize Google Drive.")
        self.status_banner.set_revealed(True)

        client_id = self.client_id_entry.get_text().strip()
        client_secret = self.client_secret_entry.get_text().strip()

        def on_success(user_data):
            GLib.idle_add(self._handle_auth_success, user_data)

        def on_error(err_msg):
            GLib.idle_add(self._handle_auth_error, err_msg)

        oauth_mgr.start_oauth_flow(
            client_id=client_id,
            client_secret=client_secret,
            on_success=on_success,
            on_error=on_error
        )

    def _handle_auth_success(self, user_data):
        self.spinner.stop()
        self.status_banner.set_title(f"Connected as {user_data.get('email', 'Google Drive User')}!")
        self.status_banner.set_revealed(True)
        if self.on_auth_complete_callback:
            self.on_auth_complete_callback(user_data)
        GLib.timeout_add(1200, self.close)

    def _handle_auth_error(self, err_msg):
        self.spinner.stop()
        self.signin_btn.set_sensitive(True)
        self.status_banner.set_title(f"Sign in failed: {err_msg}")
        self.status_banner.set_revealed(True)

    def _on_demo_clicked(self, btn):
        oauth_mgr.setup_demo_mode()
        self.status_banner.set_title("Offline Demo Account activated!")
        self.status_banner.set_revealed(True)
        if self.on_auth_complete_callback:
            self.on_auth_complete_callback({
                "email": config.get("account_email"),
                "name": config.get("account_name"),
                "avatar": "",
                "quota": {
                    "used": config.get("quota_used_bytes"),
                    "total": config.get("quota_total_bytes")
                }
            })
        GLib.timeout_add(800, self.close)
