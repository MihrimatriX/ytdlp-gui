"""Reusable widgets and platform helpers for the views."""

import os
import subprocess
import sys
from typing import Optional

import flet as ft

from ..formatting import format_duration
from ..i18n import t
from .theme import RADIUS_SM


def thumbnail(src: Optional[str], width: float, height: float, duration: Optional[float] = None,
              radius: int = RADIUS_SM, badge: Optional[ft.Control] = None, icon=ft.Icons.SMART_DISPLAY_ROUNDED) -> ft.Container:
    placeholder = ft.Container(
        content=ft.Icon(icon, size=min(width, height) * 0.38, color=ft.Colors.ON_SURFACE_VARIANT),
        alignment=ft.Alignment.CENTER,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        width=width,
        height=height,
    )
    layers = [
        ft.Image(src=src, width=width, height=height, fit=ft.BoxFit.COVER, error_content=placeholder,
                 gapless_playback=True) if src else placeholder
    ]
    if duration:
        layers.append(ft.Container(
            content=ft.Text(format_duration(duration), size=11, color="#FFFFFF", weight=ft.FontWeight.W_600),
            bgcolor="#CC000000",
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
            border_radius=5,
            right=6,
            bottom=6,
        ))
    if badge is not None:
        layers.append(ft.Container(content=badge, left=6, bottom=6))
    return ft.Container(
        content=ft.Stack(layers, width=width, height=height),
        width=width,
        height=height,
        border_radius=radius,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
    )


def empty_state(icon, title: str, subtitle: str = "", action: Optional[ft.Control] = None) -> ft.Container:
    items = [
        ft.Container(
            content=ft.Icon(icon, size=40, color=ft.Colors.PRIMARY),
            width=88,
            height=88,
            border_radius=44,
            alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
        ),
        ft.Text(title, size=18, weight=ft.FontWeight.W_700, text_align=ft.TextAlign.CENTER),
    ]
    if subtitle:
        items.append(ft.Text(subtitle, size=13, color=ft.Colors.ON_SURFACE_VARIANT, text_align=ft.TextAlign.CENTER))
    if action is not None:
        items.append(ft.Container(content=action, margin=ft.Margin.only(top=8)))
    return ft.Container(
        content=ft.Column(items, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10, tight=True),
        alignment=ft.Alignment.CENTER,
        expand=True,
        padding=40,
    )


def section_title(text: str, trailing: Optional[ft.Control] = None) -> ft.Row:
    controls = [ft.Text(text, size=13, weight=ft.FontWeight.W_700, color=ft.Colors.ON_SURFACE_VARIANT)]
    if trailing is not None:
        controls += [ft.Container(expand=True), trailing]
    return ft.Row(controls, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def page_header(title: str, subtitle: str = "", actions: Optional[list] = None) -> ft.Row:
    texts = [ft.Text(title, size=26, weight=ft.FontWeight.W_800)]
    if subtitle:
        texts.append(ft.Text(subtitle, size=13, color=ft.Colors.ON_SURFACE_VARIANT))
    return ft.Row(
        [ft.Column(texts, spacing=2, expand=True)] + (actions or []),
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def selectable_tile(content: ft.Control, selected: bool, on_click, disabled: bool = False,
                    padding=ft.Padding.symmetric(horizontal=14, vertical=10), tooltip: Optional[str] = None) -> ft.Container:
    return ft.Container(
        content=content,
        padding=padding,
        border_radius=12,
        border=ft.Border.all(2 if selected else 1, ft.Colors.PRIMARY if selected else ft.Colors.OUTLINE_VARIANT),
        bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.PRIMARY) if selected else ft.Colors.SURFACE_CONTAINER_LOW,
        on_click=None if disabled else on_click,
        opacity=0.4 if disabled else 1.0,
        animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
        tooltip=tooltip,
        ink=False,
    )


def _popen(args) -> None:
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000
    subprocess.Popen(args, **kwargs)


def open_path(path: str) -> bool:
    """Open a file or folder with the system's default application."""
    if not path or not os.path.exists(path):
        return False
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            _popen(["open", path])
        else:
            _popen(["xdg-open", path])
        return True
    except OSError:
        return False


def reveal_path(path: str) -> bool:
    """Show a file selected in the system file manager (falls back to its folder)."""
    if not path:
        return False
    if os.path.isdir(path):
        return open_path(path)
    if not os.path.exists(path):
        return open_path(os.path.dirname(path))
    try:
        if sys.platform == "win32":
            _popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            _popen(["open", "-R", path])
        else:
            return open_path(os.path.dirname(path))
        return True
    except OSError:
        return open_path(os.path.dirname(path))


def format_label(req) -> str:
    """Short human label for a request's format, e.g. "1080p · MP4" or "MP3 320 kbps"."""
    if req.mode == "audio":
        lossy = req.audio_format not in ("flac", "wav") and req.audio_quality != "best"
        return f"{req.audio_format.upper()} {req.audio_quality} kbps" if lossy else req.audio_format.upper()
    quality = t("best") if req.video_quality == "best" else f"{req.video_quality}p"
    return f"{quality} · {req.video_container.upper()}"
