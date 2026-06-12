$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
  throw "[build-windows-exe] $Message"
}

function Require-Command([string]$Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    Fail "Missing prerequisite '$Name'. Install it and retry."
  }
}

Require-Command "cargo"
Require-Command "rustc"
Require-Command "uv"
Require-Command "pnpm"

cmd /c "cargo tauri --version >nul 2>nul"
if ($LASTEXITCODE -ne 0) {
  Fail "Missing Tauri CLI. Install with: cargo install tauri-cli --version ^2.0.0 --locked"
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $repoRoot ".build-venv"
$venvPython = Join-Path $venvPath "Scripts/python.exe"
$specPath = Join-Path $repoRoot "scripts/pyinstaller/brain_ds.spec"
$distStage = Join-Path $repoRoot "src-tauri/binaries-stage"
$workPath = Join-Path $repoRoot "build/pyinstaller"
$binariesPath = Join-Path $repoRoot "src-tauri/binaries"
$distOut = Join-Path $repoRoot "dist"

New-Item -ItemType Directory -Force -Path $distStage | Out-Null
New-Item -ItemType Directory -Force -Path $workPath | Out-Null
New-Item -ItemType Directory -Force -Path $binariesPath | Out-Null
New-Item -ItemType Directory -Force -Path $distOut | Out-Null

# Rebuild the UI bundle from source so the exe never ships a stale committed
# viewer.bundle.js (the bundle is generated, and trusting the repo copy already
# shipped an outdated UI once). Supply-chain guards:
#   - frozen lockfile: dependency tree must match pnpm-lock.yaml exactly
#   - ignore-scripts: package lifecycle scripts never execute (esbuild ships
#     its binary as an optionalDependency, so the build works without them)
#   - audit gate: high/critical advisories in the tree fail the build
$uiPath = Join-Path $repoRoot "brain_ds/ui"
$bundlePath = Join-Path $uiPath "assets/viewer.bundle.js"
$uiSourceRoot = Join-Path $uiPath "src"
Push-Location -LiteralPath $uiPath
try {
  $env:PNPM_CONFIG_IGNORE_SCRIPTS = "true"
  pnpm install --frozen-lockfile
  if ($LASTEXITCODE -ne 0) { Fail "pnpm install --frozen-lockfile failed with exit code $LASTEXITCODE." }
  pnpm audit --audit-level high
  if ($LASTEXITCODE -ne 0) { Fail "pnpm audit found high/critical advisories (exit $LASTEXITCODE). Resolve them before shipping the exe." }
  pnpm run build
  if ($LASTEXITCODE -ne 0) { Fail "UI bundle build failed with exit code $LASTEXITCODE." }
  pnpm run bundle-size
  if ($LASTEXITCODE -ne 0) { Fail "UI bundle size check failed with exit code $LASTEXITCODE." }

  if (-not (Test-Path -LiteralPath $bundlePath)) {
    Fail "Expected rebuilt UI bundle at $bundlePath"
  }
  $sourceFiles = @(Get-ChildItem -LiteralPath $uiSourceRoot -Recurse -File -Include *.ts)
  if ($sourceFiles.Count -eq 0) {
    Fail "No TypeScript sources found under $uiSourceRoot"
  }
  $newestSource = ($sourceFiles | Sort-Object LastWriteTimeUtc -Descending)[0]
  $bundleItem = Get-Item -LiteralPath $bundlePath
  if ($bundleItem.LastWriteTimeUtc -lt $newestSource.LastWriteTimeUtc) {
    Fail "viewer.bundle.js is older than TypeScript source '$($newestSource.FullName)'. Rebuild freshness check failed."
  }
}
finally {
  Pop-Location
}

if (-not (Test-Path -LiteralPath $venvPython)) {
  uv venv --python 3.13 $venvPath
}

$pythonVersion = (& $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')").Trim()
if (-not $pythonVersion.StartsWith("3.13.")) {
  Fail "PyInstaller compatibility requires CPython 3.13.x for sidecar packaging. Found $pythonVersion in .build-venv. Recreate with: uv venv --python 3.13 .build-venv. (Runtime probe failure signature: Unsupported python version?)"
}
uv pip install --python $venvPath pyinstaller==6.11.1
Push-Location -LiteralPath $repoRoot
try {
  uv pip install --python $venvPath -e .
}
finally {
  Pop-Location
}

& $venvPython -m PyInstaller --noconfirm --clean --distpath $distStage --workpath $workPath $specPath
if ($LASTEXITCODE -ne 0) {
  Fail "PyInstaller failed with exit code $LASTEXITCODE. See output above for details."
}

$stagedSidecar = Join-Path $distStage "brain_ds.exe"
if (-not (Test-Path -LiteralPath $stagedSidecar)) {
  Fail "Expected sidecar not found: $stagedSidecar"
}

$targetSidecar = Join-Path $binariesPath "brain_ds-x86_64-pc-windows-msvc.exe"
Copy-Item -LiteralPath $stagedSidecar -Destination $targetSidecar -Force

$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
  $probe = (& $targetSidecar ui --probe 2>&1 | Out-String)
  $probeExitCode = $LASTEXITCODE
}
finally {
  $ErrorActionPreference = $previousErrorActionPreference
}
if ($probeExitCode -ne 0) {
  Fail "Sidecar probe failed (exit $probeExitCode). Ensure hidden imports are complete and retry PyInstaller configuration. Output:`n$probe"
}
if (-not ($probe -match "READY")) {
  Fail "Sidecar probe did not emit READY within expected output. Output:`n$probe"
}

cargo tauri build --features bundled --bundles nsis
if ($LASTEXITCODE -ne 0) {
  Fail "Tauri build failed with exit code $LASTEXITCODE."
}

$bundleDir = Join-Path $repoRoot "src-tauri/target/release/bundle/nsis"
if (-not (Test-Path -LiteralPath $bundleDir)) {
  Fail "Expected NSIS bundle directory not found: $bundleDir"
}
Get-ChildItem -LiteralPath $bundleDir -Filter "*setup.exe" | ForEach-Object {
  Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $distOut $_.Name) -Force
}

"Build orchestration finished. Installer artifacts copied to dist/."
