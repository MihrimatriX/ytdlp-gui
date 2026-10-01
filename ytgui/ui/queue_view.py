"""Downloads page: live progress of every task with per-item controls."""

import os
from typing import Dict

import flet as ft

from .. import engine as E
from ..formatting import format_bytes, format_eta, format_speed
from ..i18n import t
from ..options import command_line
from .common import format_label
from .common import empty_state, open_path, reveal_path, thumbnail
from .theme import DANGER, INFO, SUCCESS, WARNING, pill, subtle_button_style

STATUS_STYLE = {
    E.QUEUED: (ft.Icons.SCHEDULE_ROUNDED, ft.Colors.ON_SURFACE_VARIANT),
    E.STARTING: (ft.Icons.HOURGLASS_TOP_ROUNDED, ft.Colors.PRIMARY),
    E.DOWNLOADING: (ft.Icons.DOWNLOADING_ROUNDED, ft.Colors.PRIMARY),
    E.PROCESSING: (ft.Icons.AUTO_FIX_HIGH_ROUNDED, INFO),
    E.PAUSED: (ft.Icons.PAUSE_CIRCLE_ROUNDED, WARNING),
    E.COMPLETED: (ft.Icons.CHECK_CIRCLE_ROUNDED, SUCCESS),
    E.SKIPPED: (ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED, SUCCESS),
    E.FAILED: (ft.Icons.ERROR_ROUNDED, DANGER),
    E.CANCELLED: (ft.Icons.CANCEL_ROUNDED, ft.Colors.ON_SURFACE_VARIANT),
}


