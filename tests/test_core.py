import json
import re
from pathlib import Path

import pytest

from ytgui import errors, formatting, i18n, urls
from ytgui.history import HistoryItem, HistoryStore
from ytgui.media import _to_entries, build_quality_options
from ytgui.options import DownloadRequest, build_args, command_line, is_valid_rate, safe_folder_name, to_ydl_opts
from ytgui.settings import Settings, SettingsStore


# ---------------------------------------------------------------- urls
@pytest.mark.parametrize("text, kind, video, playlist", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "url", True, False),
    ("https://youtu.be/dQw4w9WgXcQ", "url", True, False),
    ("youtube.com/watch?v=dQw4w9WgXcQ&list=PL123", "url", True, True),
    ("https://www.youtube.com/playlist?list=PL123", "url", False, True),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "url", True, False),
    ("dQw4w9WgXcQ", "url", True, False),
    ("lofi hip hop", "search", False, False),
    ("   ", "empty", False, False),
])
def test_parse_input(text, kind, video, playlist):
    parsed = urls.parse_input(text)
    assert parsed.kind == kind
    if kind == "url":
        assert parsed.has_video is video
        assert parsed.has_playlist is playlist


def test_search_query_uses_ytsearch():
    assert urls.parse_input("cats").query == f"ytsearch{urls.SEARCH_RESULTS}:cats"


def test_channel_root_points_to_videos_tab():
    assert urls.normalize_url("https://www.youtube.com/@SomeChannel") == "https://www.youtube.com/@SomeChannel/videos"
    assert urls.normalize_url("https://www.youtube.com/@SomeChannel/shorts").endswith("/shorts")
    assert urls.normalize_url("https://example.com/@x") == "https://example.com/@x"


def test_playlist_helpers():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123&index=4"
    assert urls.playlist_url(url) == "https://www.youtube.com/playlist?list=PL123"
    assert urls.video_only_url(url) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_extract_url_from_text():
    assert urls.extract_url("look at this https://youtu.be/abc123def45, nice") == "https://youtu.be/abc123def45"
    assert urls.extract_url("no link here") is None


# ---------------------------------------------------------------- formatting
def test_format_helpers():
    assert formatting.format_bytes(0) == "0 B"
    assert formatting.format_bytes(1536) == "2 KB"
    assert formatting.format_bytes(1000 * 1024) == "1.0 MB"
    assert formatting.format_bytes(5 * 1024 ** 3) == "5.0 GB"
    assert formatting.format_duration(65) == "1:05"
    assert formatting.format_duration(3725) == "1:02:05"
    assert formatting.format_count(1834221, "en") == "1.8M"
    assert formatting.format_count(1834221, "tr") == "1,8 Mn"
    assert formatting.format_upload_date("20260412") == "12.04.2026"


# ---------------------------------------------------------------- errors
@pytest.mark.parametrize("message, key", [
    ("ERROR: [youtube] abc: Sign in to confirm you're not a bot.", "err_bot_check"),
    ("ERROR: [youtube] abc: Sign in to confirm your age", "err_age"),
    ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access", "err_private"),
    ("ERROR: unable to download video data: HTTP Error 403: Forbidden", "err_forbidden"),
    ("ERROR: Unable to download webpage: HTTP Error 404: Not Found", "err_unavailable"),
    ("ERROR: [youtube] abc: Video unavailable", "err_unavailable"),
    ("ERROR: Requested format is not available", "err_format"),
    ("ERROR: Unable to download webpage: <urlopen error [Errno -2] Name or service not known>", "err_network"),
    ("something odd happened", "err_generic"),
])
def test_friendly_error(message, key):
    assert errors.friendly_error(message)[0] == key


def test_clean_message_strips_prefix():
    assert errors.clean_message("ERROR: [youtube] dQw4w9WgXcQ: Video unavailable") == "Video unavailable"


