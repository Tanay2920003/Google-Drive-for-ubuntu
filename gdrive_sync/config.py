"""
GDriveSync Configuration & State Manager
Persists configuration to ~/.config/gdrivesync/config.json
"""

import json
import os
import time
from pathlib import Path

DEFAULT_CONFIG = {
    "sync_mode": "stream",  # 'stream' (FUSE virtual mount) or 'mirror' (offline 2-way sync)
    "stream_mount_path": str(Path.home() / "GoogleDrive"),
    "mirror_local_path": str(Path.home() / "GoogleDrive_Mirror"),
    "remote_name": "gdrive",
    "cache_max_size_gb": 10,
    "autostart": True,
    "bookmark_nautilus": True,
    "poll_interval_sec": 30,
    "bandwidth_limit_kbps": 0,  # 0 = unlimited
    "account_email": "",
    "account_name": "",
    "account_avatar_url": "",
    "quota_used_bytes": 0,
    "quota_total_bytes": 15 * 1024 * 1024 * 1024,  # default 15 GB
    "include_other_computers": True,  # Show 'My Drive' & 'Other computers' in virtual mount
    "other_computers": [],  # List of dicts: {"id": "...", "name": "Work PC", "folder_id": "...", "url": "..."}
    "start_hidden": True,  # Start hidden in background on boot
    "minimize_to_tray": True,  # Keep running in background when closing window
    "is_paused": False,
    "recent_activity": []
}


class ConfigManager:
    def __init__(self):
        self.config_dir = Path.home() / ".config" / "gdrivesync"
        self.config_file = self.config_dir / "config.json"
        self.rclone_config_file = self.config_dir / "rclone.conf"
        self.data = DEFAULT_CONFIG.copy()
        self._ensure_paths()
        self.load()

    def _ensure_paths(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        # Ensure default directories exist or can be created
        Path(self.data["stream_mount_path"]).mkdir(parents=True, exist_ok=True)
        Path(self.data["mirror_local_path"]).mkdir(parents=True, exist_ok=True)

    def load(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.data.update(loaded)
            except Exception as e:
                print(f"[Config] Error loading config, using defaults: {e}")
        else:
            self.save()

    def save(self):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"[Config] Error saving config: {e}")

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def add_activity(self, name: str, relative_path: str, size_bytes: int, action: str, status: str = "done"):
        """
        Record a sync event. action: 'upload', 'download', 'delete', 'sync'
        """
        item = {
            "name": name,
            "path": relative_path,
            "size": size_bytes,
            "time": int(time.time()),
            "action": action,
            "status": status
        }
        activity = self.data.get("recent_activity", [])
        # Keep recent 100 items, most recent first
        activity.insert(0, item)
        self.data["recent_activity"] = activity[:100]
        self.save()

    def add_other_computer(self, name: str, folder_id_or_url: str) -> dict:
        import uuid
        import re
        # Extract folder ID if full URL was provided
        match = re.search(r'folders/([a-zA-Z0-9_-]+)', folder_id_or_url)
        folder_id = match.group(1) if match else folder_id_or_url.strip()

        comp = {
            "id": f"comp_{uuid.uuid4().hex[:8]}",
            "name": name.strip(),
            "folder_id": folder_id,
            "url": folder_id_or_url.strip()
        }
        computers = self.data.get("other_computers", [])
        computers.append(comp)
        self.data["other_computers"] = computers
        self.save()
        return comp

    def remove_other_computer(self, comp_id: str):
        computers = [c for c in self.data.get("other_computers", []) if c.get("id") != comp_id]
        self.data["other_computers"] = computers
        self.save()


# Global singleton instance
config = ConfigManager()
