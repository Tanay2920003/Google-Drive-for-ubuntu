"""
GDriveSync Mirror Service
Manages two-way local offline synchronization (Mirror Mode).
All files are stored both in Google Drive and physically on your local computer.
"""

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List

from gdrive_sync.config import config
from gdrive_sync.engine.rclone_manager import rclone_mgr


class MirrorService:
    def __init__(self):
        self.is_running = False
        self.status = "idle"  # idle, syncing, paused, error
        self.error_message = ""
        self.sync_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.stats_callbacks: List[Callable] = []
        self._last_local_snapshot: Dict[str, float] = {}

    def add_stats_callback(self, cb: Callable):
        self.stats_callbacks.append(cb)

    def _notify_stats(self, payload: Dict[str, Any]):
        for cb in self.stats_callbacks:
            try:
                cb(payload)
            except Exception:
                pass

    def start(self, local_path: Optional[str] = None):
        """Start the bidirectional mirror sync daemon."""
        if self.is_running:
            return True

        if local_path is None:
            local_path = config.get("mirror_local_path", str(Path.home() / "GoogleDrive_Mirror"))

        local_dir = Path(local_path).expanduser().resolve()
        local_dir.mkdir(parents=True, exist_ok=True)

        self._stop_event.clear()
        self.is_running = True
        self.status = "idle"

        def mirror_loop():
            remote = f"{config.get('remote_name', 'gdrive')}:"
            poll_interval = config.get("poll_interval_sec", 30)

            # Initial scan snapshot of local files
            self._take_local_snapshot(str(local_dir))

            # Initial sync: pull down remote files to local folder first
            self._run_sync_cycle(remote, str(local_dir))

            while not self._stop_event.is_set():
                if config.get("is_paused", False):
                    self.status = "paused"
                    self._notify_stats({"status": "paused", "speed": 0, "transferring": []})
                    time.sleep(2)
                    continue

                # Check if local files changed
                local_changed = self._check_local_changes(str(local_dir))
                if local_changed:
                    self._run_upload_cycle(str(local_dir), remote)

                # Periodic bidirectional sync
                self._run_sync_cycle(remote, str(local_dir))

                # Sleep in short increments to allow rapid stop/pause response
                for _ in range(poll_interval):
                    if self._stop_event.is_set():
                        break
                    time.sleep(1)

            self.is_running = False
            self.status = "idle"

        self.sync_thread = threading.Thread(target=mirror_loop, daemon=True)
        self.sync_thread.start()
        return True

    def stop(self):
        """Stop the mirror sync service."""
        self._stop_event.set()
        self.is_running = False
        self.status = "idle"

    def _take_local_snapshot(self, local_path: str):
        snapshot = {}
        for root, _, files in os.walk(local_path):
            for file in files:
                p = os.path.join(root, file)
                try:
                    snapshot[p] = os.path.getmtime(p)
                except OSError:
                    pass
        self._last_local_snapshot = snapshot

    def _check_local_changes(self, local_path: str) -> bool:
        current = {}
        changed = False
        for root, _, files in os.walk(local_path):
            for file in files:
                p = os.path.join(root, file)
                try:
                    mtime = os.path.getmtime(p)
                    current[p] = mtime
                    if p not in self._last_local_snapshot or self._last_local_snapshot[p] != mtime:
                        changed = True
                except OSError:
                    pass
        if len(current) != len(self._last_local_snapshot):
            changed = True
        self._last_local_snapshot = current
        return changed

    def _run_upload_cycle(self, local_path: str, remote: str):
        """Upload any changed local files to Google Drive."""
        self.status = "syncing"
        self._notify_stats({
            "status": "syncing",
            "speed": 1024 * 500,  # approximate
            "transferring": [{"name": "Uploading local changes...", "size": 0, "bytes": 0}]
        })

        bw_limit = config.get("bandwidth_limit_kbps", 0)
        bw_flag = [f"--bwlimit={bw_limit}k"] if bw_limit > 0 else []

        include_computers = config.get("include_other_computers", True)
        other_computers = config.get("other_computers", [])

        if include_computers and other_computers:
            my_drive_src = os.path.join(local_path, "My Drive")
            if os.path.exists(my_drive_src):
                code, out, err = rclone_mgr.run_cmd(["copy", my_drive_src, "gdrive:", "--update", "--verbose"] + bw_flag, timeout=120)
                if code == 0:
                    self._log_transfers_from_output(err, action="upload")

            for comp in other_computers:
                comp_src = os.path.join(local_path, "Other computers", comp.get("name", "Computer"))
                if os.path.exists(comp_src):
                    comp_remote = f"gdrive_{comp['id']}:"
                    code, out, err = rclone_mgr.run_cmd(["copy", comp_src, comp_remote, "--update", "--verbose"] + bw_flag, timeout=120)
                    if code == 0:
                        self._log_transfers_from_output(err, action="upload")
        else:
            args = ["copy", local_path, remote, "--update", "--verbose"] + bw_flag
            code, out, err = rclone_mgr.run_cmd(args, timeout=120)
            if code == 0:
                self._log_transfers_from_output(err, action="upload")

        self.status = "idle"
        self._notify_stats({"status": "idle", "speed": 0, "transferring": []})

    def _run_sync_cycle(self, remote: str, local_path: str):
        """Pull down any new/updated remote files to local folder."""
        self.status = "syncing"
        self._notify_stats({
            "status": "syncing",
            "speed": 1024 * 500,
            "transferring": [{"name": "Checking Google Drive for updates...", "size": 0, "bytes": 0}]
        })

        bw_limit = config.get("bandwidth_limit_kbps", 0)
        bw_flag = [f"--bwlimit={bw_limit}k"] if bw_limit > 0 else []

        include_computers = config.get("include_other_computers", True)
        other_computers = config.get("other_computers", [])

        if include_computers and other_computers:
            # Sync My Drive
            my_drive_dest = os.path.join(local_path, "My Drive")
            os.makedirs(my_drive_dest, exist_ok=True)
            code, out, err = rclone_mgr.run_cmd(["copy", "gdrive:", my_drive_dest, "--update", "--verbose"] + bw_flag, timeout=120)
            if code == 0:
                self._log_transfers_from_output(err, action="download")

            # Sync each other computer
            for comp in other_computers:
                comp_dest = os.path.join(local_path, "Other computers", comp.get("name", "Computer"))
                os.makedirs(comp_dest, exist_ok=True)
                comp_remote = f"gdrive_{comp['id']}:"
                code, out, err = rclone_mgr.run_cmd(["copy", comp_remote, comp_dest, "--update", "--verbose"] + bw_flag, timeout=120)
                if code == 0:
                    self._log_transfers_from_output(err, action="download")
        else:
            args = ["copy", remote, local_path, "--update", "--verbose"] + bw_flag
            code, out, err = rclone_mgr.run_cmd(args, timeout=120)
            if code == 0:
                self._log_transfers_from_output(err, action="download")

        self.status = "idle"
        self._notify_stats({"status": "idle", "speed": 0, "transferring": []})

    def _log_transfers_from_output(self, log_output: str, action: str):
        """Parse rclone verbose output lines and add to recent activity."""
        for line in log_output.splitlines():
            # e.g.: 2026/10/31 02:00:00 INFO : document.pdf: Copied (new)
            if "Copied" in line or "Transferred" in line:
                parts = line.split("INFO  :")
                if len(parts) > 1:
                    filename = parts[1].split(":")[0].strip()
                    if filename:
                        config.add_activity(
                            name=os.path.basename(filename),
                            relative_path=filename,
                            size_bytes=0,
                            action=action,
                            status="done"
                        )


mirror_service = MirrorService()
