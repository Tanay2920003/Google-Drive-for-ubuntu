"""
GDriveSync Rclone Process Manager
Handles rclone binary lifecycle, config management, and query operations.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from gdrive_sync.config import config


class RcloneManager:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.local_bin = self.project_root / "bin" / "rclone"
        self.config_file = config.rclone_config_file

    def get_binary_path(self) -> str:
        """Find the rclone binary: bundled first, then ~/.local/bin, then system PATH."""
        if self.local_bin.exists() and os.access(self.local_bin, os.X_OK):
            return str(self.local_bin)
        
        user_bin = Path.home() / ".local" / "bin" / "rclone"
        if user_bin.exists() and os.access(user_bin, os.X_OK):
            return str(user_bin)
        
        system_bin = shutil.which("rclone")
        if system_bin:
            return system_bin
        
        return str(self.local_bin)

    def is_configured(self) -> bool:
        """Check if the Google Drive remote is set up in rclone.conf."""
        if not self.config_file.exists():
            return False
        try:
            content = self.config_file.read_text(encoding="utf-8")
            return f"[{config.get('remote_name', 'gdrive')}]" in content
        except Exception:
            return False

    def get_configured_remotes(self) -> list:
        if not self.config_file.exists():
            return []
        try:
            cmd = [self.get_binary_path(), "listremotes", "--config", str(self.config_file)]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if res.returncode == 0:
                return [line.strip().rstrip(":") for line in res.stdout.strip().splitlines() if line.strip()]
        except Exception:
            pass
        return []

    def run_cmd(self, args: list, timeout: int = 300) -> Tuple[int, str, str]:
        """Execute an rclone command with the app's config file."""
        cmd = [self.get_binary_path(), "--config", str(self.config_file)] + args
        try:
            p = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout
            )
            return p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)

    def get_storage_quota(self) -> Dict[str, int]:
        """
        Fetch Google Drive storage quota (used, total, trash, free).
        Returns dict with bytes.
        """
        remote = f"{config.get('remote_name', 'gdrive')}:"
        code, out, err = self.run_cmd(["about", remote, "--json"], timeout=15)
        if code == 0:
            try:
                data = json.loads(out)
                total = data.get("total", 15 * 1024 * 1024 * 1024)
                used = data.get("used", 0)
                free = data.get("free", total - used)
                trash = data.get("trashed", 0)
                config.set("quota_used_bytes", used)
                config.set("quota_total_bytes", total)
                return {
                    "total": total,
                    "used": used,
                    "free": free,
                    "trash": trash
                }
            except Exception as e:
                print(f"[RcloneManager] Error parsing quota: {e}")
        return {
            "total": config.get("quota_total_bytes", 15 * 1024 * 1024 * 1024),
            "used": config.get("quota_used_bytes", 0),
            "free": max(0, config.get("quota_total_bytes", 15 * 1024 * 1024 * 1024) - config.get("quota_used_bytes", 0)),
            "trash": 0
        }

    def get_credentials(self) -> Dict[str, str]:
        """Extract existing credentials (token, client_id, client_secret) from the [gdrive] section."""
        creds = {"token": "", "client_id": "", "client_secret": ""}
        if not self.config_file.exists():
            return creds
        try:
            content = self.config_file.read_text(encoding="utf-8")
            in_gdrive = False
            token_str = ""
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("[") and stripped.endswith("]"):
                    in_gdrive = (stripped == f"[{config.get('remote_name', 'gdrive')}]")
                    continue
                if in_gdrive:
                    if stripped.startswith("client_id ="):
                        creds["client_id"] = stripped.split("=", 1)[1].strip()
                    elif stripped.startswith("client_secret ="):
                        creds["client_secret"] = stripped.split("=", 1)[1].strip()
                    elif stripped.startswith("token ="):
                        token_str = stripped.split("=", 1)[1].strip()

            if token_str:
                start = token_str.find("{")
                end = token_str.rfind("}")
                if start != -1 and end != -1:
                    token_str = token_str[start:end+1]
                try:
                    json.loads(token_str)
                    creds["token"] = token_str
                except Exception:
                    pass
        except Exception as e:
            print(f"[RcloneManager] Error reading credentials: {e}")
        return creds

    def update_user_info_from_drive_api(self):
        """Fetch user display name, email, and storage quota from Google Drive API."""
        import urllib.request
        # Always update storage quota via rclone (handles token refresh automatically)
        try:
            self.get_storage_quota()
        except Exception:
            pass

        creds = self.get_credentials()
        token_str = creds.get("token")
        if not token_str:
            return
        try:
            token_data = json.loads(token_str)
            access_token = token_data.get("access_token")
            if not access_token:
                return

            req = urllib.request.Request(
                "https://www.googleapis.com/drive/v3/about?fields=user,storageQuota",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    user = data.get("user", {})
                    quota = data.get("storageQuota", {})

                    email = user.get("emailAddress")
                    name = user.get("displayName")
                    photo = user.get("photoLink", "")

                    if email:
                        config.set("account_email", email)
                    if name:
                        config.set("account_name", name)
                    if photo:
                        config.set("account_avatar_url", photo)

                    used = int(quota.get("usage", config.get("quota_used_bytes", 0)))
                    total = int(quota.get("limit", config.get("quota_total_bytes", 15 * 1024**3)))
                    config.set("quota_used_bytes", used)
                    config.set("quota_total_bytes", total)
        except Exception:
            # Silently fall back if direct userinfo endpoint is restricted
            pass

    def rebuild_config(self, token_json: Optional[str] = None, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        """
        Reconstructs rclone.conf with:
        1. [gdrive]: Standard My Drive remote
        2. [gdrive_comp_*]: Individual remotes for each linked other computer
        3. [other_computers]: Combine remote listing all linked other computers
        4. [gdrive_virtual]: Top-level combine remote ('My Drive' + 'Other computers')
        """
        creds = self.get_credentials()
        final_token = token_json if token_json is not None else creds.get("token", "")
        final_client_id = client_id if client_id is not None else creds.get("client_id", "")
        final_client_secret = client_secret if client_secret is not None else creds.get("client_secret", "")

        if not final_token:
            return

        remote = config.get("remote_name", "gdrive")
        lines = [
            f"[{remote}]",
            "type = drive",
            "scope = drive",
        ]
        if final_client_id:
            lines.append(f"client_id = {final_client_id}")
        if final_client_secret:
            lines.append(f"client_secret = {final_client_secret}")
        lines.append(f"token = {final_token}")
        lines.append("")

        include_computers = config.get("include_other_computers", True)
        other_computers = config.get("other_computers", [])

        if include_computers:
            if other_computers:
                # Add remote for each other computer
                computer_upstreams = []
                for comp in other_computers:
                    comp_remote_name = f"gdrive_{comp['id']}"
                    folder_id = comp.get("folder_id", "").strip()
                    lines.extend([
                        f"[{comp_remote_name}]",
                        "type = drive",
                        "scope = drive",
                    ])
                    if final_client_id:
                        lines.append(f"client_id = {final_client_id}")
                    if final_client_secret:
                        lines.append(f"client_secret = {final_client_secret}")
                    lines.append(f"token = {final_token}")
                    if folder_id:
                        lines.append(f"root_folder_id = {folder_id}")
                    lines.append("")

                    sanitized_name = comp.get("name", "Computer").replace("=", "_").replace('"', '')
                    computer_upstreams.append(f'"{sanitized_name}={comp_remote_name}:"')

                # Combine remote for other computers
                lines.extend([
                    "[other_computers]",
                    "type = combine",
                    f"upstreams = {' '.join(computer_upstreams)}",
                    ""
                ])

                # Top-level virtual drive combine remote
                lines.extend([
                    "[gdrive_virtual]",
                    "type = combine",
                    'upstreams = "My Drive=gdrive:" "Other computers=other_computers:"',
                    ""
                ])
            else:
                # If no other computers configured yet, create placeholder directory
                placeholder_dir = config.config_dir / "placeholders" / "other_computers"
                placeholder_dir.mkdir(parents=True, exist_ok=True)
                readme_file = placeholder_dir / "How_to_add_computers.txt"
                if not readme_file.exists():
                    readme_file.write_text(
                        "No other computers added yet.\n\n"
                        "To link your other synced computers:\n"
                        "1. Open GDriveSync Preferences (gear icon)\n"
                        "2. Go to the 'Computers' tab\n"
                        "3. Click 'Add Other Computer' and enter the computer name & Google Drive link.\n",
                        encoding="utf-8"
                    )

                lines.extend([
                    "[gdrive_virtual]",
                    "type = combine",
                    f'upstreams = "My Drive=gdrive:" "Other computers={placeholder_dir}"',
                    ""
                ])

        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text("\n".join(lines), encoding="utf-8")

    def write_remote_config(self, token_json: str, client_id: str = "", client_secret: str = ""):
        """Write or update the Google Drive remote in rclone.conf and rebuild virtual layout."""
        self.rebuild_config(token_json=token_json, client_id=client_id, client_secret=client_secret)

    def get_mount_remote_name(self) -> str:
        """Determine which remote to mount in Stream mode."""
        if config.get("include_other_computers", True):
            return "gdrive_virtual:"
        return f"{config.get('remote_name', 'gdrive')}:"


rclone_mgr = RcloneManager()

