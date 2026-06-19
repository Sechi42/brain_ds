#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf '[build-macos] %s\n' "$1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing prerequisite '$1'. Install it and retry."
}

require_command cargo
require_command rustc
require_command uv
require_command pnpm

cargo tauri --version >/dev/null 2>&1 || fail "Missing Tauri CLI. Install with: cargo install tauri-cli --version ^2.0.0 --locked"

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
venv_path="$repo_root/.build-venv"
venv_python="$venv_path/bin/python"
spec_path="$repo_root/scripts/pyinstaller/brain_ds.spec"
dist_stage="$repo_root/src-tauri/binaries-stage"
work_path="$repo_root/build/pyinstaller"
binaries_path="$repo_root/src-tauri/binaries"
dist_out="$repo_root/dist"
ui_path="$repo_root/brain_ds/ui"
bundle_path="$ui_path/assets/viewer.bundle.js"
ui_source_root="$ui_path/src"

mkdir -p "$dist_stage" "$work_path" "$binaries_path" "$dist_out"

pushd "$ui_path" >/dev/null
export PNPM_CONFIG_IGNORE_SCRIPTS=true
pnpm install --frozen-lockfile
pnpm audit --audit-level high
pnpm run build
pnpm run bundle-size
uv run python -m brain_ds.ui.bundle_freshness --ui-root "$ui_path"

[[ -f "$bundle_path" ]] || fail "Expected rebuilt UI bundle at $bundle_path"

newest_source="$(find "$ui_source_root" -type f -name '*.ts' -print | head -n 1)"
[[ -n "$newest_source" ]] || fail "No TypeScript sources found under $ui_source_root"

while IFS= read -r source_file; do
  [[ "$source_file" -nt "$newest_source" ]] && newest_source="$source_file"
done < <(find "$ui_source_root" -type f -name '*.ts' -print)

[[ "$bundle_path" -nt "$newest_source" || "$bundle_path" -ef "$newest_source" ]] || fail "viewer.bundle.js is older than TypeScript source '$newest_source'. Rebuild freshness check failed."
popd >/dev/null

if [[ ! -x "$venv_python" ]]; then
  uv venv --python 3.13 "$venv_path"
fi

python_version="$($venv_python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
[[ "$python_version" == 3.13.* ]] || fail "PyInstaller compatibility requires CPython 3.13.x for sidecar packaging. Found $python_version in .build-venv. Recreate with: uv venv --python 3.13 .build-venv. (Runtime probe failure signature: Unsupported python version?)"

uv pip install --python "$venv_path" pyinstaller==6.11.1
pushd "$repo_root" >/dev/null
uv pip install --python "$venv_path" -e .
popd >/dev/null

"$venv_python" -m PyInstaller --noconfirm --clean --distpath "$dist_stage" --workpath "$work_path" "$spec_path"

staged_sidecar="$dist_stage/brain_ds"
[[ -f "$staged_sidecar" ]] || fail "Expected sidecar not found: $staged_sidecar"

arch="$(uname -m)"
case "$arch" in
  x86_64) target_triple="x86_64-apple-darwin" ;;
  arm64|aarch64) target_triple="aarch64-apple-darwin" ;;
  *) fail "Unsupported macOS architecture '$arch'. Expected x86_64 or arm64/aarch64." ;;
esac

target_sidecar="$repo_root/src-tauri/binaries/brain_ds-$target_triple"
cp "$staged_sidecar" "$target_sidecar"

set +e
probe_output="$($target_sidecar ui --probe 2>&1)"
probe_exit=$?
set -e
[[ $probe_exit -eq 0 ]] || fail "Sidecar probe failed (exit $probe_exit). Ensure hidden imports are complete and retry PyInstaller configuration. Output:
$probe_output"
[[ "$probe_output" == *READY* ]] || fail "Sidecar probe did not emit READY within expected output. Output:
$probe_output"

pushd "$repo_root/src-tauri" >/dev/null
cargo tauri build --features bundled --bundles dmg,app
popd >/dev/null

bundle_dir="$repo_root/src-tauri/target/release/bundle/dmg"
[[ -d "$bundle_dir" ]] || fail "Expected DMG bundle directory not found: $bundle_dir"

shopt -s nullglob
for dmg in "$bundle_dir"/*.dmg; do
  cp "$dmg" "$dist_out/$(basename "$dmg")"
done
shopt -u nullglob

printf 'Build orchestration finished. macOS installer artifacts copied to dist/.\n'
