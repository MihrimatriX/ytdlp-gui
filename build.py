#!/usr/bin/env python3
"""Build a standalone executable for the current platform.

    python build.py                # build into ./dist
    python build.py --with-ffmpeg  # Windows: download & bundle FFmpeg first

Uses ``flet pack`` (PyInstaller under the hood), which also bundles the Flet
desktop client so the app runs without Python or an internet connection.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from ytgui import APP_NAME, APP_VERSION  # noqa: E402

NAMES = {"win32": "YouTube-Downloader", "darwin": "YouTube-Downloader-macOS"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--with-ffmpeg", action="store_true", help="Windows: download and bundle FFmpeg")
    args = parser.parse_args()

    os.chdir(ROOT)
    name = NAMES.get(sys.platform, "YouTube-Downloader-Linux")
    icon = ROOT / "assets" / ("icon.ico" if sys.platform == "win32" else "icon.png")

    cmd = [
        sys.executable, "-m", "flet_cli.cli", "pack", "main.py",
        "--name", name,
        "--icon", str(icon),
        "--product-name", APP_NAME,
        "--product-version", APP_VERSION,
        "--file-version", APP_VERSION,
        "--file-description", f"{APP_NAME} - powered by yt-dlp",
        "--bundle-id", "io.github.mihrimatrix.ytdlpgui",
        "--add-data", f"assets{os.pathsep}assets",
        "--yes",
    ]

    if args.with_ffmpeg:
        if sys.platform != "win32":
            print("--with-ffmpeg is only needed on Windows; Linux/macOS use the system FFmpeg.")
        else:
            from ytgui.ffmpeg import download_windows_build

            if not (ROOT / "ffmpeg" / "ffmpeg.exe").exists():
                print("Downloading FFmpeg…")
                download_windows_build(ROOT / "ffmpeg", lambda p: print(f"\r  {p * 100:5.1f}%", end=""))
                print()
            cmd += ["--add-binary", f"ffmpeg{os.sep}ffmpeg.exe{os.pathsep}ffmpeg",
                    "--add-binary", f"ffmpeg{os.sep}ffprobe.exe{os.pathsep}ffmpeg"]

    print(" ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
