"""Classification and normalisation of what the user typed into the search box."""

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

SEARCH_RESULTS = 24

_YT_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")
_CHANNEL_ROOT = re.compile(r"^/(@[^/]+|channel/[^/]+|c/[^/]+|user/[^/]+)/?$")
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+")
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


@dataclass(frozen=True)
class ParsedInput:
    kind: str  # "empty" | "search" | "url"
    query: str  # what to hand to yt-dlp
    is_youtube: bool = False
    has_video: bool = False
    has_playlist: bool = False


def extract_url(text: str) -> Optional[str]:
    """Return the first http(s) URL found in arbitrary text (e.g. clipboard)."""
    match = _URL_IN_TEXT.search(text or "")
    if not match:
        return None
    return match.group(0).rstrip(").,;]")


def is_youtube_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return any(host == h or host.endswith("." + h) for h in _YT_HOSTS)


def normalize_url(url: str) -> str:
    """Make YouTube URLs friendlier to yt-dlp.

    * bare channel URLs (``/@name``) are pointed at their *Videos* tab so the
      user gets a list of uploads rather than a list of channel tabs;
    * ``youtube.com/shorts/<id>`` and ``youtu.be/<id>`` stay as they are –
      yt-dlp understands them natively.
    """
    url = url.strip()
    if not is_youtube_url(url):
        return url
    parts = urlparse(url)
    if _CHANNEL_ROOT.match(parts.path or ""):
        path = parts.path.rstrip("/") + "/videos"
        return urlunparse(parts._replace(path=path))
    return url


def video_only_url(url: str) -> str:
    """Strip the playlist part of a watch URL (``&list=…&index=…``)."""
    parts = urlparse(url)
    query = parse_qs(parts.query)
    for key in ("list", "index", "start_radio", "pp"):
        query.pop(key, None)
    return urlunparse(parts._replace(query=urlencode(query, doseq=True)))


def playlist_url(url: str) -> Optional[str]:
    """Return the canonical playlist URL for a watch URL that carries ``list=``."""
    query = parse_qs(urlparse(url).query)
    list_id = (query.get("list") or [None])[0]
    if not list_id:
        return None
    return f"https://www.youtube.com/playlist?list={list_id}"


def parse_input(text: str) -> ParsedInput:
    text = (text or "").strip()
    if not text:
        return ParsedInput("empty", "")

    url = text if re.match(r"^https?://", text, re.I) else None
    if url is None and re.match(r"^(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/", text, re.I):
        url = "https://" + text
    if url is None and _VIDEO_ID.match(text) and any(c.isdigit() for c in text) and any(c.isalpha() for c in text):
        url = f"https://www.youtube.com/watch?v={text}"

    if url is None:
        return ParsedInput("search", f"ytsearch{SEARCH_RESULTS}:{text}")

    yt = is_youtube_url(url)
    query = parse_qs(urlparse(url).query)
    parts = urlparse(url)
    has_video = bool(query.get("v")) or "/shorts/" in parts.path or (parts.hostname or "").endswith("youtu.be")
    has_playlist = bool(query.get("list")) or parts.path.rstrip("/").endswith("/playlist")
    return ParsedInput("url", normalize_url(url), is_youtube=yt, has_video=has_video, has_playlist=has_playlist)


def thumbnail_for_id(video_id: Optional[str], quality: str = "mqdefault") -> Optional[str]:
    if not video_id or not _VIDEO_ID.match(video_id):
        return None
    return f"https://i.ytimg.com/vi/{video_id}/{quality}.jpg"
