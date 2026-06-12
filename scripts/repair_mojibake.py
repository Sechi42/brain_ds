"""CLI wrapper: repair mojibake text in a project's .brain_ds/store.db.

Usage:
    python scripts/repair_mojibake.py [--project-root PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from brain_ds.store.repair import repair_store


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair mojibake text in the brain_ds store")
    parser.add_argument("--project-root", default=".", help="Project root containing .brain_ds/store.db")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    args = parser.parse_args()

    db_path = Path(args.project_root).resolve() / ".brain_ds" / "store.db"
    report = repair_store(db_path, dry_run=args.dry_run)

    mode = "DRY RUN" if report.dry_run else "APPLIED"
    print(f"[{mode}] {report.db_path}")
    if report.backup_path:
        print(f"backup: {report.backup_path}")
    print(f"cells repaired: {report.cells_repaired}")
    for location, before, after in report.samples:
        print(f"  {location}: {before!r} -> {after!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
