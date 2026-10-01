"""Human-friendly formatting helpers (sizes, speeds, durations, counts)."""

from datetime import datetime
from typing import Optional, Union

Number = Union[int, float]


def format_bytes(size: Optional[Number]) -> str:
    if size is None or size < 0:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1000 or unit == units[-1]:
            if unit in ("B", "KB"):
                return f"{value:.0f} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def format_speed(bytes_per_sec: Optional[Number]) -> str:
    if not bytes_per_sec:
        return "—"
    return f"{format_bytes(bytes_per_sec)}/s"


def format_duration(seconds: Optional[Number]) -> str:
    if seconds is None:
        return ""
    seconds = int(round(seconds))
    if seconds < 0:
        return ""
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_eta(seconds: Optional[Number]) -> str:
    if seconds is None:
        return "—"
    return format_duration(seconds) or "0:00"


def format_count(n: Optional[Number], lang: str = "en") -> str:
    """Compact number: 1.2K / 3.4M (B in English, Mr in Turkish)."""
    if n is None:
        return ""
    n = float(n)
    suffixes = [(1e9, "Mr" if lang == "tr" else "B"), (1e6, "Mn" if lang == "tr" else "M"), (1e3, "B" if lang == "tr" else "K")]
    for threshold, suffix in suffixes:
        if n >= threshold:
            value = n / threshold
            text = f"{value:.1f}".rstrip("0").rstrip(".")
            if lang == "tr":
                text = text.replace(".", ",")
            return f"{text} {suffix}" if lang == "tr" else f"{text}{suffix}"
    return str(int(n))


def format_upload_date(value: Optional[str]) -> str:
    """yt-dlp upload_date (YYYYMMDD) -> DD.MM.YYYY."""
    if not value or len(value) != 8 or not value.isdigit():
        return ""
    try:
        return datetime.strptime(value, "%Y%m%d").strftime("%d.%m.%Y")
    except ValueError:
        return ""


def format_timestamp(ts: Optional[Number]) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")


def truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: max(0, limit - 1)].rstrip() + "…"
