"""Read-only Google Sheets connector.

Connects via direct Google Sheets API when configured, with the legacy gspread
path retained for older callers. Enforces read-only access structurally — the
connector class exposes NO write methods whatsoever.

Row caps (matching sqlite_connector):
  - preview() cap: 50 rows

Credentials are held in-memory only and never written to logs or
responses (INV-1). ``describe()`` deliberately excludes
``service_account_info`` from its output.

list_containers() returns a single-entry list with the spreadsheet title.
list_tables()     returns worksheet tab titles.
get_table_schema()returns the header row as columns + inferred type from
                  the first data row.
preview()         returns first N rows (capped at 50) as dicts keyed by
                  header column name.
"""
from __future__ import annotations

import json
from typing import Any

from brain_ds.connectors.sqlite_connector import _PREVIEW_ROW_CAP

from .base import ReadOnlyConnector
from .google_sheets_api import DEFAULT_PROFILE_RANGE, GoogleSheetsApiClient, profile_workbook

# Install hint raised when gspread is not installed.
_GSPREAD_HINT = (
    "gspread is not installed. "
    "Run `pip install brain_ds[gsheets]` to enable Google Sheets exploration."
)


def _lazy_gspread():
    """Import gspread lazily; raise ImportError with install hint if absent."""
    try:
        import gspread  # type: ignore[import-untyped]

        return gspread
    except ImportError as exc:
        raise ImportError(_GSPREAD_HINT) from exc


def _infer_type(value: str) -> str:
    """Infer a simple column type from a string sample value."""
    if not value:
        return "string"
    # Try integer
    try:
        int(value)
        return "integer"
    except ValueError:
        pass
    # Try float
    try:
        float(value)
        return "number"
    except ValueError:
        pass
    return "string"


