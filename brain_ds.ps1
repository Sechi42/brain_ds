$ErrorActionPreference = 'Stop'

if (-not (Get-Command -Name uv -ErrorAction SilentlyContinue)) {
  [Console]::Error.WriteLine('Error: uv is not installed. Please install uv: https://docs.astral.sh/uv/getting-started/installation/')
  exit 1
}

Push-Location $PSScriptRoot
try {
  & uv run brain_ds @args
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
