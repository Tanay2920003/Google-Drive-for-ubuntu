#!/usr/bin/env bash
set -e

# ==========================================================
# Google Drive for Linux (GDriveSync) - Installer
# Supports:
#   1. One-line curl pipe: curl -fsSL <url> | bash
#   2. Local execution: ./install.sh
# ==========================================================

REPO_URL="https://github.com/Tanay2920003/Google-Drive-for-ubuntu.git"
DEFAULT_INSTALL_DIR="$HOME/.local/share/gdrivesync"

# Determine execution mode (local clone vs curl pipe)
if [ -n "${BASH_SOURCE[0]}" ] && [ -f "${BASH_SOURCE[0]}" ] && [ -d "$(dirname "${BASH_SOURCE[0]}")/gdrive_sync" ]; then
    DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    # Piped via curl / remote execution
    DIR="$DEFAULT_INSTALL_DIR"
    echo "=========================================================="
    echo "   Downloading Google Drive Desktop for Linux...          "
    echo "=========================================================="
    mkdir -p "$DIR"
    if [ -d "$DIR/.git" ]; then
        echo "Updating existing installation in $DIR..."
        git -C "$DIR" pull --quiet || true
    else
        echo "Cloning repository into $DIR..."
        git clone --depth 1 "$REPO_URL" "$DIR"
    fi
fi

export PYTHONPATH="$DIR:$PYTHONPATH"

echo "=========================================================="
echo "      Installing Google Drive Desktop for Linux           "
echo "=========================================================="

# 1. Download and setup cloud synchronization engine (rclone)
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

# 2. Download official Google Drive logo from internet & install all resolutions
echo "[2/4] Downloading official Google Drive logo from internet & setting up icon themes..."
python3 "$DIR/gdrive_sync/utils/download_logo.py"

# 3. Setup desktop application launcher & autostart
echo "[3/4] Installing application launcher and background autostart..."
python3 -c "
import sys
sys.path.insert(0, '$DIR')
from gdrive_sync.utils.desktop_entry import desktop_mgr
desktop_mgr.project_root = __import__('pathlib').Path('$DIR')
desktop_mgr.run_script = desktop_mgr.project_root / 'run.sh'
desktop_mgr.install_application_launcher()
desktop_mgr.update_autostart(True)
"

# Create terminal CLI shortcut in ~/.local/bin
mkdir -p "$HOME/.local/bin"
ln -sf "$DIR/run.sh" "$HOME/.local/bin/google-drive"
chmod +x "$HOME/.local/bin/google-drive"

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
echo "To launch from terminal:"
echo "  google-drive          (Opens the GUI window)"
echo "  google-drive --hidden (Runs silently in background on boot)"
echo "=========================================================="