class GoogleSheetsConnector(ReadOnlyConnector):
    """Read-only connector for Google Sheets spreadsheets.

    Implements the ``ReadOnlyConnector`` ABC (5 methods:
    describe/list_containers/list_tables/get_table_schema/preview).

    Connection params dict:
      - service_account_info : full SA JSON dict (in-memory only, never logged)
      - spreadsheet_id       : Google Sheets spreadsheet ID
      - sheet_range          : default cell range (e.g. ``Sheet1!A1:Z``)
    """

    def __init__(self, params: dict[str, Any]) -> None:
        self._params = params
        self._spreadsheet_id = params["spreadsheet_id"]
        self._sheet_range = params.get("sheet_range", "")
        service_account_info = self._service_account_info(params)
        self._use_direct_api = bool(params.get("use_direct_api") or params.get("api_builder"))
        self._api_profile: dict[str, Any] | None = None
        if self._use_direct_api:
            self._gc = None
            self._api_client = GoogleSheetsApiClient(
                service_account_info,
                builder=params.get("api_builder"),
                formula_builder=params.get("formula_api_builder"),
            )
        else:
            # Authenticate once at init via gspread (lazy import).
            gspread = _lazy_gspread()
            self._gc = gspread.service_account_from_dict(service_account_info)
            self._api_client = None

    @staticmethod
    def _service_account_info(params: dict[str, Any]) -> dict[str, Any]:
        info = params.get("service_account_info")
        if isinstance(info, dict):
            return info
        raw_json = params.get("service_account_json")
        if isinstance(raw_json, str):
            loaded = json.loads(raw_json)
            if isinstance(loaded, dict):
                return loaded
        raise KeyError("service_account_info")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _open_spreadsheet(self):
        """Open and return the gspread Spreadsheet object."""
        if self._gc is None:
            raise RuntimeError("gspread spreadsheet is unavailable for direct API connector")
        return self._gc.open_by_key(self._spreadsheet_id)

    def _workbook_profile(self) -> dict[str, Any]:
        if self._api_profile is None:
            if self._api_client is None:
                raise RuntimeError("direct Google Sheets API profile is unavailable")
            if "!" in self._sheet_range:
                default_range = self._sheet_range.split("!", 1)[1]
            else:
                default_range = self._sheet_range or DEFAULT_PROFILE_RANGE
            self._api_profile = profile_workbook(
                self._api_client,
                self._spreadsheet_id,
                default_range=default_range,
            )
        return self._api_profile

    def _sheet_profiles(self) -> list[dict[str, Any]]:
        return list(self._workbook_profile().get("sheets", []))

    def sheet_profile(self, table: str) -> dict[str, Any]:
        """Return the rich profile for one worksheet tab."""
        for profile in self._sheet_profiles():
            if profile.get("title") == table or profile.get("gid") == str(table):
                return profile
        raise KeyError(f"Worksheet not found: {table}")

    # ------------------------------------------------------------------
    # ReadOnlyConnector ABC
    # ------------------------------------------------------------------

    def describe(self) -> dict[str, Any]:
        """Return source-level metadata. Never includes credentials."""
        if self._use_direct_api:
            workbook = self._workbook_profile()
            title = workbook.get("title", "")
            return {
                "kind": "google-sheets",
                "spreadsheet_id": self._spreadsheet_id,
                "title": title,
                "url": f"https://docs.google.com/spreadsheets/d/{self._spreadsheet_id}",
                "sheet_range": self._sheet_range,
                "profile": {
                    "sheet_count": len(workbook.get("sheets", [])),
                    "provenance": "google-sheets-api",
                },
                "description": f"Google Sheets spreadsheet '{title}'",
            }
        ss = self._open_spreadsheet()
        return {
            "kind": "google-sheets",
            "spreadsheet_id": self._spreadsheet_id,
            "title": ss.title,
            "url": ss.url,
            "sheet_range": self._sheet_range,
            "description": f"Google Sheets spreadsheet '{ss.title}'",
            # INV-1: service_account_info is deliberately absent
        }

    def list_containers(self) -> list[str]:
        """Return the spreadsheet title as the single container.

        A spreadsheet is the top-level container. There is always exactly one.
        """
        if self._use_direct_api:
            return [str(self._workbook_profile().get("title") or "")]
        ss = self._open_spreadsheet()
        return [ss.title]

    def list_tables(self, container: str) -> list[str]:
        """Return worksheet tab titles within the spreadsheet."""
        if self._use_direct_api:
            return [str(profile.get("title") or "") for profile in self._sheet_profiles()]
        ss = self._open_spreadsheet()
        # gspread: Spreadsheet.worksheets() is a method, not a property.
        return [ws.title for ws in ss.worksheets()]

    def get_table_schema(self, container: str, table: str) -> dict[str, Any]:
        """Return schema from the worksheet's header row.

        The header row (row 1) provides column names. The first data row
        (row 2) is used to infer column types.

        Returns a dict with:
          - columns: list of {name, type, sample, meaning} dicts
          - row_count_estimate: -1 (Google Sheets does not expose a cheap row count)
        """
        if self._use_direct_api:
            profile = self.sheet_profile(table)
            samples = profile.get("samples", [])
            sample_row = samples[0] if samples else {}
            return {
                "columns": [
                    {
                        "name": header,
                        "type": _infer_type(str(sample_row.get(header, ""))),
                        "sample": sample_row.get(header),
                        "meaning": "",
                    }
                    for header in profile.get("headers", [])
                ],
                "row_count_estimate": profile.get("grid", {}).get("row_count", -1),
                "profile": profile,
            }
        ss = self._open_spreadsheet()
        ws = ss.worksheet(table)
        all_rows = ws.get_all_values()

        if not all_rows:
            return {"columns": [], "row_count_estimate": -1}

        header = all_rows[0]
        data_row = all_rows[1] if len(all_rows) > 1 else []

        columns = []
        for i, col_name in enumerate(header):
            sample = data_row[i] if i < len(data_row) else None
            col_type = _infer_type(sample) if sample is not None else "string"
            columns.append(
                {
                    "name": col_name,
                    "type": col_type,
                    "sample": sample,
                    "meaning": "",
                }
            )

        return {
            "columns": columns,
            "row_count_estimate": -1,  # no cheap row count in Sheets API
        }

    def preview(self, container: str, table: str, limit: int = 5) -> dict[str, Any]:
        """Return up to min(limit, 50) rows from the worksheet.

        The header row is used for column names; data rows follow.
        No write operation is performed.
        """
        capped = min(max(1, limit), _PREVIEW_ROW_CAP)

        if self._use_direct_api:
            profile = self.sheet_profile(table)
            samples = list(profile.get("samples", []))
            data_row_count = max(0, int((profile.get("detected_ranges") or [{}])[0].get("row_count") or 0) - 1)
            if not self._sheet_range:
                data_row_count = max(data_row_count, int(profile.get("grid", {}).get("row_count") or 0) - 1)
            truncated = data_row_count > capped
            return {
                "columns": list(profile.get("headers", [])),
                "rows": samples[:capped],
                "truncated": truncated,
                "profile": profile,
            }

        ss = self._open_spreadsheet()
        ws = ss.worksheet(table)
        all_rows = ws.get_all_values()

        if not all_rows:
            return {"columns": [], "rows": [], "truncated": False}

        header = all_rows[0]
        data_rows = all_rows[1:]  # exclude header

        truncated = len(data_rows) > capped
        data_rows = data_rows[:capped]

        return {
            "columns": header,
            "rows": [dict(zip(header, row)) for row in data_rows],
            "truncated": truncated,
        }
