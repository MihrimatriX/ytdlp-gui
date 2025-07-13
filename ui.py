"""
YouTube Downloader - User Interface Module
Modern Flet-based GUI for YouTube video downloading
"""

import flet as ft
from downloader import Downloader
import threading
import os
import subprocess
import sys
from utils import log_event, log_error, log_warning, get_disk_space, format_bytes
from typing import Dict, List, Optional
import queue
import uuid
from concurrent.futures import ThreadPoolExecutor
import time

# Global variables for progress tracking
progress_event_queue = queue.Queue()
download_counter = 0

# UI Configuration constants
UI_CONFIG = {
    "spacing": 15,
    "card_spacing": 10,
    "progress_height": 200,
    "video_list_height": 300,
    "thumbnail_size": {"width": 60, "height": 34},
    "colors": {
        "primary": "#4FC3F7",
        "success": "#43A047",
        "error": "#F44336",
        "warning": "#FFA726",
        "info": "#2196F3",
        "background": "#181A20",
        "border": "#333"
    }
}

def create_app_ui(page: ft.Page) -> ft.Row:
    """
    Create the main application UI
    
    Args:
        page: Flet page instance
        
    Returns:
        Main UI container
    """
    # Initialize downloader
    downloader = Downloader()
    
    # Initialize UI components
    ui_components = _initialize_ui_components(page, downloader)
    
    # Create layout sections
    main_column = _create_main_section(ui_components)
    settings_column = _create_settings_section(ui_components)
    videos_column = _create_videos_section(ui_components)
    
    # Set up event handlers
    _setup_event_handlers(ui_components, downloader, page)
    
    # Start progress monitoring
    _start_progress_monitoring(ui_components, page)
    
    return ft.Row(
        [
            ft.Column([main_column, settings_column, ui_components["download_button"]], expand=1, spacing=20),
            ft.VerticalDivider(),
            ft.Column([videos_column], expand=2),
        ],
        expand=True,
        spacing=20,
    )

def _initialize_ui_components(page: ft.Page, downloader: Downloader) -> Dict[str, ft.Control]:
    """Initialize all UI components"""
    
    # Initialize components dict first
    components = {}
    
    # Input components
    components = {
        "download_type": ft.RadioGroup(
            content=ft.Row([
                ft.Radio(value="channel", label="Channel"),
                ft.Radio(value="playlist", label="Playlist"),
                ft.Radio(value="video", label="Video"),
            ]),
            value="channel",
        ),
        "url_input": ft.TextField(
            label="YouTube URL", 
            hint_text="Enter a YouTube channel, playlist, or video URL", 
            expand=True
        ),
        "info_text": ft.Text(),
        "progress_bar": ft.ProgressBar(width=400, visible=False),
        "video_list": ft.ListView(expand=True, spacing=10, auto_scroll=True),
        
        # Quality settings
        "merge_video_audio_checkbox": ft.Checkbox(label="Merge video and audio", value=True),
        "subtitle_checkbox": ft.Checkbox(label="Download Subtitles", value=True),
        "auto_subtitle_checkbox": ft.Checkbox(label="Auto-translated subtitles", value=False),
        "embed_subtitles_checkbox": ft.Checkbox(label="Embed subtitles in video", value=False),
        
        # Language dropdowns
        "subtitle_language_dropdown": _create_language_dropdown("Subtitle Language", "tr"),
        "auto_translate_language_dropdown": _create_language_dropdown("Auto-translate to", "tr"),
        
        # Path settings
        "download_path_text": ft.TextField(label="Download Path", read_only=True, expand=True),
        "cookies_path_text": ft.TextField(
            label="Cookies File (Optional)", 
            read_only=True, 
            expand=True, 
            hint_text="Select cookies.txt file for member-only videos"
        ),
        
        # Sliders
        "concurrent_downloads_slider": ft.Slider(
            min=1, max=10, divisions=9, 
            label="{value} concurrent fragments", 
            value=4
        ),
        "concurrent_videos_slider": ft.Slider(
            min=1, max=5, divisions=4, 
            label="{value} videos at once", 
            value=2
        ),
        
        # Buttons
        "validate_button": ft.ElevatedButton("Validate"),
        "download_button": ft.ElevatedButton("Start Download", disabled=True),
        "reset_button": ft.ElevatedButton(
            "New Download", 
            bgcolor="green", 
            color="white"
        ),
        "clear_archive_button": ft.ElevatedButton(
            "Clear Archive", 
            bgcolor="orange", 
            color="white"
        ),
        "check_issues_button": ft.ElevatedButton(
            "Check Issues", 
            bgcolor="purple", 
            color="white"
        ),
        "select_path_button": ft.ElevatedButton("Select Folder"),
        "select_cookies_button": ft.ElevatedButton("Select Cookies"),
        "extract_cookies_button": ft.ElevatedButton(
            "Extract from Browser", 
            bgcolor="blue", 
            color="white"
        ),
        
        # File pickers will be added later
        
        # Progress display
        "progress_display": ft.ListView([
            ft.Text(
                "No downloads yet. Progress will appear here when you start downloading.", 
                size=12, 
                color="#666", 
                italic=True
            )
        ], spacing=5, expand=True, auto_scroll=True),
        
        # Data storage
        "validated_video_urls": [],
        "video_cards_dict": {},
    }
    
    # Add merge info text
    components["merge_info"] = ft.Text(
        "🔧 FFmpeg will be automatically applied. Required for merging.",
        size=11,
        color="blue",
        weight=ft.FontWeight.W_500
    )
    
    # File pickers (after components dict is complete)
    file_picker = ft.FilePicker(on_result=lambda e: _on_folder_selected(e, components, page))
    cookies_picker = ft.FilePicker(on_result=lambda e: _on_cookies_selected(e, components, downloader, page))
    page.overlay.extend([file_picker, cookies_picker])
    
    # Update components with file pickers
    components["file_picker"] = file_picker
    components["cookies_picker"] = cookies_picker
    
    return components

