"""Download queue built on the yt-dlp Python API.

Each task runs in its own worker thread with its own ``YoutubeDL`` instance.
Workers never touch the UI: they update plain task fields and mark the task
dirty; the UI drains dirty ids on its own event loop at a steady frame rate.
"""

import glob
import os
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

from yt_dlp.utils import DownloadCancelled, DownloadError

from .errors import friendly_error
from .logs import get_logger
from .options import DownloadRequest, build_args, to_ydl_opts

log = get_logger(__name__)

QUEUED = "queued"
STARTING = "starting"
DOWNLOADING = "downloading"
PROCESSING = "processing"
PAUSED = "paused"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"
SKIPPED = "skipped"

ACTIVE_STATES = {STARTING, DOWNLOADING, PROCESSING}
FINISHED_STATES = {COMPLETED, FAILED, CANCELLED, SKIPPED}

# yt-dlp post-processor name -> i18n key shown while it runs
STAGE_KEYS = {
    "Merger": "stage_merging",
    "FFmpegMerger": "stage_merging",
    "ExtractAudio": "stage_extract_audio",
    "FFmpegExtractAudio": "stage_extract_audio",
    "EmbedThumbnail": "stage_thumbnail",
    "FFmpegThumbnailsConvertor": "stage_thumbnail",
    "FFmpegEmbedSubtitle": "stage_subtitles",
    "EmbedSubtitle": "stage_subtitles",
    "FFmpegSubtitlesConvertor": "stage_subtitles",
    "FFmpegMetadata": "stage_metadata",
    "Metadata": "stage_metadata",
    "SponsorBlock": "stage_sponsorblock",
    "ModifyChapters": "stage_sponsorblock",
    "FFmpegFixupM4a": "stage_fixup",
    "FFmpegFixupM3u8": "stage_fixup",
    "FFmpegFixupDuplicateMoov": "stage_fixup",
    "FFmpegFixupTimestamp": "stage_fixup",
    "FFmpegFixupDuration": "stage_fixup",
    "FFmpegVideoRemuxer": "stage_merging",
    "VideoRemuxer": "stage_merging",
    "FFmpegVideoConvertor": "stage_merging",
    "MoveFiles": "stage_finishing",
    "MoveFilesAfterDownload": "stage_finishing",
}


