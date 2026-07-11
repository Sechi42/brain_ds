"""Direct Google Sheets API profile helpers."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse


PROFILE_FIELDS = (
    "spreadsheetId,properties.title,"
    "sheets.properties,sheets.charts,sheets.protectedRanges,"
    "sheets.filterViews,sheets.developerMetadata"
)

DEFAULT_PROFILE_RANGE = "A1:T51"
PROFILE_SAMPLE_ROW_LIMIT = 50
PROFILE_SAMPLE_COLUMN_LIMIT = 20


def _validation_error(message: str):
    from brain_ds.mcp.security import ValidationError

    return ValidationError(message=message)


@dataclass
class SheetGrid:
    row_count: int = 0
    column_count: int = 0
    hidden: bool = False
    frozen_row_count: int = 0
    frozen_column_count: int = 0
    hide_gridlines: bool = False


@dataclass
class SheetProfile:
    spreadsheet_id: str
    gid: str
    title: str
    index: int
    grid: dict[str, Any]
    headers: list[str]
    detected_ranges: list[dict[str, Any]] = field(default_factory=list)
    samples: list[dict[str, Any]] = field(default_factory=list)
    formulas: list[dict[str, Any]] = field(default_factory=list)
    charts: list[dict[str, Any]] = field(default_factory=list)
    protected_ranges: list[dict[str, Any]] = field(default_factory=list)
    filter_views: list[dict[str, Any]] = field(default_factory=list)
    pivots: list[dict[str, Any]] = field(default_factory=list)
    developer_metadata: list[dict[str, Any]] = field(default_factory=list)
    safety: dict[str, Any] = field(default_factory=dict)
    escalation_flags: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_google_sheet_url(url: str) -> dict[str, str]:
    """Extract spreadsheet_id and optional gid from a Google Sheets URL."""
    if not isinstance(url, str) or not url.strip():
        raise _validation_error("spreadsheet_url must be a non-empty string")
    parsed = urlparse(url.strip())
    parts = [part for part in parsed.path.split("/") if part]
    try:
        spreadsheets_index = parts.index("spreadsheets")
    except ValueError as exc:
        raise _validation_error("spreadsheet_url must contain /spreadsheets/d/{spreadsheetId}") from exc
    if len(parts) <= spreadsheets_index + 2 or parts[spreadsheets_index + 1] != "d":
        raise _validation_error("spreadsheet_url must contain /spreadsheets/d/{spreadsheetId}")
    spreadsheet_id = parts[spreadsheets_index + 2].strip()
    if not spreadsheet_id:
        raise _validation_error("spreadsheet_url is missing spreadsheet_id")
    query_gid = parse_qs(parsed.query).get("gid", [""])[0]
    fragment_gid = parse_qs(parsed.fragment).get("gid", [""])[0]
    result = {"spreadsheet_id": spreadsheet_id}
    if fragment_gid or query_gid:
        result["gid"] = fragment_gid or query_gid
    return result


def build_sheets_service(service_account_info: dict[str, Any]) -> Any:
    """Build a read-only Google Sheets API service lazily."""
    try:
        from google.oauth2 import service_account  # type: ignore[import-untyped]
        from googleapiclient.discovery import build  # type: ignore[import-untyped]
    except ImportError as exc:
        raise _validation_error("google-api-python-client and google-auth are required for Google Sheets API exploration") from exc
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


class GoogleSheetsApiClient:
    """Thin fakeable boundary around read-only Sheets API calls."""

    def __init__(
        self,
        service_account_info: dict[str, Any],
        *,
        builder: Callable[[dict[str, Any]], Any] | None = None,
        formula_builder: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self._service = (builder or build_sheets_service)(service_account_info)
        self._formula_service = (formula_builder or builder or build_sheets_service)(service_account_info)

    def metadata(self, spreadsheet_id: str) -> dict[str, Any]:
        return (
            self._service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, includeGridData=False, fields=PROFILE_FIELDS)
            .execute()
        )

    def values(self, spreadsheet_id: str, ranges: list[str], *, formula: bool = False) -> dict[str, list[list[Any]]]:
        service = self._formula_service if formula else self._service
        request = service.spreadsheets().values().batchGet(
            spreadsheetId=spreadsheet_id,
            ranges=ranges,
            majorDimension="ROWS",
            valueRenderOption="FORMULA" if formula else "UNFORMATTED_VALUE",
        )
        response = request.execute()
        return {str(item.get("range") or ""): item.get("values", []) for item in response.get("valueRanges", [])}


def profile_workbook(
    api_client: GoogleSheetsApiClient,
    spreadsheet_id: str,
    *,
    default_range: str = DEFAULT_PROFILE_RANGE,
) -> dict[str, Any]:
    metadata = api_client.metadata(spreadsheet_id)
    sheets = metadata.get("sheets", [])
    ranges = [_range_for_sheet_metadata(sheet, default_range) for sheet in sheets]
    display_values = api_client.values(spreadsheet_id, ranges)
    formula_values = api_client.values(spreadsheet_id, ranges, formula=True)
    profiles = [
        map_sheet_profile(metadata, sheet, display_values, formula_values, default_range=default_range).to_dict()
        for sheet in sheets
    ]
    return {
        "spreadsheet_id": str(metadata.get("spreadsheetId") or spreadsheet_id),
        "title": str((metadata.get("properties") or {}).get("title") or ""),
        "sheets": profiles,
    }


def map_sheet_profile(
    workbook: dict[str, Any],
    sheet: dict[str, Any],
    display_values_by_range: dict[str, list[list[Any]]],
    formula_values_by_range: dict[str, list[list[Any]]],
    *,
    default_range: str = DEFAULT_PROFILE_RANGE,
) -> SheetProfile:
    props = sheet.get("properties") or {}
    title = str(props.get("title") or "")
    grid = _map_grid(props)
    range_name = _range_for_sheet_metadata(sheet, default_range)
    rows = display_values_by_range.get(range_name, [])
    formula_rows = formula_values_by_range.get(range_name, [])
    headers = [str(value) for value in (rows[0] if rows else [])]
    data_rows = rows[1:]
    limitations = ["Apps Script metadata is unavailable from the Sheets API profile"]
    if not rows:
        limitations.append(f"No values returned for range {range_name}")
    escalation_flags = _escalation_flags(grid)
    if "row_sample_truncated" in escalation_flags:
        limitations.append("Row sample truncated; request explicit escalation for deeper reads")
    if "column_sample_truncated" in escalation_flags:
        limitations.append("Column sample truncated; request explicit escalation for wider reads")
    return SheetProfile(
        spreadsheet_id=str(workbook.get("spreadsheetId") or ""),
        gid=str(props.get("sheetId") or ""),
        title=title,
        index=int(props.get("index") or 0),
        grid=asdict(grid),
        headers=headers,
        detected_ranges=[
            {
                "range": range_name,
                "row_count": len(rows),
                "column_count": len(headers),
                "sampled_row_cap": _sample_row_count(grid),
                "sampled_column_cap": _sample_column_count(grid),
            }
        ],
        samples=_sample_rows(headers, data_rows),
        formulas=_formula_cells(headers, formula_rows),
        charts=_charts(sheet.get("charts", [])),
        protected_ranges=_protected_ranges(sheet.get("protectedRanges", [])),
        filter_views=_filter_views(sheet.get("filterViews", [])),
        pivots=[],
        developer_metadata=_developer_metadata(sheet.get("developerMetadata", [])),
        safety=_safety_flags(props, sheet),
        escalation_flags=escalation_flags,
        limitations=limitations,
        provenance={
            "source": "google-sheets-api",
            "metadata_fields": PROFILE_FIELDS,
            "value_render_options": ["UNFORMATTED_VALUE", "FORMULA"],
        },
    )


def _range_for_sheet(title: str, default_range: str) -> str:
    return f"{_quote_sheet_title(title)}!{default_range}" if "!" not in default_range else default_range


def _range_for_sheet_metadata(sheet: dict[str, Any], default_range: str) -> str:
    props = sheet.get("properties") or {}
    title = str(props.get("title") or "")
    if not title:
        return default_range
    grid = _map_grid(props)
    end_column = _column_label(_sample_column_count(grid))
    end_row = _sample_row_count(grid)
    return f"{_quote_sheet_title(title)}!A1:{end_column}{end_row}"


def _sample_row_count(grid: SheetGrid) -> int:
    if grid.row_count <= 0:
        return 1
    return min(grid.row_count, PROFILE_SAMPLE_ROW_LIMIT + 1)


def _sample_column_count(grid: SheetGrid) -> int:
    if grid.column_count <= 0:
        return 1
    return min(grid.column_count, PROFILE_SAMPLE_COLUMN_LIMIT)


def _column_label(index: int) -> str:
    label = ""
    current = max(1, index)
    while current:
        current, remainder = divmod(current - 1, 26)
        label = chr(ord("A") + remainder) + label
    return label


def _quote_sheet_title(title: str) -> str:
    if title.replace("_", "").isalnum():
        return title
    escaped = title.replace("'", "''")
    return f"'{escaped}'"


def _map_grid(props: dict[str, Any]) -> SheetGrid:
    grid = props.get("gridProperties") or {}
    return SheetGrid(
        row_count=int(grid.get("rowCount") or 0),
        column_count=int(grid.get("columnCount") or 0),
        hidden=bool(props.get("hidden", False)),
        frozen_row_count=int(grid.get("frozenRowCount") or 0),
        frozen_column_count=int(grid.get("frozenColumnCount") or 0),
        hide_gridlines=bool(grid.get("hideGridlines", False)),
    )


def _safety_flags(props: dict[str, Any], sheet: dict[str, Any]) -> dict[str, Any]:
    return {
        "hidden": bool(props.get("hidden", False)),
        "protected_range_count": len(sheet.get("protectedRanges", []) or []),
        "filter_view_count": len(sheet.get("filterViews", []) or []),
        "has_developer_metadata": bool(sheet.get("developerMetadata", [])),
    }


def _escalation_flags(grid: SheetGrid) -> list[str]:
    flags: list[str] = []
    if grid.row_count > PROFILE_SAMPLE_ROW_LIMIT + 1:
        flags.append("row_sample_truncated")
    if grid.column_count > PROFILE_SAMPLE_COLUMN_LIMIT:
        flags.append("column_sample_truncated")
    return flags


def _sample_rows(headers: list[str], rows: list[list[Any]], limit: int = PROFILE_SAMPLE_ROW_LIMIT) -> list[dict[str, Any]]:
    return [dict(zip(headers, row)) for row in rows[:limit]]


def _formula_cells(headers: list[str], rows: list[list[Any]]) -> list[dict[str, Any]]:
    formulas: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows[1:], start=2):
        for col_index, value in enumerate(row):
            if isinstance(value, str) and value.startswith("="):
                formulas.append(
                    {
                        "row": row_index,
                        "column": headers[col_index] if col_index < len(headers) else str(col_index + 1),
                        "formula": value,
                    }
                )
    return formulas


def _charts(charts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"chart_id": chart.get("chartId"), "title": (chart.get("spec") or {}).get("title", "")} for chart in charts]


def _protected_ranges(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "protected_range_id": item.get("protectedRangeId"),
            "description": item.get("description", ""),
            "range": item.get("range", {}),
        }
        for item in items
    ]


def _filter_views(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"filter_view_id": item.get("filterViewId"), "title": item.get("title", "")} for item in items]


def _developer_metadata(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "metadata_id": item.get("metadataId"),
            "key": item.get("metadataKey", ""),
            "value": item.get("metadataValue", ""),
        }
        for item in items
    ]