def _create_language_dropdown(label: str, default_value: str) -> ft.Dropdown:
    """Create a language selection dropdown"""
    # Base options for all dropdowns
    base_options = [
        ft.dropdown.Option("en", "English"),
        ft.dropdown.Option("tr", "Türkçe"),
        ft.dropdown.Option("es", "Español"),
        ft.dropdown.Option("fr", "Français"),
        ft.dropdown.Option("de", "Deutsch"),
        ft.dropdown.Option("it", "Italiano"),
        ft.dropdown.Option("pt", "Português"),
        ft.dropdown.Option("ru", "Русский"),
        ft.dropdown.Option("ja", "日本語"),
        ft.dropdown.Option("ko", "한국어"),
        ft.dropdown.Option("zh", "中文"),
        ft.dropdown.Option("ar", "العربية"),
        ft.dropdown.Option("hi", "हिन्दी"),
    ]
    
    # Add "All Available" option only for subtitle dropdowns
    if "Subtitle" in label:
        base_options.append(ft.dropdown.Option("all", "All Available"))
    
    return ft.Dropdown(
        label=label,
        hint_text=f"Select {label.lower()}",
        options=base_options,
        value=default_value,
        width=200
    )

def _create_main_section(components: Dict[str, ft.Control]) -> ft.Column:
    """Create the main input section"""
    return ft.Column([
        ft.Text("1. Select Download Type", size=16, weight=ft.FontWeight.BOLD),
        components["download_type"],
        ft.Text("2. Enter URL and Validate", size=16, weight=ft.FontWeight.BOLD),
        ft.Row([components["url_input"], components["validate_button"]]),
        components["info_text"],
        components["progress_bar"],
        ft.Row([
            components["reset_button"], 
            components["clear_archive_button"], 
            components["check_issues_button"]
        ], alignment=ft.MainAxisAlignment.CENTER),
    ], spacing=UI_CONFIG["spacing"])

def _create_settings_section(components: Dict[str, ft.Control]) -> ft.Column:
    """Create the settings section"""
    return ft.Column([
        ft.Text("Download Settings", size=16, weight=ft.FontWeight.BOLD),
        components["merge_video_audio_checkbox"],
        components["merge_info"],
        components["subtitle_checkbox"],
        ft.Row([components["subtitle_language_dropdown"]], alignment=ft.MainAxisAlignment.START),
        components["auto_subtitle_checkbox"],
        ft.Row([components["auto_translate_language_dropdown"]], alignment=ft.MainAxisAlignment.START),
        components["embed_subtitles_checkbox"],
        ft.Row([components["download_path_text"], components["select_path_button"]]),
        ft.Text("Authentication (for member-only videos)", size=14, weight=ft.FontWeight.BOLD),
        ft.Row([components["cookies_path_text"], components["select_cookies_button"]]),
        ft.Row([components["extract_cookies_button"]], alignment=ft.MainAxisAlignment.CENTER),
        ft.Text("Concurrent Fragments"),
        components["concurrent_downloads_slider"],
        ft.Text("Concurrent Videos"),
        components["concurrent_videos_slider"],
    ])

def _create_videos_section(components: Dict[str, ft.Control]) -> ft.Column:
    """Create the videos display section"""
    return ft.Column([
        ft.Text("3. Found Videos", size=16, weight=ft.FontWeight.BOLD),
        ft.Container(
            content=components["video_list"],
            border=ft.border.all(1, "gray"),
            border_radius=5,
            padding=10,
            expand=True,
        ),
        ft.Container(
            content=ft.Text("Download Progress", size=15, weight=ft.FontWeight.BOLD),
            margin=ft.margin.only(top=10)
        ),
        ft.Container(
            content=components["progress_display"],
            height=UI_CONFIG["progress_height"],
            expand=True,
            border=ft.border.all(1, UI_CONFIG["colors"]["border"]),
            border_radius=6,
            padding=10,
            bgcolor="#1A1A1A",
        ),
    ], expand=True)

def _on_folder_selected(e: ft.FilePickerResultEvent, components: Dict[str, ft.Control], page: ft.Page):
    """Handles the result of the folder selection dialog."""
    if e.path:
        components["download_path_text"].value = e.path
        page.update()
        log_event(f"user_action: selected_download_path, path={e.path}")

def _on_cookies_selected(e: ft.FilePickerResultEvent, components: Dict[str, ft.Control], downloader: Downloader, page: ft.Page):
    """Handles the result of the cookies file selection dialog."""
    if e.files:
        cookies_file = e.files[0].path
        components["cookies_path_text"].value = cookies_file
        downloader.set_cookies_file(cookies_file)
        page.update()
        log_event(f"user_action: selected_cookies_file, file={cookies_file}")

