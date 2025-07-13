"""
YouTube Downloader - Core Download Module
Handles video downloading using yt-dlp with FFmpeg integration
"""

import subprocess
import json
import re
import os
import zipfile
import urllib.request
import platform
from typing import Dict, List, Optional, Tuple, Iterator, Any
from utils import log_event, log_error, log_warning, ensure_directory_exists, format_bytes

class Downloader:
    """Main downloader class for YouTube videos using yt-dlp"""
    
    # Regex patterns for parsing yt-dlp output
    PROGRESS_PATTERN = re.compile(
        r'(\d+\.\d+)%.*?of\s+(\S+).*?at\s+(\S+)(?:.*?ETA\s+(\S+))?'
    )
    TITLE_PATTERN = re.compile(r'\[info\]\s+(.+?):')
    DESTINATION_PATTERN = re.compile(r'\[download\] Destination:\s+(.+)')
    YOUTUBE_ID_PATTERN = re.compile(r'\[youtube\]\s+(.+?):\s+Downloading webpage')
    
    def __init__(self, archive_path: str = "archive.txt", cookies_file: Optional[str] = None):
        """
        Initialize the downloader
        
        Args:
            archive_path: Path to the download archive file
            cookies_file: Path to cookies file for authentication
        """
        self.archive_path = archive_path
        self.cookies_file = cookies_file
        self.ffmpeg_path: Optional[str] = None
        self.setup_ffmpeg()
        
        log_event(f"Downloader initialized: archive={archive_path}, cookies={bool(cookies_file)}")

    def setup_ffmpeg(self) -> None:
        """Set up FFmpeg for video/audio merging"""
        ffmpeg_dir = os.path.join(os.path.dirname(__file__), "ffmpeg")
        ensure_directory_exists(ffmpeg_dir)
        
        # Determine FFmpeg executable name based on platform
        if platform.system() == "Windows":
            self.ffmpeg_path = os.path.join(ffmpeg_dir, "ffmpeg.exe")
        else:
            self.ffmpeg_path = os.path.join(ffmpeg_dir, "ffmpeg")
        
        # Download FFmpeg if not available
        if not os.path.exists(self.ffmpeg_path):
            self._download_ffmpeg(ffmpeg_dir)
        
        log_event(f"FFmpeg setup complete: {self.ffmpeg_path}")

    def _download_ffmpeg(self, ffmpeg_dir: str) -> None:
        """
        Download and install FFmpeg
        
        Args:
            ffmpeg_dir: Directory to install FFmpeg
        """
        try:
            log_event("Starting FFmpeg download...")
            
            if platform.system() == "Windows":
                self._download_ffmpeg_windows(ffmpeg_dir)
            else:
                self._setup_ffmpeg_unix()
                
        except Exception as e:
            log_error(f"FFmpeg download failed: {str(e)}")
            self.ffmpeg_path = "ffmpeg"  # Fallback to system PATH

    def _download_ffmpeg_windows(self, ffmpeg_dir: str) -> None:
        """Download FFmpeg for Windows"""
        ffmpeg_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        zip_path = os.path.join(ffmpeg_dir, "ffmpeg.zip")
        
        # Download ZIP file
        urllib.request.urlretrieve(ffmpeg_url, zip_path)
        
        # Extract ZIP file
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(ffmpeg_dir)
        
        # Clean up ZIP file
        os.remove(zip_path)
        
        # Move executable to correct location
        extracted_dir = self._find_extracted_ffmpeg_dir(ffmpeg_dir)
        if extracted_dir:
            self._move_ffmpeg_executable(extracted_dir)
        
        log_event("FFmpeg downloaded and installed successfully for Windows")

    def _find_extracted_ffmpeg_dir(self, ffmpeg_dir: str) -> Optional[str]:
        """Find the extracted FFmpeg directory"""
        for item in os.listdir(ffmpeg_dir):
            item_path = os.path.join(ffmpeg_dir, item)
            if os.path.isdir(item_path) and item.startswith("ffmpeg"):
                return item_path
        return None

    def _move_ffmpeg_executable(self, extracted_dir: str) -> None:
        """Move FFmpeg executable to the correct location"""
        import shutil
        bin_dir = os.path.join(extracted_dir, "bin")
        if os.path.exists(bin_dir):
            shutil.copy2(os.path.join(bin_dir, "ffmpeg.exe"), self.ffmpeg_path)
            shutil.rmtree(extracted_dir)

    def _check_system_ffmpeg(self) -> bool:
        """Check if system FFmpeg is available"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False

    def _setup_ffmpeg_unix(self) -> None:
        """Set up FFmpeg for Unix-like systems"""
        # Try to find system FFmpeg first
        if self._check_system_ffmpeg():
            log_event("Using system FFmpeg installation")
            self.ffmpeg_path = "ffmpeg"  # Use system PATH
        else:
            log_warning("Linux/Mac: Please install FFmpeg using 'sudo apt install ffmpeg' or 'brew install ffmpeg'")
            self.ffmpeg_path = "ffmpeg"  # Use system PATH anyway, will fail gracefully

    def check_ffmpeg(self) -> bool:
        """
        Check if FFmpeg is available and working
        
        Returns:
            bool: True if FFmpeg is available
        """
        try:
            # Check application-specific FFmpeg first
            if self.ffmpeg_path and os.path.exists(self.ffmpeg_path):
                result = subprocess.run(
                    [self.ffmpeg_path, "-version"], 
                    capture_output=True, 
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    log_event("FFmpeg available (application-specific)")
                    return True
            
            # Fallback to system FFmpeg
            result = subprocess.run(
                ["ffmpeg", "-version"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                log_event("FFmpeg available (system)")
                self.ffmpeg_path = "ffmpeg"
                return True
                
            log_warning("FFmpeg not available - video merging will not work")
            return False
            
        except Exception as e:
            log_error(f"FFmpeg check failed: {e}")
            return False

    def get_video_info(self, url: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        Get video information from URL
        
        Args:
            url: YouTube URL
            
        Returns:
            Tuple of (video_list, error_message)
        """
        log_event(f"Getting video info for URL: {url}")
        
        try:
            # Handle playlist URLs specially
            if self._is_playlist_url(url):
                return self._get_playlist_info(url)
            else:
                return self._get_video_info_flat(url)
                
        except Exception as e:
            log_error(f"Failed to get video info: {e}")
            return None, str(e)

    def _is_playlist_url(self, url: str) -> bool:
        """Check if URL is a playlist URL"""
        return "playlist" in url or "list=" in url

    def _get_playlist_info(self, url: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """Get playlist information using dump-single-json"""
        command = self._build_base_command(["--dump-single-json"])
        command.append(url)
        
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        
        if result.returncode != 0:
            log_error(f"Playlist info failed: {result.stderr}")
            return None, result.stderr
            
        try:
            data = json.loads(result.stdout)
            if data.get("_type") == "playlist" and "entries" in data:
                videos = [entry for entry in data["entries"] if entry]
                log_event(f"Found {len(videos)} videos in playlist")
                return videos, None
        except json.JSONDecodeError as e:
            log_error(f"JSON parsing failed: {e}")
            return None, str(e)
            
        return None, "No playlist data found"

    def _get_video_info_flat(self, url: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """Get video information using flat-playlist approach"""
        command = self._build_base_command(["--flat-playlist", "--dump-json"])
        command.append(url)
        
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        
        if result.returncode != 0:
            log_error(f"Video info failed: {result.stderr}")
            return None, result.stderr
            
        videos = []
        playlist_video_ids = []
        is_playlist = False
        
        # Parse JSON output line by line
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
                
            try:
                data = json.loads(line)
                
                if self._is_playlist_data(data):
                    is_playlist = True
                    playlist_video_ids.extend(self._extract_video_ids(data))
                else:
                    videos.append(data)
                    
            except json.JSONDecodeError:
                continue
        
        # Get detailed info for playlist videos
        if is_playlist and playlist_video_ids:
            detailed_videos = self._get_detailed_video_info(playlist_video_ids)
            log_event(f"Found {len(detailed_videos)} videos in playlist")
            return detailed_videos, None
        
        log_event(f"Found {len(videos)} videos")
        return videos, None

    def _is_playlist_data(self, data: Dict) -> bool:
        """Check if JSON data represents playlist information"""
        return (data.get('_type') == 'playlist' or 
                data.get('ie_key') == 'YoutubePlaylist' or
                data.get('_type') == 'url')

    def _extract_video_ids(self, data: Dict) -> List[str]:
        """Extract video IDs from playlist data"""
        video_ids = []
        
        if 'entries' in data:
            for entry in data['entries']:
                if isinstance(entry, dict) and 'id' in entry:
                    video_ids.append(entry['id'])
                elif isinstance(entry, str):
                    video_ids.append(entry)
        elif 'id' in data:
            video_ids.append(data['id'])
            
        return video_ids

    def _get_detailed_video_info(self, video_ids: List[str]) -> List[Dict]:
        """Get detailed information for a list of video IDs"""
        detailed_videos = []
        
        for vid_id in video_ids:
            vid_url = f"https://www.youtube.com/watch?v={vid_id}"
            command = self._build_base_command(["--dump-json"])
            command.append(vid_url)
            
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
            
            if result.returncode == 0:
                try:
                    detailed_videos.append(json.loads(result.stdout.strip()))
                except json.JSONDecodeError:
                    continue
                    
        return detailed_videos

    def _build_base_command(self, base_args: List[str]) -> List[str]:
        """Build base yt-dlp command with common arguments"""
        command = ["yt-dlp"] + base_args
        
        # Add cookies if available
        if self.cookies_file and os.path.exists(self.cookies_file):
            command.extend(["--cookies", self.cookies_file])
            
        # Add FFmpeg location if available
        if self.ffmpeg_path and os.path.exists(self.ffmpeg_path):
            command.extend(["--ffmpeg-location", os.path.dirname(self.ffmpeg_path)])
            
        return command

    def download_videos(self, urls: List[str], download_options: Dict[str, Any], 
                       output_path: str) -> Iterator[Dict[str, Any]]:
        """
        Download videos with progress tracking
        
        Args:
            urls: List of video URLs
            download_options: Download configuration
            output_path: Output directory
            
        Yields:
            Progress updates as dictionaries
        """
        thread_id = download_options.get("thread_id", "unknown")
        log_event(f"Starting download: urls={len(urls)}, thread_id={thread_id}")
        
        base_command = self._build_download_command(download_options, output_path)
        
        for url in urls:
            log_event(f"Downloading: {url}")
            command = base_command + [url]
            
            yield {"type": "status", "message": f"Starting download for: {url}"}
            
            for progress_update in self._run_yt_dlp_command(command, thread_id):
                yield progress_update
                
            log_event(f"Download completed: {url}")

    def _build_download_command(self, download_options: Dict[str, Any], 
                               output_path: str) -> List[str]:
        """Build the complete yt-dlp download command"""
        command = self._build_base_command([])
        
        # Output path configuration
        if output_path:
            command.extend(["-o", f"{output_path}/%(playlist)s/%(title)s.%(ext)s"])
        else:
            command.extend(["-o", "%(playlist)s/%(title)s.%(ext)s"])
        
        # Quality and format selection
        self._add_quality_options(command, download_options)
        
        # Subtitle options
        self._add_subtitle_options(command, download_options)
        
        # Performance options
        concurrent_fragments = int(download_options.get("concurrent_fragments", 5))
        command.extend(["--concurrent-fragments", str(concurrent_fragments)])
        
        # Download archive
        command.extend(["--download-archive", self.archive_path])
        
        return command

    def _add_quality_options(self, command: List[str], options: Dict[str, Any]) -> None:
        """Add quality and format options to command"""
        quality = options.get("quality", "bestvideo+bestaudio/best")
        merge_video_audio = options.get("merge_video_audio", True)
        
        if merge_video_audio and self.check_ffmpeg():
            command.extend(["--merge-output-format", "mkv"])
            command.extend(["--audio-quality", "0"])
            command.extend(["--audio-format", "m4a"])
            
            if self.ffmpeg_path and self.ffmpeg_path != "ffmpeg":
                command.extend(["--postprocessor-args", "ffmpeg:-c:v copy -c:a aac -strict experimental"])
            
            log_event("Video/audio merging enabled with FFmpeg")
        
        # Format selection based on quality
        format_map = {
            "best": "best",
            "4K": "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
            "1440p": "bestvideo[height<=1440]+bestaudio/best[height<=1440]",
            "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
            "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
            "worst": "worst",
        }
        
        format_string = format_map.get(quality, "bestvideo[height>=720]+bestaudio/best[height>=720]/bestvideo+bestaudio/best")
        command.extend(["-f", format_string])
        log_event(f"Quality format: {format_string}")

    def _add_subtitle_options(self, command: List[str], options: Dict[str, Any]) -> None:
        """Add subtitle options to command"""
        if options.get("download_subtitles"):
            subtitle_lang = options.get("subtitle_language", "tr")
            if subtitle_lang == "all":
                command.extend(["--write-subs", "--all-subs"])
            else:
                command.extend(["--write-subs", "--sub-langs", subtitle_lang])
        
        if options.get("auto_subtitles"):
            auto_lang = options.get("auto_translate_language", "tr")
            command.extend(["--write-auto-subs", "--sub-langs", auto_lang])
        
        if options.get("embed_subtitles"):
            command.extend(["--embed-subs"])
            log_event("Subtitles will be embedded in video")

    def _run_yt_dlp_command(self, command: List[str], thread_id: str) -> Iterator[Dict[str, Any]]:
        """
        Execute yt-dlp command and parse output
        
        Args:
            command: Complete yt-dlp command
            thread_id: Thread identifier for tracking
            
        Yields:
            Progress updates
        """
        log_event(f"Executing: {' '.join(command)}")
        
        try:
            process = subprocess.Popen(
                command, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True, 
                bufsize=1, 
                universal_newlines=True,
                encoding='utf-8', 
                errors='replace'
            )
        except Exception as e:
            log_error(f"Failed to start process: {e}")
            yield {"type": "error", "message": str(e), "thread_id": thread_id}
            return
        
        current_title = None
        current_ext = None
        video_title = None
        
        # Process stdout line by line
        for line in iter(process.stdout.readline, ''):
            yield {"type": "log", "message": line.strip()}
            
            # Extract video information
            title_info = self._extract_video_info(line)
            if title_info:
                video_title, current_title, current_ext = title_info
            
            # Parse progress information
            progress_info = self._parse_progress_line(line, video_title, current_title, current_ext, thread_id)
            if progress_info:
                yield progress_info
        
        process.stdout.close()
        process.wait()
        
        # Handle process completion
        stderr_output = process.stderr.read() if process.stderr else ""
        
        if process.returncode != 0:
            log_error(f"yt-dlp failed: {stderr_output}")
            yield {
                "type": "error", 
                "message": stderr_output.strip(), 
                "thread_id": thread_id,
                "title": video_title or current_title or "Unknown"
            }
        else:
            log_event("Download completed successfully")
            yield {
                "type": "complete", 
                "message": "Download finished", 
                "thread_id": thread_id,
                "title": video_title or current_title or "Unknown"
            }

    def _extract_video_info(self, line: str) -> Optional[Tuple[str, str, str]]:
        """Extract video information from yt-dlp output line"""
        video_title = None
        current_title = None
        current_ext = None
        
        # Extract title from info line
        if "[info]" in line and ":" in line:
            if not any(keyword in line.lower() for keyword in 
                      ['format', 'downloading', 'available', 'playlist', 'writing', 'subtitle']):
                match = self.TITLE_PATTERN.search(line)
                if match:
                    potential_title = match.group(1).strip()
                    if len(potential_title) > 10 and not potential_title.startswith(('http', '[')):
                        video_title = potential_title
        
        # Extract title from destination line
        if '[download] Destination:' in line:
            match = self.DESTINATION_PATTERN.search(line)
            if match:
                file_path = match.group(1).strip()
                filename = os.path.basename(file_path)
                current_title, ext = os.path.splitext(filename)
                current_ext = ext[1:] if ext.startswith('.') else ext
                
                # Clean up format codes
                current_title = re.sub(r'\.[f]\d+$', '', current_title)
                if len(current_title) > 5 and not video_title:
                    video_title = current_title
        
        if video_title or current_title:
            return video_title, current_title, current_ext
        return None

    def _parse_progress_line(self, line: str, video_title: Optional[str], 
                           current_title: Optional[str], current_ext: Optional[str], 
                           thread_id: str) -> Optional[Dict[str, Any]]:
        """Parse progress information from yt-dlp output line"""
        if not ("[download]" in line and "%" in line and " of " in line and " at " in line):
            return None
        
        match = self.PROGRESS_PATTERN.search(line)
        if not match:
            return None
        
        display_title = video_title or current_title or "Unknown"
        display_ext = current_ext or "Unknown"
        
        return {
            "type": "progress",
            "percent": float(match.group(1)),
            "total_size": match.group(2),
            "speed": match.group(3),
            "eta": match.group(4) if match.group(4) else "N/A",
            "title": display_title,
            "ext": display_ext,
            "thread_id": thread_id
        }

    def set_cookies_file(self, cookies_file: str) -> None:
        """
        Set the cookies file path for authentication
        
        Args:
            cookies_file: Path to cookies file
        """
        self.cookies_file = cookies_file
        log_event(f"Cookies file set: {cookies_file}")
