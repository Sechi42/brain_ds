#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "Error: uv is not installed. Please install uv: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

cd "$SCRIPT_DIR" || exit 1
uv run brain_ds "$@"
exit $?
