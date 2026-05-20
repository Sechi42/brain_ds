"""Workspace localStorage contract helpers for tabs/history.

Production-adjacent source of truth for R08 tab/history contract semantics.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, fields

TABS_STORAGE_KEY = "brain_ds.workspace.tabs.v1"
HISTORY_STORAGE_KEY = "brain_ds.workspace.history.v1"
HISTORY_MAX_ENTRIES = 50
LOCKED_UTC_SECONDS_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"


@dataclass(frozen=True)
class TabModel:
    id: str
    label: str
    graphPath: str
    active: bool
    closeable: bool
    openedAt: str


TAB_MODEL_FIELDS = tuple(field.name for field in fields(TabModel))


def _is_tab_model_payload(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    return (
        isinstance(item.get("id"), str)
        and isinstance(item.get("label"), str)
        and isinstance(item.get("graphPath"), str)
        and isinstance(item.get("active"), bool)
        and isinstance(item.get("closeable"), bool)
        and isinstance(item.get("openedAt"), str)
    )


def load_tabs_payload(raw: str | None, logger: logging.Logger | None = None) -> tuple[list[TabModel], bool]:
    """Parse persisted tabs payload.

    Returns (tabs, should_reset_storage). For malformed JSON or wrong shape,
    returns ([], True) and logs an error.
    """

    if raw is None:
        return [], False

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        if logger is not None:
            logger.error("Malformed tabs payload for %s; resetting to []", TABS_STORAGE_KEY)
        return [], True

    if not isinstance(parsed, list) or not all(_is_tab_model_payload(item) for item in parsed):
        if logger is not None:
            logger.error("Invalid tabs payload shape for %s; resetting to []", TABS_STORAGE_KEY)
        return [], True

    return [TabModel(**item) for item in parsed], False


def parse_history_payload(raw: str | None, max_entries: int = HISTORY_MAX_ENTRIES) -> list[str]:
    """Parse persisted history as bounded list of POSIX path strings."""

    if raw is None:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []

    strings_only = [entry for entry in parsed if isinstance(entry, str)]
    return strings_only[:max_entries]


def serialize_tabs(tabs: list[TabModel]) -> str:
    return json.dumps([asdict(tab) for tab in tabs], ensure_ascii=False)
