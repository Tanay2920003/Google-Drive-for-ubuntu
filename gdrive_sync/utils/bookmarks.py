"""
GDriveSync Nautilus Sidebar Bookmark Integration
Manages bookmarks in ~/.config/gtk-3.0/bookmarks so Google Drive
appears natively in the GNOME Files (Nautilus) sidebar.
"""

from pathlib import Path


class BookmarkManager:
    def __init__(self):
        self.bookmarks_file = Path.home() / ".config" / "gtk-3.0" / "bookmarks"

    def update_bookmark(self, folder_path: str, label: str = "Google Drive"):
        """Add or update the bookmark entry in the file manager."""
        self.bookmarks_file.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        if self.bookmarks_file.exists():
            try:
                lines = self.bookmarks_file.read_text(encoding="utf-8").splitlines()
            except Exception:
                pass

        # Filter out old Google Drive bookmarks
        clean_lines = [l for l in lines if not ("Google Drive" in l or "GoogleDrive" in l)]

        # Add new entry
        uri = Path(folder_path).expanduser().resolve().as_uri()
        entry = f"{uri} {label}"
        clean_lines.append(entry)

        try:
            self.bookmarks_file.write_text("\n".join(clean_lines) + "\n", encoding="utf-8")
        except Exception as e:
            print(f"[Bookmarks] Failed to write bookmark: {e}")

    def remove_bookmark(self):
        if not self.bookmarks_file.exists():
            return
        try:
            lines = self.bookmarks_file.read_text(encoding="utf-8").splitlines()
            clean_lines = [l for l in lines if not ("Google Drive" in l or "GoogleDrive" in l)]
            self.bookmarks_file.write_text("\n".join(clean_lines) + "\n", encoding="utf-8")
        except Exception:
            pass


bookmarks_mgr = BookmarkManager()
