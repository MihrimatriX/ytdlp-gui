"""Translate a download request into yt-dlp options.

Options are expressed as yt-dlp *command line arguments* and turned into the
``YoutubeDL`` params dict by yt-dlp's own parser.  This keeps us aligned with
yt-dlp's semantics (post-processor ordering, SponsorBlock, thumbnails …) and
lets us show users the exact equivalent command.
"""

import os
import re
import shlex
import shutil
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from .settings import Settings

_RATE = re.compile(r"^\d+(\.\d+)?[KMG]?$", re.I)
_UNSAFE_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
SPONSORBLOCK_REMOVE = "sponsor,selfpromo,interaction"
THUMBNAIL_CONTAINERS = {"mp4", "mkv", "mp3", "m4a", "opus", "flac"}


@dataclass
class DownloadRequest:
    """Everything needed to download one item – a snapshot taken at enqueue time."""

    url: str
    title: str = ""
    thumbnail: Optional[str] = None
    duration: Optional[float] = None
    uploader: str = ""

    mode: str = "video"
    video_quality: str = "best"
    video_container: str = "mp4"
    prefer_compatible: bool = False
    audio_format: str = "mp3"
    audio_quality: str = "320"

    subtitles: bool = False
    subtitle_langs: str = "tr,en"
    auto_subtitles: bool = False
    embed_subtitles: bool = True

    output_dir: str = ""
    subfolder: str = ""
    index: Optional[int] = None

    filename_template: str = "%(title)s.%(ext)s"
    embed_thumbnail: bool = True
    embed_metadata: bool = True
    embed_chapters: bool = True
    sponsorblock: str = "off"

    concurrent_fragments: int = 4
    rate_limit: str = ""
    retries: int = 10
    proxy: str = ""
    cookies_browser: str = ""
    cookies_file: str = ""
    archive_path: str = ""
    extra_args: str = ""

    @classmethod
    def from_settings(cls, settings: Settings, url: str, archive_path: str = "", **overrides) -> "DownloadRequest":
        base = dict(
            url=url,
            mode=settings.mode,
            video_quality=settings.video_quality,
            video_container=settings.video_container,
            prefer_compatible=settings.prefer_compatible,
            audio_format=settings.audio_format,
            audio_quality=settings.audio_quality,
            subtitles=settings.subtitles,
            subtitle_langs=settings.subtitle_langs,
            auto_subtitles=settings.auto_subtitles,
            embed_subtitles=settings.embed_subtitles,
            output_dir=settings.download_dir,
            filename_template=settings.filename_template,
            embed_thumbnail=settings.embed_thumbnail,
            embed_metadata=settings.embed_metadata,
            embed_chapters=settings.embed_chapters,
            sponsorblock=settings.sponsorblock,
            concurrent_fragments=settings.concurrent_fragments,
            rate_limit=settings.rate_limit,
            retries=settings.retries,
            proxy=settings.proxy,
            cookies_browser=settings.cookies_browser,
            cookies_file=settings.cookies_file,
            archive_path=archive_path if settings.use_archive else "",
            extra_args=settings.extra_args,
        )
        base.update(overrides)
        return cls(**base)

    def to_dict(self) -> Dict:
        return asdict(self)


def safe_folder_name(name: str, limit: int = 80) -> str:
    cleaned = _UNSAFE_PATH_CHARS.sub("_", name or "").strip(" .")
    return cleaned[:limit].rstrip(" .") or "Playlist"


def is_valid_rate(value: str) -> bool:
    return not value or bool(_RATE.match(value.strip()))


def available_js_runtimes() -> List[str]:
    return [name for name in ("deno", "node", "bun") if shutil.which(name)]


def _has_ejs() -> bool:
    import importlib.util

    return importlib.util.find_spec("yt_dlp_ejs") is not None


