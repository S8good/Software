# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path(SPECPATH).resolve().parent
ICON_PATH = ROOT / "nanosense/gui/assets/app_icon.ico"
SPLASH_PATH = ROOT / "nanosense/gui/assets/splash.png"
TRANSLATION_PATH = ROOT / "nanosense/translations/chinese.qm"


datas = [
    # These explicit paths document the files required by the launcher and translator.
    (str(SPLASH_PATH), "nanosense/gui/assets"),
    (str(TRANSLATION_PATH), "nanosense/translations"),
    (str(ROOT / "nanosense/gui/assets"), "nanosense/gui/assets"),
    (str(ROOT / "nanosense/translations"), "nanosense/translations"),
]

binaries = [
    (str(ROOT / "drivers/IdeaOptics.dll"), "drivers"),
    (str(ROOT / "drivers/CyUSB.DLL"), "drivers"),
    (str(ROOT / "drivers/IdeaOptics.tlb"), "drivers"),
    (
        str(ROOT / "drivers/Oceandirect/oceandirect/lib/OceanDirect.dll"),
        "drivers/Oceandirect/oceandirect/lib",
    ),
]

hiddenimports = [
    "clr",
    "clr_loader",
    "oceandirect.OceanDirectAPI",
    "oceandirect.sdk_properties",
]
hiddenimports.extend(collect_submodules("pyqtgraph.exporters"))

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT), str(ROOT / "drivers/Oceandirect")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt6", "PyQt6.*"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NanoSense",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_PATH),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="NanoSense",
)
