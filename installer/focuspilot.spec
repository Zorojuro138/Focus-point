# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent
package_data = root / "src" / "focuspilot" / "data"

a = Analysis(
    [str(root / "src" / "focuspilot" / "__main__.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=[
        (str(package_data), "focuspilot/data"),
        (str(root / "installer" / "PORTABLE-README.txt"), "."),
        (str(root / "browser-extension"), "browser-extension"),
    ],
    hiddenimports=collect_submodules("PySide6.QtSvg"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "transformers", "sentence_transformers"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FocusPilot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FocusPilot",
)