def build_args(req: DownloadRequest, ffmpeg_location: Optional[str]) -> List[str]:
    has_ffmpeg = bool(ffmpeg_location)
    args: List[str] = ["--no-playlist", "--no-mtime", "--trim-filenames", "150"]

    # Output location / naming
    out_dir = req.output_dir or os.getcwd()
    if req.subfolder:
        out_dir = os.path.join(out_dir, safe_folder_name(req.subfolder))
    template = req.filename_template or "%(title)s.%(ext)s"
    if req.index is not None:
        template = f"{req.index:03d} - {template}"
    args += ["-P", out_dir, "-o", template]
    if ffmpeg_location:
        args += ["--ffmpeg-location", ffmpeg_location]

    # Format selection
    if req.mode == "audio":
        args += ["-f", "ba/b", "-x", "--audio-format", req.audio_format]
        if req.audio_format in ("mp3", "m4a", "opus") and req.audio_quality != "best":
            args += ["--audio-quality", f"{req.audio_quality}K"]
        else:
            args += ["--audio-quality", "0"]
    else:
        sort: List[str] = []
        if req.prefer_compatible:
            sort += ["vcodec:h264", "acodec:aac"]
        if req.video_quality != "best":
            sort.append(f"res:{req.video_quality}")
        if req.video_container == "mp4":
            sort.append("ext:mp4:m4a")
        elif req.video_container == "webm":
            sort.append("ext:webm:webm")
        if has_ffmpeg:
            args += ["-f", "bv*+ba/b", "--merge-output-format", req.video_container]
        else:
            # Without FFmpeg we can only take pre-merged single-file formats.
            args += ["-f", "b"]
        if sort:
            args += ["-S", ",".join(sort)]

    # Subtitles
    if req.subtitles or req.auto_subtitles:
        if req.subtitles:
            args.append("--write-subs")
        if req.auto_subtitles:
            args.append("--write-auto-subs")
        langs = re.sub(r"\s+", "", req.subtitle_langs or "") or "en"
        args += ["--sub-langs", langs]
        if req.mode == "video" and req.embed_subtitles and has_ffmpeg:
            args.append("--embed-subs")
        elif has_ffmpeg:
            args += ["--convert-subs", "srt"]

    # Post-processing (all need FFmpeg)
    if has_ffmpeg:
        container = req.audio_format if req.mode == "audio" else req.video_container
        if req.embed_metadata:
            args.append("--embed-metadata")
        if req.embed_chapters and req.mode == "video":
            args.append("--embed-chapters")
        if req.embed_thumbnail and container in THUMBNAIL_CONTAINERS:
            args.append("--embed-thumbnail")
        if req.sponsorblock == "mark" and req.mode == "video":
            args += ["--sponsorblock-mark", "all"]
        elif req.sponsorblock == "remove":
            args += ["--sponsorblock-remove", SPONSORBLOCK_REMOVE]

    # Performance & reliability
    args += ["-N", str(max(1, req.concurrent_fragments))]
    args += ["--retries", str(req.retries), "--fragment-retries", str(req.retries)]
    if req.rate_limit and is_valid_rate(req.rate_limit):
        args += ["-r", req.rate_limit.strip().upper()]

    # Network & authentication
    if req.proxy.strip():
        args += ["--proxy", req.proxy.strip()]
    if req.cookies_file and os.path.isfile(req.cookies_file):
        args += ["--cookies", req.cookies_file]
    elif req.cookies_browser:
        args += ["--cookies-from-browser", req.cookies_browser]
    if req.archive_path:
        args += ["--download-archive", req.archive_path]

    # YouTube needs a JavaScript runtime for full format support.
    for runtime in available_js_runtimes():
        if runtime != "deno":  # deno is enabled by default
            args += ["--js-runtimes", runtime]
    if not _has_ejs():
        args += ["--remote-components", "ejs:github"]

    if req.extra_args.strip():
        args += shlex.split(req.extra_args)
    return args


def probe_args(settings: Settings) -> List[str]:
    """Arguments shared by metadata extraction (no download)."""
    args: List[str] = []
    if settings.proxy.strip():
        args += ["--proxy", settings.proxy.strip()]
    if settings.cookies_file and os.path.isfile(settings.cookies_file):
        args += ["--cookies", settings.cookies_file]
    elif settings.cookies_browser:
        args += ["--cookies-from-browser", settings.cookies_browser]
    for runtime in available_js_runtimes():
        if runtime != "deno":
            args += ["--js-runtimes", runtime]
    if not _has_ejs():
        args += ["--remote-components", "ejs:github"]
    return args


def to_ydl_opts(args: List[str]) -> Dict:
    """Run yt-dlp's own option parser over *args*."""
    import yt_dlp

    parsed = yt_dlp.parse_options(args)
    opts = dict(parsed.ydl_opts)
    # The CLI defaults to "ignore errors while downloading"; we want failures to raise.
    opts["ignoreerrors"] = False
    opts["quiet"] = True
    opts["noprogress"] = True
    opts["no_warnings"] = False
    opts.pop("warn_when_outdated", None)
    return opts


def command_line(req: DownloadRequest, ffmpeg_location: Optional[str]) -> str:
    parts = ["yt-dlp"] + build_args(req, ffmpeg_location) + [req.url]
    return " ".join(shlex.quote(p) for p in parts)
