@echo off
REM Build a standalone Windows executable (with FFmpeg bundled) into .\dist
cd /d "%~dp0"
echo == YouTube Downloader - Windows build ==
py -3 -m pip install -r requirements-dev.txt || goto :error
py -3 build.py --with-ffmpeg || goto :error
echo.
echo Done: dist\YouTube-Downloader.exe
pause
exit /b 0
:error
echo BUILD FAILED
pause
exit /b 1
