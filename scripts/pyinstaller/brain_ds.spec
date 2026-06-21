# brain_ds PyInstaller spec (onefile sidecar)
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path.cwd()
ENTRYPOINT = ROOT / "brain_ds" / "__main__.py"

datas = collect_data_files("brain_ds")
binaries = []
hiddenimports = [
    "brain_ds.ui",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]

# Optional connection backends (aws / postgres / gsheets extras). These are
# imported LAZILY inside the secret adapters and connectors, so PyInstaller's
# static analysis never sees them — they must be collected explicitly or the
# frozen exe raises "boto3 is not installed" at secret-validation time.
# boto3/botocore also ship data files (endpoints.json, service models) and
# psycopg[binary] ships a compiled wheel, so collect_all (not just hiddenimports)
# is required. Wrapped defensively so a missing optional package never breaks
# the build (the build venv installs the extras; see build-windows-exe.ps1).
for _opt_pkg in (
    "boto3",
    "botocore",
    "psycopg",
    "psycopg_binary",
    "gspread",
    "google.auth",
    "google_auth_oauthlib",
):
    try:
        _d, _b, _h = collect_all(_opt_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception as _exc:  # pragma: no cover - build-time best effort
        print(f"[brain_ds.spec] skipped optional package {_opt_pkg!r}: {_exc}")

a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(ROOT)],
    binaries=binaries,
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
