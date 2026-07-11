# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows seilio-billing.exe build.

Build on Windows, inside a venv with the app's runtime deps plus pyinstaller
installed (`pip install .[dev] pyinstaller` or see
.github/workflows/windows-build.yml for the exact steps):

    pyinstaller packaging/windows/seilio-billing.spec --noconfirm

Output: dist/seilio-billing/seilio-billing.exe (a single-file executable;
first launch unpacks to a temp dir, which is why icon_path() in
seilio_billing/icons.py checks sys._MEIPASS).
"""
import os

from PyInstaller.utils.hooks import collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
MAIN_SCRIPT = os.path.join(ROOT, "seilio_billing", "main.py")
ICON_DIR = os.path.join(ROOT, "resources", "icons")
APP_ICON = os.path.join(ICON_DIR, "app.ico")

# facturx ships XSD/schematron validation files, reportlab ships font
# metrics — both are read as plain files at runtime, so PyInstaller's static
# import analysis won't find them on its own.
datas = collect_data_files("facturx") + collect_data_files("reportlab")
datas.append((ICON_DIR, os.path.join("resources", "icons")))

a = Analysis(
    [MAIN_SCRIPT],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="seilio-billing",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=APP_ICON,
)