class _Stop(DownloadCancelled):
    """Raised from the progress hook to pause or cancel a running download."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class DownloadTask:
    request: DownloadRequest
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = QUEUED
    progress: float = 0.0
    downloaded: int = 0
    total: Optional[int] = None
    speed: Optional[float] = None
    eta: Optional[float] = None
    stage: str = ""  # i18n key of the current post-processing step
    error_key: str = ""
    error_detail: str = ""
    filepath: str = ""
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None

    # internal
    _stop: Optional[str] = field(default=None, repr=False)  # "pause" | "cancel"
    _temp_files: Set[str] = field(default_factory=set, repr=False)
    _part_index: int = field(default=0, repr=False)

    @property
    def title(self) -> str:
        return self.request.title or self.request.url

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATES

    @property
    def is_finished(self) -> bool:
        return self.status in FINISHED_STATES


class _TaskLogger:
    def __init__(self, task: DownloadTask):
        self.task = task
        self.errors: List[str] = []
        self.archived = False

    def debug(self, msg: str) -> None:
        if "has already been recorded in the archive" in msg:
            self.archived = True

    def info(self, msg: str) -> None:
        self.debug(msg)

    def warning(self, msg: str) -> None:
        log.info("[%s] %s", self.task.id, msg)

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        log.warning("[%s] %s", self.task.id, msg)


class DownloadManager:
    def __init__(
        self,
        ffmpeg_location: Callable[[], Optional[str]],
        max_concurrent: int = 3,
    ):
        self._ffmpeg_location = ffmpeg_location
        self._max_concurrent = max(1, max_concurrent)
        self._tasks: "OrderedDict[str, DownloadTask]" = OrderedDict()
        self._lock = threading.RLock()
        self._dirty: Set[str] = set()
        self._finished_events: List[DownloadTask] = []
        self._structure_changed = False

    # ------------------------------------------------------------------ queries
    @property
    def tasks(self) -> List[DownloadTask]:
        with self._lock:
            return list(self._tasks.values())

    def get(self, task_id: str) -> Optional[DownloadTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def counts(self) -> Dict[str, int]:
        with self._lock:
            tasks = list(self._tasks.values())
        return {
            "active": sum(t.is_active for t in tasks),
            "queued": sum(t.status == QUEUED for t in tasks),
            "paused": sum(t.status == PAUSED for t in tasks),
            "completed": sum(t.status in (COMPLETED, SKIPPED) for t in tasks),
            "failed": sum(t.status == FAILED for t in tasks),
            "total": len(tasks),
        }

    def overall_progress(self) -> Optional[float]:
        """Progress across unfinished work, for the taskbar / header bar."""
        with self._lock:
            pending = [t for t in self._tasks.values() if t.is_active or t.status == QUEUED]
        if not pending:
            return None
        return sum(t.progress for t in pending) / len(pending)

    def total_speed(self) -> float:
        with self._lock:
            return sum(t.speed or 0 for t in self._tasks.values() if t.status == DOWNLOADING)

    def drain(self):
        """Return (dirty_ids, finished_tasks, structure_changed) and reset them."""
        with self._lock:
            dirty, self._dirty = self._dirty, set()
            finished, self._finished_events = self._finished_events, []
            structure, self._structure_changed = self._structure_changed, False
        return dirty, finished, structure

    # ------------------------------------------------------------------ commands
    def add(self, request: DownloadRequest) -> DownloadTask:
        task = DownloadTask(request=request)
        with self._lock:
            self._tasks[task.id] = task
            self._structure_changed = True
        self._schedule()
        return task

    def add_many(self, requests: List[DownloadRequest]) -> List[DownloadTask]:
        tasks = [DownloadTask(request=r) for r in requests]
        with self._lock:
            for task in tasks:
                self._tasks[task.id] = task
            self._structure_changed = True
        self._schedule()
        return tasks

    def set_max_concurrent(self, value: int) -> None:
        self._max_concurrent = max(1, int(value))
        self._schedule()

    def pause(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            if task.status == QUEUED:
                task.status = PAUSED
                task.speed = task.eta = None
                self._dirty.add(task_id)
            elif task.is_active:
                task._stop = "pause"

    def resume(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status == PAUSED:
                task.status = QUEUED
                self._dirty.add(task_id)
        self._schedule()

    def cancel(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            if task.is_active:
                task._stop = "cancel"
            elif task.status in (QUEUED, PAUSED):
                self._finish(task, CANCELLED)
                self._cleanup_temp(task)

    def retry(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or not (task.is_finished or task.status == PAUSED):
                return
            self._reset(task)
            # move to the end so it does not jump ahead of waiting items
            self._tasks.move_to_end(task_id)
            self._structure_changed = True
        self._schedule()

    def remove(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            if task.is_active:
                task._stop = "cancel"
            elif task.status in (QUEUED, PAUSED):
                self._cleanup_temp(task)
            self._tasks.pop(task_id, None)
            self._structure_changed = True

    def pause_all(self) -> None:
        for task in self.tasks:
            if task.status == QUEUED or task.is_active:
                self.pause(task.id)

    def resume_all(self) -> None:
        with self._lock:
            for task in self._tasks.values():
                if task.status == PAUSED:
                    task.status = QUEUED
                    self._dirty.add(task.id)
        self._schedule()

    def retry_failed(self) -> None:
        for task in self.tasks:
            if task.status == FAILED:
                self.retry(task.id)

    def clear_finished(self) -> None:
        with self._lock:
            for task_id in [t.id for t in self._tasks.values() if t.is_finished]:
                self._tasks.pop(task_id, None)
            self._structure_changed = True

    def shutdown(self) -> None:
        with self._lock:
            for task in self._tasks.values():
                if task.is_active:
                    task._stop = "pause"

    # ------------------------------------------------------------------ internals
    def _reset(self, task: DownloadTask) -> None:
        task.status = QUEUED
        task.progress = 0.0
        task.downloaded = 0
        task.total = task.speed = task.eta = None
        task.stage = task.error_key = task.error_detail = ""
        task.finished_at = None
        task._stop = None
        task._part_index = 0
        self._dirty.add(task.id)

    def _finish(self, task: DownloadTask, status: str) -> None:
        task.status = status
        task.speed = task.eta = None
        task.stage = ""
        task.finished_at = time.time()
        if status == COMPLETED:
            task.progress = 1.0
        self._dirty.add(task.id)
        self._finished_events.append(task)

    def _schedule(self) -> None:
        with self._lock:
            running = sum(1 for t in self._tasks.values() if t.is_active)
            for task in self._tasks.values():
                if running >= self._max_concurrent:
                    break
                if task.status == QUEUED:
                    task.status = STARTING
                    task._stop = None
                    self._dirty.add(task.id)
                    running += 1
                    threading.Thread(target=self._run, args=(task,), daemon=True, name=f"dl-{task.id}").start()

    def _mark(self, task: DownloadTask) -> None:
        with self._lock:
            self._dirty.add(task.id)

    def _progress_hook(self, task: DownloadTask, d: dict) -> None:
        if task._stop:
            raise _Stop(task._stop)
        status = d.get("status")
        for key in ("tmpfilename", "filename"):
            if d.get(key):
                task._temp_files.add(d[key])
        info = d.get("info_dict") or {}
        parts = info.get("requested_formats") or []
        format_id = info.get("format_id")

        downloaded = d.get("downloaded_bytes") or 0
        part_total = d.get("total_bytes") or d.get("total_bytes_estimate")

        if len(parts) > 1:
            ids = [p.get("format_id") for p in parts]
            index = ids.index(format_id) if format_id in ids else task._part_index
            task._part_index = index
            sizes = [p.get("filesize") or p.get("filesize_approx") or 0 for p in parts]
            if part_total:
                sizes[index] = part_total
            if all(sizes):
                total = sum(sizes)
                done = sum(sizes[:index]) + downloaded
                task.total, task.downloaded = total, done
                fraction = done / total
            else:
                part_fraction = downloaded / part_total if part_total else 0
                fraction = (index + part_fraction) / len(parts)
                task.total, task.downloaded = None, downloaded
        else:
            task.total, task.downloaded = part_total, downloaded
            if part_total:
                fraction = downloaded / part_total
            elif d.get("fragment_count"):
                fraction = (d.get("fragment_index") or 0) / d["fragment_count"]
            else:
                fraction = task.progress

        if status == "finished" and len(parts) <= 1:
            fraction = 1.0
        task.progress = max(0.0, min(fraction, 1.0))
        task.speed = d.get("speed")
        task.eta = d.get("eta")
        if task.status != DOWNLOADING and status == "downloading":
            task.status = DOWNLOADING
        self._mark(task)

    def _postprocessor_hook(self, task: DownloadTask, d: dict) -> None:
        if d.get("status") == "started":
            name = d.get("postprocessor") or ""
            task.status = PROCESSING
            task.stage = STAGE_KEYS.get(name, "stage_processing")
            task.progress = 1.0
            task.speed = task.eta = None
            self._mark(task)
        elif d.get("status") == "finished":
            path = (d.get("info_dict") or {}).get("filepath")
            if path:
                task.filepath = path

    def _run(self, task: DownloadTask) -> None:
        import yt_dlp

        logger = _TaskLogger(task)
        try:
            args = build_args(task.request, self._ffmpeg_location())
            opts = to_ydl_opts(args)
        except Exception as exc:  # bad extra args, etc.
            with self._lock:
                task.error_key, task.error_detail = "err_options", str(exc)
                self._finish(task, FAILED)
            self._schedule()
            return

        opts["logger"] = logger
        opts["progress_hooks"] = [lambda d: self._progress_hook(task, d)]
        opts["postprocessor_hooks"] = [lambda d: self._postprocessor_hook(task, d)]
        if task.request.output_dir:
            os.makedirs(task.request.output_dir, exist_ok=True)

        log.info("Starting %s: %s", task.id, task.request.url)
        final_status = COMPLETED
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(task.request.url, download=True)
            if info:
                downloads = info.get("requested_downloads") or []
                path = (downloads[-1].get("filepath") if downloads else None) or info.get("filepath")
                if path:
                    task.filepath = path
                if not task.request.title:
                    task.request.title = info.get("title") or ""
                if not task.request.thumbnail:
                    task.request.thumbnail = info.get("thumbnail")
            if logger.archived and not task.filepath:
                final_status = SKIPPED
        except DownloadCancelled:
            final_status = PAUSED if task._stop == "pause" else CANCELLED
        except DownloadError as exc:
            if task._stop:
                final_status = PAUSED if task._stop == "pause" else CANCELLED
            else:
                final_status = FAILED
                task.error_key, task.error_detail = friendly_error("\n".join(logger.errors) or str(exc))
        except Exception as exc:
            log.exception("Task %s crashed", task.id)
            final_status = FAILED
            task.error_key, task.error_detail = friendly_error(str(exc))

        with self._lock:
            if final_status == PAUSED:
                task.status = PAUSED
                task.speed = task.eta = None
                task.stage = ""
                self._dirty.add(task.id)
            else:
                if final_status == CANCELLED:
                    self._cleanup_temp(task)
                    task.progress = 0.0
                self._finish(task, final_status)
            task._stop = None
        log.info("Task %s finished: %s %s", task.id, final_status, task.error_detail)
        self._schedule()

    @staticmethod
    def _cleanup_temp(task: DownloadTask) -> None:
        for path in list(task._temp_files):
            if task.filepath and os.path.abspath(path) == os.path.abspath(task.filepath):
                continue
            for candidate in [path] + glob.glob(glob.escape(path) + ".part*") + glob.glob(glob.escape(path) + ".ytdl"):
                try:
                    if os.path.isfile(candidate):
                        os.remove(candidate)
                except OSError:
                    pass
        task._temp_files.clear()
