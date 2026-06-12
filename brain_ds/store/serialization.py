"""Serialization helpers for JSON and embedding vectors."""

from __future__ import annotations

import json
import struct
from typing import Any, Sequence

from .errors import CorruptVectorError


def encode_json(value: Any) -> str:
    """Encode object as deterministic JSON text."""

    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def decode_json(value: str | None) -> Any:
    """Decode JSON text to Python object, handling nullish values."""

    if value in (None, ""):
        return None
    return json.loads(str(value))


def encode_vector(vector: Sequence[float]) -> bytes:
    """Pack vector to little-endian float32 bytes."""

    return struct.pack(f"<{len(vector)}f", *vector)


def decode_vector(buffer: bytes, *, dimensions: int) -> list[float]:
    """Unpack little-endian float32 bytes to a vector."""

    expected_size = dimensions * 4
    if len(buffer) != expected_size:
        raise CorruptVectorError(
            f"Vector byte-length {len(buffer)} does not match dimensions={dimensions}"
        )
    unpacked = struct.unpack(f"<{dimensions}f", buffer)
    return list(unpacked)
