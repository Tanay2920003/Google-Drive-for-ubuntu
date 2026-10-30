"""
Desktop Entry and Autostart Manager.
Handles creation and registration of the GNOME/Linux desktop launcher
and autostart service for Google Drive.
"""

import os
import shutil
import subprocess
from pathlib import Path
from gdrive_sync.utils.download_logo import setup_all_icons


class DesktopEntryManager:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent.resolve()
        self.run_script = self.project_root / "run.sh"
        self.apps_dir = Path.home() / ".local" / "share" / "applications"
        self.autostart_dir = Path.home() / ".config" / "autostart"

    def install_icons(self):
        """Download and install official Google Drive icons in all resolutions."""
        setup_all_icons(self.project_root)

    def _generate_desktop_content(self, hidden: bool = False) -> str:
        exec_cmd = f"{self.run_script} --hidden" if hidden else f"{self.run_script}"
        return f"""[Desktop Entry]
Name=Google Drive
GenericName=Cloud Storage Client
Comment=Access and sync your Google Drive files
Exec={exec_cmd}
Icon=google-drive
Terminal=false
Type=Application
Categories=Network;FileTransfer;Utility;
Keywords=google;drive;cloud;sync;gdrive;backup;storage;online;
StartupNotify=true
StartupWMClass=com.google.GDriveSync
X-GNOME-Keywords=google;drive;cloud;sync;gdrive;backup;storage;online;
"""

    def install_application_launcher(self):
        """Install into GNOME applications menu, search index, and icon theme."""
        # 1. Ensure icons are installed
        self.install_icons()

        # 2. Setup desktop entry
        self.apps_dir.mkdir(parents=True, exist_ok=True)
        desktop_file = self.apps_dir / "google-drive.desktop"
        legacy_file = self.apps_dir / "gdrivesync.desktop"

        try:
            # Remove legacy file if it exists so there are no duplicate entries in GNOME
            if legacy_file.exists():
                legacy_file.unlink()

            desktop_file.write_text(self._generate_desktop_content(hidden=False), encoding="utf-8")
            desktop_file.chmod(0o755)

            # Update desktop database so GNOME Shell search indexes it immediately
            subprocess.run(["update-desktop-database", str(self.apps_dir)],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("[DesktopEntry] Installed launcher to ~/.local/share/applications/google-drive.desktop")
        except Exception as e:
            print(f"[DesktopEntry] Error creating launcher: {e}")

    def update_autostart(self, enable: bool):
        """Enable or disable autostart on system boot (starts hidden in background)."""
        self.autostart_dir.mkdir(parents=True, exist_ok=True)
        autostart_file = self.autostart_dir / "google-drive.desktop"
        legacy_autostart = self.autostart_dir / "gdrivesync.desktop"

        if legacy_autostart.exists():
            try:
                legacy_autostart.unlink()
            except Exception:
                pass

        if enable:
            try:
                autostart_file.write_text(self._generate_desktop_content(hidden=True), encoding="utf-8")
                autostart_file.chmod(0o755)
            except Exception as e:
                print(f"[DesktopEntry] Error enabling autostart: {e}")
        else:
            if autostart_file.exists():
                try:
                    autostart_file.unlink()
                except Exception:
                    pass


desktop_mgr = DesktopEntryManager()
