"""Metadata extraction ("probe") for videos, playlists, channels and searches."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .errors import friendly_error
from .logs import get_logger
from .options import probe_args, to_ydl_opts
from .settings import Settings
from .urls import thumbnail_for_id

log = get_logger(__name__)

QUALITY_STEPS = [4320, 2160, 1440, 1080, 720, 480, 360, 240, 144]
QUALITY_TAGS = {4320: "8K", 2160: "4K", 1440: "2K", 1080: "Full HD", 720: "HD"}


class ProbeError(Exception):
    def __init__(self, key: str, detail: str = ""):
        super().__init__(detail or key)
        self.key = key
        self.detail = detail


@dataclass
class QualityOption:
    key: str  # value for DownloadRequest.video_quality ("1080", ...)
    height: int
    size: Optional[int] = None
    fps: Optional[float] = None
    hdr: bool = False

    @property
    def label(self) -> str:
        return f"{self.height}p"

    @property
    def tag(self) -> str:
        return QUALITY_TAGS.get(self.height, "")


@dataclass
class MediaEntry:
    url: str
    id: str = ""
    title: str = ""
    duration: Optional[float] = None
    thumbnail: Optional[str] = None
    uploader: str = ""
    view_count: Optional[int] = None
    index: int = 0
    available: bool = True


@dataclass
class ProbeResult:
    kind: str  # "video" | "list"
    source: str = "video"  # "video" | "playlist" | "channel" | "search"
    id: str = ""
    url: str = ""
    title: str = ""
    uploader: str = ""
    thumbnail: Optional[str] = None
    duration: Optional[float] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    upload_date: str = ""
    is_live: bool = False
    qualities: List[QualityOption] = field(default_factory=list)
    audio_size: Optional[int] = None
    entries: List[MediaEntry] = field(default_factory=list)
    playlist_url: Optional[str] = None  # video URL that also references a playlist

    @property
    def total_duration(self) -> float:
        return sum(e.duration or 0 for e in self.entries)


def _format_size(fmt: Dict[str, Any], duration: Optional[float]) -> Optional[int]:
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    if size:
        return int(size)
    tbr = fmt.get("tbr")
    if tbr and duration:
        return int(tbr * 1000 / 8 * duration)
    return None


def _short_side(fmt: Dict[str, Any]) -> Optional[int]:
    height, width = fmt.get("height"), fmt.get("width")
    if height and width:
        return min(height, width)
    return height or None


def _bucket(side: int) -> int:
    """Map an actual resolution (e.g. 1076) to the nearest standard step at or below."""
    for step in QUALITY_STEPS:
        if side >= step * 0.92:
            return step
    return QUALITY_STEPS[-1]


def build_quality_options(info: Dict[str, Any]) -> (List[QualityOption], Optional[int]):
    formats = info.get("formats") or []
    duration = info.get("duration")
    audio = [
        f for f in formats
        if f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none")
    ]
    best_audio = max(audio, key=lambda f: (f.get("abr") or 0, f.get("ext") == "m4a"), default=None)
    audio_size = _format_size(best_audio, duration) if best_audio else None

    buckets: Dict[int, QualityOption] = {}
    for fmt in formats:
        if fmt.get("vcodec") in (None, "none"):
            continue
        side = _short_side(fmt)
        if not side:
            continue
        step = _bucket(side)
        size = _format_size(fmt, duration)
        if size and fmt.get("acodec") in (None, "none") and audio_size:
            size += audio_size
        current = buckets.get(step)
        fps = fmt.get("fps")
        hdr = (fmt.get("dynamic_range") or "SDR") != "SDR"
        if current is None:
            buckets[step] = QualityOption(key=str(step), height=step, size=size, fps=fps, hdr=hdr)
        else:
            current.size = max(filter(None, [current.size, size]), default=None)
            current.fps = max(filter(None, [current.fps, fps]), default=None)
            current.hdr = current.hdr or hdr
    options = sorted(buckets.values(), key=lambda q: q.height, reverse=True)
    return options, audio_size


def _pick_thumbnail(entry: Dict[str, Any]) -> Optional[str]:
    thumb = thumbnail_for_id(entry.get("id")) if entry.get("ie_key", "Youtube") == "Youtube" else None
    if thumb:
        return thumb
    thumbs = [t for t in (entry.get("thumbnails") or []) if t.get("url")]
    if thumbs:
        sized = [t for t in thumbs if (t.get("width") or 0) >= 300]
        return (sized[0] if sized else thumbs[-1])["url"]
    return entry.get("thumbnail")


def _entry_url(entry: Dict[str, Any]) -> Optional[str]:
    url = entry.get("webpage_url") or entry.get("url")
    if url and url.startswith("http"):
        return url
    if entry.get("id") and entry.get("ie_key", "Youtube") == "Youtube":
        return f"https://www.youtube.com/watch?v={entry['id']}"
    return url


def _to_entries(raw_entries) -> List[MediaEntry]:
    entries: List[MediaEntry] = []
    for i, entry in enumerate(raw_entries or [], start=1):
        if not entry:
            continue
        url = _entry_url(entry)
        if not url:
            continue
        title = entry.get("title") or ""
        unavailable = title in ("[Private video]", "[Deleted video]") or entry.get("availability") in (
            "private", "needs_auth", "subscriber_only", "premium_only",
        )
        entries.append(MediaEntry(
            url=url,
            id=entry.get("id") or "",
            title=title or url,
            duration=entry.get("duration"),
            thumbnail=_pick_thumbnail(entry),
            uploader=entry.get("channel") or entry.get("uploader") or "",
            view_count=entry.get("view_count"),
            index=i,
            available=not unavailable,
        ))
    return entries


def probe(query: str, settings: Settings, single_video: bool = True) -> ProbeResult:
    """Fetch metadata for *query* (URL or ``ytsearchN:...``). Blocking."""
    import yt_dlp

    opts = to_ydl_opts(probe_args(settings))
    opts.update({
        "extract_flat": "in_playlist",
        "skip_download": True,
        "noplaylist": single_video,
        "lazy_playlist": False,
        "format": "bv*+ba/b",
        "ignore_no_formats_error": True,
        "logger": _QuietLogger(),
    })
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(query, download=False)
    except yt_dlp.utils.DownloadError as exc:
        key, detail = friendly_error(str(exc))
        raise ProbeError(key, detail) from exc
    except Exception as exc:  # extractor bugs etc.
        log.exception("Probe failed")
        raise ProbeError("err_generic", str(exc)) from exc

    if not info:
        raise ProbeError("err_nothing_found")

    if info.get("_type") in ("playlist", "multi_video") or "entries" in info:
        entries = _to_entries(info.get("entries"))
        if not entries:
            raise ProbeError("err_nothing_found")
        if query.startswith("ytsearch"):
            source = "search"
        elif info.get("extractor_key") == "YoutubeTab" and not str(info.get("id", "")).startswith(("PL", "OL", "UU", "FL", "RD")):
            source = "channel"
        else:
            source = "playlist"
        return ProbeResult(
            kind="list",
            source=source,
            id=info.get("id") or "",
            url=info.get("webpage_url") or query,
            title=info.get("title") or "",
            uploader=info.get("channel") or info.get("uploader") or "",
            thumbnail=_pick_thumbnail({"thumbnails": info.get("thumbnails"), "ie_key": "", "thumbnail": info.get("thumbnail")}),
            entries=entries,
        )

    qualities, audio_size = build_quality_options(info)
    return ProbeResult(
        kind="video",
        source="video",
        id=info.get("id") or "",
        url=info.get("webpage_url") or query,
        title=info.get("title") or "",
        uploader=info.get("channel") or info.get("uploader") or "",
        thumbnail=info.get("thumbnail") or thumbnail_for_id(info.get("id"), "hqdefault"),
        duration=info.get("duration"),
        view_count=info.get("view_count"),
        like_count=info.get("like_count"),
        upload_date=info.get("upload_date") or "",
        is_live=bool(info.get("is_live")),
        qualities=qualities,
        audio_size=audio_size,
    )


class _QuietLogger:
    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        log.info("probe warning: %s", msg)

    def error(self, msg: str) -> None:
        log.info("probe error: %s", msg)
