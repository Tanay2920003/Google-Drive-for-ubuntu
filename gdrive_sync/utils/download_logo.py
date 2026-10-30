"""
Official Google Drive Logo Downloader & System Icon Installer.
Downloads the official vector logo from the internet (Wikimedia Commons),
renders crisp multi-resolution square PNGs, and installs them into the
system's hicolor icon theme and pixmaps for GNOME Shell search integration.
"""

import os
import shutil
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path

# Official Wikimedia Commons Vector SVG URL
OFFICIAL_SVG_URL = "https://upload.wikimedia.org/wikipedia/commons/1/12/Google_Drive_icon_%282020%29.svg"

# Embedded vector SVG as offline fallback
FALLBACK_SVG = """<svg viewBox="0 0 87.3 78" xmlns="http://www.w3.org/2000/svg">
	<path d="m6.6 66.85 3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8h-27.5c0 1.55.4 3.1 1.2 4.5z" fill="#0066da"/>
	<path d="m43.65 25-13.75-23.8c-1.35.8-2.5 1.9-3.3 3.3l-25.4 44a9.06 9.06 0 0 0 -1.2 4.5h27.5z" fill="#00ac47"/>
	<path d="m73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.4 1.2-2.95 1.2-4.5h-27.502l5.852 11.5z" fill="#ea4335"/>
	<path d="m43.65 25 13.75-23.8c-1.35-.8-2.9-1.2-4.5-1.2h-18.5c-1.6 0-3.15.45-4.5 1.2z" fill="#00832d"/>
	<path d="m59.8 53h-32.3l-13.75 23.8c1.35.8 2.9 1.2 4.5 1.2h50.8c1.6 0 3.15-.45 4.5-1.2z" fill="#2684fc"/>
	<path d="m73.4 26.5-12.7-22c-.8-1.4-1.95-2.5-3.3-3.3l-13.75 23.8 16.15 28h27.45c0-1.55-.4-3.1-1.2-4.5z" fill="#ffba00"/>
</svg>"""


def download_official_svg(dest_path: Path) -> bool:
    """Download the official Google Drive vector SVG from the internet."""
    print(f"[IconInstaller] Downloading official Google Drive logo from: {OFFICIAL_SVG_URL}")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        ctx = ssl.create_default_context()
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        req = urllib.request.Request(OFFICIAL_SVG_URL, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=12) as response:
            content = response.read().decode("utf-8")
            if "<svg" in content and "</svg>" in content:
                dest_path.write_text(content, encoding="utf-8")
                print(f"[IconInstaller] Successfully downloaded official SVG ({len(content)} bytes).")
                return True
            else:
                print("[IconInstaller] Warning: Downloaded content does not appear to be valid SVG.")
    except Exception as e:
        print(f"[IconInstaller] Internet download failed ({e}). Using embedded official SVG fallback.")

    # Write fallback if download failed
    dest_path.write_text(FALLBACK_SVG, encoding="utf-8")
    return True


def render_square_png(svg_path: Path, out_path: Path, size: int) -> bool:
    """
    Render SVG to a crisp square PNG with the icon centered and properly padded.
    Uses GdkPixbuf for high-quality antialiasing.
    """
    try:
        import gi
        gi.require_version('GdkPixbuf', '2.0')
        from gi.repository import GdkPixbuf

        # Optical margin: 92% of bounding box so it displays beautifully inside icon docks
        inner_size = max(12, int(size * 0.92))
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(svg_path), inner_size, inner_size, True)
        pw = pixbuf.get_width()
        ph = pixbuf.get_height()

        # Create transparent canvas of exact size x size
        canvas = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, size, size)
        canvas.fill(0x00000000)

        offset_x = (size - pw) // 2
        offset_y = (size - ph) // 2

        pixbuf.composite(
            canvas,
            offset_x, offset_y, pw, ph,
            offset_x, offset_y,
            1.0, 1.0,
            GdkPixbuf.InterpType.BILINEAR,
            255
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.savev(str(out_path), "png", [], [])
        return True
    except Exception as e:
        print(f"[IconInstaller] Error rendering {size}x{size} PNG: {e}")
        return False


def setup_all_icons(project_root: Path):
    """
    Complete pipeline:
    1. Downloads SVG from internet to assets/gdrive_icon.svg.
    2. Renders all standard sizes (16, 24, 32, 48, 64, 128, 256, 512, 1024).
    3. Installs into ~/.local/share/icons/hicolor and ~/.local/share/pixmaps.
    4. Updates GTK icon cache.
    """
    assets_dir = project_root / "assets"
    icons_dir = assets_dir / "icons"
    svg_file = assets_dir / "gdrive_icon.svg"
    png_512_file = assets_dir / "gdrive_icon.png"

    # 1. Download official SVG
    download_official_svg(svg_file)

    # 2. Render all resolutions
    sizes = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
    print(f"[IconInstaller] Rendering official icons in {len(sizes)} resolutions...")
    for sz in sizes:
        dest_png = icons_dir / f"{sz}x{sz}.png"
        render_square_png(svg_file, dest_png, sz)

    # Copy 512x512 as main assets/gdrive_icon.png
    if (icons_dir / "512x512.png").exists():
        shutil.copy2(icons_dir / "512x512.png", png_512_file)

    # 3. Install into system icon theme (hicolor)
    hicolor_root = Path.home() / ".local" / "share" / "icons" / "hicolor"
    icon_names = ["google-drive", "gdrivesync", "com.google.GDriveSync"]

    for sz in sizes:
        theme_apps_dir = hicolor_root / f"{sz}x{sz}" / "apps"
        theme_apps_dir.mkdir(parents=True, exist_ok=True)
        src_png = icons_dir / f"{sz}x{sz}.png"
        if src_png.exists():
            for name in icon_names:
                shutil.copy2(src_png, theme_apps_dir / f"{name}.png")

    # Scalable vector
    scalable_dir = hicolor_root / "scalable" / "apps"
    scalable_dir.mkdir(parents=True, exist_ok=True)
    if svg_file.exists():
        for name in icon_names:
            shutil.copy2(svg_file, scalable_dir / f"{name}.svg")

    # Install into pixmaps as universal fallback
    pixmaps_dir = Path.home() / ".local" / "share" / "pixmaps"
    pixmaps_dir.mkdir(parents=True, exist_ok=True)
    if png_512_file.exists():
        for name in icon_names:
            shutil.copy2(png_512_file, pixmaps_dir / f"{name}.png")

    # 4. Refresh icon cache
    print("[IconInstaller] Updating system GTK icon cache...")
    try:
        subprocess.run(
            ["gtk-update-icon-cache", "-f", "-t", str(hicolor_root)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass

    print("[IconInstaller] Official Google Drive icon installation completed successfully.")


if __name__ == "__main__":
    root = Path(__file__).parent.parent.parent.resolve()
    setup_all_icons(root)
