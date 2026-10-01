#!/bin/bash
# Build a standalone macOS app bundle into ./dist
set -e
cd "$(dirname "$0")"
echo "== YouTube Downloader - macOS build =="
python3 -m pip install -r requirements-dev.txt
python3 build.py
echo
echo "Done: dist/YouTube-Downloader-macOS.app"
echo "Users need FFmpeg installed (brew install ffmpeg) for high quality and MP3."
