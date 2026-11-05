# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
#  PyInstaller yapılandırması — "Xbox2MIDI DJ.app"
#  Kullanım:  build_app.command dosyasına çift tıklayın
#             (veya: .venv/bin/python -m PyInstaller --noconfirm Xbox2MIDI.spec)
#
#  Not: macOS'ta .app zaten tek bir paket (bundle) öğesidir. PyInstaller 6+
#  "onefile + .app" kombinasyonunu açılış gecikmesi ve imza sorunları nedeniyle
#  önermediği için "onedir" bundle kullanılır — kullanıcı açısından yine tek
#  dosyadır ve anında açılır.
# =============================================================================
import os

block_cipher = None
HERE = os.path.abspath(SPECPATH)
ICON = os.path.join(HERE, "assets", "AppIcon.icns")

datas = []
if os.path.exists(os.path.join(HERE, "assets", "icon.png")):
    datas.append((os.path.join(HERE, "assets", "icon.png"), "assets"))

a = Analysis(
    [os.path.join(HERE, "main.py")],
    pathex=[HERE],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "objc", "Foundation", "AppKit", "GameController",
        "xbox2midi", "xbox2midi.gui", "xbox2midi.engine",
        "xbox2midi.controller", "xbox2midi.midi_out", "xbox2midi.config",
    ],
    excludes=[
        "tkinter", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtNetwork",
        "PySide6.QtWebEngineCore", "PySide6.QtMultimedia", "PySide6.QtSql",
        "PySide6.QtOpenGL", "PySide6.QtPdf", "PySide6.QtTest",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Xbox2MIDI DJ",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch=None,          # Çalıştırılan Python'un mimarisi (Apple Silicon: arm64)
    codesign_identity=None,
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Xbox2MIDI DJ")

app = BUNDLE(
    coll,
    name="Xbox2MIDI DJ.app",
    icon=ICON if os.path.exists(ICON) else None,
    bundle_identifier="com.xbox2midi.dj",
    version="1.1.0",
    info_plist={
        "CFBundleName": "Xbox2MIDI DJ",
        "CFBundleDisplayName": "Xbox2MIDI DJ",
        "CFBundleShortVersionString": "1.1.0",
        "LSMinimumSystemVersion": "11.3",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,      # Karanlık mod
        "NSAppSleepDisabled": True,                   # App Nap kapalı (düşük gecikme)
        "LSApplicationCategoryType": "public.app-category.music",
        "NSBluetoothAlwaysUsageDescription":
            "Xbox Wireless Controller'ı Bluetooth üzerinden okumak için gereklidir.",
        "GCSupportsControllerUserInteraction": True,
        "GCSupportedGameControllers": [{"ProfileName": "ExtendedGamepad"}],
    },
)
