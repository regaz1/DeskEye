# -*- mode: python ; coding: utf-8 -*-
# Portable Windows build: ό,τι χρειάζεται ο χρήστης βρίσκεται σε έναν φάκελο.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH)
mp_data, mp_bins, mp_imports = collect_all("mediapipe",
    filter_submodules=lambda name: ".test" not in name and ".benchmark" not in name)
a = Analysis([str(root / "main.py")], pathex=[str(root)],
    binaries=mp_bins, datas=mp_data + [(str(root / "models"), "models"), (str(root / "assets"), "assets")],
    hiddenimports=mp_imports + ["mediapipe.tasks.c"],
    hookspath=[], hooksconfig={"matplotlib": {"backends": ["Agg"]}}, runtime_hooks=[],
    excludes=["pytest", "IPython"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="DeskEye",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    icon=str(root / "assets" / "deskeye.ico"), version=str(root / "version_info.txt"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="DeskEye")
