from __future__ import annotations

import os
import sqlite3
from pathlib import Path


FIXTURE_PATH = Path(__file__).with_name("synthetic_source.db")

# Environment variable that prevents build_synthetic_source() from rewriting
# the checked-in seed.  Set automatically by the conftest `synthetic_source_path`
# fixture so that normal test runs never mutate the tracked file.
_ENV_GUARD = "BRAIN_DS_NO_SEED_REBUILD"


def build_synthetic_source(target: Path | None = None) -> Path:
    """Build (or return) the synthetic SQLite source fixture.

    When called WITHOUT a `target`:
    - If the seed already exists AND the guard env-var is set (i.e. we are
      inside a pytest session), return the seed path unchanged to preserve
      the byte-for-byte hash that isolation tests assert.
    - Otherwise (first-time checkout or explicit rebuild from the CLI /
      ``__main__`` block), write the seed as before.

    When called WITH a `target`, always write to that path (the caller owns it).
    """
    if target is None:
        seed = FIXTURE_PATH.resolve()
        if seed.exists() and os.environ.get(_ENV_GUARD):
            # Inside a test session — seed exists, do NOT rewrite it.
            return seed
        db_path = seed
    else:
        db_path = target.resolve()

    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                customer_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                segment TEXT NOT NULL,
                region TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                order_total REAL NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("DELETE FROM customers")
        conn.execute("DELETE FROM orders")
        conn.executemany(
            "INSERT INTO customers (customer_id, name, segment, region) VALUES (?, ?, ?, ?)",
            [
                (1, "Acme Logistics", "Enterprise", "LATAM"),
                (2, "Beta Retail", "SMB", "LATAM"),
                (3, "Cielo Health", "Enterprise", "North America"),
                (4, "Delta Foods", "Mid Market", "EMEA"),
                (5, "Evergreen Energy", "Enterprise", "North America"),
            ],
        )
        conn.executemany(
            "INSERT INTO orders (order_id, customer_id, order_total, status, created_at) VALUES (?, ?, ?, ?, ?)",
            [
                (101, 1, 12500.50, "fulfilled", "2026-06-10"),
                (102, 2, 980.00, "pending", "2026-06-11"),
                (103, 3, 4430.75, "fulfilled", "2026-06-11"),
                (104, 1, 2175.20, "cancelled", "2026-06-12"),
                (105, 5, 8890.10, "pending", "2026-06-13"),
            ],
        )
        conn.commit()

    return db_path


if __name__ == "__main__":
    print(build_synthetic_source())
