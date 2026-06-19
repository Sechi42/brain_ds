from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BUNDLE_JS = Path("assets/viewer.bundle.js")
BUNDLE_CSS = Path("assets/viewer.bundle.css")
SOURCE_PATTERNS = ("*.ts", "*.css")
REVISION_PATTERN = re.compile(r"bundleRevision:\s*[\"']([^\"']+)[\"']")


@dataclass(frozen=True)
class BundleFreshnessResult:
    ok: bool
    messages: list[str]


def _source_files(src_root: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in SOURCE_PATTERNS:
        files.extend(path for path in src_root.rglob(pattern) if path.is_file())
    return sorted(files)


def _newest(paths: Iterable[Path]) -> Path | None:
    newest: Path | None = None
    for path in paths:
        if newest is None or path.stat().st_mtime_ns > newest.stat().st_mtime_ns:
            newest = path
    return newest


def _bundle_revision(path: Path) -> str | None:
    match = REVISION_PATTERN.search(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def check_viewer_bundle_freshness(ui_root: Path) -> BundleFreshnessResult:
    """Validate that committed viewer bundle assets are deployable.

    Release/deploy paths package ``brain_ds/ui/assets`` directly, so this guard
    fails fast when the built assets are missing, older than source, or carry a
    different ``bundleRevision`` from ``src/main.ts``.
    """

    messages: list[str] = []
    ui_root = ui_root.resolve()
    src_root = ui_root / "src"
    main_source = src_root / "main.ts"
    bundles = [ui_root / BUNDLE_JS, ui_root / BUNDLE_CSS]

    sources = _source_files(src_root)
    if not sources:
        messages.append(f"missing UI sources under {src_root}")
    newest_source = _newest(sources)

    for bundle in bundles:
        if not bundle.exists():
            messages.append(f"missing rebuilt UI bundle asset: {bundle}")
            continue
        if newest_source is not None and bundle.stat().st_mtime_ns < newest_source.stat().st_mtime_ns:
            messages.append(
                f"{bundle.name} is older than UI source {newest_source.relative_to(ui_root)}; "
                "run `pnpm --dir brain_ds/ui run build` before release/deploy."
            )

    if not main_source.exists():
        messages.append(f"missing bundle revision source: {main_source}")
    elif (ui_root / BUNDLE_JS).exists():
        source_revision = _bundle_revision(main_source)
        bundle_revision = _bundle_revision(ui_root / BUNDLE_JS)
        if source_revision is None:
            messages.append("src/main.ts is missing window.brainDsUI.bundleRevision")
        elif bundle_revision is None:
            messages.append("viewer.bundle.js is missing bundleRevision")
        elif source_revision != bundle_revision:
            messages.append(
                "bundleRevision mismatch: "
                f"src/main.ts has {source_revision!r}, viewer.bundle.js has {bundle_revision!r}; "
                "run `pnpm --dir brain_ds/ui run build`."
            )

    return BundleFreshnessResult(ok=not messages, messages=messages)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail if brain_ds UI bundle assets are stale.")
    parser.add_argument(
        "--ui-root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Path to brain_ds/ui (default: installed package UI directory).",
    )
    args = parser.parse_args(argv)

    result = check_viewer_bundle_freshness(args.ui_root)
    if result.ok:
        print("UI bundle freshness check passed.")
        return 0
    for message in result.messages:
        print(f"ERROR: {message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
