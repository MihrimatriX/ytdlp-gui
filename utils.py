import subprocess
from datetime import datetime

def check_yt_dlp():
    try:
        subprocess.run(["yt-dlp", "--version"], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def log_event(message: str):
    with open("app_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
