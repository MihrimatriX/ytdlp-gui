"""Application shell: sidebar navigation, view switching and the UI update pump."""

import asyncio
import os
import threading
from typing import Dict, Optional

import flet as ft

from .. import APP_NAME, APP_VERSION
from ..engine import COMPLETED, DownloadManager
from ..ffmpeg import can_auto_install, download_windows_build, find_ffmpeg
from ..formatting import format_speed
from ..history import HistoryItem, HistoryStore
from ..i18n import resolve_language, set_language, t
from ..logs import get_logger
from ..paths import archive_file, resource_dir
from ..settings import SettingsStore
from ..urls import extract_url, is_youtube_url
from .common import format_label, open_path
from .download_view import DownloadView
from .history_view import HistoryView
from .queue_view import QueueView
from .settings_view import SettingsView
from .system_view import SystemView
from .theme import DANGER, SUCCESS, build_theme

log = get_logger(__name__)

NAV = [
    ("download", ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED, ft.Icons.ADD_CIRCLE_ROUNDED, "nav_download"),
    ("queue", ft.Icons.DOWNLOAD_OUTLINED, ft.Icons.DOWNLOAD_ROUNDED, "nav_queue"),
    ("history", ft.Icons.HISTORY_ROUNDED, ft.Icons.HISTORY_ROUNDED, "nav_history"),
    ("settings", ft.Icons.TUNE_ROUNDED, ft.Icons.TUNE_ROUNDED, "nav_settings"),
    ("system", ft.Icons.MONITOR_HEART_OUTLINED, ft.Icons.MONITOR_HEART_ROUNDED, "nav_system"),
]
COMPACT_BREAKPOINT = 1080


