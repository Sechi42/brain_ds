"""Read-only external data-source connectors for brain_ds.

All connectors implement the ReadOnlyConnector ABC. The API surface has no
write methods — read-only enforcement is structural, not policy.

Supported:
- SQLiteConnector       — opens databases in URI mode=ro + PRAGMA query_only=ON
- CsvConnector          — reads CSV/TSV files with encoding="utf-8-sig" and sniffed delimiter
- PostgresConnector     — read-only psycopg v3 connector; requires brain_ds[postgres]
- GoogleSheetsConnector — read-only Google Sheets connector; requires brain_ds[gsheets]
"""
from .base import ReadOnlyConnector
from .sqlite_connector import SQLiteConnector
from .csv_connector import CsvConnector
from .google_sheets_connector import GoogleSheetsConnector
from .postgres_connector import PostgresConnector

__all__ = [
    "ReadOnlyConnector",
    "SQLiteConnector",
    "CsvConnector",
    "GoogleSheetsConnector",
    "PostgresConnector",
]
