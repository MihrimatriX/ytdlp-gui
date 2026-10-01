"""History page: everything downloaded so far, searchable."""

import os

import flet as ft

from ..formatting import format_bytes, format_timestamp
from ..history import HistoryItem
from ..i18n import t
from .common import empty_state, open_path, reveal_path, thumbnail
from .theme import DANGER, pill, subtle_button_style

PAGE_SIZE = 200


class HistoryView:
    def __init__(self, app):
        self.app = app
        self._stale = True
        self._query = ""
        self.count_text = ft.Text("", size=13, color=ft.Colors.ON_SURFACE_VARIANT)
        self.search = ft.TextField(
            hint_text=t("search_history"), prefix_icon=ft.Icons.SEARCH_ROUNDED, dense=True, width=300,
            border_radius=12, on_change=self._on_search, text_size=13,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        )
        self.clear_btn = ft.TextButton(t("clear_history"), icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                                       on_click=self._on_clear, style=subtle_button_style())
        self.list_view = ft.ListView(spacing=8, expand=True, padding=ft.Padding.only(right=12, bottom=12))
        self.body = ft.Container(expand=True)
        self.control = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Column([ft.Text(t("nav_history"), size=26, weight=ft.FontWeight.W_800), self.count_text],
                              spacing=2, expand=True),
                    self.search,
                    self.clear_btn,
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.body,
            ], spacing=16, expand=True),
            padding=ft.Padding.only(left=32, right=20, top=28, bottom=12),
            expand=True,
        )
        self.refresh()

    def mark_stale(self) -> None:
        self._stale = True
        if self.app.current == "history":
            self.refresh()

    def on_show(self) -> None:
        self.refresh()

    def _on_search(self, e) -> None:
        self._query = e.control.value or ""
        self.refresh()
        self.control.update()

    def _on_clear(self, e) -> None:
        def do_clear():
            self.app.history.clear()
            self.refresh()
            self.control.update()

        self.app.confirm(t("clear_history_title"), t("clear_history_body"), t("clear_history"), do_clear)

    def refresh(self) -> None:
        self._stale = False
        items = self.app.history.search(self._query)
        total = len(self.app.history.items)
        self.count_text.value = t("history_count", n=total)
        self.clear_btn.visible = total > 0
        self.search.visible = total > 0
        if not items:
            self.body.content = empty_state(
                ft.Icons.HISTORY_ROUNDED,
                t("history_empty_title") if not self._query else t("no_matches"),
                t("history_empty_body") if not self._query else "",
            )
            return
        self.list_view.controls = [self._row(item) for item in items[:PAGE_SIZE]]
        self.body.content = self.list_view

    def _row(self, item: HistoryItem) -> ft.Container:
        exists = bool(item.filepath) and os.path.exists(item.filepath)
        meta = [x for x in [item.format_label, format_bytes(item.size) if item.size else "",
                            format_timestamp(item.finished_at)] if x]
        title_row = [ft.Text(item.title, size=14, weight=ft.FontWeight.W_700, max_lines=1,
                             overflow=ft.TextOverflow.ELLIPSIS, expand=True)]
        if not exists:
            title_row.append(pill(t("file_missing"), DANGER))

        async def copy_link(e):
            await self.app.clipboard.set(item.url)
            self.app.toast(t("link_copied"))

        async def redownload(e):
            self.app.navigate("download")
            await self.app.views["download"].fetch(item.url)

        def remove(e):
            self.app.history.remove(item.id)
            self.refresh()
            self.control.update()

        actions = []
        if exists:
            actions += [
                ft.IconButton(ft.Icons.PLAY_CIRCLE_OUTLINE_ROUNDED, tooltip=t("open_file"),
                              on_click=lambda e: open_path(item.filepath), icon_color=ft.Colors.PRIMARY),
                ft.IconButton(ft.Icons.FOLDER_OPEN_ROUNDED, tooltip=t("show_in_folder"),
                              on_click=lambda e: reveal_path(item.filepath), icon_color=ft.Colors.ON_SURFACE_VARIANT),
            ]
        actions.append(ft.PopupMenuButton(
            icon=ft.Icons.MORE_VERT_ROUNDED, icon_color=ft.Colors.ON_SURFACE_VARIANT, tooltip=t("more"),
            items=[
                ft.PopupMenuItem(content=t("download_again"), icon=ft.Icons.DOWNLOAD_ROUNDED, on_click=redownload),
                ft.PopupMenuItem(content=t("copy_link"), icon=ft.Icons.LINK_ROUNDED, on_click=copy_link),
                ft.PopupMenuItem(content=t("remove_from_history"), icon=ft.Icons.DELETE_OUTLINE_ROUNDED, on_click=remove),
            ],
        ))
        return ft.Container(
            content=ft.Row([
                thumbnail(item.thumbnail, 112, 63, item.duration,
                          icon=ft.Icons.MUSIC_NOTE_ROUNDED if item.mode == "audio" else ft.Icons.SMART_DISPLAY_ROUNDED),
                ft.Column([
                    ft.Row(title_row, spacing=8),
                    ft.Text("  ·  ".join(meta), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text(item.uploader, size=12, color=ft.Colors.ON_SURFACE_VARIANT, visible=bool(item.uploader)),
                ], spacing=3, expand=True),
                ft.Row(actions, spacing=0),
            ], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=10,
            border_radius=14,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            opacity=1.0 if exists else 0.75,
        )
