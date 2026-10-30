"""
GDriveSync Stream Service
Manages the virtual FUSE mounted Google Drive folder (On-Demand streaming).
Files are downloaded and cached only when accessed, saving local disk space.
"""

import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional, Callable

from gdrive_sync.config import config
from gdrive_sync.engine.rclone_manager import rclone_mgr


class StreamService:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.is_running = False
        self.status = "idle"  # idle, mounting, active, error, paused
        self.error_message = ""
        self.rc_port = 5572
        self.rc_url = f"http://127.0.0.1:{self.rc_port}"
        self.monitor_thread: Optional[threading.Thread] = None
        self.stats_callbacks = []
        self._stop_event = threading.Event()
        self.uses_systemd_run = False

    def add_stats_callback(self, cb: Callable):
        self.stats_callbacks.append(cb)

    def is_mounted(self, mount_point: str) -> bool:
        """Check if mount_point is currently a mount point in /proc/mounts."""
        try:
            with open("/proc/mounts", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2 and os.path.realpath(parts[1]) == os.path.realpath(mount_point):
                        return True
        except Exception:
            pass
        return False

    def unmount(self, mount_point: str):
        """Unmount the virtual directory safely."""
        try:
            # Try fusermount3 first
            cmd = ["fusermount3", "-u", mount_point]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except Exception:
            pass

        try:
            # Also try via systemd-run in case it was mounted via systemd
            subprocess.run(["systemd-run", "--user", "--pipe", "fusermount3", "-u", mount_point],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except Exception:
            pass

    def start(self, mount_point: Optional[str] = None):
        """Start the FUSE streaming mount daemon."""
        if self.is_running:
            return True

        if mount_point is None:
            mount_point = config.get("stream_mount_path", str(Path.home() / "GoogleDrive"))

        mount_path = Path(mount_point).expanduser().resolve()
        mount_path.mkdir(parents=True, exist_ok=True)

        # If already mounted from previous run, clean it up first
        if self.is_mounted(str(mount_path)):
            self.unmount(str(mount_path))
            time.sleep(0.5)

        # Ensure rclone configuration layout (My Drive + Other computers) is up to date
        rclone_mgr.rebuild_config()
        remote = rclone_mgr.get_mount_remote_name()
        cache_gb = config.get("cache_max_size_gb", 10)
        bw_limit = config.get("bandwidth_limit_kbps", 0)

        rclone_bin = rclone_mgr.get_binary_path()
        config_file = str(config.rclone_config_file)

        mount_args = [
            rclone_bin,
            "mount",
            remote,
            str(mount_path),
            "--config", config_file,
            "--vfs-cache-mode", "full",
            f"--vfs-cache-max-size={cache_gb}G",
            "--vfs-read-chunk-size=32M",
            "--vfs-read-chunk-size-limit=2G",
            "--buffer-size=32M",
            "--dir-cache-time=5m",
            "--attr-timeout=1s",
            "--drive-chunk-size=32M",
            "--rc",
            f"--rc-addr=127.0.0.1:{self.rc_port}",
            "--rc-no-auth"
        ]

        if bw_limit > 0:
            mount_args.append(f"--bwlimit={bw_limit}k")

        # Test if standard mount works or if systemd-run is required (Snap / AppArmor container)
        # Attempt direct execution first; if socket fd error occurs, use systemd-run --user
        self.status = "mounting"
        self._stop_event.clear()

        def run_daemon():
            # Check if running inside snap or apparmor restricted environment
            is_confined = os.path.exists("/proc/self/attr/current") and "snap." in Path("/proc/self/attr/current").read_text(errors="ignore")
            
            launch_cmd = mount_args
            if is_confined and shutil.which("systemd-run"):
                launch_cmd = ["systemd-run", "--user", "--pipe"] + mount_args
                self.uses_systemd_run = True
            else:
                self.uses_systemd_run = False

            try:
                self.process = subprocess.Popen(
                    launch_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                self.is_running = True
                
                # Wait briefly to verify mount succeeded
                for _ in range(20):
                    if self.is_mounted(str(mount_path)) or self._check_rc_alive():
                        self.status = "active"
                        break
                    if self.process.poll() is not None:
                        break
                    time.sleep(0.2)

                if self.status != "active":
                    # If direct failed and we haven't tried systemd-run yet, retry with systemd-run
                    if not self.uses_systemd_run and shutil.which("systemd-run"):
                        self.uses_systemd_run = True
                        launch_cmd = ["systemd-run", "--user", "--pipe"] + mount_args
                        self.process = subprocess.Popen(
                            launch_cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True
                        )
                        for _ in range(20):
                            if self.is_mounted(str(mount_path)) or self._check_rc_alive():
                                self.status = "active"
                                break
                            time.sleep(0.2)

                if self.status == "active":
                    self._start_stats_monitor()
                    # Wait for process
                    self.process.wait()
                else:
                    self.status = "error"
                    self.error_message = "Failed to mount Google Drive virtual folder."

            except Exception as e:
                self.status = "error"
                self.error_message = str(e)
            finally:
                self.is_running = False
                if self.status != "error":
                    self.status = "idle"

        t = threading.Thread(target=run_daemon, daemon=True)
        t.start()
        return True

    def stop(self, mount_point: Optional[str] = None):
        """Stop streaming service and unmount."""
        self._stop_event.set()
        if mount_point is None:
            mount_point = config.get("stream_mount_path", str(Path.home() / "GoogleDrive"))

        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

        self.unmount(mount_point)
        self.is_running = False
        self.status = "idle"

    def _check_rc_alive(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.rc_url}/core/version", method="POST")
            with urllib.request.urlopen(req, timeout=1) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _start_stats_monitor(self):
        def monitor_loop():
            while not self._stop_event.is_set() and self.is_running:
                try:
                    req = urllib.request.Request(f"{self.rc_url}/core/stats", method="POST")
                    with urllib.request.urlopen(req, timeout=2) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode("utf-8"))
                            speed = data.get("speed", 0.0)  # bytes/sec
                            transferring = data.get("transferring", [])
                            bytes_transferred = data.get("bytes", 0)

                            stats_payload = {
                                "speed": speed,
                                "transferring": transferring,
                                "bytes": bytes_transferred,
                                "status": "syncing" if (len(transferring) > 0 or speed > 1024) else "idle"
                            }
                            for cb in self.stats_callbacks:
                                try:
                                    cb(stats_payload)
                                except Exception:
                                    pass
                except Exception:
                    pass
                time.sleep(2)

        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()


stream_service = StreamService()
