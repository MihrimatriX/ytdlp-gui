"""Filesystem locations: per-user config/data dirs and bundled resources."""

import os
import sys
from pathlib import Path

from . import APP_ID


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Directory holding bundled read-only resources (PyInstaller aware)."""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def _base_data_dir() -> Path:
    override = os.environ.get("YTDLP_GUI_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
        return Path(root) / APP_ID
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_ID
    root = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(root) / APP_ID


def data_dir() -> Path:
    path = _base_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_file() -> Path:
    return data_dir() / "settings.json"


def history_file() -> Path:
    return data_dir() / "history.json"


def archive_file() -> Path:
    return data_dir() / "archive.txt"


def log_file() -> Path:
    return data_dir() / "app.log"


def ffmpeg_dir() -> Path:
    return data_dir() / "ffmpeg"


def default_download_dir() -> str:
    downloads = Path.home() / "Downloads"
    return str(downloads if downloads.is_dir() else Path.home())
