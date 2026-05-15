@echo off
setlocal

where uv >nul 2>nul
if errorlevel 1 (
  echo Error: uv is not installed. Please install uv: https://docs.astral.sh/uv/getting-started/installation/ 1>&2
  exit /b 1
)

cd /d "%~dp0" || exit /b 1
uv run brain_ds %*
exit /b %ERRORLEVEL%
