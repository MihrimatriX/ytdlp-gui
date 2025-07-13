#!/bin/bash

echo "========================================"
echo "YouTube Downloader - Linux Build Script"
echo "========================================"
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}[1/5] Checking Python version...${NC}"
python3 --version || {
    echo -e "${RED}❌ Python 3 is required but not installed.${NC}"
    exit 1
}

echo -e "${YELLOW}[2/5] Installing dependencies...${NC}"
pip3 install -r requirements.txt || {
    echo -e "${RED}❌ Failed to install dependencies.${NC}"
    exit 1
}

echo -e "${YELLOW}[3/5] Installing PyInstaller...${NC}"
pip3 install pyinstaller || {
    echo -e "${RED}❌ Failed to install PyInstaller.${NC}"
    exit 1
}

echo -e "${YELLOW}[4/5] Setting up FFmpeg...${NC}"
python3 -c "from downloader import Downloader; d = Downloader(); d.setup_ffmpeg(); print('FFmpeg setup completed')" || {
    echo -e "${RED}❌ Failed to setup FFmpeg.${NC}"
    exit 1
}

echo -e "${YELLOW}[5/5] Building executable...${NC}"
pyinstaller youtube_downloader_linux.spec --clean --noconfirm || {
    echo -e "${RED}❌ Build failed.${NC}"
    exit 1
}

echo
if [ -f "dist/YouTube-Downloader-Linux" ]; then
    echo -e "${GREEN}✅ BUILD SUCCESSFUL!${NC}"
    echo
    echo "Executable location: dist/YouTube-Downloader-Linux"
    echo "File size: $(du -h dist/YouTube-Downloader-Linux | cut -f1)"
    echo
    echo "You can now distribute this single binary file!"
    echo "It contains everything needed to run the YouTube Downloader on Linux."
    echo
    echo "To run: ./dist/YouTube-Downloader-Linux"
else
    echo -e "${RED}❌ BUILD FAILED!${NC}"
    echo "Check the output above for errors."
    exit 1
fi

echo
echo "Build completed successfully! 🎉" 