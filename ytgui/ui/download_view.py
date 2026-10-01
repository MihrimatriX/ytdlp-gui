"""The main "New download" page: paste/search, preview, choose format, download."""

import asyncio
import os
from typing import Dict, List, Optional

import flet as ft

from ..formatting import format_bytes, format_count, format_duration, format_upload_date, truncate
from ..i18n import current_language, t
from ..media import MediaEntry, ProbeError, ProbeResult, probe
from ..options import DownloadRequest, command_line
from ..settings import AUDIO_FORMATS, AUDIO_QUALITIES, VIDEO_CONTAINERS, VIDEO_QUALITIES
from ..urls import parse_input, playlist_url, video_only_url
from .common import open_path, section_title, selectable_tile, thumbnail
from .theme import DANGER, RADIUS, RADIUS_LG, WARNING, card, pill, primary_button_style

AUDIO_KBPS = {"flac": 900, "wav": 1411}
CONTAINER_HINTS = {"mp4": "container_mp4", "mkv": "container_mkv", "webm": "container_webm"}
AUDIO_HINTS = {"mp3": "audio_mp3", "m4a": "audio_m4a", "opus": "audio_opus", "flac": "audio_flac", "wav": "audio_wav"}


class DownloadView:
    def __init__(self, app):
        self.app = app
        self.settings = app.settings
        self.result: Optional[ProbeResult] = None
        self._token = 0
        self._last_query = ("", True)
        self._reset_choices()

        self.url_field = ft.TextField(
            hint_text=t("url_hint"),
            border=ft.NoInputBorder(),
            text_size=15,
            expand=True,
            autofocus=True,
            on_submit=self.on_fetch,
            on_change=self._on_text_change,
            content_padding=ft.Padding.symmetric(horizontal=4, vertical=14),
        )
        self.clear_btn = ft.IconButton(ft.Icons.CLOSE_ROUNDED, tooltip=t("clear"), visible=False,
                                       on_click=self._on_clear, icon_size=20, icon_color=ft.Colors.ON_SURFACE_VARIANT)
        self.fetch_btn = ft.FilledButton(
            t("fetch"), icon=ft.Icons.ARROW_FORWARD_ROUNDED, on_click=self.on_fetch,
            height=48, style=primary_button_style(),
        )
        search_bar = ft.Container(
            content=ft.Row([
                ft.Container(ft.Icon(ft.Icons.LINK_ROUNDED, color=ft.Colors.ON_SURFACE_VARIANT), padding=ft.Padding.only(left=10)),
                self.url_field,
                self.clear_btn,
                ft.IconButton(ft.Icons.CONTENT_PASTE_ROUNDED, tooltip=t("paste"), on_click=self.on_paste,
                              icon_color=ft.Colors.ON_SURFACE_VARIANT),
                self.fetch_btn,
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.only(left=6, right=6, top=6, bottom=6),
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=RADIUS_LG,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            shadow=ft.BoxShadow(blur_radius=30, spread_radius=-12, color=ft.Colors.with_opacity(0.25, "#000000"),
                                offset=ft.Offset(0, 10)),
        )

        self.hero = ft.Column([
            ft.Text(t("hero_title"), size=30, weight=ft.FontWeight.W_800),
            ft.Text(t("hero_subtitle"), size=14, color=ft.Colors.ON_SURFACE_VARIANT),
        ], spacing=4)

        self.clip_text = ft.Text("", size=13, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True)
        self.clip_banner = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.CONTENT_PASTE_GO_ROUNDED, color=ft.Colors.PRIMARY, size=20),
                ft.Text(t("clipboard_found"), size=13, weight=ft.FontWeight.W_600),
                self.clip_text,
                ft.TextButton(t("clipboard_use"), on_click=self._use_clipboard),
                ft.IconButton(ft.Icons.CLOSE_ROUNDED, icon_size=18, on_click=self._hide_clipboard,
                              icon_color=ft.Colors.ON_SURFACE_VARIANT),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.only(left=14, right=6, top=4, bottom=4),
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.PRIMARY),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ft.Colors.PRIMARY)),
            visible=False,
        )
        self._clip_url = ""

        self.body = ft.Container(expand=True)
        self.control = ft.Container(
            content=ft.Column([self.hero, search_bar, self.clip_banner, self.body], spacing=18, expand=True),
            padding=ft.Padding.only(left=32, right=32, top=28, bottom=20),
            expand=True,
        )
        self._render_idle()

    # ------------------------------------------------------------------ state
    def _reset_choices(self) -> None:
        s = self.settings
        self.mode = s.mode
        self.quality = s.video_quality
        self.container = s.video_container
        self.audio_format = s.audio_format
        self.audio_quality = s.audio_quality
        self.subtitles = s.subtitles

    def on_show(self) -> None:
        if self.result is None:
            self._render_idle()

    async def focus_input(self) -> None:
        await self.url_field.focus()

    def _update(self) -> None:
        if self.control.page:
            self.control.update()

    # ------------------------------------------------------------------ input
    def _on_text_change(self, e) -> None:
        visible = bool(self.url_field.value)
        if self.clear_btn.visible != visible:
            self.clear_btn.visible = visible
            self.clear_btn.update()

    def _on_clear(self, e) -> None:
        self.url_field.value = ""
        self.clear_btn.visible = False
        self.result = None
        self._token += 1
        self._render_idle()
        self._update()

    async def on_paste(self, e) -> None:
        try:
            text = await self.app.clipboard.get()
        except Exception:
            text = ""
        text = (text or "").strip()
        if not text:
            self.app.toast(t("clipboard_empty"))
            return
        self.url_field.value = text
        self.clear_btn.visible = True
        await self.fetch()

    def offer_clipboard(self, url: str) -> None:
        if url in ((self.url_field.value or "").strip(), self.result.url if self.result else ""):
            return
        self._clip_url = url
        self.clip_text.value = url
        self.clip_banner.visible = True
        self._update()

    async def _use_clipboard(self, e) -> None:
        self.url_field.value = self._clip_url
        self.clear_btn.visible = True
        self.clip_banner.visible = False
        await self.fetch()

    def _hide_clipboard(self, e) -> None:
        self.clip_banner.visible = False
        self._update()

    async def on_fetch(self, e=None) -> None:
        await self.fetch()

    async def fetch(self, text: Optional[str] = None, single_video: bool = True) -> None:
        parsed = parse_input(text if text is not None else self.url_field.value)
        if parsed.kind == "empty":
            await self.url_field.focus()
            return
        if text is not None:
            self.url_field.value = text
        self.clip_banner.visible = False
        self._token += 1
        token = self._token
        self._last_query = (parsed.query, single_video)
        self._render_loading(parsed.kind == "search", not single_video or (parsed.has_playlist and not parsed.has_video))
        self.fetch_btn.disabled = True
        self._update()
        try:
            result = await asyncio.to_thread(probe, parsed.query, self.settings, single_video)
            error = None
        except ProbeError as exc:
            result, error = None, exc
        if token != self._token:
            return  # superseded by a newer request
        self.fetch_btn.disabled = False
        if error is not None:
            self._render_error(error)
        else:
            if result.kind == "video" and parsed.has_playlist and parsed.has_video:
                result.playlist_url = playlist_url(parsed.query)
            self.result = result
            self._reset_choices()
            if result.kind == "video":
                self._render_video()
            else:
                self._render_list()
        self._update()

    # ------------------------------------------------------------------ idle
    def _render_idle(self) -> None:
        self.hero.visible = True
        features = [
            (ft.Icons.HIGH_QUALITY_ROUNDED, "feat_quality_title", "feat_quality_body"),
            (ft.Icons.MUSIC_NOTE_ROUNDED, "feat_audio_title", "feat_audio_body"),
            (ft.Icons.PLAYLIST_PLAY_ROUNDED, "feat_lists_title", "feat_lists_body"),
            (ft.Icons.BOLT_ROUNDED, "feat_fast_title", "feat_fast_body"),
        ]
        tiles = [
            ft.Container(
                content=ft.Column([
                    ft.Container(ft.Icon(icon, color=ft.Colors.PRIMARY, size=22), width=42, height=42, border_radius=12,
                                 alignment=ft.Alignment.CENTER, bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY)),
                    ft.Text(t(title), size=14, weight=ft.FontWeight.W_700),
                    ft.Text(t(body), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                ], spacing=8),
                padding=18,
                height=150,
                border_radius=RADIUS,
                bgcolor=ft.Colors.SURFACE_CONTAINER,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                col={"xs": 12, "sm": 6, "lg": 3},
            )
            for icon, title, body in features
        ]
        content: List[ft.Control] = [ft.ResponsiveRow(tiles, spacing=14, run_spacing=14)]

        recent = self.app.history.items[:4]
        if recent:
            rows = []
            for item in recent:
                exists = bool(item.filepath) and os.path.exists(item.filepath)
                rows.append(ft.Container(
                    content=ft.Row([
                        thumbnail(item.thumbnail, 96, 54, radius=8,
                                  icon=ft.Icons.MUSIC_NOTE_ROUNDED if item.mode == "audio" else ft.Icons.SMART_DISPLAY_ROUNDED),
                        ft.Column([
                            ft.Text(item.title, size=13, weight=ft.FontWeight.W_600, max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(" · ".join(filter(None, [item.format_label, format_bytes(item.size) if item.size else ""])),
                                    size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        ], spacing=2, expand=True),
                        ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE_ROUNDED if exists else ft.Icons.LINK_OFF_ROUNDED,
                                color=ft.Colors.ON_SURFACE_VARIANT, size=20),
                    ], spacing=14),
                    padding=10,
                    border_radius=12,
                    on_click=(lambda e, p=item.filepath: open_path(p)) if exists else None,
                    on_hover=self._hover,
                    tooltip=t("open_file") if exists else t("file_missing"),
                ))
            content.append(ft.Container(height=6))
            content.append(section_title(t("recent_downloads"), ft.TextButton(
                t("see_all"), on_click=lambda e: self.app.navigate("history"))))
            content.append(card(ft.Column(rows, spacing=2), padding=8))

        content.append(ft.Row([
            ft.Icon(ft.Icons.TIPS_AND_UPDATES_OUTLINED, size=16, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text(t("tip_shortcuts"), size=12, color=ft.Colors.ON_SURFACE_VARIANT, expand=True),
        ], spacing=8))
        self.body.content = ft.Column(content, spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

    @staticmethod
    def _hover(e) -> None:
        e.control.bgcolor = ft.Colors.SURFACE_CONTAINER_HIGH if e.data in (True, "true") else None
        e.control.update()

    # ------------------------------------------------------------------ loading / error
    def _render_loading(self, search: bool, is_list: bool) -> None:
        self.hero.visible = False
        message = t("loading_search") if search else (t("loading_list") if is_list else t("loading_video"))

        def block(w, h, r=8):
            return ft.Container(width=w, height=h, border_radius=r, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST)

        skeleton = ft.Row([
            ft.Container(height=225, expand=4, border_radius=RADIUS, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST),
            ft.Column([block(420, 26), block(260, 16), ft.Container(height=12), block(200, 14),
                       ft.Row([block(110, 64, 12) for _ in range(4)], spacing=10, wrap=True),
                       ft.Container(height=12), block(320, 48, 12)], spacing=12, expand=5),
        ], spacing=28, vertical_alignment=ft.CrossAxisAlignment.START)
        self.body.content = ft.Column([
            ft.Row([ft.ProgressRing(width=18, height=18, stroke_width=2.5),
                    ft.Text(message, size=13, color=ft.Colors.ON_SURFACE_VARIANT)], spacing=12),
            ft.Shimmer(
                content=card(skeleton, padding=24),
                base_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                highlight_color=ft.Colors.SURFACE_CONTAINER_LOW,
            ),
        ], spacing=16)

    def _render_error(self, error: ProbeError) -> None:
        self.hero.visible = True
        self.result = None
        actions = [ft.FilledButton(t("retry"), icon=ft.Icons.REFRESH_ROUNDED, on_click=self._retry_fetch,
                                   style=primary_button_style())]
        if error.key in ("err_bot_check", "err_age", "err_members", "err_private", "err_cookies"):
            actions.append(ft.OutlinedButton(t("open_cookie_settings"), icon=ft.Icons.COOKIE_OUTLINED,
                                             on_click=lambda e: self.app.navigate("settings")))
        if error.key in ("err_forbidden", "err_format", "err_generic"):
            actions.append(ft.OutlinedButton(t("nav_system"), icon=ft.Icons.MONITOR_HEART_OUTLINED,
                                             on_click=lambda e: self.app.navigate("system")))
        self.body.content = ft.Column([card(ft.Row([
            ft.Container(ft.Icon(ft.Icons.ERROR_OUTLINE_ROUNDED, color=DANGER, size=28), width=52, height=52,
                         border_radius=26, alignment=ft.Alignment.CENTER, bgcolor=ft.Colors.with_opacity(0.12, DANGER)),
            ft.Column([
                ft.Text(t(error.key), size=16, weight=ft.FontWeight.W_700),
                ft.Text(t(error.key + "_hint"), size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(truncate(error.detail, 400), size=12, color=ft.Colors.ON_SURFACE_VARIANT, selectable=True,
                        font_family="monospace", visible=bool(error.detail) and error.detail != t(error.key)),
                ft.Container(ft.Row(actions, spacing=10, wrap=True), margin=ft.Margin.only(top=8)),
            ], spacing=6, expand=True),
        ], spacing=18, vertical_alignment=ft.CrossAxisAlignment.START), padding=24)], scroll=ft.ScrollMode.AUTO)

    async def _retry_fetch(self, e) -> None:
        query, single = self._last_query
        if query.startswith("ytsearch"):
            await self.fetch(single_video=single)
        else:
            await self.fetch(query, single_video=single)

    # ------------------------------------------------------------------ shared format controls
    def _estimated_size(self) -> Optional[int]:
        r = self.result
        if not r:
            return None
        if self.mode == "audio":
            if not r.duration:
                return None
            kbps = AUDIO_KBPS.get(self.audio_format) or int(self.audio_quality if self.audio_quality.isdigit() else 192)
            return int(kbps * 1000 / 8 * r.duration)
        for q in r.qualities:
            if q.key == self.quality:
                return q.size
        return r.qualities[0].size if r.qualities else None

    def _mode_switch(self, on_change) -> ft.SegmentedButton:
        return ft.SegmentedButton(
            segments=[
                ft.Segment(value="video", label=ft.Text(t("mode_video")), icon=ft.Icon(ft.Icons.MOVIE_ROUNDED)),
                ft.Segment(value="audio", label=ft.Text(t("mode_audio")), icon=ft.Icon(ft.Icons.MUSIC_NOTE_ROUNDED)),
            ],
            selected=[self.mode],
            show_selected_icon=False,
            on_change=on_change,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12),
                                 padding=ft.Padding.symmetric(horizontal=18, vertical=12)),
        )

    def _make_request(self, url: str, title: str = "", thumb: Optional[str] = None, duration=None,
                      uploader: str = "", **extra) -> DownloadRequest:
        return DownloadRequest.from_settings(
            self.settings, url, archive_path=self.app.archive_path,
            title=title, thumbnail=thumb, duration=duration, uploader=uploader,
            mode=self.mode, video_quality=self.quality, video_container=self.container,
            audio_format=self.audio_format, audio_quality=self.audio_quality, subtitles=self.subtitles,
            **extra,
        )

    def _folder_row(self) -> ft.Container:
        path_text = ft.Text(self.settings.download_dir, size=13, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                            expand=True, tooltip=self.settings.download_dir)

        async def change(e):
            path = await self.app.file_picker.get_directory_path(dialog_title=t("choose_folder"),
                                                                 initial_directory=self.settings.download_dir)
            if path:
                self.app.store.set("download_dir", path)
                path_text.value = path
                path_text.tooltip = path
                path_text.update()

        return ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.FOLDER_ROUNDED, color=ft.Colors.PRIMARY, size=20),
                ft.Column([ft.Text(t("save_to"), size=11, color=ft.Colors.ON_SURFACE_VARIANT), path_text],
                          spacing=0, expand=True),
                ft.TextButton(t("change"), on_click=change),
            ], spacing=12),
            padding=ft.Padding.only(left=14, right=6, top=8, bottom=8),
            border_radius=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        )

    # ------------------------------------------------------------------ single video
    def _render_video(self) -> None:
        r = self.result
        self.hero.visible = False
        if r.qualities and self.quality not in [q.key for q in r.qualities]:
            if self.quality == "best":
                self.quality = r.qualities[0].key
            else:
                wanted = int(self.quality)
                below = [q for q in r.qualities if q.height <= wanted]
                self.quality = (below[0] if below else r.qualities[-1]).key

        lang = current_language()
        meta = [x for x in [
            t("views", n=format_count(r.view_count, lang)) if r.view_count else "",
            format_upload_date(r.upload_date),
        ] if x]
        live = pill(t("live"), "#FFFFFF", DANGER) if r.is_live else None

        self.options_host = ft.Column(spacing=12)
        self.download_btn = ft.FilledButton(height=54, icon=ft.Icons.DOWNLOAD_ROUNDED, on_click=self._download_video,
                                            style=primary_button_style(), expand=True)
        left = ft.Column([
            ft.Container(
                content=thumbnail(r.thumbnail, 480, 270, r.duration, radius=RADIUS, badge=live),
                alignment=ft.Alignment.TOP_CENTER,
            ),
            ft.Container(height=4),
            self._folder_row(),
            ft.Row([
                self.download_btn,
                ft.IconButton(ft.Icons.TERMINAL_ROUNDED, tooltip=t("copy_command"), on_click=self._copy_command,
                              icon_color=ft.Colors.ON_SURFACE_VARIANT),
            ], spacing=8),
        ], spacing=12, col={"xs": 12, "md": 5})
        info = ft.Column([
            ft.Text(r.title, size=21, weight=ft.FontWeight.W_800, max_lines=3, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Row([
                ft.Icon(ft.Icons.ACCOUNT_CIRCLE_ROUNDED, size=18, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(r.uploader or "—", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.ON_SURFACE_VARIANT),
                *[ft.Text("·  " + m, size=13, color=ft.Colors.ON_SURFACE_VARIANT) for m in meta],
            ], spacing=6, wrap=True),
            ft.Divider(height=14),
            ft.Row([self._mode_switch(self._on_video_mode)], wrap=True),
            self.options_host,
        ], spacing=10, col={"xs": 12, "md": 7})

        content: List[ft.Control] = []
        if r.playlist_url:
            content.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.PLAYLIST_PLAY_ROUNDED, color=ft.Colors.PRIMARY),
                    ft.Text(t("part_of_playlist"), size=13, expand=True),
                    ft.TextButton(t("load_playlist"), icon=ft.Icons.ARROW_FORWARD_ROUNDED,
                                  on_click=self._load_playlist),
                ], spacing=12),
                padding=ft.Padding.only(left=14, right=6, top=2, bottom=2),
                border_radius=12,
                bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
            ))
        if not self.app.ffmpeg_location:
            content.append(self._ffmpeg_warning())
        content.append(card(ft.ResponsiveRow([left, info], spacing=28, run_spacing=20), padding=24))
        self.body.content = ft.Column(content, spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)
        self._render_video_options()

    def _ffmpeg_warning(self) -> ft.Container:
        return ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=WARNING),
                ft.Text(t("ffmpeg_missing_inline"), size=13, expand=True),
                ft.TextButton(t("nav_system"), on_click=lambda e: self.app.navigate("system")),
            ], spacing=12),
            padding=ft.Padding.only(left=14, right=6, top=2, bottom=2),
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.10, WARNING),
        )

    def _render_video_options(self) -> None:
        r = self.result
        controls: List[ft.Control] = []
        if self.mode == "video":
            if r.qualities:
                chips = []
                for q in r.qualities:
                    badges = [b for b in [q.tag, "HDR" if q.hdr else "", f"{q.fps:.0f}fps" if q.fps and q.fps > 30 else ""] if b]
                    chips.append(selectable_tile(
                        ft.Column([
                            ft.Row([ft.Text(q.label, size=15, weight=ft.FontWeight.W_800),
                                    *[ft.Text(b, size=10, weight=ft.FontWeight.W_700, color=ft.Colors.PRIMARY) for b in badges]],
                                   spacing=6, tight=True),
                            ft.Text(("~" + format_bytes(q.size)) if q.size else " ", size=11,
                                    color=ft.Colors.ON_SURFACE_VARIANT),
                        ], spacing=2, tight=True),
                        selected=q.key == self.quality,
                        on_click=lambda e, k=q.key: self._set_choice("quality", k),
                    ))
                controls += [section_title(t("quality")), ft.Row(chips, wrap=True, spacing=10, run_spacing=10)]
            else:
                controls.append(ft.Text(t("no_quality_info"), size=12, color=ft.Colors.ON_SURFACE_VARIANT))
            controls += [section_title(t("container")), self._choice_row(
                VIDEO_CONTAINERS, self.container, "container", lambda c: c.upper(), lambda c: t(CONTAINER_HINTS[c]))]
            controls.append(self._subtitle_switch())
        else:
            controls += [section_title(t("audio_format")), self._choice_row(
                AUDIO_FORMATS, self.audio_format, "audio_format", lambda f: f.upper(), lambda f: t(AUDIO_HINTS[f]))]
            lossless = self.audio_format in ("flac", "wav")
            controls += [section_title(t("audio_quality")), self._choice_row(
                AUDIO_QUALITIES, self.audio_quality, "audio_quality",
                lambda q: t("best") if q == "best" else f"{q} kbps", None, disabled=lossless)]
        self.options_host.controls = controls
        size = self._estimated_size()
        self.download_btn.content = t("download") + (f"  ·  ~{format_bytes(size)}" if size else "")

    def _choice_row(self, values, current, attr, label_fn, hint_fn=None, disabled=False) -> ft.Row:
        tiles = []
        for value in values:
            parts = [ft.Text(label_fn(value), size=14, weight=ft.FontWeight.W_700)]
            if hint_fn:
                parts.append(ft.Text(hint_fn(value), size=11, color=ft.Colors.ON_SURFACE_VARIANT))
            tiles.append(selectable_tile(
                ft.Column(parts, spacing=1, tight=True),
                selected=value == current and not disabled,
                disabled=disabled,
                on_click=lambda e, v=value: self._set_choice(attr, v),
            ))
        return ft.Row(tiles, wrap=True, spacing=10, run_spacing=10)

    def _subtitle_switch(self) -> ft.Row:
        def toggle(e):
            self.subtitles = e.control.value

        return ft.Row([
            ft.Switch(value=self.subtitles, on_change=toggle, label=t("download_subtitles")),
            ft.Text(f"({self.settings.subtitle_langs})", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
        ], spacing=8)

    def _set_choice(self, attr: str, value: str) -> None:
        setattr(self, attr, value)
        self._render_video_options()
        self._update()

    def _on_video_mode(self, e) -> None:
        self.mode = e.control.selected[0] if e.control.selected else "video"
        self._render_video_options()
        self._update()

    async def _load_playlist(self, e) -> None:
        if self.result and self.result.playlist_url:
            await self.fetch(self.result.playlist_url, single_video=False)

    def _download_video(self, e) -> None:
        r = self.result
        if not r:
            return
        url = video_only_url(r.url) if r.playlist_url else r.url
        self.app.manager.add(self._make_request(url, r.title, r.thumbnail, r.duration, r.uploader))
        self.app.toast(t("toast_queued_one", title=truncate(r.title, 60)), "success", action=t("view"),
                       on_action=lambda ev: self.app.navigate("queue"))

    async def _copy_command(self, e) -> None:
        r = self.result
        if not r:
            return
        cmd = command_line(self._make_request(r.url, r.title), self.app.ffmpeg_location)
        await self.app.clipboard.set(cmd)
        self.app.toast(t("command_copied"))

    # ------------------------------------------------------------------ lists (playlist / channel / search)
    def _render_list(self) -> None:
        r = self.result
        self.hero.visible = False
        self.checkboxes: Dict[int, ft.Checkbox] = {}
        self.rows: Dict[int, ft.Container] = {}
        lang = current_language()
        list_view = ft.ListView(spacing=2, expand=True, padding=ft.Padding.only(right=10), build_controls_on_demand=True)
        for i, entry in enumerate(r.entries):
            list_view.controls.append(self._list_row(i, entry, lang))
        self.list_view = list_view

        icon = {"search": ft.Icons.SEARCH_ROUNDED, "channel": ft.Icons.ACCOUNT_BOX_ROUNDED}.get(r.source, ft.Icons.PLAYLIST_PLAY_ROUNDED)
        title = t("search_results_for", q=r.title) if r.source == "search" else (r.title or t("playlist"))
        sub = [t(f"source_{r.source}"), t("n_videos", n=len(r.entries))]
        if r.total_duration:
            sub.append(format_duration(r.total_duration))
        if r.uploader and r.source != "search":
            sub.insert(1, r.uploader)

        self.select_all = ft.Checkbox(value=True, on_change=self._on_select_all)
        self.selection_text = ft.Text("", size=13, color=ft.Colors.ON_SURFACE_VARIANT)
        filter_field = ft.TextField(
            hint_text=t("filter_list"), prefix_icon=ft.Icons.SEARCH_ROUNDED, dense=True, width=260,
            border_radius=12, on_change=self._on_filter, text_size=13,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        )
        header = card(ft.Row([
            ft.Container(ft.Icon(icon, color=ft.Colors.PRIMARY, size=26), width=52, height=52, border_radius=14,
                         alignment=ft.Alignment.CENTER, bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY)),
            ft.Column([
                ft.Text(title, size=18, weight=ft.FontWeight.W_800, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text("  ·  ".join(sub), size=13, color=ft.Colors.ON_SURFACE_VARIANT),
            ], spacing=2, expand=True),
        ], spacing=16), padding=16)

        toolbar = ft.Row([
            self.select_all,
            self.selection_text,
            ft.Container(expand=True),
            filter_field,
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER)

        self.list_options = ft.Row(spacing=10, wrap=True, run_spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self.list_download_btn = ft.FilledButton(icon=ft.Icons.DOWNLOAD_ROUNDED, height=48, on_click=self._download_list,
                                                 style=primary_button_style())
        bottom = ft.Container(
            content=ft.Row([
                self._mode_switch(self._on_list_mode),
                ft.Container(content=self.list_options, expand=True),
                self.list_download_btn,
            ], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(horizontal=16, vertical=12),
            border_radius=RADIUS,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        )
        list_card = ft.Container(
            content=list_view, expand=True, padding=ft.Padding.only(left=6, top=6, bottom=6),
            border_radius=RADIUS, bgcolor=ft.Colors.SURFACE_CONTAINER,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        )
        parts: List[ft.Control] = [header]
        if not self.app.ffmpeg_location:
            parts.append(self._ffmpeg_warning())
        parts += [toolbar, list_card, bottom]
        self.body.content = ft.Column(parts, spacing=12, expand=True)
        self._render_list_options()
        self._update_selection()

    def _list_row(self, i: int, entry: MediaEntry, lang: str) -> ft.Container:
        cb = ft.Checkbox(value=entry.available, disabled=not entry.available, on_change=lambda e: self._update_selection(True))
        self.checkboxes[i] = cb
        meta = [x for x in [entry.uploader, t("views", n=format_count(entry.view_count, lang)) if entry.view_count else ""] if x]

        def toggle(e):
            if entry.available:
                cb.value = not cb.value
                self._update_selection(True)

        row = ft.Container(
            content=ft.Row([
                cb,
                ft.Text(str(entry.index), size=12, color=ft.Colors.ON_SURFACE_VARIANT, width=30,
                        text_align=ft.TextAlign.RIGHT),
                thumbnail(entry.thumbnail, 128, 72, entry.duration),
                ft.Column([
                    ft.Text(entry.title, size=14, weight=ft.FontWeight.W_600, max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text("  ·  ".join(meta) if entry.available else t("unavailable"), size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT if entry.available else DANGER),
                ], spacing=4, expand=True),
            ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(horizontal=6, vertical=6),
            border_radius=12,
            on_click=toggle,
            on_hover=self._hover,
            opacity=1.0 if entry.available else 0.5,
        )
        self.rows[i] = row
        return row

    def _selected_entries(self) -> List[MediaEntry]:
        return [e for i, e in enumerate(self.result.entries) if self.checkboxes[i].value]

    def _update_selection(self, push: bool = False) -> None:
        selected = self._selected_entries()
        available = sum(1 for e in self.result.entries if e.available)
        self.selection_text.value = t("n_selected", n=len(selected), total=len(self.result.entries))
        self.select_all.value = len(selected) == available and available > 0
        self.list_download_btn.content = t("download_n", n=len(selected))
        self.list_download_btn.disabled = not selected
        if push:
            self._update()

    def _on_select_all(self, e) -> None:
        value = bool(self.select_all.value)
        for i, entry in enumerate(self.result.entries):
            if entry.available and self.rows[i].visible:
                self.checkboxes[i].value = value
        self._update_selection(True)

    def _on_filter(self, e) -> None:
        text = (e.control.value or "").strip().lower()
        for i, entry in enumerate(self.result.entries):
            self.rows[i].visible = not text or text in entry.title.lower()
        self.list_view.update()

    def _dropdown(self, value: str, options, on_select, width=150) -> ft.Dropdown:
        return ft.Dropdown(
            value=value,
            options=[ft.DropdownOption(key=k, text=label) for k, label in options],
            on_select=on_select,
            width=width,
            dense=True,
            border_radius=12,
            text_size=13,
        )

    def _render_list_options(self) -> None:
        if self.mode == "video":
            quality_opts = [(q, t("best") if q == "best" else f"{q}p") for q in VIDEO_QUALITIES]
            self.list_options.controls = [
                self._dropdown(self.quality, quality_opts, lambda e: setattr(self, "quality", e.control.value)),
                self._dropdown(self.container, [(c, c.upper()) for c in VIDEO_CONTAINERS],
                               lambda e: setattr(self, "container", e.control.value), width=120),
            ]
        else:
            self.list_options.controls = [
                self._dropdown(self.audio_format, [(f, f.upper()) for f in AUDIO_FORMATS],
                               lambda e: setattr(self, "audio_format", e.control.value), width=120),
                self._dropdown(self.audio_quality,
                               [(q, t("best") if q == "best" else f"{q} kbps") for q in AUDIO_QUALITIES],
                               lambda e: setattr(self, "audio_quality", e.control.value)),
            ]

    def _on_list_mode(self, e) -> None:
        self.mode = e.control.selected[0] if e.control.selected else "video"
        self._render_list_options()
        self._update()

    def _download_list(self, e) -> None:
        r = self.result
        entries = self._selected_entries()
        if not r or not entries:
            return
        subfolder = r.title if (self.settings.playlist_subfolder and r.source != "search") else ""
        number = self.settings.number_playlist_items and r.source == "playlist"
        requests = [
            self._make_request(entry.url, entry.title, entry.thumbnail, entry.duration, entry.uploader,
                               subfolder=subfolder, index=entry.index if number else None)
            for entry in entries
        ]
        self.app.manager.add_many(requests)
        self.app.toast(t("toast_queued_many", n=len(requests)), "success", action=t("view"),
                       on_action=lambda ev: self.app.navigate("queue"))
