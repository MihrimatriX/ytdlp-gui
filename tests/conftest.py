import functools
import http.server
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Keep settings/history/logs out of the real user profile."""
    monkeypatch.setenv("YTDLP_GUI_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Static file server with single-range ``Range`` support (needed to test resume)."""

    def log_message(self, *args):
        pass

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            pass

    def send_head(self):
        header = self.headers.get("Range", "")
        path = self.translate_path(self.path)
        if not header.startswith("bytes=") or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        start_text, _, end_text = header[6:].partition("-")
        start = int(start_text or 0)
        end = min(int(end_text) if end_text else size - 1, size - 1)
        if start >= size:
            self.send_error(416)
            return None
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        return f


@pytest.fixture(scope="session")
def media_server(tmp_path_factory):
    """Serve a short generated video over HTTP (requires ffmpeg)."""
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is required for download tests")
    root = tmp_path_factory.mktemp("media")
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=25",
         "-f", "lavfi", "-i", "sine=frequency=440", "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:v", "1M", str(root / "clip.mp4")],
        check=True,
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_QuietHandler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
