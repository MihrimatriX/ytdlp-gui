"""End-to-end downloads through the real yt-dlp engine against a local HTTP server."""

import os
import shutil
import time

from ytgui import engine as E
from ytgui.options import DownloadRequest


def ffmpeg_dir():
    found = shutil.which("ffmpeg")
    return os.path.dirname(found) if found else None


def wait_for(manager, tasks, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        manager.drain()
        if all(t.is_finished or t.status == E.PAUSED for t in tasks):
            return
        time.sleep(0.2)
    raise AssertionError(f"timed out: {[t.status for t in tasks]}")


def test_video_and_audio_download(media_server, tmp_path):
    manager = E.DownloadManager(ffmpeg_dir, max_concurrent=2)
    video = manager.add(DownloadRequest(url=f"{media_server}/clip.mp4", output_dir=str(tmp_path)))
    audio = manager.add(DownloadRequest(url=f"{media_server}/clip.mp4", output_dir=str(tmp_path), mode="audio",
                                        audio_format="mp3", filename_template="%(title)s-audio.%(ext)s"))
    wait_for(manager, [video, audio])
    assert video.status == E.COMPLETED, video.error_detail
    assert audio.status == E.COMPLETED, audio.error_detail
    assert video.filepath.endswith(".mp4") and os.path.getsize(video.filepath) > 0
    assert audio.filepath.endswith(".mp3") and os.path.getsize(audio.filepath) > 0
    assert video.progress == 1.0
    dirty, finished, structure = manager.drain()
    assert structure is False  # already drained while waiting


def test_failed_download_reports_friendly_error(media_server, tmp_path):
    manager = E.DownloadManager(lambda: None)
    task = manager.add(DownloadRequest(url=f"{media_server}/missing.mp4", output_dir=str(tmp_path), retries=0))
    wait_for(manager, [task])
    assert task.status == E.FAILED
    assert task.error_key == "err_unavailable"
    manager.retry(task.id)
    assert task.status in (E.QUEUED, E.STARTING, E.DOWNLOADING, E.FAILED)


def test_pause_resume_and_cancel(media_server, tmp_path):
    manager = E.DownloadManager(lambda: None)
    task = manager.add(DownloadRequest(url=f"{media_server}/clip.mp4", output_dir=str(tmp_path), rate_limit="60K"))
    deadline = time.time() + 30
    while task.progress < 0.1 and time.time() < deadline:
        time.sleep(0.1)
    manager.pause(task.id)
    wait_for(manager, [task])
    assert task.status == E.PAUSED
    assert any(name.endswith(".part") for name in os.listdir(tmp_path))
    paused_at = task.progress

    manager.resume(task.id)
    deadline = time.time() + 30
    while task.status != E.DOWNLOADING and time.time() < deadline:
        time.sleep(0.05)
    assert task.progress >= paused_at * 0.9  # resumed, not restarted
    manager.cancel(task.id)
    wait_for(manager, [task])
    assert task.status == E.CANCELLED
    assert not os.listdir(tmp_path)  # partial files cleaned up


def test_queue_respects_concurrency():
    started = []
    manager = E.DownloadManager(lambda: None, max_concurrent=1)
    manager._run = lambda task: started.append(task.id)  # don't actually download
    a = manager.add(DownloadRequest(url="a"))
    b = manager.add(DownloadRequest(url="b"))
    assert started == [a.id]
    assert b.status == E.QUEUED
    manager.pause(b.id)
    assert b.status == E.PAUSED
    manager.cancel(b.id)
    assert b.status == E.CANCELLED
    manager.remove(b.id)
    assert manager.get(b.id) is None
    assert manager.counts()["total"] == 1
