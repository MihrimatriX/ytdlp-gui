"""
YouTube Downloader - Utility Functions
Common utility functions for the application
"""

import subprocess
import os
import sys
import shutil
from datetime import datetime
from typing import Optional, Dict, Any

# Application constants
LOG_FILE = "app_log.txt"
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB

def check_yt_dlp() -> bool:
    """
    Check if yt-dlp is installed and accessible
    
    Returns:
        bool: True if yt-dlp is available, False otherwise
    """
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"], 
            check=True, 
            capture_output=True, 
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False

def check_ffmpeg() -> bool:
    """
    Check if FFmpeg is installed and accessible
    
    Returns:
        bool: True if FFmpeg is available, False otherwise
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], 
            check=True, 
            capture_output=True, 
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False

def get_disk_space(path: str) -> Optional[Dict[str, float]]:
    """
    Get disk space information for a given path
    
    Args:
        path: Directory path to check
        
    Returns:
        Dict with total, used, and free space in GB, or None if error
    """
    try:
        usage = shutil.disk_usage(path)
        return {
            "total": usage.total / (1024**3),
            "used": usage.used / (1024**3),
            "free": usage.free / (1024**3)
        }
    except Exception:
        return None

def format_bytes(bytes_size: int) -> str:
    """
    Format bytes to human readable format
    
    Args:
        bytes_size: Size in bytes
        
    Returns:
        Formatted string (e.g., "1.5 GB")
    """
    if bytes_size == 0:
        return "0 B"
    
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while bytes_size >= 1024 and i < len(units) - 1:
        bytes_size /= 1024
        i += 1
    
    return f"{bytes_size:.1f} {units[i]}"

def validate_url(url: str) -> bool:
    """
    Basic URL validation for YouTube URLs
    
    Args:
        url: URL to validate
        
    Returns:
        bool: True if URL appears to be valid YouTube URL
    """
    if not url or not isinstance(url, str):
        return False
    
    youtube_domains = [
        "youtube.com", "youtu.be", "www.youtube.com", 
        "m.youtube.com", "music.youtube.com"
    ]
    
    return any(domain in url.lower() for domain in youtube_domains)

def cleanup_log_file() -> None:
    """Clean up log file if it exceeds maximum size"""
    try:
        if os.path.exists(LOG_FILE):
            if os.path.getsize(LOG_FILE) > MAX_LOG_SIZE:
                # Keep only the last 50% of the file
                with open(LOG_FILE, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                keep_lines = len(lines) // 2
                with open(LOG_FILE, 'w', encoding='utf-8') as f:
                    f.writelines(lines[-keep_lines:])
                    f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOG_CLEANUP: Log file rotated\n")
    except Exception:
        pass  # Ignore cleanup errors

def log_event(message: str, level: str = "INFO") -> None:
    """
    Log an event with timestamp and level
    
    Args:
        message: Log message
        level: Log level (INFO, WARNING, ERROR, DEBUG)
    """
    try:
        # Clean up log file if needed
        cleanup_log_file()
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {level}: {message}\n"
        
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
            
        # Also print to console for debugging
        if level in ["ERROR", "WARNING"]:
            print(f"[{level}] {message}")
    except Exception:
        pass  # Ignore logging errors to prevent cascading failures

def log_error(message: str) -> None:
    """Log an error message"""
    log_event(message, "ERROR")

def log_warning(message: str) -> None:
    """Log a warning message"""
    log_event(message, "WARNING")

def log_debug(message: str) -> None:
    """Log a debug message"""
    log_event(message, "DEBUG")

def get_system_info() -> Dict[str, Any]:
    """
    Get system information for debugging
    
    Returns:
        Dict with system information
    """
    return {
        "platform": sys.platform,
        "python_version": sys.version,
        "cwd": os.getcwd(),
        "yt_dlp_available": check_yt_dlp(),
        "ffmpeg_available": check_ffmpeg(),
    }

def ensure_directory_exists(path: str) -> bool:
    """
    Ensure a directory exists, create if it doesn't
    
    Args:
        path: Directory path
        
    Returns:
        bool: True if directory exists or was created successfully
    """
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception:
        return False
