"""System page: health checks, maintenance actions and app info."""

import asyncio

import flet as ft

from .. import APP_NAME, APP_VERSION, REPO_URL
from ..diagnostics import can_self_update, run_checks, update_ytdlp
from ..ffmpeg import can_auto_install, install_hint
from ..i18n import t
from ..paths import data_dir
from .common import open_path
from .theme import DANGER, RADIUS, SUCCESS, WARNING, card

SHORTCUTS = [("Ctrl + L", "sc_focus"), ("Ctrl + V", "sc_paste"), ("Enter", "sc_fetch"), ("Ctrl + 1…5", "sc_pages")]


class SystemView:
    def __init__(self, app):
        self.app = app
        self.checks_col = ft.Column(spacing=0)
        self.check_btn = ft.OutlinedButton(t("recheck"), icon=ft.Icons.REFRESH_ROUNDED, on_click=self._on_recheck)
        self._loaded = False

        logo = ft.Container(
            content=ft.Icon(ft.Icons.DOWNLOAD_ROUNDED, color="#FFFFFF", size=34),
            width=68, height=68, border_radius=20, alignment=ft.Alignment.CENTER,
            gradient=ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                                       colors=[app.settings.accent, ft.Colors.with_opacity(0.7, app.settings.accent)]),
        )
        about = card(ft.Row([
            logo,
            ft.Column([
                ft.Text(APP_NAME, size=20, weight=ft.FontWeight.W_800),
                ft.Text(f"{t('version')} {APP_VERSION}  ·  {t('about_body')}", size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Row([
                    ft.TextButton("GitHub", icon=ft.Icons.CODE_ROUNDED, url=REPO_URL),
                    ft.TextButton(t("releases"), icon=ft.Icons.NEW_RELEASES_OUTLINED, url=REPO_URL + "/releases"),
                    ft.TextButton(t("report_issue"), icon=ft.Icons.BUG_REPORT_OUTLINED, url=REPO_URL + "/issues"),
                ], spacing=0, wrap=True),
            ], spacing=4, expand=True),
        ], spacing=20), padding=22)

        shortcuts = card(ft.Column([
            ft.Text(t("shortcuts"), size=15, weight=ft.FontWeight.W_700),
            *[ft.Row([
                ft.Container(ft.Text(keys, size=12, weight=ft.FontWeight.W_700, font_family="monospace"),
                             padding=ft.Padding.symmetric(horizontal=8, vertical=3), border_radius=6,
                             bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, width=110, alignment=ft.Alignment.CENTER),
                ft.Text(t(label), size=13, color=ft.Colors.ON_SURFACE_VARIANT),
            ], spacing=14) for keys, label in SHORTCUTS],
        ], spacing=10), padding=20)

        data = card(ft.Row([
            ft.Column([ft.Text(t("data_folder"), size=14, weight=ft.FontWeight.W_600),
                       ft.Text(str(data_dir()), size=12, color=ft.Colors.ON_SURFACE_VARIANT, selectable=True)],
                      spacing=2, expand=True),
            ft.OutlinedButton(t("open_folder"), icon=ft.Icons.FOLDER_OPEN_ROUNDED, on_click=lambda e: open_path(str(data_dir()))),
        ]), padding=20)

        self.control = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Column([ft.Text(t("nav_system"), size=26, weight=ft.FontWeight.W_800),
                               ft.Text(t("system_subtitle"), size=13, color=ft.Colors.ON_SURFACE_VARIANT)],
                              spacing=2, expand=True),
                    self.check_btn,
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.ListView([
                    about,
                    ft.Container(
                        content=self.checks_col,
                        bgcolor=ft.Colors.SURFACE_CONTAINER,
                        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                        border_radius=RADIUS,
                        padding=ft.Padding.symmetric(horizontal=18, vertical=6),
                    ),
                    ft.ResponsiveRow([
                        ft.Container(shortcuts, col={"xs": 12, "lg": 6}),
                        ft.Container(data, col={"xs": 12, "lg": 6}),
                    ], spacing=16, run_spacing=16),
                ], spacing=16, expand=True, padding=ft.Padding.only(right=16, bottom=24)),
            ], spacing=16, expand=True),
            padding=ft.Padding.only(left=32, right=16, top=28, bottom=0),
            expand=True,
        )
        self._show_loading()

    def _show_loading(self) -> None:
        self.checks_col.controls = [ft.Container(
            ft.Row([ft.ProgressRing(width=18, height=18, stroke_width=2.5),
                    ft.Text(t("checking"), color=ft.Colors.ON_SURFACE_VARIANT)], spacing=12),
            padding=ft.Padding.symmetric(vertical=16),
        )]

    def on_show(self) -> None:
        if not self._loaded:
            self._loaded = True
            self.app.page.run_task(self._run_checks)

    def refresh(self) -> None:
        self.app.page.run_task(self._run_checks)

    async def _on_recheck(self, e) -> None:
        await self._run_checks()

    async def _run_checks(self) -> None:
        self.check_btn.disabled = True
        self._show_loading()
        if self.control.page:
            self.control.update()
        checks = await asyncio.to_thread(run_checks, self.app.settings.download_dir)
        rows = []
        for i, check in enumerate(checks):
            if i:
                rows.append(ft.Divider(height=1))
            rows.append(self._check_row(check))
        self.checks_col.controls = rows
        self.check_btn.disabled = False
        if self.control.page:
            self.control.update()

    def _check_row(self, check) -> ft.Container:
        if check.ok is True:
            icon, color = ft.Icons.CHECK_CIRCLE_ROUNDED, SUCCESS
        elif check.ok is None:
            icon, color = ft.Icons.WARNING_ROUNDED, WARNING
        else:
            icon, color = ft.Icons.ERROR_ROUNDED, DANGER
        texts = [ft.Row([ft.Text(t(check.key), size=14, weight=ft.FontWeight.W_600),
                         ft.Text(check.detail, size=12, color=ft.Colors.ON_SURFACE_VARIANT, selectable=True)],
                        spacing=10, wrap=True)]
        hint = t(check.hint_key) if check.hint_key else ""
        if check.key == "diag_ffmpeg" and check.ok is False and install_hint():
            hint = f"{hint}  {install_hint()}"
        if hint:
            texts.append(ft.Text(hint, size=12, color=ft.Colors.ON_SURFACE_VARIANT, selectable=True))

        action = None
        if check.key == "diag_ffmpeg" and check.ok is False and can_auto_install():
            action = ft.FilledButton(t("install"), icon=ft.Icons.DOWNLOAD_ROUNDED, on_click=self._install_ffmpeg)
        elif check.key == "diag_ytdlp" and check.ok is None:
            if can_self_update():
                action = ft.FilledButton(t("update"), icon=ft.Icons.SYSTEM_UPDATE_ALT_ROUNDED, on_click=self._update_ytdlp)
            else:
                action = ft.OutlinedButton(t("releases"), icon=ft.Icons.OPEN_IN_NEW_ROUNDED, url=REPO_URL + "/releases")
        elif check.key == "diag_js" and check.ok is None:
            action = ft.OutlinedButton(t("how_to"), icon=ft.Icons.OPEN_IN_NEW_ROUNDED,
                                       url="https://github.com/yt-dlp/yt-dlp/wiki/EJS")
        row = [ft.Icon(icon, color=color, size=22), ft.Column(texts, spacing=2, expand=True)]
        if action:
            row.append(action)
        return ft.Container(ft.Row(row, spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            padding=ft.Padding.symmetric(vertical=12))

    def _install_ffmpeg(self, e) -> None:
        self.app.install_ffmpeg_now()
        e.control.disabled = True
        e.control.update()

    async def _update_ytdlp(self, e) -> None:
        e.control.disabled = True
        e.control.update()
        self.app.toast(t("updating"))
        result = await asyncio.to_thread(update_ytdlp)
        if result.returncode == 0:
            self.app.toast(t("updated_restart"), "success")
        else:
            self.app.toast(t("update_failed"), "error")
        await self._run_checks()
