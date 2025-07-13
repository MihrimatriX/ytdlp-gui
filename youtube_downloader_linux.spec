# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Flet için gerekli data dosyalarını topla
try:
    flet_data = collect_data_files('flet')
    flet_submodules = collect_submodules('flet')
except Exception:
    flet_data = []
    flet_submodules = []

# yt-dlp için gerekli data dosyalarını topla
try:
    ytdlp_data = collect_data_files('yt_dlp')
    ytdlp_submodules = collect_submodules('yt_dlp')
except Exception:
    ytdlp_data = []
    ytdlp_submodules = []

# Cryptography için gerekli data dosyalarını topla
try:
    crypto_data = collect_data_files('cryptography')
except Exception:
    crypto_data = []

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Flet data dosyaları
        *flet_data,
        # yt-dlp data dosyaları
        *ytdlp_data,
        # Cryptography data dosyaları
        *crypto_data,
        # System FFmpeg kullanacağız, binary dahil etmiyoruz
        # ('ffmpeg/ffmpeg', 'ffmpeg/') if os.path.exists('ffmpeg/ffmpeg') else None,
        # Diğer gerekli dosyalar
        ('requirements.txt', '.'),
        ('README.md', '.'),
    ],
    hiddenimports=[
        # Flet hidden imports
        'flet',
        'flet.core',
        'flet.core.page',
        'flet.core.control',
        'flet.controls',
        *flet_submodules,
        
        # yt-dlp hidden imports
        'yt_dlp',
        'yt_dlp.extractor',
        'yt_dlp.downloader',
        'yt_dlp.postprocessor',
        *ytdlp_submodules,
        
        # Cryptography hidden imports
        'cryptography',
        'cryptography.fernet',
        'cryptography.hazmat',
        'cryptography.hazmat.primitives',
        'cryptography.hazmat.primitives.ciphers',
        'cryptography.hazmat.primitives.hashes',
        'cryptography.hazmat.primitives.kdf',
        'cryptography.hazmat.primitives.serialization',
        'cryptography.hazmat.backends',
        'cryptography.hazmat.backends.openssl',
        
        # Linux specific
        'keyring',
        'keyring.backends',
        'keyring.backends.SecretService',
        'sqlite3',
        'gi',
        'gi.repository',
        'gi.repository.Gtk',
        'gi.repository.GLib',
        'gi.repository.GObject',
        
        # JSON ve diğer standart kütüphaneler
        'json',
        'tempfile',
        'shutil',
        'urllib.request',
        'zipfile',
        'platform',
        'subprocess',
        'threading',
        'queue',
        'concurrent.futures',
        'uuid',
        'time',
        'datetime',
        'pathlib',
        'argparse',
        'sys',
        'os',
        're',
        
        # Diğer bağımlılıklar
        'packaging',
        'setuptools',
        'pkg_resources',
        'importlib_metadata',
        'zipp',
        'typing_extensions',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# None değerlerini filtrele
a.datas = [item for item in a.datas if item is not None]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='YouTube-Downloader-Linux',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI uygulaması için False
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
) 