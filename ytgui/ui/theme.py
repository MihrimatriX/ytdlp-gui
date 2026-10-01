"""Colour schemes and shared style constants.

All views use Material colour *tokens* (``ft.Colors.SURFACE_CONTAINER`` …) so
switching light/dark mode or the accent colour re-themes the app instantly.
"""

import flet as ft

RADIUS_SM = 8
RADIUS = 14
RADIUS_LG = 20

SUCCESS = "#22C55E"
WARNING = "#F59E0B"
DANGER = "#EF4444"
INFO = "#3B82F6"

_DARK = dict(
    surface="#101217",
    on_surface="#ECEEF3",
    on_surface_variant="#9BA3B4",
    surface_container_lowest="#0B0C10",
    surface_container_low="#14161C",
    surface_container="#191C23",
    surface_container_high="#20242D",
    surface_container_highest="#282D38",
    outline="#3A4150",
    outline_variant="#262B35",
)

_LIGHT = dict(
    surface="#F5F6FA",
    on_surface="#141720",
    on_surface_variant="#5D6577",
    surface_container_lowest="#FFFFFF",
    surface_container_low="#FFFFFF",
    surface_container="#FFFFFF",
    surface_container_high="#EEF0F5",
    surface_container_highest="#E4E7EE",
    outline="#C5CAD6",
    outline_variant="#E3E6EE",
)


def build_theme(accent: str, dark: bool) -> ft.Theme:
    tokens = _DARK if dark else _LIGHT
    scheme = ft.ColorScheme(
        primary=accent,
        on_primary="#FFFFFF",
        error=DANGER,
        surface_tint="#00000000",
        **tokens,
    )
    return ft.Theme(
        color_scheme_seed=accent,
        color_scheme=scheme,
        use_material3=True,
        scaffold_bgcolor=tokens["surface"],
        canvas_color=tokens["surface"],
        card_bgcolor=tokens["surface_container"],
        divider_color=tokens["outline_variant"],
        visual_density=ft.VisualDensity.COMFORTABLE,
        tooltip_theme=ft.TooltipTheme(wait_duration=400),
        scrollbar_theme=ft.ScrollbarTheme(
            thickness=6,
            radius=6,
            main_axis_margin=2,
            cross_axis_margin=2,
        ),
    )


def card(content: ft.Control, padding=20, **kwargs) -> ft.Container:
    """Rounded surface with a hairline border – the basic building block."""
    return ft.Container(
        content=content,
        padding=padding,
        bgcolor=kwargs.pop("bgcolor", ft.Colors.SURFACE_CONTAINER),
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=kwargs.pop("border_radius", RADIUS),
        **kwargs,
    )


def pill(text: str, color: str = ft.Colors.ON_SURFACE_VARIANT, bgcolor=None, icon=None, size: int = 11) -> ft.Container:
    controls = []
    if icon:
        controls.append(ft.Icon(icon, size=size + 2, color=color))
    controls.append(ft.Text(text, size=size, color=color, weight=ft.FontWeight.W_600))
    return ft.Container(
        content=ft.Row(controls, spacing=4, tight=True),
        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
        border_radius=999,
        bgcolor=bgcolor or ft.Colors.with_opacity(0.12, color if color.startswith("#") else ft.Colors.ON_SURFACE),
    )


def primary_button_style(height: int = 48) -> ft.ButtonStyle:
    return ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=12),
        padding=ft.Padding.symmetric(horizontal=22, vertical=0),
        text_style=ft.TextStyle(size=15, weight=ft.FontWeight.W_600),
        icon_size=20,
    )


def subtle_button_style() -> ft.ButtonStyle:
    return ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=10),
        padding=ft.Padding.symmetric(horizontal=14, vertical=0),
    )
