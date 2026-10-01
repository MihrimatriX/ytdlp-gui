"""
YouTube Downloader - application entry point.

Run with ``python main.py``. Set ``YTDLP_GUI_WEB=1`` to serve the UI in a
browser instead of a desktop window (handy for development).
"""

import os

import flet as ft

from ytgui.logs import get_logger
from ytgui.ui.app import App

log = get_logger("ytgui.main")


def main(page: ft.Page) -> None:
    App(page).start()
    log.info("Application started")


if __name__ == "__main__":
    if os.environ.get("YTDLP_GUI_WEB"):
        ft.run(main, view=ft.AppView.WEB_BROWSER, port=int(os.environ.get("YTDLP_GUI_PORT", "8550")), no_cdn=True)
    else:
        ft.run(main)
