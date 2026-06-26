"""Shared deterministic dossier serialization utilities."""

from __future__ import annotations

import json
from typing import Any

MAX_PAYLOAD_BYTES = 256 * 1024
TRUNCATED_TEXT_BYTES = 1024
TRUNCATED_DETAIL_BYTES = 512


def payload_size(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def truncate_text(value: str, max_chars: int) -> str:
    text = str(value)
    return text if len(text) <= max_chars else text[:max_chars] + "…"