# ---------------------------------------------------------------- options
def _req(**kw):
    base = dict(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", output_dir="/tmp/out")
    base.update(kw)
    return DownloadRequest(**base)


def test_video_args_with_ffmpeg():
    args = build_args(_req(video_quality="1080", video_container="mp4"), "/usr/bin")
    joined = " ".join(args)
    assert "-f bv*+ba/b" in joined
    assert "--merge-output-format mp4" in joined
    assert "res:1080" in joined and "ext:mp4:m4a" in joined
    assert "--embed-thumbnail" in joined and "--embed-metadata" in joined


def test_video_args_without_ffmpeg_use_single_file():
    args = build_args(_req(video_quality="720"), None)
    assert args[args.index("-f") + 1] == "b"
    assert "--merge-output-format" not in args
    assert "--embed-thumbnail" not in args


def test_audio_args():
    args = build_args(_req(mode="audio", audio_format="mp3", audio_quality="192"), "/usr/bin")
    assert args[args.index("--audio-format") + 1] == "mp3"
    assert args[args.index("--audio-quality") + 1] == "192K"
    assert "-x" in args
    flac = build_args(_req(mode="audio", audio_format="flac", audio_quality="192"), "/usr/bin")
    assert flac[flac.index("--audio-quality") + 1] == "0"
    wav = build_args(_req(mode="audio", audio_format="wav"), "/usr/bin")
    assert "--embed-thumbnail" not in wav


def test_subfolder_and_numbering():
    args = build_args(_req(subfolder='My: "List"/x', index=7), None)
    out_dir = args[args.index("-P") + 1]
    assert out_dir.endswith("My_ _List__x")
    assert args[args.index("-o") + 1].startswith("007 - ")


def test_ydl_opts_are_parsed_by_ytdlp():
    req = _req(mode="audio", sponsorblock="remove", rate_limit="2M", subtitles=True, subtitle_langs="tr, en")
    opts = to_ydl_opts(build_args(req, "/usr/bin"))
    assert opts["ignoreerrors"] is False
    assert opts["noplaylist"] is True
    assert opts["ratelimit"] == 2 * 1024 * 1024
    assert opts["subtitleslangs"] == ["tr", "en"]
    keys = [pp["key"] for pp in opts["postprocessors"]]
    assert "FFmpegExtractAudio" in keys and "SponsorBlock" in keys


def test_extra_args_and_command_line():
    req = _req(extra_args="--limit-rate 1M --no-part")
    assert "--no-part" in build_args(req, None)
    assert command_line(req, None).startswith("yt-dlp ")


def test_request_from_settings_snapshot():
    s = Settings(mode="audio", audio_format="opus", use_archive=True)
    req = DownloadRequest.from_settings(s, "https://youtu.be/x", archive_path="/tmp/a.txt", title="T")
    assert req.mode == "audio" and req.audio_format == "opus" and req.archive_path == "/tmp/a.txt"
    assert DownloadRequest.from_settings(Settings(), "u", archive_path="/tmp/a.txt").archive_path == ""


def test_validators():
    assert is_valid_rate("") and is_valid_rate("500K") and is_valid_rate("2.5M")
    assert not is_valid_rate("fast")
    assert safe_folder_name("  ...  ") == "Playlist"


# ---------------------------------------------------------------- media parsing
def test_quality_buckets_and_sizes():
    info = {
        "duration": 100,
        "formats": [
            {"format_id": "140", "vcodec": "none", "acodec": "mp4a", "abr": 128, "ext": "m4a", "filesize": 1_600_000},
            {"format_id": "137", "vcodec": "avc1", "acodec": "none", "height": 1080, "width": 1920, "filesize": 50_000_000, "fps": 30},
            {"format_id": "299", "vcodec": "avc1", "acodec": "none", "height": 1080, "width": 1920, "filesize": 70_000_000, "fps": 60},
            {"format_id": "22", "vcodec": "avc1", "acodec": "mp4a", "height": 720, "width": 1280, "tbr": 1000},
            {"format_id": "vert", "vcodec": "vp9", "acodec": "none", "height": 1918, "width": 1076, "filesize": 9},
        ],
    }
    options, audio = build_quality_options(info)
    assert audio == 1_600_000
    by_key = {o.key: o for o in options}
    assert list(by_key) == ["1080", "720"]  # vertical 1076x1918 counts as 1080p
    assert by_key["1080"].size == 70_000_000 + 1_600_000
    assert by_key["1080"].fps == 60
    assert by_key["720"].size == 1000 * 1000 // 8 * 100  # muxed: no audio added


def test_flat_entries():
    raw = [
        {"id": "dQw4w9WgXcQ", "title": "A", "duration": 10, "ie_key": "Youtube", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        None,
        {"id": "aaaaaaaaaaa", "title": "[Private video]", "ie_key": "Youtube"},
    ]
    entries = _to_entries(raw)
    assert len(entries) == 2
    assert entries[0].thumbnail == "https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg"
    assert entries[1].available is False
    assert entries[1].url == "https://www.youtube.com/watch?v=aaaaaaaaaaa"


# ---------------------------------------------------------------- persistence
def test_settings_roundtrip_and_sanitize(tmp_path):
    path = tmp_path / "s.json"
    store = SettingsStore(path)
    seen = []
    store.subscribe(lambda k, v: seen.append((k, v)))
    store.set("max_concurrent", 99)
    assert store.settings.max_concurrent == 8
    assert seen == [("max_concurrent", 8)]
    reloaded = SettingsStore(path)
    assert reloaded.settings.max_concurrent == 8

    path.write_text(json.dumps({"video_quality": "9999", "mode": 3, "unknown": True, "retries": 2.0}))
    s = SettingsStore(path).settings
    assert s.video_quality == "best" and s.mode == "video" and s.retries == 2


def test_corrupt_settings_fall_back_to_defaults(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not json")
    assert SettingsStore(path).settings == Settings(download_dir=SettingsStore(path).settings.download_dir)


def test_history_store(tmp_path):
    store = HistoryStore(tmp_path / "h.json")
    store.add(HistoryItem(title="Alpha", url="u1", uploader="Chan"))
    store.add(HistoryItem(title="Beta", url="u2"))
    assert [i.title for i in store.items] == ["Beta", "Alpha"]
    assert [i.title for i in store.search("chan")] == ["Alpha"]
    reloaded = HistoryStore(tmp_path / "h.json")
    reloaded.remove(reloaded.items[0].id)
    assert [i.title for i in HistoryStore(tmp_path / "h.json").items] == ["Alpha"]


# ---------------------------------------------------------------- i18n
def test_every_used_key_is_translated():
    used = set()
    for path in (Path(__file__).resolve().parent.parent / "ytgui").rglob("*.py"):
        used |= set(re.findall(r'\bt\("([a-z0-9_]+)"', path.read_text(encoding="utf-8")))
    assert not sorted(k for k in used if k not in i18n.STRINGS)
    for key, value in i18n.STRINGS.items():
        assert set(value) == {"tr", "en"}, key
    for key in [k for k in i18n.STRINGS if k.startswith("err_") and not k.endswith("_hint")]:
        assert key + "_hint" in i18n.STRINGS


def test_language_resolution(monkeypatch):
    assert i18n.resolve_language("tr") == "tr"
    monkeypatch.setenv("LANG", "tr_TR.UTF-8")
    assert i18n.resolve_language("auto") == "tr"
    i18n.set_language("en")
    assert i18n.t("n_videos", n=3) == "3 videos"
    assert i18n.t("missing_key") == "missing_key"
