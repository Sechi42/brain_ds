@echo off
setlocal

where uv >nul 2>nul
if errorlevel 1 (
  echo Error: uv is not installed. Please install uv: https://docs.astral.sh/uv/getting-started/installation/ 1>&2
  exit /b 1
)

rem Keep the caller's cwd: the MCP server resolves its workspace from it.
rem --project points uv at this repo's environment without chdir.
uv run --project "%~dp0." brain_ds %*
exit /b %ERRORLEVEL%
