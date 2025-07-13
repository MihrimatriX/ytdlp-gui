#!/bin/bash

echo "========================================"
echo "YouTube Downloader - macOS Build Script"
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
    echo "Please install Python 3 using Homebrew: brew install python3"
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
pyinstaller youtube_downloader_macos.spec --clean --noconfirm || {
    echo -e "${RED}❌ Build failed.${NC}"
    exit 1
}

echo
if [ -f "dist/YouTube-Downloader-macOS.app/Contents/MacOS/YouTube-Downloader-macOS" ]; then
    echo -e "${GREEN}✅ BUILD SUCCESSFUL!${NC}"
    echo
    echo "Application location: dist/YouTube-Downloader-macOS.app"
    echo "Executable location: dist/YouTube-Downloader-macOS.app/Contents/MacOS/YouTube-Downloader-macOS"
    echo "App bundle size: $(du -sh dist/YouTube-Downloader-macOS.app | cut -f1)"
    echo
    echo "You can now distribute this .app bundle!"
    echo "It contains everything needed to run the YouTube Downloader on macOS."
    echo
    echo "To run: open dist/YouTube-Downloader-macOS.app"
    echo "Or directly: ./dist/YouTube-Downloader-macOS.app/Contents/MacOS/YouTube-Downloader-macOS"
    
    # Create a DMG for easier distribution
    echo -e "${YELLOW}Creating DMG for distribution...${NC}"
    if command -v create-dmg &> /dev/null; then
        create-dmg \
            --volname "YouTube Downloader" \
            --volicon "dist/YouTube-Downloader-macOS.app/Contents/Resources/icon.icns" \
            --window-pos 200 120 \
            --window-size 600 300 \
            --icon-size 100 \
            --icon "YouTube-Downloader-macOS.app" 175 120 \
            --hide-extension "YouTube-Downloader-macOS.app" \
            --app-drop-link 425 120 \
            "dist/YouTube-Downloader-macOS.dmg" \
            "dist/YouTube-Downloader-macOS.app"
        echo -e "${GREEN}✅ DMG created: dist/YouTube-Downloader-macOS.dmg${NC}"
    else
        echo -e "${YELLOW}⚠️ create-dmg not found. Install with: brew install create-dmg${NC}"
    fi
else
    echo -e "${RED}❌ BUILD FAILED!${NC}"
    echo "Check the output above for errors."
    exit 1
fi

echo
echo "Build completed successfully! 🎉" 