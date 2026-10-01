"""System health checks shown on the System page."""

import json
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .ffmpeg import find_ffmpeg, has_ffprobe
from .options import available_js_runtimes
from .formatting import format_bytes
from .paths import is_frozen

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


@dataclass
class Check:
    key: str  # i18n key of the check title
    ok: Optional[bool]  # None = warning / unknown
    detail: str = ""
    hint_key: str = ""


def ytdlp_version() -> str:
    try:
        from yt_dlp.version import __version__
        return __version__
    except ImportError:
        return ""


def latest_ytdlp_version(timeout: float = 6.0) -> Optional[str]:
    try:
        with urllib.request.urlopen("https://pypi.org/pypi/yt-dlp/json", timeout=timeout) as resp:
            return json.load(resp)["info"]["version"]
    except Exception:
        return None


def _normalize_version(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return ()


def ffmpeg_version(location: Optional[str]) -> str:
    exe = "ffmpeg"
    if location:
        exe = str(Path(location) / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"))
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=8, creationflags=_NO_WINDOW)
        first = (out.stdout or "").splitlines()[0] if out.stdout else ""
        parts = first.split()
        return parts[2] if len(parts) > 2 else first
    except Exception:
        return ""


def internet_ok(timeout: float = 5.0) -> bool:
    try:
        req = urllib.request.Request("https://www.youtube.com/generate_204", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 204)
    except Exception:
        return False


def run_checks(download_dir: str) -> list:
    checks = []

    version = ytdlp_version()
    latest = latest_ytdlp_version()
    if latest and version and _normalize_version(latest) > _normalize_version(version):
        checks.append(Check("diag_ytdlp", None, f"{version} → {latest}", "hint_update_ytdlp"))
    else:
        checks.append(Check("diag_ytdlp", bool(version), version or "—"))

    location = find_ffmpeg()
    if location:
        detail = ffmpeg_version(location) or location
        checks.append(Check("diag_ffmpeg", True if has_ffprobe(location) else None, detail,
                            "" if has_ffprobe(location) else "hint_ffprobe"))
    else:
        checks.append(Check("diag_ffmpeg", False, "", "hint_ffmpeg"))

    runtimes = available_js_runtimes()
    checks.append(Check("diag_js", True if runtimes else None, ", ".join(runtimes) or "—",
                        "" if runtimes else "hint_js"))

    checks.append(Check("diag_internet", internet_ok(), "", ""))

    try:
        free = shutil.disk_usage(download_dir).free
        if free > 2 * 1024 ** 3:
            checks.append(Check("diag_disk", True, format_bytes(free)))
        else:
            checks.append(Check("diag_disk", None if free > 200 * 1024 ** 2 else False, format_bytes(free), "hint_disk"))
    except OSError:
        checks.append(Check("diag_disk", False, "", "hint_folder"))
    return checks


def can_self_update() -> bool:
    return not is_frozen()


def update_ytdlp() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pip", "install", "-U", "yt-dlp[default]"],
        capture_output=True, text=True, timeout=300, creationflags=_NO_WINDOW,
    )
