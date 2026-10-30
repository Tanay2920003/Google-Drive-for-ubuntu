"""
GDriveSync OAuth Authentication Helper
Launches Google Drive OAuth 2.0 flow via browser, captures token,
and fetches user profile info (name, email, avatar).
"""

import json
import os
import subprocess
import threading
import urllib.request
import webbrowser
from typing import Optional, Callable, Dict, Any

from gdrive_sync.config import config
from gdrive_sync.engine.rclone_manager import rclone_mgr


class OAuthManager:
    def __init__(self):
        self.auth_process: Optional[subprocess.Popen] = None
        self.is_authenticating = False

    def start_oauth_flow(
        self,
        client_id: str = "",
        client_secret: str = "",
        on_success: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_error: Optional[Callable[[str], None]] = None
    ):
        """
        Runs 'rclone authorize drive' in a background thread.
        Rclone will automatically start a local web server (http://127.0.0.1:53682/)
        and prompt the user to authorize in their browser.
        """
        if self.is_authenticating:
            return

        self.is_authenticating = True

        def auth_worker():
            rclone_bin = rclone_mgr.get_binary_path()
            cmd = [rclone_bin, "authorize", "drive"]
            if client_id and client_secret:
                cmd.extend([client_id, client_secret])

            try:
                self.auth_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                stdout, stderr = self.auth_process.communicate(timeout=180)

                # Look for token JSON in stdout
                token_str = ""
                capture = False
                for line in stdout.splitlines():
                    if "Paste the following into your remote machine --->" in line:
                        capture = True
                        continue
                    if "<---End paste" in line:
                        capture = False
                        break
                    if capture:
                        token_str += line

                if not token_str:
                    # Sometimes rclone outputs JSON directly between curly braces
                    start = stdout.find("{")
                    end = stdout.rfind("}")
                    if start != -1 and end != -1:
                        token_str = stdout[start:end+1]

                if token_str:
                    token_data = json.loads(token_str)
                    # Write to rclone config
                    rclone_mgr.write_remote_config(
                        token_json=token_str,
                        client_id=client_id,
                        client_secret=client_secret
                    )

                    # Try to fetch user info from Google OAuth2 API
                    user_info = self._fetch_user_info(token_data.get("access_token", ""))
                    email = user_info.get("email", "Google Drive User")
                    name = user_info.get("name", email.split("@")[0])
                    picture = user_info.get("picture", "")

                    config.set("account_email", email)
                    config.set("account_name", name)
                    config.set("account_avatar_url", picture)

                    # Update storage quota
                    quota = rclone_mgr.get_storage_quota()

                    if on_success:
                        on_success({
                            "email": email,
                            "name": name,
                            "avatar": picture,
                            "quota": quota
                        })
                else:
                    if on_error:
                        on_error("Authorization failed or was cancelled.")

            except subprocess.TimeoutExpired:
                if on_error:
                    on_error("Authorization timed out after 3 minutes.")
            except Exception as e:
                if on_error:
                    on_error(f"Error during authorization: {e}")
            finally:
                self.is_authenticating = False
                self.auth_process = None

        thread = threading.Thread(target=auth_worker, daemon=True)
        thread.start()

    def cancel(self):
        if self.auth_process:
            try:
                self.auth_process.terminate()
            except Exception:
                pass
        self.is_authenticating = False

    def setup_demo_mode(self):
        """
        Sets up an offline demo mode so the user can test the app
        immediately without needing to log into Google Drive right now.
        """
        config.set("account_email", "demo.user@gmail.com")
        config.set("account_name", "Demo User")
        config.set("account_avatar_url", "")
        config.set("quota_used_bytes", 4 * 1024 * 1024 * 1024 + 500 * 1024 * 1024)  # 4.5 GB
        config.set("quota_total_bytes", 15 * 1024 * 1024 * 1024)  # 15 GB

        # Populate sample recent activity if empty
        if not config.get("recent_activity"):
            config.add_activity("Annual_Report_2026.pdf", "Work/Annual_Report_2026.pdf", 3450000, "upload")
            config.add_activity("Team_Presentation.pptx", "Work/Team_Presentation.pptx", 12800000, "upload")
            config.add_activity("Project_Budget.xlsx", "Finance/Project_Budget.xlsx", 540000, "download")
            config.add_activity("vacation_photo.jpg", "Photos/vacation_photo.jpg", 4200000, "download")

        # Populate sample other computers if empty
        if not config.get("other_computers"):
            config.set("other_computers", [
                {
                    "id": "comp_work_laptop",
                    "name": "Work ThinkPad",
                    "folder_id": "demo_laptop_folder_id",
                    "url": "https://drive.google.com/drive/folders/demo_laptop_folder_id"
                },
                {
                    "id": "comp_home_pc",
                    "name": "Home Desktop",
                    "folder_id": "demo_home_folder_id",
                    "url": "https://drive.google.com/drive/folders/demo_home_folder_id"
                }
            ])

        rclone_mgr.rebuild_config()

    def _fetch_user_info(self, access_token: str) -> Dict[str, Any]:
        if not access_token:
            return {}
        try:
            req = urllib.request.Request(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            pass
        return {}


oauth_mgr = OAuthManager()