def extract_cookies_from_browser(components: Dict[str, ft.Control], downloader: Downloader, page: ft.Page):
    """Extract cookies from browser"""
    components["info_text"].value = "Cookies are being extracted from the browser..."
    components["info_text"].color = "blue"
    page.update()
    log_event(f"user_action: extracted_cookies_from_browser")
    
    try:
        # Run cookie extractor script
        script_path = os.path.join(os.path.dirname(__file__), "cookie_extractor.py")
        result = subprocess.run([sys.executable, script_path, "--browser", "auto"], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            # If successful, automatically select cookies file
            cookies_file = os.path.join(os.path.dirname(__file__), "youtube_cookies.txt")
            if os.path.exists(cookies_file):
                components["cookies_path_text"].value = cookies_file
                downloader.set_cookies_file(cookies_file)
                components["info_text"].value = "Cookies successfully extracted and selected!"
                components["info_text"].color = "green"
                log_event(f"user_action: cookies_extracted_and_selected, file={cookies_file}")
            else:
                components["info_text"].value = "Cookies extracted but file not found."
                components["info_text"].color = "orange"
                log_event(f"user_action: cookies_extracted_but_file_not_found, file={cookies_file}")
        else:
            components["info_text"].value = f"Cookies extraction error: {result.stderr}"
            components["info_text"].color = "red"
            log_event(f"user_action: cookies_extraction_failed, error={result.stderr}")
            
    except subprocess.TimeoutExpired:
        components["info_text"].value = "Cookies extraction timed out."
        components["info_text"].color = "red"
        log_event(f"user_action: cookies_extraction_timed_out")
    except Exception as e:
        components["info_text"].value = f"Cookies extraction error: {str(e)}"
        components["info_text"].color = "red"
        log_event(f"user_action: cookies_extraction_error, error={str(e)}")
    
    page.update()

def _setup_event_handlers(components: Dict[str, ft.Control], downloader: Downloader, page: ft.Page):
    """Set up event handlers for UI components."""
    
    # Format duration function
    def format_duration(seconds):
        """Saniyeyi saat:dakika:saniye formatına çevirir"""
        if not seconds:
            return "Unknown"
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    
    # File Picker button events
    components["select_path_button"].on_click = lambda _: components["file_picker"].get_directory_path()
    components["select_cookies_button"].on_click = lambda _: components["cookies_picker"].pick_files(allowed_extensions=["txt"], allow_multiple=False)
    components["extract_cookies_button"].on_click = lambda _: extract_cookies_from_browser(components, downloader, page)
    
    # Subtitle checkbox events for enabling/disabling dropdowns
    def on_subtitle_change(e):
        components["subtitle_language_dropdown"].disabled = not components["subtitle_checkbox"].value
        # Embed subtitles sadece altyazı indirme aktifken kullanılabilir
        if not components["subtitle_checkbox"].value and not components["auto_subtitle_checkbox"].value:
            components["embed_subtitles_checkbox"].disabled = True
        else:
            components["embed_subtitles_checkbox"].disabled = False
        page.update()
    
    def on_auto_subtitle_change(e):
        components["auto_translate_language_dropdown"].disabled = not components["auto_subtitle_checkbox"].value
        # Embed subtitles sadece altyazı indirme aktifken kullanılabilir
        if not components["subtitle_checkbox"].value and not components["auto_subtitle_checkbox"].value:
            components["embed_subtitles_checkbox"].disabled = True
        else:
            components["embed_subtitles_checkbox"].disabled = False
        page.update()
    
    components["subtitle_checkbox"].on_change = on_subtitle_change
    components["auto_subtitle_checkbox"].on_change = on_auto_subtitle_change
    
    # Başlangıçta durumları ayarla
    components["subtitle_language_dropdown"].disabled = not components["subtitle_checkbox"].value
    components["auto_translate_language_dropdown"].disabled = not components["auto_subtitle_checkbox"].value
    components["embed_subtitles_checkbox"].disabled = not (components["subtitle_checkbox"].value or components["auto_subtitle_checkbox"].value)

    # --- Download Progress Table ---
    # This section is no longer needed as progress is displayed in the ListView
    # def build_download_progress_table():
    #     return ft.DataTable(
    #         columns=[
    #             ft.DataColumn(ft.Text("Title", size=12)),
    #             ft.DataColumn(ft.Text("Ext", size=12)),
    #             ft.DataColumn(ft.Text("Size", size=12)),
    #             ft.DataColumn(ft.Text("Percent", size=12)),
    #             ft.DataColumn(ft.Text("ETA", size=12)),
    #             ft.DataColumn(ft.Text("Speed", size=12)),
    #             ft.DataColumn(ft.Text("Status", size=12)),
    #         ],
    #         rows=[
    #             ft.DataRow(
    #                 cells=[
    #                     ft.DataCell(ft.Text(row["title"], size=11, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)),
    #                     ft.DataCell(ft.Text(row["ext"], size=11)),
    #                     ft.DataCell(ft.Text(row["size"], size=11)),
    #                     ft.DataCell(ft.Text(row["percent"], size=11)),
    #                     ft.DataCell(ft.Text(row["eta"], size=11)),
    #                     ft.DataCell(ft.Text(row["speed"], size=11)),
    #                     ft.DataCell(ft.Text(row["status"], size=11)),
    #                 ]
    #             ) for row in download_progress_rows.values()
    #         ],
    #         heading_row_color="#23272F",
    #         data_row_color={"hovered": "#23272F"},
    #         border=ft.border.all(1, "#333"),
    #         border_radius=6,
    #         vertical_lines=ft.border.BorderSide(0, "transparent"),
    #         horizontal_lines=ft.border.BorderSide(0, "#23272F"),
    #         column_spacing=8,
    #         heading_row_height=28,
    #         width=820,
    #     )
    # components["download_progress_container"] = ft.Container(
    #     content=build_download_progress_table(),
    #     height=180,
    #     expand=False,
    # )
    
    # Progress tablosunu kaldır, basit progress display kullan
    # components["progress_display"] = ft.ListView([
    #     ft.Text("No downloads yet. Progress will appear here when you start downloading.", 
    #             size=12, 
    #             color="#666", 
    #             italic=True)
    # ], spacing=5, expand=True, auto_scroll=True)
    
    # --- Global video URL listesi ---
    # This section is no longer needed as video list is managed by the downloader
    # validated_video_urls = []
    # video_cards_dict = {}  # Video kartlarını takip etmek için

    def reset_application():
        """Uygulamayı yeni indirme için sıfırlar"""
        global download_counter
        
        # URL input'u temizle
        components["url_input"].value = ""
        
        # Info text'i sıfırla
        components["info_text"].value = "Application reset. Ready for new download."
        components["info_text"].color = "green"
        
        # Progress bar'ı gizle
        components["progress_bar"].visible = False
        components["progress_bar"].value = 0
        
        # Video listesini temizle
        components["video_list"].controls.clear()
        
        # Progress display'i temizle
        components["progress_display"].controls.clear()
        components["progress_display"].controls.append(
            ft.Text("No downloads yet. Progress will appear here when you start downloading.", 
                    size=12, 
                    color="#666", 
                    italic=True)
        )
        
        # Local değişkenleri sıfırla
        components["validated_video_urls"].clear()
        components["video_cards_dict"].clear()
        download_counter = 0
        
        # Butonları aktif et
        components["validate_button"].disabled = False
        components["download_button"].disabled = True
        
        # Progress event queue'yu temizle
        while not progress_event_queue.empty():
            try:
                progress_event_queue.get_nowait()
            except queue.Empty:
                break
        
        page.update()
        log_event("user_action: application_reset")

    # --- Event Fonksiyonları ---
    def validate_url_click(e):
        url = components["url_input"].value
        if not url:
            components["info_text"].value = "Please enter a URL."
            components["info_text"].color = "red"
            page.update()
            log_event(f"user_action: validate_url_clicked, url={url}")
            return
        components["info_text"].value = "Validating URL, please wait..."
        components["info_text"].color = None
        components["progress_bar"].visible = True
        components["video_list"].controls.clear()
        components["validate_button"].disabled = True
        components["download_button"].disabled = True
        page.update()
        log_event(f"user_action: validate_url_clicked, url={url}")
        threading.Thread(target=validate_url_thread, args=(url,)).start()

    def validate_url_thread(url):
        videos, error = downloader.get_video_info(url)
        page.run_thread(lambda: update_ui_after_validation(videos, error))

    def update_ui_after_validation(videos, error):
        components["progress_bar"].visible = False
        components["validate_button"].disabled = False
        components["validated_video_urls"].clear()
        components["video_cards_dict"].clear()  # Video kartları sözlüğünü temizle
        if error:
            if "fragment 1 not found" in error or "unable to continue" in error:
                components["info_text"].value = (
                    "Error: Video format not available or fragments missing. "
                    "Try a lower quality (e.g., 'Best Available') or different format."
                )
                components["info_text"].color = "red"
                page.update()
                log_event(f"download_error: validation_failed, error={error}")
                return
            components["info_text"].value = f"Error: {error.strip().splitlines()[-1]}"
            components["info_text"].color = "red"
            page.update()
            log_event(f"download_error: validation_failed, error={error}")
            return
        if not videos:
            components["info_text"].value = "No videos found at this URL."
            page.update()
            log_event(f"download_info: no_videos_found, url={components['url_input'].value}")
            return
        components["info_text"].value = f"Found {len(videos)} videos. Ready to download."
        components["download_button"].disabled = False
        components["video_list"].controls.clear()
        for video in videos:
            # Her video için URL'yi topla
            video_url = None
            if 'webpage_url' in video:
                video_url = video['webpage_url']
                components["validated_video_urls"].append(video_url)
            elif 'url' in video:
                video_url = video['url']
                components["validated_video_urls"].append(video_url)
            thumbnail_url = video.get('thumbnail')
            title = video.get('title', 'No Title')
            duration = video.get('duration', 0)
            duration_str = format_duration(duration) if duration else "Unknown"
            formats = video.get('formats', [])
            best_quality = "-"
            best_format = None
            file_size = "-"
            vcodec = "-"
            acodec = "-"
            ext = "-"
            def safe_val(val):
                return val if val and val not in ["Unknown", "none"] else "-"
            if formats:
                video_formats = [f for f in formats if f.get('vcodec') != 'none' and f.get('height')]
                if video_formats:
                    best_format = max(video_formats, key=lambda x: (x.get('height', 0), x.get('fps', 0), x.get('tbr', 0)))
                    best_quality = f"{safe_val(best_format.get('height', '-'))}p"
                    filesize = best_format.get('filesize', 0) or best_format.get('filesize_approx', 0)
                    if filesize:
                        file_size = f"{round(filesize/1024/1024, 2)} MB"
                    vcodec = safe_val(best_format.get('vcodec', '-'))
                    acodec = safe_val(best_format.get('acodec', '-'))
                    ext = safe_val(best_format.get('ext', '-'))
            # Kompakt video kartı UI
            video_card = ft.Card(
                content=ft.Container(
                    bgcolor="#181A20",
                    border_radius=6,
                    padding=6,
                    content=ft.Row([
                            # Thumbnail - daha küçük
                            ft.Container(
                                content=ft.Image(
                                    src=thumbnail_url, 
                                width=60,
                                height=34,
                                    fit="cover", 
                                    border_radius=3
                                ) if thumbnail_url else ft.Container(
                                width=60,
                                height=34,
                                bgcolor="#23272F",
                                border_radius=3,
                                alignment=ft.alignment.center,
                                content=ft.Text("📹", size=14)
                                ),
                                margin=ft.margin.only(right=8)
                            ),
                        # Video info - daha kompakt
                            ft.Column([
                                ft.Text(
                                    title, 
                                size=12,
                                weight=ft.FontWeight.W_600,
                                    max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                color="#F1F1F1"
                                ),
                            ft.Row([
                                ft.Text(duration_str, size=10, color="#A0A0A0"),
                                ft.Text("|", size=10, color="#444"),
                                ft.Text(best_quality, size=10, color="#4FC3F7"),
                                ft.Text("|", size=10, color="#444"),
                                ft.Text(ext, size=10, color="#BA68C8"),
                                ft.Text("|", size=10, color="#444"),
                                ft.Text(file_size, size=10, color="#26A69A"),
                            ], spacing=3),
                            ft.Container(
                                content=ft.Text("Ready", size=9, color="#43A047", weight=ft.FontWeight.W_500),
                                bgcolor="#263238",
                                border_radius=3,
                                padding=ft.padding.symmetric(horizontal=4, vertical=1),
                                margin=ft.margin.only(top=1)
                            )
                            ], expand=True, alignment=ft.MainAxisAlignment.START, spacing=2),
                        # Download checkbox - daha küçük
                        ft.Container(
                            content=ft.Checkbox(label="", value=True, scale=0.7),
                            alignment=ft.alignment.center_right,
                            expand=False,
                            margin=ft.margin.only(left=6)
                        ),
                        ], expand=True),
                ),
                margin=ft.margin.only(bottom=4)
            )
            components["video_list"].controls.append(video_card)
            components["video_cards_dict"][video_url] = video_card # Kartı sözlüğe ekle
        
        page.update()
        log_event(f"download_info: validation_successful, url={components['url_input'].value}, num_videos={len(videos)}")

    def start_download_click(e):
        url = components["url_input"].value
        if not url:
            components["info_text"].value = "Please enter a URL to download."
            components["info_text"].color = "red"
            page.update()
            log_event(f"user_action: start_download_clicked, url={url}")
            return
        download_path = components["download_path_text"].value
        if not download_path:
            components["info_text"].value = "Please select a download path."
            components["info_text"].color = "red"
            page.update()
            log_event(f"user_action: start_download_clicked, url={url}, download_path={download_path}")
            return
            
        # Archive dosyası kontrolü
        archive_path = downloader.archive_path
        if os.path.exists(archive_path):
            with open(archive_path, 'r', encoding='utf-8') as f:
                archive_content = f.read()
                if archive_content.strip():
                    components["info_text"].value = "⚠️ Archive file exists! Some videos might be skipped. Use 'Clear Archive' if needed."
                    components["info_text"].color = "orange"
                    page.update()
                    log_event("download_warning: archive_file_exists")
        
        components["info_text"].value = "Starting download..."
        components["info_text"].color = "blue"
        components["download_button"].disabled = True
        components["validate_button"].disabled = True
        components["progress_bar"].visible = True
        
        # Progress display'i temizle ve başlangıç mesajı ekle
        components["progress_display"].controls.clear()
        components["progress_display"].controls.append(
            ft.Text("Preparing downloads...", size=12, color="#4FC3F7", italic=True)
        )
        
        # Her video için ayrı thread başlat - ThreadPoolExecutor ile kontrollü
        urls_to_download = components["validated_video_urls"] if components["validated_video_urls"] else [url]
        
        # İndirme bilgisi ekle
        total_videos = len(urls_to_download)
        max_concurrent = int(components["concurrent_videos_slider"].value)
        components["progress_display"].controls.append(
            ft.Text(f"📊 Total videos: {total_videos} | Max concurrent: {max_concurrent}", 
                   size=11, color="#FFA726", italic=True)
        )
        page.update()
        
        log_event(f"user_action: start_download_clicked, url={url}, download_path={download_path}")
        download_options = {
            "quality": "bestvideo+bestaudio/best",
            "merge_video_audio": components["merge_video_audio_checkbox"].value,
            "download_subtitles": components["subtitle_checkbox"].value,
            "subtitle_language": components["subtitle_language_dropdown"].value,
            "auto_subtitles": components["auto_subtitle_checkbox"].value,
            "auto_translate_language": components["auto_translate_language_dropdown"].value,
            "embed_subtitles": components["embed_subtitles_checkbox"].value,
            "concurrent_fragments": int(components["concurrent_downloads_slider"].value),
        }
        
        # Aynı anda indirme sayısını al
        max_concurrent_videos = int(components["concurrent_videos_slider"].value)
        
        def start_concurrent_downloads():
            with ThreadPoolExecutor(max_workers=max_concurrent_videos) as executor:
                futures = []
                for video_url in urls_to_download:
                    future = executor.submit(download_single_video_wrapper, video_url, download_options.copy(), download_path)
                    futures.append(future)
                    time.sleep(0.5)  # Videolar arasında kısa bekleme
                
                # Tüm indirmelerin tamamlanmasını bekle
                for future in futures:
                    try:
                        future.result()
                    except Exception as e:
                        log_event(f"Download thread error: {e}")
        
        # Concurrent downloads'ı ayrı thread'de başlat
        threading.Thread(target=start_concurrent_downloads, daemon=True).start()

    def download_single_video_wrapper(video_url, download_options, download_path):
        """ThreadPoolExecutor için wrapper fonksiyon"""
        global download_counter
        download_counter += 1
        thread_id = f"download_{download_counter}"
        download_options["thread_id"] = thread_id
        download_options["video_url"] = video_url  # URL'yi de ekle
        
        print(f"[DEBUG] Starting download wrapper for: {video_url}")
        log_event(f"download_wrapper_start: thread_id={thread_id}, url={video_url}")
        
        try:
            for update in downloader.download_videos([video_url], download_options, download_path):
                update["video_url"] = video_url  # Her update'e URL ekle
                print(f"[DEBUG] Wrapper sending update: {update}")
                progress_event_queue.put(update)
            print(f"[DEBUG] Download wrapper completed for: {video_url}")
            log_event(f"download_wrapper_end: thread_id={thread_id}, url={video_url}")
        except Exception as e:
            print(f"[DEBUG] Download wrapper error for {video_url}: {e}")
            log_event(f"download_wrapper_error: thread_id={thread_id}, url={video_url}, error={e}")
            # Hata durumunda error eventi gönder
            error_update = {
                "type": "error",
                "message": str(e),
                "thread_id": thread_id,
                "video_url": video_url,
                "title": "Unknown"
            }
            progress_event_queue.put(error_update)

    # Progress polling is handled by _start_progress_monitoring function
    # No need for duplicate polling here

    # Note: update_video_card_status is now defined outside this function

    # Note: update_ui_during_download is now defined outside this function

    # Button event handlers
    components["validate_button"].on_click = validate_url_click
    components["download_button"].on_click = start_download_click
    components["reset_button"].on_click = lambda _: reset_application()
    components["clear_archive_button"].on_click = lambda _: clear_download_archive()
    components["check_issues_button"].on_click = lambda _: check_download_issues()
    
    # Additional utility functions
    def clear_download_archive():
        """Clear download archive file"""
        try:
            archive_path = downloader.archive_path
            if os.path.exists(archive_path):
                os.remove(archive_path)
                components["info_text"].value = "Download archive cleared! Previously downloaded videos will be downloaded again."
                components["info_text"].color = "green"
                log_event("user_action: download_archive_cleared")
            else:
                components["info_text"].value = "No archive file found."
                components["info_text"].color = "orange"
                log_event("user_action: no_archive_file_found")
            page.update()
        except Exception as e:
            components["info_text"].value = f"Error clearing archive: {e}"
            components["info_text"].color = "red"
            log_event(f"user_action: archive_clear_error, error={e}")
            page.update()
    
    def check_download_issues():
        """Check for download issues and system status"""
        from utils import check_yt_dlp, check_ffmpeg, get_disk_space
        
        issues = []
        
        # 1. Check yt-dlp version
        try:
            result = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                version = result.stdout.strip()
                issues.append(f"✅ yt-dlp version: {version}")
            else:
                issues.append("❌ yt-dlp not working properly")
        except Exception as e:
            issues.append(f"❌ yt-dlp error: {e}")
        
        # 2. Check internet connection
        try:
            result = subprocess.run(["ping", "youtube.com", "-n", "1"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                issues.append("✅ Internet connection: OK")
            else:
                issues.append("❌ Internet connection: Failed")
        except Exception:
            issues.append("❌ Internet connection: Cannot test")
        
        # 3. Check disk space
        download_path = components["download_path_text"].value or "."
        disk_info = get_disk_space(download_path)
        if disk_info:
            free_gb = disk_info["free"]
            if free_gb > 1:
                issues.append(f"✅ Disk space: {free_gb:.1f} GB available")
            else:
                issues.append(f"⚠️ Disk space: Only {free_gb:.1f} GB available")
        else:
            issues.append("❌ Disk space check failed")
        
        # 4. Check FFmpeg
        if downloader.check_ffmpeg():
            issues.append("✅ FFmpeg: Available")
        else:
            issues.append("❌ FFmpeg: Not available (video merging may fail)")
        
        # 5. Check cookies
        if downloader.cookies_file and os.path.exists(downloader.cookies_file):
            issues.append("✅ Cookies: Available")
        else:
            issues.append("⚠️ Cookies: Not set (member-only videos may fail)")
        
        # 6. Check archive file
        if os.path.exists(downloader.archive_path):
            with open(downloader.archive_path, 'r', encoding='utf-8') as f:
                archive_lines = len(f.readlines())
            issues.append(f"⚠️ Archive: {archive_lines} videos already downloaded")
        else:
            issues.append("✅ Archive: Clean")
        
        # 7. Check log file for recent errors
        try:
            if os.path.exists("app_log.txt"):
                with open("app_log.txt", 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    recent_errors = [line for line in lines[-50:] if "DETAILED_ERROR" in line]
                    if recent_errors:
                        issues.append(f"❌ Recent errors: {len(recent_errors)} found in log")
                        last_error = recent_errors[-1].strip()
                        issues.append(f"   Last error: {last_error[-100:]}")
                    else:
                        issues.append("✅ No recent errors in log")
            else:
                issues.append("⚠️ No log file found")
        except Exception as e:
            issues.append(f"❌ Log check failed: {e}")
        
        # Display results
        components["info_text"].value = "\n".join(issues)
        components["info_text"].color = "blue"
        page.update()
        log_event("user_action: download_issues_checked")

    # --- Layout ---
    # settings_column = ft.Column([
    #     ft.Text("Download Settings", size=16, weight=ft.FontWeight.BOLD),
    #     merge_video_audio_checkbox,
    #     merge_info,
    #     subtitle_checkbox,
    #     ft.Row([subtitle_language_dropdown], alignment=ft.MainAxisAlignment.START),
    #     auto_subtitle_checkbox,
    #     ft.Row([auto_translate_language_dropdown], alignment=ft.MainAxisAlignment.START),
    #     embed_subtitles_checkbox,
    #     ft.Row([download_path_text, select_path_button]),
    #     ft.Text("Authentication (for member-only videos)", size=14, weight=ft.FontWeight.BOLD),
    #     ft.Row([cookies_path_text, select_cookies_button]),
    #     ft.Row([extract_cookies_button], alignment=ft.MainAxisAlignment.CENTER),
    #     ft.Text("Concurrent Fragments"),
    #     concurrent_downloads_slider,
    #     ft.Text("Concurrent Videos"),
    #     concurrent_videos_slider,
    # ])

    # main_column = ft.Column(
    #     [
    #         ft.Text("1. Select Download Type", size=16, weight=ft.FontWeight.BOLD),
    #         download_type,
    #         ft.Text("2. Enter URL and Validate", size=16, weight=ft.FontWeight.BOLD),
    #         ft.Row([url_input, validate_button]),
    #         info_text,
    #         progress_bar,
    #         ft.Row([reset_button, clear_archive_button, check_issues_button], alignment=ft.MainAxisAlignment.CENTER),
    #     ],
    #     spacing=15
    # )

    # videos_column = ft.Column([
    #     ft.Text("3. Found Videos", size=16, weight=ft.FontWeight.BOLD),
    #     ft.Container(
    #         content=video_list,
    #         border=ft.border.all(1, "gray"),
    #         border_radius=5,
    #         padding=10,
    #         expand=True,
    #     ),
    #     ft.Container(
    #         content=ft.Text("Download Progress", size=15, weight=ft.FontWeight.BOLD),
    #         margin=ft.margin.only(top=10)
    #     ),
    #     ft.Container(
    #         content=progress_display,
    #         height=200,
    #         expand=True,
    #         border=ft.border.all(1, "#333"),
    #         border_radius=6,
    #         padding=10,
    #         bgcolor="#1A1A1A",
    #     ),
    # ], expand=True)

def _start_progress_monitoring(components: Dict[str, ft.Control], page: ft.Page) -> None:
    """Start progress monitoring thread for download updates"""
    def poll_progress_events():
        while True:
            try:
                update = progress_event_queue.get(timeout=1.0)  # Longer timeout
                # Use lambda to capture update correctly
                def update_ui():
                    update_ui_during_download(update, components, page)
                
                # Schedule UI update on main thread
                page.run_thread(update_ui)
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[ERROR] Progress polling error: {e}")
                continue
    
    # Start polling thread
    thread = threading.Thread(target=poll_progress_events, daemon=True)
    thread.start()

def update_ui_during_download(update: Dict[str, any], components: Dict[str, ft.Control], page: ft.Page) -> None:
    """Update UI during download process"""
    print("[DEBUG] Progress event:", update)
    event_type = update.get("type", "unknown")
    thread_id = update.get("thread_id", "unknown")
    video_url = update.get("video_url", "unknown")
    
    print(f"[DEBUG] Processing event: type={event_type}, thread={thread_id}, url={video_url}")
    
    # Update progress display based on event type
    if event_type == "progress":
        # Handle progress updates
        title = update.get('title', 'Unknown')
        percent = update.get('percent', 0)
        speed = update.get('speed', 'Unknown')
        eta = update.get('eta', 'Unknown')
        total_size = update.get('total_size', 'Unknown')
        ext = update.get('ext', 'Unknown')
        
        print(f"[DEBUG] Progress: {title} - {percent}% - {speed}")
        
        progress_text_line = ft.Text(
            f"📥 {title} ({ext}) - {percent:.1f}% of {total_size} at {speed} | ETA: {eta}",
            size=12,
            color=UI_CONFIG["colors"]["primary"]
        )
        
        # Update or add progress line
        thread_id = update.get('thread_id', 'unknown')
        found = False
        for i, control in enumerate(components["progress_display"].controls):
            if hasattr(control, 'data') and control.data == thread_id:
                components["progress_display"].controls[i] = progress_text_line
                progress_text_line.data = thread_id
                found = True
                break
        
        if not found:
            progress_text_line.data = thread_id
            components["progress_display"].controls.append(progress_text_line)
        
        # Update main progress bar
        components["progress_bar"].value = percent / 100
        components["info_text"].value = f"Downloading: {title} - {percent:.1f}% of {total_size} at {speed}"
        components["info_text"].color = None
        
    elif event_type == "complete":
        print(f"[DEBUG] COMPLETE event received for: {video_url}")
        
        thread_id = update.get('thread_id', 'unknown')
        title = update.get('title', 'Unknown')
        video_url = update.get('video_url')
        
        print(f"[DEBUG] Marking as completed: title={title}, url={video_url}")
        
        completed_text = ft.Text(
            f"✅ {title} - Download completed successfully!",
            size=12,
            color=UI_CONFIG["colors"]["success"]
        )
        
        for i, control in enumerate(components["progress_display"].controls):
            if hasattr(control, 'data') and control.data == thread_id:
                components["progress_display"].controls[i] = completed_text
                completed_text.data = thread_id
                break
        
        # Update video card status
        if video_url:
            print(f"[DEBUG] About to update card status for: {video_url}")
            update_video_card_status(video_url, "completed", components)
        
        # Check if all downloads are complete
        all_completed = all(
            "✅" in control.value or "❌" in control.value 
            for control in components["progress_display"].controls 
            if hasattr(control, 'value')
        )
        
        if all_completed:
            components["info_text"].value = "All downloads completed! Videos have been saved to the selected folder. Use 'New Download' for next download."
            components["info_text"].color = UI_CONFIG["colors"]["success"]
            components["download_button"].disabled = False
            components["validate_button"].disabled = False
            components["progress_bar"].visible = False
            
    elif event_type == "error":
        print(f"[DEBUG] ERROR event received for: {video_url}")
        
        thread_id = update.get('thread_id', 'unknown')
        title = update.get('title', 'Unknown')
        video_url = update.get('video_url')
        error_message = update.get('message', 'Unknown error')
        
        # Show error in progress display
        error_text = ft.Text(
            f"❌ {title} - Error: {error_message[:100]}...",
            size=12,
            color=UI_CONFIG["colors"]["error"]
        )
        
        for i, control in enumerate(components["progress_display"].controls):
            if hasattr(control, 'data') and control.data == thread_id:
                components["progress_display"].controls[i] = error_text
                error_text.data = thread_id
                break
        
        # Update video card status
        if video_url:
            update_video_card_status(video_url, "error", components)
        
        # Show error in main info text
        components["info_text"].value = f"Download Error: {error_message}"
        components["info_text"].color = UI_CONFIG["colors"]["error"]
        
        # Log detailed error
        log_event(f"DETAILED_ERROR: thread={thread_id}, url={video_url}, error={error_message}")
    
    elif event_type == "status":
        print(f"[DEBUG] STATUS event: {update.get('message', '')}")
    
    elif event_type == "log":
        # Handle FFmpeg messages
        message = update.get("message", "")
        if "FFmpeg is being downloaded" in message:
            components["info_text"].value = "FFmpeg is being downloaded, please wait..."
            components["info_text"].color = UI_CONFIG["colors"]["info"]
        elif "FFmpeg" in message and "successfully" in message:
            components["info_text"].value = "FFmpeg installation successful!"
            components["info_text"].color = UI_CONFIG["colors"]["success"]
    
    # Update UI once at the end
    try:
        page.update()
    except Exception as e:
        print(f"[ERROR] Page update error: {e}")
        log_error(f"UI update failed: {e}")

def update_video_card_status(video_url: str, status: str, components: Dict[str, ft.Control]) -> None:
    """Update video card visual status"""
    print(f"[DEBUG] Updating video card status: {video_url} -> {status}")
    log_event(f"card_update: url={video_url}, status={status}")
    
    if video_url in components["video_cards_dict"]:
        card = components["video_cards_dict"][video_url]
        container = card.content
        
        if status == "completed":
            container.bgcolor = "#1B4332"  # Dark green
            container.border = ft.border.all(2, "#40916C")  # Green border
            print(f"[DEBUG] Card colored GREEN for: {video_url}")
        elif status == "error":
            container.bgcolor = "#4A1A1A"  # Dark red
            container.border = ft.border.all(2, "#DC2626")  # Red border
            print(f"[DEBUG] Card colored RED for: {video_url}")
        
        try:
            # Note: page.update() should be called by the caller
            pass
        except Exception as e:
            print(f"[ERROR] Card update error: {e}")
    else:
        print(f"[DEBUG] Video URL not found in cards dict: {video_url}")
        print(f"[DEBUG] Available URLs in dict: {list(components['video_cards_dict'].keys())}")

def main(page: ft.Page):
    app_ui = create_app_ui(page)
    page.add(app_ui)
    page.update()

if __name__ == "__main__":
    ft.app(target=main)
