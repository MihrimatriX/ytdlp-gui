"""Map raw yt-dlp error text to short, actionable i18n keys."""

import re
from typing import Tuple

_RULES = [
    (("confirm you're not a bot", "confirm you’re not a bot", "not a bot"), "err_bot_check"),
    (("confirm your age", "age-restricted", "inappropriate for some users"), "err_age"),
    (("members-only", "join this channel", "available to this channel's members"), "err_members"),
    (("private video", "video is private"), "err_private"),
    (("premieres in", "this live event will begin", "premiere will begin"), "err_upcoming"),
    (("not available in your country", "geo restrict", "geo-restrict"), "err_geo"),
    (("requested format is not available", "no video formats found"), "err_format"),
    (("ffmpeg", "ffprobe"), "err_ffmpeg"),
    (("no space left", "disk full", "errno 28"), "err_disk"),
    (("permission denied", "errno 13", "access is denied"), "err_permission"),
    (("http error 403", "forbidden"), "err_forbidden"),
    (("http error 404", "http error 410"), "err_unavailable"),
    (("http error 429", "too many requests"), "err_rate_limited"),
    (("could not copy chrome cookie", "could not copy", "failed to decrypt", "cookie database",
      "cookies database", "could not find firefox", "could not find chrome", "could not find edge"), "err_cookies"),
    (("unable to download webpage", "timed out", "getaddrinfo", "name or service not known",
      "connection refused", "network is unreachable", "temporary failure in name resolution",
      "connection reset", "unable to connect"), "err_network"),
    (("video unavailable", "this video has been removed", "does not exist", "is not available"), "err_unavailable"),
    (("unsupported url",), "err_unsupported"),
]

_PREFIX = re.compile(r"^(ERROR:\s*)?(\[[^\]]+\]\s*)?([\w-]{6,}:\s*)?", re.I)


def clean_message(message: str) -> str:
    lines = [ln.strip() for ln in (message or "").splitlines() if ln.strip()]
    errors = [ln for ln in lines if ln.upper().startswith("ERROR")]
    line = (errors or lines or [""])[-1]
    return _PREFIX.sub("", line, count=1).strip()


def friendly_error(message: str) -> Tuple[str, str]:
    """Return ``(i18n_key, cleaned_detail)``."""
    lowered = (message or "").lower()
    for needles, key in _RULES:
        if any(n in lowered for n in needles):
            return key, clean_message(message)
    return "err_generic", clean_message(message)
