"""Read-only external data-source connectors for brain_ds.

All connectors implement the ReadOnlyConnector ABC. The API surface has no
write methods — read-only enforcement is structural, not policy.

Supported:
- SQLiteConnector  — opens databases in URI mode=ro + PRAGMA query_only=ON
- CsvConnector     — reads CSV/TSV files with encoding="utf-8-sig" and sniffed delimiter

Google Sheets exploration is delegated to the agent layer via MCP Google Drive
read tools (mcp__claude_ai_Google_Drive__*). Exported Google Sheets CSV files
can be read through CsvConnector.
"""
from .base import ReadOnlyConnector
from .sqlite_connector import SQLiteConnector
from .csv_connector import CsvConnector

__all__ = ["ReadOnlyConnector", "SQLiteConnector", "CsvConnector"]
