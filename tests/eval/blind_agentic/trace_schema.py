from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


TRACE_VERSION = "2026-06-27.pr1"
TRACE_ROLES = {"verifier", "orchestrator", "subagent", "tool", "user", "system"}


class TraceSchemaError(ValueError):
    """Raised when a trace/session export cannot be normalized."""


@dataclass(frozen=True)
class TraceEvent:
    ts: str
    role: str
    agent_name: str | None = None
    action: str = "message"
    target: str | None = None
    content_ref: str | None = None
    tool_name: str | None = None
    delegated_by: str | None = None
    pathway_milestone: str | None = None

    def __post_init__(self) -> None:
        if self.role not in TRACE_ROLES:
            raise TraceSchemaError(f"Unsupported role: {self.role}")


@dataclass(frozen=True)
class SessionTrace:
    trace_version: str
    run_id: str
    scenario: str
    pathway_id: str
    model_provider: str | None
    model: str | None
    created_at_utc: str
    events: list[TraceEvent]
    freshness: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.trace_version != TRACE_VERSION:
            raise TraceSchemaError(f"Unsupported trace_version: {self.trace_version}")
        if not self.run_id:
            raise TraceSchemaError("run_id is required")
        if not self.scenario:
            raise TraceSchemaError("scenario is required")
        if not self.pathway_id:
            raise TraceSchemaError("pathway_id is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def parse_opencode_export(
    export_root: Path | str,
    *,
    scenario: str,
    run_id: str,
    pathway_id: str,
    model_provider: str | None = None,
    model: str | None = None,
) -> tuple[SessionTrace, list[dict[str, str]]]:
    """Normalize OpenCode exported JSON/JSONL artifacts into a typed session trace."""

    root = Path(export_root)
    records, omissions = _read_export_records(root)
    events: list[TraceEvent] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            omissions.append({"artifact": "opencode_record", "reason": f"record {index} is not an object"})
            continue
        try:
            events.append(_record_to_event(record, index=index, root=root))
        except TraceSchemaError as exc:
            omissions.append({"artifact": "opencode_record", "reason": f"record {index}: {str(exc).lower()}"})
    if not events:
        omissions.append({"artifact": "session_trace", "reason": "no traceable OpenCode records found"})

    trace = SessionTrace(
        trace_version=TRACE_VERSION,
        run_id=run_id,
        scenario=scenario,
        pathway_id=pathway_id,
        model_provider=model_provider,
        model=model,
        created_at_utc=_deterministic_created_at(events),
        events=events,
        freshness={"status": "not_checked", "schema_version": TRACE_VERSION},
    )
    return trace, omissions


def _deterministic_created_at(events: list[TraceEvent]) -> str:
    for event in events:
        if not event.ts.startswith("event-"):
            return event.ts
    return "1970-01-01T00:00:00+00:00"


def write_session_trace(trace: SessionTrace, target: Path) -> dict[str, str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = trace.to_json() + "\n"
    target.write_text(payload, encoding="utf-8")
    return {"path": target.as_posix(), "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest()}


def _read_export_records(root: Path) -> tuple[list[Any], list[dict[str, str]]]:
    records: list[Any] = []
    omissions: list[dict[str, str]] = []
    for source in sorted(root.rglob("*")):
        if not source.is_file() or source.suffix.lower() not in {".json", ".jsonl", ".ndjson"}:
            continue
        try:
            if source.suffix.lower() == ".json":
                parsed = json.loads(source.read_text(encoding="utf-8"))
                if isinstance(parsed, list):
                    records.extend(parsed)
                elif isinstance(parsed, dict):
                    records.extend(_extract_records_from_object(parsed))
                else:
                    omissions.append({"artifact": source.as_posix(), "reason": "JSON root is not an object/list"})
            else:
                for line in source.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            omissions.append({"artifact": source.as_posix(), "reason": f"invalid JSON: {exc.msg}"})
    return records, omissions


def _extract_records_from_object(parsed: dict[str, Any]) -> list[Any]:
    for key in ("events", "messages", "items", "records"):
        value = parsed.get(key)
        if isinstance(value, list):
            return value
    return [parsed]


def _record_to_event(record: dict[str, Any], *, index: int, root: Path) -> TraceEvent:
    agent_name = _optional_text(record, "agent_name") or _optional_text(record, "agent") or _optional_text(record, "name")
    tool_name = _optional_text(record, "tool_name") or _optional_text(record, "tool")
    role = _normalize_role(_optional_text(record, "role"), agent_name=agent_name, tool_name=tool_name)
    action = _optional_text(record, "action") or _infer_action(record, role)
    content_ref = _content_ref(record, index=index, root=root)
    return TraceEvent(
        ts=_optional_text(record, "ts") or _optional_text(record, "timestamp") or f"event-{index:04d}",
        role=role,
        agent_name=agent_name,
        action=action,
        target=_optional_text(record, "target"),
        content_ref=content_ref,
        tool_name=tool_name,
        delegated_by=_optional_text(record, "delegated_by") or _optional_text(record, "parent_agent"),
        pathway_milestone=_optional_text(record, "pathway_milestone") or _optional_text(record, "milestone"),
    )


def _normalize_role(role: str | None, *, agent_name: str | None, tool_name: str | None) -> str:
    normalized = (role or "").casefold().replace("-", "_")
    agent = (agent_name or "").casefold()
    if tool_name or normalized in {"tool", "tool_call", "tool_result", "tool_response"}:
        return "tool"
    if normalized in {"user", "system", "verifier", "orchestrator", "subagent"}:
        return normalized
    if agent == "brainds-orchestrator":
        return "orchestrator"
    if agent.startswith("brainds-"):
        return "subagent"
    if "verifier" in agent:
        return "verifier"
    return "verifier" if normalized in {"assistant", ""} else normalized


def _infer_action(record: dict[str, Any], role: str) -> str:
    if role == "tool":
        return "tool_call" if record.get("arguments") or record.get("input") else "tool_response"
    if record.get("delegated_by") or record.get("parent_agent"):
        return "delegated_message"
    return "message"


def _content_ref(record: dict[str, Any], *, index: int, root: Path) -> str | None:
    for key in ("content_ref", "path", "file"):
        value = _optional_text(record, key)
        if value:
            return value
    if "content" not in record:
        return None
    digest = hashlib.sha256(json.dumps(record["content"], sort_keys=True).encode("utf-8")).hexdigest()
    return f"opencode:event-{index:04d}:{digest[:12]}"


def _optional_text(record: dict[str, Any], key: str) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None
