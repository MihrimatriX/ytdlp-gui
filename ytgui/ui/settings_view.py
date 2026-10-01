"""Settings page. Every change is saved immediately."""

import os
import shlex

import flet as ft

from ..i18n import t
from ..options import is_valid_rate
from ..settings import (
    ACCENT_COLORS, AUDIO_FORMATS, AUDIO_QUALITIES, COOKIE_BROWSERS, FILENAME_TEMPLATES,
    SPONSORBLOCK_MODES, VIDEO_CONTAINERS, VIDEO_QUALITIES,
)
from .common import open_path
from .theme import DANGER, RADIUS

FILENAME_LABELS = ["tpl_title", "tpl_uploader_title", "tpl_date_title", "tpl_title_id"]
BROWSER_NAMES = {
    "": None, "chrome": "Chrome", "firefox": "Firefox", "edge": "Edge", "brave": "Brave",
    "opera": "Opera", "vivaldi": "Vivaldi", "chromium": "Chromium", "safari": "Safari",
}


class SettingsView:
    def __init__(self, app):
        self.app = app
        self.store = app.store
        self.list_view = ft.ListView(spacing=18, expand=True, padding=ft.Padding.only(right=16, bottom=24))
        self.control = ft.Container(
            content=ft.Column([
                ft.Column([ft.Text(t("nav_settings"), size=26, weight=ft.FontWeight.W_800),
                           ft.Text(t("settings_subtitle"), size=13, color=ft.Colors.ON_SURFACE_VARIANT)], spacing=2),
                self.list_view,
            ], spacing=16, expand=True),
            padding=ft.Padding.only(left=32, right=16, top=28, bottom=0),
            expand=True,
        )
        self.build()

    # ------------------------------------------------------------------ helpers
    @property
    def s(self):
        return self.store.settings

    def _set(self, key):
        def handler(e):
            value = e.control.value
            if isinstance(e.control, ft.Slider):
                value = int(value)
            self.store.set(key, value)
        return handler

    def _section(self, icon, title: str, rows) -> ft.Container:
        body = []
        for i, row in enumerate(rows):
            if i:
                body.append(ft.Divider(height=1))
            body.append(row)
        return ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(icon, size=20, color=ft.Colors.PRIMARY),
                        ft.Text(title, size=15, weight=ft.FontWeight.W_700)], spacing=10),
                ft.Container(
                    content=ft.Column(body, spacing=0),
                    bgcolor=ft.Colors.SURFACE_CONTAINER,
                    border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                    border_radius=RADIUS,
                    padding=ft.Padding.symmetric(horizontal=18, vertical=4),
                ),
            ], spacing=10),
        )

    def _row(self, title: str, subtitle: str, control: ft.Control) -> ft.Container:
        texts = [ft.Text(title, size=14, weight=ft.FontWeight.W_600)]
        if subtitle:
            texts.append(ft.Text(subtitle, size=12, color=ft.Colors.ON_SURFACE_VARIANT))
        return ft.Container(
            content=ft.Row([ft.Column(texts, spacing=2, expand=True), control], spacing=20,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(vertical=12),
        )

    def _switch(self, key: str) -> ft.Switch:
        return ft.Switch(value=getattr(self.s, key), on_change=self._set(key))

    def _dropdown(self, key: str, options, width: int = 220) -> ft.Dropdown:
        return ft.Dropdown(
            value=getattr(self.s, key),
            options=[ft.DropdownOption(key=k, text=label) for k, label in options],
            on_select=self._set(key),
            width=width,
            dense=True,
            border_radius=12,
            text_size=13,
        )

    def _text(self, key: str, hint: str = "", width: int = 260, validator=None) -> ft.TextField:
        field = ft.TextField(value=getattr(self.s, key), hint_text=hint, width=width, dense=True, border_radius=12,
                             text_size=13, content_padding=ft.Padding.symmetric(horizontal=12, vertical=10))

        def commit(e):
            value = (field.value or "").strip()
            if validator and not validator(value):
                field.error = t("invalid_value")
                field.update()
                return
            field.error = None
            field.update()
            self.store.set(key, value)

        field.on_blur = commit
        field.on_submit = commit
        return field

    def _slider(self, key: str, lo: int, hi: int) -> ft.Row:
        label = ft.Text(str(getattr(self.s, key)), size=14, weight=ft.FontWeight.W_700, width=28,
                        text_align=ft.TextAlign.RIGHT)

        def live(e):
            label.value = str(int(e.control.value))
            label.update()

        slider = ft.Slider(min=lo, max=hi, divisions=hi - lo, value=getattr(self.s, key), width=220,
                           on_change=live, on_change_end=self._set(key))
        return ft.Row([slider, label], spacing=0, tight=True)

    def _path_row(self, title: str, subtitle: str, key: str, pick_folder: bool) -> ft.Container:
        path_text = ft.Text(getattr(self.s, key) or t("not_set"), size=12, color=ft.Colors.ON_SURFACE_VARIANT,
                            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, selectable=True)

        async def choose(e):
            if pick_folder:
                path = await self.app.file_picker.get_directory_path(dialog_title=t("choose_folder"),
                                                                     initial_directory=self.s.download_dir)
            else:
                files = await self.app.file_picker.pick_files(dialog_title=t("choose_cookies"),
                                                              allowed_extensions=["txt"], allow_multiple=False)
                path = files[0].path if files else None
            if path:
                self.store.set(key, path)
                path_text.value = path
                path_text.update()

        def clear(e):
            self.store.set(key, "")
            path_text.value = t("not_set")
            path_text.update()

        buttons = [ft.OutlinedButton(t("change") if pick_folder else t("choose"), on_click=choose)]
        if pick_folder:
            buttons.append(ft.IconButton(ft.Icons.FOLDER_OPEN_ROUNDED, tooltip=t("open_folder"),
                                         on_click=lambda e: open_path(getattr(self.s, key))))
        else:
            buttons.append(ft.IconButton(ft.Icons.CLOSE_ROUNDED, tooltip=t("clear"), on_click=clear))
        return ft.Container(
            content=ft.Row([
                ft.Column([ft.Text(title, size=14, weight=ft.FontWeight.W_600),
                           ft.Text(subtitle, size=12, color=ft.Colors.ON_SURFACE_VARIANT, visible=bool(subtitle)),
                           path_text], spacing=2, expand=True),
                ft.Row(buttons, spacing=4, tight=True),
            ], spacing=20, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(vertical=12),
        )

    # ------------------------------------------------------------------ build
    def build(self) -> None:
        s = self.s

        theme = ft.SegmentedButton(
            segments=[
                ft.Segment(value="system", label=ft.Text(t("theme_system")), icon=ft.Icon(ft.Icons.BRIGHTNESS_AUTO_ROUNDED)),
                ft.Segment(value="dark", label=ft.Text(t("theme_dark")), icon=ft.Icon(ft.Icons.DARK_MODE_ROUNDED)),
                ft.Segment(value="light", label=ft.Text(t("theme_light")), icon=ft.Icon(ft.Icons.LIGHT_MODE_ROUNDED)),
            ],
            selected=[s.theme_mode],
            show_selected_icon=False,
            on_change=lambda e: self.store.set("theme_mode", e.control.selected[0]),
        )
        swatches = ft.Row([
            ft.Container(
                width=30, height=30, border_radius=15, bgcolor=color,
                border=ft.Border.all(3, ft.Colors.ON_SURFACE) if color == s.accent else None,
                on_click=lambda e, c=color: self.store.set("accent", c),
                content=ft.Icon(ft.Icons.CHECK_ROUNDED, color="#FFFFFF", size=16) if color == s.accent else None,
                alignment=ft.Alignment.CENTER,
            ) for color in ACCENT_COLORS
        ], spacing=10, tight=True)
        language = self._dropdown("language", [("auto", t("lang_auto")), ("tr", "Türkçe"), ("en", "English")], 180)

        appearance = self._section(ft.Icons.PALETTE_OUTLINED, t("sec_appearance"), [
            self._row(t("theme"), "", theme),
            self._row(t("accent_color"), "", swatches),
            self._row(t("language"), "", language),
        ])

        output = self._section(ft.Icons.FOLDER_OUTLINED, t("sec_output"), [
            self._path_row(t("download_folder"), "", "download_dir", True),
            self._row(t("filename_template"), t("filename_template_hint"),
                      self._dropdown("filename_template", list(zip(FILENAME_TEMPLATES, [t(k) for k in FILENAME_LABELS])), 280)),
            self._row(t("playlist_subfolder"), t("playlist_subfolder_hint"), self._switch("playlist_subfolder")),
            self._row(t("number_items"), t("number_items_hint"), self._switch("number_playlist_items")),
        ])

        defaults = self._section(ft.Icons.TUNE_ROUNDED, t("sec_defaults"), [
            self._row(t("default_mode"), "", self._dropdown("mode", [("video", t("mode_video")), ("audio", t("mode_audio"))], 180)),
            self._row(t("video_quality"), t("video_quality_hint"),
                      self._dropdown("video_quality", [(q, t("best") if q == "best" else f"{q}p") for q in VIDEO_QUALITIES], 180)),
            self._row(t("container"), "", self._dropdown("video_container", [(c, c.upper()) for c in VIDEO_CONTAINERS], 180)),
            self._row(t("prefer_compatible"), t("prefer_compatible_hint"), self._switch("prefer_compatible")),
            self._row(t("audio_format"), "", self._dropdown("audio_format", [(f, f.upper()) for f in AUDIO_FORMATS], 180)),
            self._row(t("audio_quality"), "",
                      self._dropdown("audio_quality", [(q, t("best") if q == "best" else f"{q} kbps") for q in AUDIO_QUALITIES], 180)),
        ])

        subtitles = self._section(ft.Icons.SUBTITLES_OUTLINED, t("sec_subtitles"), [
            self._row(t("download_subtitles"), t("download_subtitles_hint"), self._switch("subtitles")),
            self._row(t("subtitle_langs"), t("subtitle_langs_hint"), self._text("subtitle_langs", "tr,en", 180)),
            self._row(t("auto_subtitles"), t("auto_subtitles_hint"), self._switch("auto_subtitles")),
            self._row(t("embed_subtitles"), t("embed_subtitles_hint"), self._switch("embed_subtitles")),
        ])

        post = self._section(ft.Icons.AUTO_FIX_HIGH_OUTLINED, t("sec_postprocessing"), [
            self._row(t("embed_thumbnail"), t("embed_thumbnail_hint"), self._switch("embed_thumbnail")),
            self._row(t("embed_metadata"), t("embed_metadata_hint"), self._switch("embed_metadata")),
            self._row(t("embed_chapters"), t("embed_chapters_hint"), self._switch("embed_chapters")),
            self._row(t("sponsorblock"), t("sponsorblock_hint"),
                      self._dropdown("sponsorblock", [(m, t(f"sb_{m}")) for m in SPONSORBLOCK_MODES], 220)),
        ])

        performance = self._section(ft.Icons.SPEED_ROUNDED, t("sec_performance"), [
            self._row(t("max_concurrent"), t("max_concurrent_hint"), self._slider("max_concurrent", 1, 8)),
            self._row(t("fragments"), t("fragments_hint"), self._slider("concurrent_fragments", 1, 16)),
            self._row(t("rate_limit"), t("rate_limit_hint"), self._text("rate_limit", "5M", 140, is_valid_rate)),
        ])

        def clear_archive():
            try:
                os.remove(self.app.archive_path)
            except OSError:
                pass
            self.app.toast(t("archive_cleared"), "success")

        archive_row = ft.Row([
            self._switch("use_archive"),
            ft.IconButton(ft.Icons.DELETE_SWEEP_OUTLINED, tooltip=t("clear_archive"),
                          on_click=lambda e: self.app.confirm(t("clear_archive"), t("clear_archive_body"),
                                                              t("clear_archive"), clear_archive)),
        ], tight=True, spacing=4)

        network = self._section(ft.Icons.SHIELD_OUTLINED, t("sec_network"), [
            self._row(t("cookies_browser"), t("cookies_browser_hint"),
                      self._dropdown("cookies_browser", [(b, BROWSER_NAMES[b] or t("none")) for b in COOKIE_BROWSERS], 180)),
            self._path_row(t("cookies_file"), t("cookies_file_hint"), "cookies_file", False),
            self._row(t("proxy"), t("proxy_hint"), self._text("proxy", "socks5://127.0.0.1:1080", 260)),
            self._row(t("use_archive"), t("use_archive_hint"), archive_row),
        ])

        behaviour = self._section(ft.Icons.APPS_ROUNDED, t("sec_app"), [
            self._row(t("clipboard_watch"), t("clipboard_watch_hint"), self._switch("clipboard_watch")),
            self._row(t("notify_on_complete"), "", self._switch("notify_on_complete")),
            self._row(t("open_folder_when_done"), "", self._switch("open_folder_when_done")),
        ])

        def valid_args(value):
            try:
                shlex.split(value)
                return True
            except ValueError:
                return False

        advanced = self._section(ft.Icons.CODE_ROUNDED, t("sec_advanced"), [
            self._row(t("extra_args"), t("extra_args_hint"), self._text("extra_args", "--limit-rate 2M", 300, valid_args)),
            self._row(t("reset_settings"), t("reset_settings_hint"), ft.OutlinedButton(
                t("reset"), icon=ft.Icons.RESTART_ALT_ROUNDED,
                style=ft.ButtonStyle(color=DANGER),
                on_click=lambda e: self.app.confirm(t("reset_settings"), t("reset_settings_body"), t("reset"),
                                                    self.store.reset))),
        ])

        self.list_view.controls = [appearance, output, defaults, subtitles, post, performance, network, behaviour, advanced]
