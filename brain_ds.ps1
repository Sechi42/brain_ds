$ErrorActionPreference = 'Stop'

if (-not (Get-Command -Name uv -ErrorAction SilentlyContinue)) {
  [Console]::Error.WriteLine('Error: uv is not installed. Please install uv: https://docs.astral.sh/uv/getting-started/installation/')
  exit 1
}

# Keep the caller's cwd: the MCP server resolves its workspace from it.
# --project points uv at this repo's environment without chdir.
& uv run --project $PSScriptRoot brain_ds @args
exit $LASTEXITCODE
