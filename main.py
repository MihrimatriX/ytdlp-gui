"""
YouTube Downloader - Main Application Entry Point
A modern GUI application for downloading YouTube videos with yt-dlp
"""

import flet as ft
from ui import create_app_ui
from utils import check_yt_dlp, log_event

# Application configuration constants
APP_CONFIG = {
    "title": "YouTube Downloader",
    "window_width": 1600,
    "window_height": 1200,
    "min_width": 1400,
    "min_height": 1000,
    "theme_mode": ft.ThemeMode.LIGHT
}

def setup_window_properties(page: ft.Page) -> None:
    """Configure window properties and appearance"""
    page.title = APP_CONFIG["title"]
    
    # Window sizing configuration
    page.window_width = APP_CONFIG["window_width"]
    page.window_height = APP_CONFIG["window_height"]
    page.window_min_width = APP_CONFIG["min_width"]
    page.window_min_height = APP_CONFIG["min_height"]
    
    # Window behavior
    page.window_resizable = True
    page.window_maximizable = True
    
    # Theme and layout
    page.theme_mode = APP_CONFIG["theme_mode"]
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

def main(page: ft.Page) -> None:
    """Main application entry point"""
    # Setup window properties
    setup_window_properties(page)
    
    # Check if yt-dlp is installed
    if not check_yt_dlp():
        error_message = "yt-dlp is not installed. Please install it and restart the application."
        log_event(f"startup_error: {error_message}")
        page.add(ft.Text(error_message, size=16, color="red"))
        return
    
    # Create and add the main UI
    app_ui = create_app_ui(page)
    page.add(app_ui)
    
    # Update once after adding UI
    page.update()
    
    log_event("application_started: YouTube Downloader initialized successfully")

if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.FLET_APP)