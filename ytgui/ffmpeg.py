"""Locate FFmpeg, and on Windows download it on demand.

Search order: bundled with the frozen app -> app data dir -> PATH.

Usable as a build helper too::

    python -m ytgui.ffmpeg --download ffmpeg
"""

import argparse
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

from .logs import get_logger
from .paths import ffmpeg_dir, resource_dir

log = get_logger(__name__)

# yt-dlp's own patched FFmpeg builds (recommended by the yt-dlp project).
WINDOWS_BUILD_URL = (
    "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
)
_EXE = ".exe" if sys.platform == "win32" else ""


def _has_ffmpeg(directory: Path) -> bool:
    return (directory / f"ffmpeg{_EXE}").is_file()


def find_ffmpeg() -> Optional[str]:
    """Return a value suitable for yt-dlp's ``ffmpeg_location`` or None."""
    for candidate in (resource_dir() / "ffmpeg", ffmpeg_dir()):
        if _has_ffmpeg(candidate):
            return str(candidate)
    found = shutil.which("ffmpeg")
    return str(Path(found).parent) if found else None


def has_ffprobe(location: Optional[str]) -> bool:
    if location and (Path(location) / f"ffprobe{_EXE}").is_file():
        return True
    return shutil.which("ffprobe") is not None


def can_auto_install() -> bool:
    return sys.platform == "win32"


def install_hint() -> str:
    if sys.platform == "darwin":
        return "brew install ffmpeg"
    if sys.platform.startswith("linux"):
        return "sudo apt install ffmpeg"
    return ""


def download_windows_build(
    target: Optional[Path] = None,
    progress: Optional[Callable[[float], None]] = None,
) -> Path:
    """Download ffmpeg.exe + ffprobe.exe into *target* (default: app data dir)."""
    target = Path(target or ffmpeg_dir())
    target.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        log.info("Downloading FFmpeg from %s", WINDOWS_BUILD_URL)
        with urllib.request.urlopen(WINDOWS_BUILD_URL, timeout=60) as resp, open(tmp, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(min(done / total, 1.0))
        with zipfile.ZipFile(tmp) as archive:
            for member in archive.namelist():
                name = member.rsplit("/", 1)[-1].lower()
                if name in ("ffmpeg.exe", "ffprobe.exe"):
                    with archive.open(member) as src, open(target / name, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        if not (target / "ffmpeg.exe").is_file():
            raise RuntimeError("ffmpeg.exe not found in the downloaded archive")
        log.info("FFmpeg installed into %s", target)
        return target
    finally:
        tmp.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="FFmpeg helper for the YouTube Downloader build")
    parser.add_argument("--download", metavar="DIR", help="download the Windows build into DIR")
    args = parser.parse_args(argv)
    if args.download:
        if sys.platform != "win32":
            print("Automatic FFmpeg download is only needed on Windows; install it with your package manager.")
            return 0
        path = download_windows_build(Path(args.download), lambda p: print(f"\r{p * 100:5.1f}%", end=""))
        print(f"\nFFmpeg ready in {path}")
        return 0
    print(find_ffmpeg() or "FFmpeg not found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
