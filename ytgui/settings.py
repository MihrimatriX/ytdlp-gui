"""Persistent user settings stored as JSON in the user data directory."""

import json
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Callable, List, Optional

from .logs import get_logger
from .paths import default_download_dir, settings_file

log = get_logger(__name__)

VIDEO_QUALITIES = ["best", "2160", "1440", "1080", "720", "480", "360"]
VIDEO_CONTAINERS = ["mp4", "mkv", "webm"]
AUDIO_FORMATS = ["mp3", "m4a", "opus", "flac", "wav"]
AUDIO_QUALITIES = ["best", "320", "256", "192", "128"]
COOKIE_BROWSERS = ["", "chrome", "firefox", "edge", "brave", "opera", "vivaldi", "chromium", "safari"]
SPONSORBLOCK_MODES = ["off", "mark", "remove"]
THEME_MODES = ["system", "dark", "light"]
LANGUAGES = ["auto", "tr", "en"]
FILENAME_TEMPLATES = [
    "%(title)s.%(ext)s",
    "%(uploader)s - %(title)s.%(ext)s",
    "%(upload_date>%Y-%m-%d)s - %(title)s.%(ext)s",
    "%(title)s [%(id)s].%(ext)s",
]
ACCENT_COLORS = ["#FF3D57", "#7C4DFF", "#2979FF", "#00B8D4", "#00C853", "#FF9100"]


@dataclass
class Settings:
    # Appearance
    language: str = "auto"
    theme_mode: str = "dark"
    accent: str = ACCENT_COLORS[0]

    # Output
    download_dir: str = field(default_factory=default_download_dir)
    filename_template: str = FILENAME_TEMPLATES[0]
    playlist_subfolder: bool = True
    number_playlist_items: bool = False

    # Defaults for new downloads
    mode: str = "video"  # "video" | "audio"
    video_quality: str = "best"
    video_container: str = "mp4"
    prefer_compatible: bool = False  # prefer H.264/AAC for old players & editors
    audio_format: str = "mp3"
    audio_quality: str = "320"

    # Subtitles
    subtitles: bool = False
    subtitle_langs: str = "tr,en"
    auto_subtitles: bool = False
    embed_subtitles: bool = True

    # Post-processing
    embed_thumbnail: bool = True
    embed_metadata: bool = True
    embed_chapters: bool = True
    sponsorblock: str = "off"

    # Performance
    max_concurrent: int = 3
    concurrent_fragments: int = 4
    rate_limit: str = ""
    retries: int = 10

    # Network & accounts
    proxy: str = ""
    cookies_browser: str = ""
    cookies_file: str = ""
    use_archive: bool = False

    # App behaviour
    clipboard_watch: bool = True
    notify_on_complete: bool = True
    open_folder_when_done: bool = False
    extra_args: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        defaults = cls()
        known = {f.name: f for f in fields(cls)}
        for key, value in (data or {}).items():
            if key not in known:
                continue
            expected = type(getattr(defaults, key))
            if expected is int and isinstance(value, (int, float)) and not isinstance(value, bool):
                value = int(value)
            if isinstance(value, expected):
                setattr(defaults, key, value)
        defaults._sanitize()
        return defaults

    def _sanitize(self) -> None:
        def pick(value: str, allowed: List[str], fallback: str) -> str:
            return value if value in allowed else fallback

        self.language = pick(self.language, LANGUAGES, "auto")
        self.theme_mode = pick(self.theme_mode, THEME_MODES, "dark")
        self.mode = pick(self.mode, ["video", "audio"], "video")
        self.video_quality = pick(self.video_quality, VIDEO_QUALITIES, "best")
        self.video_container = pick(self.video_container, VIDEO_CONTAINERS, "mp4")
        self.audio_format = pick(self.audio_format, AUDIO_FORMATS, "mp3")
        self.audio_quality = pick(self.audio_quality, AUDIO_QUALITIES, "320")
        self.cookies_browser = pick(self.cookies_browser, COOKIE_BROWSERS, "")
        self.sponsorblock = pick(self.sponsorblock, SPONSORBLOCK_MODES, "off")
        self.max_concurrent = max(1, min(8, self.max_concurrent))
        self.concurrent_fragments = max(1, min(16, self.concurrent_fragments))
        self.retries = max(0, min(50, self.retries))
        if not self.download_dir:
            self.download_dir = default_download_dir()

    def to_dict(self) -> dict:
        return asdict(self)


class SettingsStore:
    """Thread-safe holder for the active settings with change notification."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or settings_file()
        self._lock = threading.Lock()
        self._listeners: List[Callable[[str, Any], None]] = []
        self.settings = self._load()

    def _load(self) -> Settings:
        try:
            if self.path.exists():
                return Settings.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            log.warning("Could not read settings, using defaults: %s", exc)
        return Settings()

    def save(self) -> None:
        with self._lock:
            try:
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self.settings.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
                tmp.replace(self.path)
            except OSError as exc:
                log.error("Could not save settings: %s", exc)

    def get(self, key: str) -> Any:
        return getattr(self.settings, key)

    def set(self, key: str, value: Any) -> None:
        if getattr(self.settings, key) == value:
            return
        setattr(self.settings, key, value)
        self.settings._sanitize()
        self.save()
        for listener in list(self._listeners):
            try:
                listener(key, getattr(self.settings, key))
            except Exception:  # listeners must never break settings writes
                log.exception("Settings listener failed")

    def reset(self) -> None:
        keep_dir = self.settings.download_dir
        self.settings = Settings(download_dir=keep_dir)
        self.save()
        for listener in list(self._listeners):
            listener("*", None)

    def subscribe(self, listener: Callable[[str, Any], None]) -> None:
        self._listeners.append(listener)