class App:
    def __init__(self, page: ft.Page):
        self.page = page
        self.store = SettingsStore()
        self.settings = self.store.settings
        self.history = HistoryStore()
        self.ffmpeg_location: Optional[str] = find_ffmpeg()
        self.ffmpeg_progress: Optional[float] = None  # set while auto-installing
        self.manager = DownloadManager(lambda: self.ffmpeg_location, self.settings.max_concurrent)
        self.archive_path = str(archive_file())
        self.current = "download"
        self.views: Dict[str, object] = {}
        self._last_clipboard = ""
        self._compact = False
        set_language(resolve_language(self.settings.language))

        # Services register themselves with the page on construction.
        self.file_picker = ft.FilePicker()
        self.clipboard = ft.Clipboard()

        self.store.subscribe(self._on_setting_changed)

    # ------------------------------------------------------------------ setup
    def start(self) -> None:
        page = self.page
        page.title = APP_NAME
        page.padding = 0
        page.spacing = 0
        page.window.width = 1280
        page.window.height = 840
        page.window.min_width = 900
        page.window.min_height = 620
        icon = resource_dir() / "assets" / "icon.ico"
        if icon.is_file():
            page.window.icon = str(icon)
        page.window.on_event = self._on_window_event
        page.on_keyboard_event = self._on_key
        page.on_resize = self._on_resize
        page.on_close = lambda e: self.manager.shutdown()
        self._apply_theme()
        self._build()
        page.run_task(self._pump)
        page.run_task(self._check_clipboard)
        if not self.ffmpeg_location and can_auto_install():
            threading.Thread(target=self._install_ffmpeg, daemon=True).start()

    def _apply_theme(self) -> None:
        accent = self.settings.accent
        self.page.theme = build_theme(accent, dark=False)
        self.page.dark_theme = build_theme(accent, dark=True)
        self.page.theme_mode = {
            "system": ft.ThemeMode.SYSTEM,
            "dark": ft.ThemeMode.DARK,
            "light": ft.ThemeMode.LIGHT,
        }[self.settings.theme_mode]

    def _build(self) -> None:
        width = self.page.width or self.page.window.width or 1280
        self._compact = width < COMPACT_BREAKPOINT
        self.views = {
            "download": DownloadView(self),
            "queue": QueueView(self),
            "history": HistoryView(self),
            "settings": SettingsView(self),
            "system": SystemView(self),
        }
        self.content_host = ft.AnimatedSwitcher(
            content=self.views[self.current].control,
            duration=180,
            reverse_duration=120,
            switch_in_curve=ft.AnimationCurve.EASE_OUT,
            transition=ft.AnimatedSwitcherTransition.FADE,
            expand=True,
        )
        self.sidebar = self._build_sidebar()
        self.page.controls.clear()
        self.page.add(
            ft.Row(
                [self.sidebar, ft.Container(content=self.content_host, expand=True)],
                spacing=0,
                expand=True,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            )
        )
        self.page.update()

    def rebuild(self) -> None:
        set_language(resolve_language(self.settings.language))
        self._build()

    # ------------------------------------------------------------------ sidebar
    def _build_sidebar(self) -> ft.Container:
        compact = self._compact
        logo = ft.Container(
            content=ft.Icon(ft.Icons.DOWNLOAD_ROUNDED, color="#FFFFFF", size=22),
            width=40,
            height=40,
            border_radius=12,
            alignment=ft.Alignment.CENTER,
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
                colors=[self.settings.accent, ft.Colors.with_opacity(0.75, self.settings.accent)],
            ),
            shadow=ft.BoxShadow(blur_radius=18, spread_radius=-4, color=ft.Colors.with_opacity(0.5, self.settings.accent),
                                offset=ft.Offset(0, 6)),
        )
        brand = ft.Row(
            [logo] + ([] if compact else [ft.Column([
                ft.Text(APP_NAME, size=14, weight=ft.FontWeight.W_800, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(t("tagline"), size=11, color=ft.Colors.ON_SURFACE_VARIANT, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
            ], spacing=0, expand=True)]),
            spacing=12,
            alignment=ft.MainAxisAlignment.CENTER if compact else ft.MainAxisAlignment.START,
        )

        self.nav_items: Dict[str, ft.Container] = {}
        self.queue_badge = ft.Container(
            content=ft.Text("0", size=11, weight=ft.FontWeight.W_700, color=ft.Colors.ON_PRIMARY),
            bgcolor=ft.Colors.PRIMARY,
            border_radius=999,
            padding=ft.Padding.symmetric(horizontal=7, vertical=1),
            visible=False,
        )
        nav_controls = []
        for key, icon, selected_icon, label in NAV:
            item = self._nav_item(key, icon, selected_icon, t(label), compact)
            self.nav_items[key] = item
            nav_controls.append(item)

        self.mini_progress_text = ft.Text("", size=12, weight=ft.FontWeight.W_600, max_lines=1,
                                          overflow=ft.TextOverflow.ELLIPSIS)
        self.mini_speed_text = ft.Text("", size=11, color=ft.Colors.ON_SURFACE_VARIANT)
        self.mini_progress_bar = ft.ProgressBar(value=0, bar_height=5, border_radius=4)
        self.mini_progress = ft.Container(
            content=ft.Column([self.mini_progress_text, self.mini_progress_bar, self.mini_speed_text], spacing=6),
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            visible=False,
            on_click=lambda e: self.navigate("queue"),
        )
        self.ffmpeg_banner_text = ft.Text("", size=11, color=ft.Colors.ON_SURFACE_VARIANT)
        self.ffmpeg_banner_bar = ft.ProgressBar(value=None, bar_height=4, border_radius=4)
        self.ffmpeg_banner = ft.Container(
            content=ft.Column([self.ffmpeg_banner_text, self.ffmpeg_banner_bar], spacing=6),
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            visible=self.ffmpeg_progress is not None and not compact,
        )

        dark = self.page.theme_mode == ft.ThemeMode.DARK or (
            self.page.theme_mode == ft.ThemeMode.SYSTEM and self.page.platform_brightness == ft.Brightness.DARK)
        theme_btn = ft.IconButton(
            icon=ft.Icons.LIGHT_MODE_ROUNDED if dark else ft.Icons.DARK_MODE_ROUNDED,
            tooltip=t("toggle_theme"),
            on_click=self._toggle_theme,
            icon_color=ft.Colors.ON_SURFACE_VARIANT,
        )
        footer = ft.Row(
            [theme_btn] + ([] if compact else [
                ft.Container(expand=True),
                ft.Text(f"v{APP_VERSION}", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
            ]),
            alignment=ft.MainAxisAlignment.CENTER if compact else ft.MainAxisAlignment.START,
        )

        return ft.Container(
            width=76 if compact else 248,
            padding=ft.Padding.only(left=12, right=12, top=20, bottom=14),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border=ft.Border.only(right=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
            content=ft.Column(
                [
                    ft.Container(content=brand, padding=ft.Padding.only(left=0 if compact else 4, bottom=18)),
                    *nav_controls,
                    ft.Container(expand=True),
                    self.ffmpeg_banner,
                    self.mini_progress,
                    footer,
                ],
                spacing=4,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        )

    def _nav_item(self, key: str, icon, selected_icon, label: str, compact: bool) -> ft.Container:
        selected = key == self.current
        color = ft.Colors.PRIMARY if selected else ft.Colors.ON_SURFACE_VARIANT
        icon_ctrl = ft.Icon(selected_icon if selected else icon, size=22, color=color)
        row_controls = [icon_ctrl]
        if not compact:
            row_controls.append(ft.Text(label, size=14, weight=ft.FontWeight.W_700 if selected else ft.FontWeight.W_500,
                                        color=ft.Colors.ON_SURFACE if selected else ft.Colors.ON_SURFACE_VARIANT,
                                        expand=True))
            if key == "queue":
                row_controls.append(self.queue_badge)
        content = ft.Row(row_controls, spacing=14,
                         alignment=ft.MainAxisAlignment.CENTER if compact else ft.MainAxisAlignment.START)
        if compact and key == "queue":
            content = ft.Stack([content, ft.Container(content=self.queue_badge, right=0, top=0)])
        return ft.Container(
            content=content,
            height=46,
            padding=ft.Padding.symmetric(horizontal=0 if compact else 14),
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY) if selected else None,
            on_click=lambda e, k=key: self.navigate(k),
            tooltip=label if compact else None,
            alignment=ft.Alignment.CENTER if compact else ft.Alignment.CENTER_LEFT,
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
        )

    def _refresh_nav(self) -> None:
        for key, icon, selected_icon, label in NAV:
            new_item = self._nav_item(key, icon, selected_icon, t(label), self._compact)
            old = self.nav_items[key]
            old.content = new_item.content
            old.bgcolor = new_item.bgcolor

    # ------------------------------------------------------------------ navigation
    def navigate(self, key: str) -> None:
        if key not in self.views:
            return
        self.current = key
        view = self.views[key]
        if hasattr(view, "on_show"):
            view.on_show()
        self.content_host.content = view.control
        self._refresh_nav()
        self.page.update()

    # ------------------------------------------------------------------ feedback
    def toast(self, message: str, kind: str = "info", action: Optional[str] = None, on_action=None) -> None:
        icon, color = {
            "success": (ft.Icons.CHECK_CIRCLE_ROUNDED, SUCCESS),
            "error": (ft.Icons.ERROR_ROUNDED, DANGER),
        }.get(kind, (ft.Icons.INFO_ROUNDED, ft.Colors.PRIMARY))
        bar = ft.SnackBar(
            content=ft.Row([ft.Icon(icon, color=color, size=20),
                            ft.Text(message, color=ft.Colors.ON_SURFACE, expand=True)], spacing=12),
            behavior=ft.SnackBarBehavior.FLOATING,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            shape=ft.RoundedRectangleBorder(radius=12),
            width=460,
            duration=4500,
            persist=False,
            action=ft.SnackBarAction(label=action, text_color=ft.Colors.PRIMARY, on_click=on_action) if action else None,
        )
        self.page.show_dialog(bar)

    def confirm(self, title: str, message: str, confirm_label: str, on_confirm, danger: bool = True) -> None:
        def close(e):
            self.page.pop_dialog()

        def ok(e):
            self.page.pop_dialog()
            on_confirm()

        dialog = ft.AlertDialog(
            title=ft.Text(title, weight=ft.FontWeight.W_700),
            content=ft.Text(message, color=ft.Colors.ON_SURFACE_VARIANT),
            actions=[
                ft.TextButton(t("cancel"), on_click=close),
                ft.FilledButton(confirm_label, on_click=ok, bgcolor=DANGER if danger else None),
            ],
            shape=ft.RoundedRectangleBorder(radius=18),
        )
        self.page.show_dialog(dialog)

    # ------------------------------------------------------------------ settings
    def _on_setting_changed(self, key: str, value) -> None:
        if key == "max_concurrent":
            self.manager.set_max_concurrent(value)
        elif key in ("theme_mode", "accent", "*"):
            self._apply_theme()
            if key in ("accent", "*"):
                self.rebuild()
            else:
                self.sidebar_refresh()
        if key in ("language", "*"):
            self.rebuild()

    def sidebar_refresh(self) -> None:
        index = self.page.controls[0].controls.index(self.sidebar)
        self.sidebar = self._build_sidebar()
        self.page.controls[0].controls[index] = self.sidebar
        self._sync_sidebar()
        self.page.update()

    def _toggle_theme(self, e) -> None:
        dark = self.page.theme_mode == ft.ThemeMode.DARK or (
            self.page.theme_mode == ft.ThemeMode.SYSTEM and self.page.platform_brightness == ft.Brightness.DARK)
        self.store.set("theme_mode", "light" if dark else "dark")

    # ------------------------------------------------------------------ events
    def _on_resize(self, e) -> None:
        width = self.page.width or 1280
        compact = width < COMPACT_BREAKPOINT
        if compact != self._compact:
            self._compact = compact
            self.sidebar_refresh()

    async def _on_key(self, e: ft.KeyboardEvent) -> None:
        if not (e.ctrl or e.meta):
            return
        shortcuts = {"1": "download", "2": "queue", "3": "history", "4": "settings", "5": "system"}
        if e.key in shortcuts:
            self.navigate(shortcuts[e.key])
        elif e.key.upper() == "L":
            self.navigate("download")
            await self.views["download"].focus_input()

    async def _on_window_event(self, e) -> None:
        if e.type == ft.WindowEventType.FOCUS:
            await self._check_clipboard()

    async def _check_clipboard(self) -> None:
        if not self.settings.clipboard_watch:
            return
        try:
            text = await self.clipboard.get()
        except Exception:
            return
        url = extract_url(text or "")
        if not url or url == self._last_clipboard or not is_youtube_url(url):
            return
        self._last_clipboard = url
        self.views["download"].offer_clipboard(url)

    # ------------------------------------------------------------------ pump
    async def _pump(self) -> None:
        while True:
            await asyncio.sleep(0.25)
            try:
                self._tick()
            except Exception:
                log.exception("UI pump failed")

    def _tick(self) -> None:
        dirty, finished, structure = self.manager.drain()
        ffmpeg_changed = self._sync_ffmpeg_banner()
        if not (dirty or finished or structure or ffmpeg_changed):
            return
        self.views["queue"].sync(dirty, structure)
        for task in finished:
            self._on_task_finished(task)
        self._sync_sidebar()
        self.page.update()

    def _sync_sidebar(self) -> None:
        counts = self.manager.counts()
        pending = counts["active"] + counts["queued"]
        self.queue_badge.visible = pending > 0
        self.queue_badge.content.value = str(pending)
        overall = self.manager.overall_progress()
        active = overall is not None
        self.mini_progress.visible = active and not self._compact
        if active:
            self.mini_progress_bar.value = overall
            self.mini_progress_text.value = t("downloading_n", n=counts["active"]) if counts["active"] else t("waiting_n", n=counts["queued"])
            self.mini_speed_text.value = f"{overall * 100:.0f}% · {format_speed(self.manager.total_speed())}"
        self.page.window.progress_bar = overall if active else None

    def _on_task_finished(self, task) -> None:
        req = task.request
        if task.status == COMPLETED:
            size = None
            if task.filepath and os.path.isfile(task.filepath):
                size = os.path.getsize(task.filepath)
            self.history.add(HistoryItem(
                title=task.title,
                url=req.url,
                filepath=task.filepath,
                thumbnail=req.thumbnail,
                uploader=req.uploader,
                format_label=format_label(req),
                mode=req.mode,
                size=size,
                duration=req.duration,
            ))
            self.views["history"].mark_stale()
            if self.settings.notify_on_complete:
                self.toast(t("toast_done", title=task.title), "success", action=t("show_in_folder"),
                           on_action=lambda e, p=task.filepath: open_path(os.path.dirname(p)) if p else None)
            counts = self.manager.counts()
            if self.settings.open_folder_when_done and counts["active"] + counts["queued"] == 0 and task.filepath:
                open_path(os.path.dirname(task.filepath))
        elif task.status == "failed" and self.settings.notify_on_complete:
            self.toast(t("toast_failed", title=task.title), "error", action=t("nav_queue"),
                       on_action=lambda e: self.navigate("queue"))

    # ------------------------------------------------------------------ ffmpeg
    def _install_ffmpeg(self) -> None:
        self.ffmpeg_progress = 0.0
        try:
            download_windows_build(progress=lambda p: setattr(self, "ffmpeg_progress", p))
            self.ffmpeg_location = find_ffmpeg()
        except Exception as exc:
            log.error("FFmpeg auto-install failed: %s", exc)
        finally:
            self.ffmpeg_progress = None

    def install_ffmpeg_now(self) -> None:
        if self.ffmpeg_progress is None:
            threading.Thread(target=self._install_ffmpeg, daemon=True).start()

    def _sync_ffmpeg_banner(self) -> bool:
        installing = self.ffmpeg_progress is not None
        visible = installing and not self._compact
        changed = self.ffmpeg_banner.visible != visible
        self.ffmpeg_banner.visible = visible
        if installing:
            self.ffmpeg_banner_text.value = t("ffmpeg_installing", p=f"{self.ffmpeg_progress * 100:.0f}")
            self.ffmpeg_banner_bar.value = self.ffmpeg_progress or None
            changed = True
        if changed and not installing and self.current == "system":
            self.views["system"].refresh()
        return changed
