#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$DIR:$PYTHONPATH"

# Ensure rclone binary exists in bin/
if [ ! -f "$DIR/bin/rclone" ]; then
    echo "[GDriveSync] Downloading rclone engine binary..."
    mkdir -p "$DIR/bin"
    curl -fsSL https://downloads.rclone.org/rclone-current-linux-amd64.zip -o "$DIR/bin/rclone.zip"
    unzip -q -j "$DIR/bin/rclone.zip" "*/rclone" -d "$DIR/bin/"
    rm -f "$DIR/bin/rclone.zip"
    chmod +x "$DIR/bin/rclone"
    echo "[GDriveSync] Rclone engine ready."
fi

# Run GDriveSync desktop application
exec python3 -m gdrive_sync.main "$@"
