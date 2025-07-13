import flet as ft
from ui import create_app_ui
from utils import check_yt_dlp

def main(page: ft.Page):
    page.title = "YouTube Downloader"
    page.window_min_width = 1280
    page.window_min_height = 1024
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    if not check_yt_dlp():
        page.add(ft.Text("yt-dlp is not installed. Please install it and restart the application.", size=16))
        return

    app_ui = create_app_ui(page)
    page.add(app_ui)
    page.update()

if __name__ == "__main__":
    ft.app(target=main)