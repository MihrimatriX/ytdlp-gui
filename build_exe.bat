@echo off
echo ========================================
echo YouTube Downloader - Executable Builder
echo ========================================
echo.

echo [1/4] Installing PyInstaller...
pip install pyinstaller

echo.
echo [2/4] Setting up FFmpeg...
py -3.11 -c "from downloader import Downloader; import time; d = Downloader(); d.setup_ffmpeg(); time.sleep(1); print('FFmpeg setup completed')"

echo.
echo [3/4] Building executable...
pyinstaller youtube_downloader.spec --clean --noconfirm

echo.
echo [4/4] Checking build result...
if exist "dist\YouTube-Downloader.exe" (
    echo ✅ BUILD SUCCESSFUL!
    echo.
    echo Executable location: dist\YouTube-Downloader.exe
    echo File size: 
    for %%I in ("dist\YouTube-Downloader.exe") do echo    %%~zI bytes
    echo.
    echo You can now distribute this single .exe file!
    echo It contains everything needed to run the YouTube Downloader.
) else (
    echo ❌ BUILD FAILED!
    echo Check the output above for errors.
)

echo.
echo Press any key to exit...
pause > nul 