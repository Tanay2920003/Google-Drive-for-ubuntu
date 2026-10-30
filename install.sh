#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$DIR:$PYTHONPATH"

echo "=========================================================="
echo "      Installing Google Drive Desktop for Linux           "
echo "=========================================================="

# 1. Download and set up rclone if missing
if [ ! -f "$DIR/bin/rclone" ]; then
    echo "[1/4] Setting up cloud synchronization engine..."
    mkdir -p "$DIR/bin"
    curl -fsSL https://downloads.rclone.org/rclone-current-linux-amd64.zip -o "$DIR/bin/rclone.zip"
    unzip -q -j "$DIR/bin/rclone.zip" "*/rclone" -d "$DIR/bin/"
    rm -f "$DIR/bin/rclone.zip"
    chmod +x "$DIR/bin/rclone"
    echo "[1/4] Cloud sync engine installed successfully."
else
    echo "[1/4] Cloud sync engine verified."
fi

# 2. Download official Google Drive logo from the internet & install all resolutions
echo "[2/4] Downloading official Google Drive logo from internet & setting up icon themes..."
python3 -m gdrive_sync.utils.download_logo

# 3. Setup desktop application launcher & autostart
echo "[3/4] Installing application launcher and background autostart..."
python3 -c "
from gdrive_sync.utils.desktop_entry import desktop_mgr
desktop_mgr.install_application_launcher()
desktop_mgr.update_autostart(True)
"

# 4. Refresh desktop search database and icon caches
echo "[4/4] Updating GNOME desktop search database..."
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" || true
fi

echo ""
echo "=========================================================="
echo "          Google Drive Installation Completed!            "
echo "=========================================================="
echo "Google Drive is now fully registered in your Ubuntu system."
echo ""
echo "To search and launch:"
echo "  1. Press the 'Super' (Windows) key on your keyboard."
echo "  2. Type 'Google Drive' or 'drive'."
echo "  3. You will see Google Drive with the official colorful logo!"
echo ""
echo "To launch from terminal: ./run.sh (or 'gtk-launch google-drive')"
echo "=========================================================="
