# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

spec_dir = Path(SPECPATH)
repo_root = spec_dir.parent

# uvicorn picks its protocol/loop implementation at runtime via
# importlib.import_module (uvloop vs asyncio, httptools vs h11, websockets vs
# wsproto) — none of that shows up to PyInstaller's static import analysis.
hiddenimports = [
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.loops.uvloop",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "fugashi",
    "fugashi.fugashi",
    # fugashi.Tagger() with no explicit -d locates its dictionary by importing
    # unidic_lite from Cython at Tagger-construction time — invisible to
    # PyInstaller's static import analysis, so both the import *and* its
    # ~250MB non-Python dicdir payload (below) have to be forced in by hand.
    "unidic_lite",
]

datas = [
    (str(spec_dir / "app" / "directory_seed.json"), "backend/app"),
    (str(spec_dir / "app" / "ggml-silero-v5.1.2.bin"), "backend/app"),
    (str(repo_root / "frontend" / "dist"), "frontend/dist"),
    *collect_data_files("unidic_lite"),
]

a = Analysis(
    ["app/__main__.py"],
    pathex=[str(spec_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name="kotoba-backend-aarch64-apple-darwin",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="kotoba-backend",
)
