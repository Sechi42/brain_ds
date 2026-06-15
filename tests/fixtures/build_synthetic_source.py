from __future__ import annotations

import sqlite3
from pathlib import Path


FIXTURE_PATH = Path(__file__).with_name("synthetic_source.db")


def build_synthetic_source(target: Path | None = None) -> Path:
    db_path = (target or FIXTURE_PATH).resolve()
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
