#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "Error: uv is not installed. Please install uv: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

# Keep the caller's cwd: the MCP server resolves its workspace from it.
# --project points uv at this repo's environment without chdir.
uv run --project "$SCRIPT_DIR" brain_ds "$@"
exit $?
