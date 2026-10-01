#!/bin/bash
# Build a standalone Linux executable into ./dist
set -e
cd "$(dirname "$0")"
echo "== YouTube Downloader - Linux build =="
python3 -m pip install -r requirements-dev.txt
python3 build.py
echo
echo "Done: dist/YouTube-Downloader-Linux"
echo "Users need FFmpeg installed (sudo apt install ffmpeg) for high quality and MP3."