class TaskRow:
    """One card in the queue. Built once, then mutated in place on every tick."""

    def __init__(self, view: "QueueView", task: E.DownloadTask):
        self.view = view
        self.task_id = task.id
        req = task.request
        mode_icon = ft.Icons.MUSIC_NOTE_ROUNDED if req.mode == "audio" else ft.Icons.MOVIE_ROUNDED
        badge = ft.Container(ft.Icon(mode_icon, size=12, color="#FFFFFF"), bgcolor="#CC000000", border_radius=5,
                             padding=ft.Padding.symmetric(horizontal=5, vertical=2))
        self.thumb = thumbnail(req.thumbnail, 136, 77, req.duration, badge=badge,
                               icon=ft.Icons.MUSIC_NOTE_ROUNDED if req.mode == "audio" else ft.Icons.SMART_DISPLAY_ROUNDED)
        self.title = ft.Text(task.title, size=14, weight=ft.FontWeight.W_700, max_lines=1,
                             overflow=ft.TextOverflow.ELLIPSIS)
        self.meta = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT, max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS)
        self.bar = ft.ProgressBar(value=0, bar_height=6, border_radius=6, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST)
        self.status_icon = ft.Icon(ft.Icons.SCHEDULE_ROUNDED, size=15)
        self.status_text = ft.Text("", size=12, weight=ft.FontWeight.W_600, max_lines=2,
                                   overflow=ft.TextOverflow.ELLIPSIS, expand=True)
        self.size_text = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.actions = ft.Row(spacing=0)
        self.control = ft.Container(
            content=ft.Row([
                self.thumb,
                ft.Column([
                    self.title,
                    self.meta,
                    ft.Container(height=2),
                    self.bar,
                    ft.Row([self.status_icon, self.status_text, self.size_text], spacing=6,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ], spacing=4, expand=True),
                self.actions,
            ], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=12,
            border_radius=14,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        )
        self._last_status = None
        self.refresh(task)

    def _btn(self, icon, tooltip, handler, color=ft.Colors.ON_SURFACE_VARIANT) -> ft.IconButton:
        return ft.IconButton(icon, tooltip=tooltip, on_click=handler, icon_color=color, icon_size=20)

    def _build_actions(self, task: E.DownloadTask) -> None:
        m = self.view.app.manager
        tid = task.id
        buttons = []
        if task.status in (E.QUEUED, E.STARTING, E.DOWNLOADING):
            buttons.append(self._btn(ft.Icons.PAUSE_ROUNDED, t("pause"), lambda e: m.pause(tid)))
        if task.status == E.PAUSED:
            buttons.append(self._btn(ft.Icons.PLAY_ARROW_ROUNDED, t("resume"), lambda e: m.resume(tid), ft.Colors.PRIMARY))
        if task.status in (E.FAILED, E.CANCELLED):
            buttons.append(self._btn(ft.Icons.REFRESH_ROUNDED, t("retry"), lambda e: m.retry(tid), ft.Colors.PRIMARY))
        if task.status == E.COMPLETED and task.filepath:
            buttons.append(self._btn(ft.Icons.PLAY_CIRCLE_OUTLINE_ROUNDED, t("open_file"),
                                     lambda e: open_path(task.filepath), ft.Colors.PRIMARY))
            buttons.append(self._btn(ft.Icons.FOLDER_OPEN_ROUNDED, t("show_in_folder"), lambda e: reveal_path(task.filepath)))
        if not task.is_finished and task.status != E.PROCESSING:
            buttons.append(self._btn(ft.Icons.CLOSE_ROUNDED, t("cancel"), lambda e: m.cancel(tid)))

        menu_items = [
            ft.PopupMenuItem(content=t("copy_link"), icon=ft.Icons.LINK_ROUNDED, on_click=self._copy_link),
            ft.PopupMenuItem(content=t("copy_command"), icon=ft.Icons.TERMINAL_ROUNDED, on_click=self._copy_command),
        ]
        if task.error_detail:
            menu_items.append(ft.PopupMenuItem(content=t("copy_error"), icon=ft.Icons.BUG_REPORT_OUTLINED,
                                               on_click=self._copy_error))
        if task.is_finished or task.status == E.PAUSED or task.status == E.QUEUED:
            menu_items.append(ft.PopupMenuItem(content=t("remove_from_list"), icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                                               on_click=lambda e: self.view.remove(tid)))
        buttons.append(ft.PopupMenuButton(items=menu_items, icon=ft.Icons.MORE_VERT_ROUNDED,
                                          icon_color=ft.Colors.ON_SURFACE_VARIANT, tooltip=t("more")))
        self.actions.controls = buttons

    async def _copy_link(self, e) -> None:
        task = self.view.app.manager.get(self.task_id)
        if task:
            await self.view.app.clipboard.set(task.request.url)
            self.view.app.toast(t("link_copied"))

    async def _copy_command(self, e) -> None:
        task = self.view.app.manager.get(self.task_id)
        if task:
            await self.view.app.clipboard.set(command_line(task.request, self.view.app.ffmpeg_location))
            self.view.app.toast(t("command_copied"))

    async def _copy_error(self, e) -> None:
        task = self.view.app.manager.get(self.task_id)
        if task:
            await self.view.app.clipboard.set(task.error_detail)
            self.view.app.toast(t("error_copied"))

    def refresh(self, task: E.DownloadTask) -> None:
        req = task.request
        self.title.value = task.title
        meta = [format_label(req)]
        if req.uploader:
            meta.append(req.uploader)
        if req.subfolder:
            meta.append("📁 " + req.subfolder)
        self.meta.value = "  ·  ".join(meta)

        icon, color = STATUS_STYLE.get(task.status, STATUS_STYLE[E.QUEUED])
        self.status_icon.icon = icon
        self.status_icon.color = color
        self.status_text.color = color if task.status in (E.FAILED, E.COMPLETED, E.PAUSED) else ft.Colors.ON_SURFACE
        self.bar.color = color

        status = task.status
        if status == E.DOWNLOADING:
            self.bar.value = task.progress
            parts = [f"{task.progress * 100:.1f}%", format_speed(task.speed)]
            if task.eta is not None:
                parts.append(t("eta_left", eta=format_eta(task.eta)))
            self.status_text.value = "  ·  ".join(parts)
        elif status == E.STARTING:
            self.bar.value = None
            self.status_text.value = t("status_starting")
        elif status == E.PROCESSING:
            self.bar.value = None
            self.status_text.value = t(task.stage or "stage_processing")
        elif status == E.QUEUED:
            self.bar.value = task.progress or 0
            self.status_text.value = t("status_queued")
        elif status == E.PAUSED:
            self.bar.value = task.progress
            self.status_text.value = t("status_paused", p=f"{task.progress * 100:.0f}")
        elif status == E.COMPLETED:
            self.bar.value = 1
            self.status_text.value = t("status_completed")
        elif status == E.SKIPPED:
            self.bar.value = 1
            self.status_text.value = t("status_skipped")
        elif status == E.FAILED:
            self.bar.value = task.progress or 0
            detail = t(task.error_key or "err_generic")
            self.status_text.value = detail
            self.status_text.tooltip = task.error_detail or None
        elif status == E.CANCELLED:
            self.bar.value = 0
            self.status_text.value = t("status_cancelled")

        if status == E.COMPLETED and task.filepath and os.path.isfile(task.filepath):
            self.size_text.value = format_bytes(os.path.getsize(task.filepath))
        elif task.total and status == E.DOWNLOADING:
            self.size_text.value = f"{format_bytes(task.downloaded)} / {format_bytes(task.total)}"
        elif task.total:
            self.size_text.value = format_bytes(task.total)
        else:
            self.size_text.value = ""

        if status != self._last_status:
            self._last_status = status
            self._build_actions(task)
            self.control.border = ft.Border.all(
                1, ft.Colors.with_opacity(0.45, DANGER) if status == E.FAILED else ft.Colors.OUTLINE_VARIANT)


class QueueView:
    def __init__(self, app):
        self.app = app
        self.rows: Dict[str, TaskRow] = {}
        self.list_view = ft.ListView(spacing=10, expand=True, padding=ft.Padding.only(right=12, bottom=12))
        self.summary = ft.Row(spacing=8, wrap=True)
        self.speed_text = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)

        def action(icon, label, handler):
            return ft.TextButton(label, icon=icon, on_click=handler, style=subtle_button_style())

        m = app.manager
        self.toolbar = ft.Row([
            action(ft.Icons.PAUSE_ROUNDED, t("pause_all"), lambda e: m.pause_all()),
            action(ft.Icons.PLAY_ARROW_ROUNDED, t("resume_all"), lambda e: m.resume_all()),
            action(ft.Icons.REFRESH_ROUNDED, t("retry_failed"), lambda e: m.retry_failed()),
            action(ft.Icons.CLEANING_SERVICES_OUTLINED, t("clear_finished"), self._clear_finished),
            action(ft.Icons.FOLDER_OPEN_ROUNDED, t("open_folder"), lambda e: open_path(app.settings.download_dir)),
        ], spacing=2, wrap=True)

        self.empty = empty_state(
            ft.Icons.DOWNLOAD_ROUNDED, t("queue_empty_title"), t("queue_empty_body"),
            ft.FilledButton(t("start_downloading"), icon=ft.Icons.ADD_ROUNDED,
                            on_click=lambda e: app.navigate("download")),
        )
        self.body = ft.Container(expand=True)
        self.control = ft.Container(
            content=ft.Column([
                ft.Row([ft.Column([ft.Text(t("nav_queue"), size=26, weight=ft.FontWeight.W_800), self.speed_text],
                                  spacing=2, expand=True), self.summary],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.toolbar,
                self.body,
            ], spacing=14, expand=True),
            padding=ft.Padding.only(left=32, right=20, top=28, bottom=12),
            expand=True,
        )
        self.sync(set(), True)

    def remove(self, task_id: str) -> None:
        self.app.manager.remove(task_id)

    def _clear_finished(self, e) -> None:
        self.app.manager.clear_finished()

    def sync(self, dirty, structure_changed: bool) -> None:
        tasks = self.app.manager.tasks
        if structure_changed:
            known = {t_.id for t_ in tasks}
            for tid in list(self.rows):
                if tid not in known:
                    del self.rows[tid]
            controls = []
            for task in tasks:
                row = self.rows.get(task.id)
                if row is None:
                    row = self.rows[task.id] = TaskRow(self, task)
                controls.append(row.control)
            self.list_view.controls = controls
        for task in tasks:
            if task.id in dirty and task.id in self.rows:
                self.rows[task.id].refresh(task)
        self.body.content = self.list_view if tasks else self.empty
        self.toolbar.visible = bool(tasks)
        self._sync_summary()

    def _sync_summary(self) -> None:
        c = self.app.manager.counts()
        pills = []
        if c["active"]:
            pills.append(pill(t("count_active", n=c["active"]), ft.Colors.PRIMARY, icon=ft.Icons.DOWNLOADING_ROUNDED, size=12))
        if c["queued"]:
            pills.append(pill(t("count_queued", n=c["queued"]), ft.Colors.ON_SURFACE_VARIANT,
                              ft.Colors.SURFACE_CONTAINER_HIGHEST, icon=ft.Icons.SCHEDULE_ROUNDED, size=12))
        if c["paused"]:
            pills.append(pill(t("count_paused", n=c["paused"]), WARNING, icon=ft.Icons.PAUSE_ROUNDED, size=12))
        if c["completed"]:
            pills.append(pill(t("count_completed", n=c["completed"]), SUCCESS, icon=ft.Icons.CHECK_ROUNDED, size=12))
        if c["failed"]:
            pills.append(pill(t("count_failed", n=c["failed"]), DANGER, icon=ft.Icons.ERROR_OUTLINE_ROUNDED, size=12))
        self.summary.controls = pills
        speed = self.app.manager.total_speed()
        self.speed_text.value = t("total_speed", s=format_speed(speed)) if c["active"] else t("queue_subtitle")
