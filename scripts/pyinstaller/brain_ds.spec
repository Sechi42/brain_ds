# brain_ds PyInstaller spec (onefile sidecar)
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path.cwd()
ENTRYPOINT = ROOT / "brain_ds" / "__main__.py"

datas = collect_data_files("brain_ds")

a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "brain_ds.ui",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
    ],
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
    name='brain_ds',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
