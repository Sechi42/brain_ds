from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


TRACE_VERSION = "2026-06-27.pr1"
REPORT_SCHEMA_VERSION = "2026-06-30.pr3"
TRACE_ROLES = {"verifier", "orchestrator", "subagent", "tool", "user", "system"}
SESSION_ID_ALIASES = ("sessionID", "session_id", "session.id", "id")
PARENT_SESSION_ID_ALIASES = (
    "ParentSessionID",
    "parentSessionID",
    "parent_session_id",
    "parentID",
    "parent_id",
)


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
    source_path: str | None = None
    session_id: str | None = None
    text_hash: str | None = None
    tool_status: str | None = None
    tool_output_present: bool = False
    tool_command: str | None = None

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
    if records and not any(
        isinstance(record, dict) and _is_known_opencode_record(record) for record in records
    ):
        raise TraceSchemaError(
            "unknown OpenCode export schema: no recognized session, agent, message, or tool fields"
        )
    agent_by_session = _agent_by_session(records)
    delegated_by_session = _delegated_by_session(records, agent_by_session)
    _validate_export_record_contract(records, agent_by_session)
    events: list[TraceEvent] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            omissions.append(
                {"artifact": "opencode_record", "reason": f"record {index} is not an object"}
            )
            continue
        try:
            events.extend(
                _record_to_events(
                    record,
                    index=index,
                    root=root,
                    agent_by_session=agent_by_session,
                    delegated_by_session=delegated_by_session,
                )
            )
        except TraceSchemaError as exc:
            omissions.append(
                {"artifact": "opencode_record", "reason": f"record {index}: {str(exc).lower()}"}
            )
    if not events:
        omissions.append(
            {"artifact": "session_trace", "reason": "no traceable OpenCode records found"}
        )

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
    return {
        "path": target.as_posix(),
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def _read_export_records(root: Path) -> tuple[list[Any], list[dict[str, str]]]:
    records: list[Any] = []
    omissions: list[dict[str, str]] = []
    for source in sorted(root.rglob("*")):
        if not source.is_file() or not _is_transcript_source(source):
            continue
        try:
            if source.suffix.lower() == ".log":
                records.extend(_parse_opencode_stderr(source, root=root))
            elif source.suffix.lower() == ".json":
                parsed = json.loads(source.read_text(encoding="utf-8"))
                if isinstance(parsed, list):
                    records.extend(_with_source(item, source, root) for item in parsed)
                elif isinstance(parsed, dict):
                    records.extend(
                        _with_source(item, source, root)
                        for item in _extract_records_from_object(parsed)
                    )
                else:
                    omissions.append(
                        {"artifact": source.as_posix(), "reason": "JSON root is not an object/list"}
                    )
            else:
                for line in source.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        records.append(_with_source(json.loads(line), source, root))
        except json.JSONDecodeError as exc:
            omissions.append({"artifact": source.as_posix(), "reason": f"invalid JSON: {exc.msg}"})
    records = [
        record
        for index, record in sorted(
            enumerate(records), key=lambda item: _record_chronology_key(item[1], item[0])
        )
    ]
    return records, omissions


def _record_chronology_key(
    record: Any, fallback_index: int
) -> tuple[int, float | str | int, float | int, int]:
    if not isinstance(record, dict):
        return (3, fallback_index, fallback_index, fallback_index)
    sequence = _record_sequence_value(record, fallback_index)
    for key in ("timestamp", "ts", "time", "created_at", "createdAt"):
        value = record.get(key)
        if value is None:
            continue
        numeric = _numeric_chronology_value(value)
        if numeric is not None:
            return (0, numeric, sequence, fallback_index)
        text = str(value).strip()
        if text:
            return (1, text, sequence, fallback_index)
    if sequence != fallback_index:
        return (2, sequence, fallback_index, fallback_index)
    return (3, fallback_index, fallback_index, fallback_index)


def _record_sequence_value(record: dict[str, Any], fallback_index: int) -> float | int:
    for key in ("sequence", "seq", "index"):
        numeric = _numeric_chronology_value(record.get(key))
        if numeric is not None:
            return numeric
    return fallback_index


def _numeric_chronology_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000
            except ValueError:
                return None
    return None


def _is_transcript_source(source: Path) -> bool:
    name = source.name.lower()
    if source.suffix.lower() == ".log":
        return name.startswith("opencode") and "stderr" in name
    if source.suffix.lower() not in {".json", ".jsonl", ".ndjson"}:
        return False
    if name.startswith("opencode-stdout"):
        return True
    return name in {"transcript.json", "transcript.jsonl", "session.json", "session.jsonl"}


def _with_source(record: Any, source: Path, root: Path) -> Any:
    if isinstance(record, dict):
        copy = dict(record)
        copy.setdefault("_source_path", source.relative_to(root).as_posix())
        return copy
    return record


def _parse_opencode_stderr(source: Path, *, root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for entry in _stderr_entries(source.read_text(encoding="utf-8")):
        agent = _line_value(entry, "agent")
        if not agent:
            continue
        if "message=stream" in entry:
            records.append(
                {
                    "type": "opencode_stream",
                    "timestamp": _line_value(entry, "timestamp"),
                    "sessionID": _line_value(entry, "session.id"),
                    "agent_name": agent,
                    "action": "agent_stream",
                    "_source_path": source.relative_to(root).as_posix(),
                }
            )
        elif "message=created" in entry:
            records.append(
                {
                    "type": "opencode_session",
                    "timestamp": _line_value(entry, "timestamp"),
                    "sessionID": _line_value(entry, "id"),
                    "agent_name": agent,
                    "parent_session_id": _line_value(entry, "parentID"),
                    "action": "session_created",
                    "_source_path": source.relative_to(root).as_posix(),
                }
            )
    return records


def _stderr_entries(text: str) -> list[str]:
    entries: list[str] = []
    current: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        starts_record = "timestamp=" in line and " level=" in line
        if starts_record and current:
            entries.append(" ".join(current))
            current = []
        if starts_record or current:
            current.append(line)
    if current:
        entries.append(" ".join(current))
    return entries


def _line_value(line: str, key: str) -> str | None:
    match = re.search(rf"(?:^|\s){re.escape(key)}=(\"[^\"]*\"|\S+)", line)
    if not match:
        return None
    value = match.group(1)
    return value[1:-1] if value.startswith('"') and value.endswith('"') else value


def _agent_by_session(records: list[Any]) -> dict[str, str]:
    agents: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        session_id = _session_id(record)
        agent = _optional_text(record, "agent_name") or _optional_text(record, "agent")
        if session_id and agent and not _is_metadata_agent(agent) and session_id not in agents:
            agents[session_id] = agent
    return agents


def _delegated_by_session(records: list[Any], agent_by_session: dict[str, str]) -> dict[str, str]:
    delegated: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict) or record.get("type") != "opencode_session":
            continue
        session_id = _session_id(record)
        parent_session_id = _parent_session_id(record)
        parent_agent = agent_by_session.get(parent_session_id or "")
        if session_id and parent_agent:
            delegated[session_id] = parent_agent
    return delegated


def _extract_records_from_object(parsed: dict[str, Any]) -> list[Any]:
    if isinstance(parsed.get("info"), dict) and isinstance(parsed.get("messages"), list):
        return _extract_records_from_info_messages_envelope(parsed)
    for key in ("events", "messages", "items", "records"):
        value = parsed.get(key)
        if isinstance(value, list):
            return value
    return [parsed]


def _extract_records_from_info_messages_envelope(parsed: dict[str, Any]) -> list[Any]:
    session_info = _optional_dict(parsed, "info")
    records: list[Any] = []
    session_id = _optional_text(session_info, "id")
    agent = _optional_text(session_info, "agent")
    if session_id and agent:
        records.append(
            {
                "type": "opencode_session",
                "timestamp": _time_value(session_info),
                "sessionID": session_id,
                "agent_name": agent,
                "action": "session_created",
            }
        )
    for message in parsed.get("messages", []):
        if isinstance(message, dict):
            records.extend(_records_from_message(message, session_info=session_info))
    return records


def _records_from_message(
    message: dict[str, Any], *, session_info: dict[str, Any]
) -> list[dict[str, Any]]:
    message_info = _optional_dict(message, "info")
    inherited = {
        "timestamp": _time_value(message_info),
        "sessionID": _optional_text(message_info, "sessionID")
        or _optional_text(session_info, "id"),
        "agent_name": _optional_text(message_info, "agent")
        or _optional_text(session_info, "agent"),
        "role": _optional_text(message_info, "role"),
        "parent_id": _optional_text(message_info, "parentID"),
    }
    records: list[dict[str, Any]] = []
    for part in message.get("parts", []):
        if not isinstance(part, dict):
            continue
        record = _record_from_message_part(part, inherited=inherited)
        if record is not None:
            records.append(record)
    return records


def _record_from_message_part(
    part: dict[str, Any], *, inherited: dict[str, str | None]
) -> dict[str, Any] | None:
    part_type = _optional_text(part, "type")
    record_type_by_part = {
        "text": "text",
        "tool": "tool_use",
        "step-start": "step_start",
        "step_start": "step_start",
        "step-finish": "step_finish",
        "step_finish": "step_finish",
        "reasoning": "reasoning",
    }
    record_type = record_type_by_part.get((part_type or "").casefold())
    if record_type is None:
        raise TraceSchemaError(
            f"unsupported OpenCode message part type: {part_type or '<missing>'}"
        )
    record: dict[str, Any] = {
        "type": record_type,
        "timestamp": _time_value(part) or inherited.get("timestamp"),
        "sessionID": _optional_text(part, "sessionID") or inherited.get("sessionID"),
        "agent_name": inherited.get("agent_name"),
        "role": inherited.get("role"),
        "part": dict(part),
    }
    if inherited.get("parent_id"):
        record["parent_id"] = inherited["parent_id"]
    if record_type == "tool_use":
        record["tool_name"] = _optional_text(part, "tool")
    return record


def _time_value(record: dict[str, Any]) -> str | None:
    time_payload = _optional_dict(record, "time")
    for key in ("created", "start", "end", "completed", "updated"):
        value = time_payload.get(key)
        if value is not None:
            return str(value)
    return None


def _record_to_events(
    record: dict[str, Any],
    *,
    index: int,
    root: Path,
    agent_by_session: dict[str, str],
    delegated_by_session: dict[str, str],
) -> list[TraceEvent]:
    event = _record_to_event(
        record,
        index=index,
        root=root,
        agent_by_session=agent_by_session,
        delegated_by_session=delegated_by_session,
    )
    if event is None:
        return []
    prompt_event = _prompt_read_event(record, index=index, agent_name=event.agent_name)
    return [event, prompt_event] if prompt_event is not None else [event]


def _record_to_event(
    record: dict[str, Any],
    *,
    index: int,
    root: Path,
    agent_by_session: dict[str, str],
    delegated_by_session: dict[str, str],
) -> TraceEvent | None:
    record_type = _optional_text(record, "type")
    part = _optional_dict(record, "part")
    if record_type in {"step_start", "step_finish"}:
        return None
    session_id = _session_id(record)
    agent_name = (
        _optional_text(record, "agent_name")
        or _optional_text(record, "agent")
        or _optional_text(record, "name")
        or (agent_by_session.get(session_id) if session_id else None)
    )
    if record_type == "opencode_stream" and _is_metadata_agent(agent_name):
        return None
    tool_name = (
        _optional_text(record, "tool_name")
        or _optional_text(record, "tool")
        or _optional_text(part, "tool")
    )
    role = _normalize_role(
        _optional_text(record, "role"), agent_name=agent_name, tool_name=tool_name
    )
    if record_type in {"text", "reasoning"} and role != "user":
        role = "orchestrator" if _is_orchestrator_agent(agent_name) else role
    delegated_by = (
        _optional_text(record, "delegated_by")
        or _optional_text(record, "parent_agent")
        or (delegated_by_session.get(session_id) if session_id else None)
    )
    action = _optional_text(record, "action") or _infer_action(
        record, role, delegated_by=delegated_by
    )
    if tool_name == "task" and _has_completed_task_result(record):
        action = "delegated_task_result"
    content_ref = _content_ref(record, index=index, root=root)
    state = _tool_state(record)
    return TraceEvent(
        ts=_optional_text(record, "ts")
        or _optional_text(record, "timestamp")
        or f"event-{index:04d}",
        role=role,
        agent_name=agent_name,
        action=action,
        target=_optional_text(record, "target") or _tool_target(record),
        content_ref=content_ref,
        tool_name=tool_name,
        delegated_by=delegated_by,
        pathway_milestone=_optional_text(record, "pathway_milestone")
        or _optional_text(record, "milestone"),
        source_path=_optional_text(record, "_source_path"),
        session_id=session_id,
        text_hash=_text_hash(record),
        tool_status=_tool_status(state),
        tool_output_present=_tool_output_present(state),
        tool_command=_tool_command(state),
    )


def _prompt_read_event(
    record: dict[str, Any], *, index: int, agent_name: str | None
) -> TraceEvent | None:
    if _optional_text(record, "type") != "tool_use":
        return None
    part = _optional_dict(record, "part")
    if _optional_text(part, "tool") != "read":
        return None
    state = _optional_dict(part, "state")
    input_payload = _optional_dict(state, "input")
    file_path = _optional_text(input_payload, "filePath") or _optional_text(input_payload, "path")
    if not file_path or not _is_subject_prompt_path(file_path):
        return None
    output = _optional_text(state, "output")
    if not output:
        return None
    digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
    return TraceEvent(
        ts=_optional_text(record, "ts")
        or _optional_text(record, "timestamp")
        or f"event-{index:04d}",
        role="user",
        agent_name=None,
        action="message",
        target=file_path,
        content_ref=f"opencode:prompt-{index:04d}:{digest[:12]}",
        source_path=_optional_text(record, "_source_path"),
        session_id=_session_id(record),
        text_hash=digest,
        delegated_by=agent_name,
    )


def _is_subject_prompt_path(file_path: str) -> bool:
    path = Path(file_path)
    if path.name.casefold() != "prompt.md":
        return False
    normalized_parts = {part.casefold() for part in path.parts}
    return "subject" in normalized_parts


def _normalize_role(role: str | None, *, agent_name: str | None, tool_name: str | None) -> str:
    normalized = (role or "").casefold().replace("-", "_")
    agent = (agent_name or "").casefold()
    if tool_name or normalized in {"tool", "tool_call", "tool_result", "tool_response"}:
        return "tool"
    if normalized in {"user", "system", "verifier", "orchestrator", "subagent"}:
        return normalized
    if _is_orchestrator_agent(agent_name):
        return "orchestrator"
    if _is_brainds_agent(agent_name):
        return "subagent"
    if "verifier" in agent:
        return "verifier"
    return "verifier" if normalized in {"assistant", ""} else normalized


def _infer_action(record: dict[str, Any], role: str, *, delegated_by: str | None = None) -> str:
    record_type = _optional_text(record, "type")
    if record_type == "opencode_stream":
        return "agent_stream"
    if record_type == "tool_use":
        return "tool_call"
    if role == "subagent" and (
        delegated_by or record.get("delegated_by") or record.get("parent_agent")
    ):
        return "delegated_message"
    if record_type == "text":
        return "message"
    if record_type == "reasoning":
        return "reasoning"
    if role == "tool":
        return "tool_call" if record.get("arguments") or record.get("input") else "tool_response"
    if delegated_by or record.get("delegated_by") or record.get("parent_agent"):
        return "delegated_message"
    return "message"


def _content_ref(record: dict[str, Any], *, index: int, root: Path) -> str | None:
    part = _optional_dict(record, "part")
    if _optional_text(record, "type") == "tool_use":
        state = _optional_dict(part, "state")
        status = _optional_text(state, "status") or "unknown"
        body = json.dumps(state, sort_keys=True, default=str)
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        return f"opencode:tool-{index:04d}:status={status}:{digest[:12]}"
    for key in ("content_ref", "path", "file"):
        value = _optional_text(record, key)
        if value:
            return value
    text = _optional_text(part, "text")
    if text:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"opencode:text-{index:04d}:{digest[:12]}"
    if "content" not in record:
        return None
    digest = hashlib.sha256(
        json.dumps(record["content"], sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"opencode:event-{index:04d}:{digest[:12]}"


def _tool_state(record: dict[str, Any]) -> dict[str, Any]:
    if _optional_text(record, "type") != "tool_use":
        return {}
    part = _optional_dict(record, "part")
    return _optional_dict(part, "state")


def _tool_status(state: dict[str, Any]) -> str | None:
    status = _optional_text(state, "status")
    return status.casefold() if status else None


def _tool_output_present(state: dict[str, Any]) -> bool:
    return bool(_optional_text(state, "output") or _optional_text(state, "result"))


def _tool_command(state: dict[str, Any]) -> str | None:
    input_payload = _optional_dict(state, "input")
    return _optional_text(input_payload, "command") or _optional_text(input_payload, "cmd")


def _session_id(record: dict[str, Any]) -> str | None:
    return _optional_alias(record, SESSION_ID_ALIASES)


def _parent_session_id(record: dict[str, Any]) -> str | None:
    return _optional_alias(record, PARENT_SESSION_ID_ALIASES)


def _optional_alias(record: dict[str, Any], aliases: tuple[str, ...]) -> str | None:
    for key in aliases:
        value = _optional_text(record, key)
        if value:
            return value
    return None


def _is_known_opencode_record(record: dict[str, Any]) -> bool:
    known_top_level = {
        "type",
        "role",
        "agent_name",
        "agent",
        "name",
        "part",
        "content",
        "text",
        "tool_name",
        "tool",
        "action",
        "info",
        "parts",
    }
    return bool(known_top_level.intersection(record))


def _validate_export_record_contract(records: list[Any], agent_by_session: dict[str, str]) -> None:
    supported_record_types = {
        "text",
        "tool_use",
        "opencode_session",
        "opencode_stream",
        "step_start",
        "step_finish",
        "reasoning",
    }
    attribution_required_types = {"text", "tool_use", "opencode_session", "opencode_stream"}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        record_type = _optional_text(record, "type")
        if record_type and record_type not in supported_record_types:
            raise TraceSchemaError(
                f"unsupported OpenCode export record type at record {index}: {record_type}"
            )
        if not record_type and not _is_known_opencode_record(record):
            raise TraceSchemaError(
                f"unknown OpenCode export schema at record {index}: no recognized session, agent, message, or tool fields"
            )
        if record_type not in attribution_required_types:
            continue
        session_id = _session_id(record)
        agent_name = (
            _optional_text(record, "agent_name")
            or _optional_text(record, "agent")
            or _optional_text(record, "name")
            or (agent_by_session.get(session_id) if session_id else None)
        )
        if not session_id or not agent_name:
            raise TraceSchemaError(
                f"record {index} cannot yield valid attribution/session semantics"
            )


def _text_hash(record: dict[str, Any]) -> str | None:
    part = _optional_dict(record, "part")
    text = (
        _optional_text(record, "content")
        or _optional_text(record, "text")
        or _optional_text(part, "text")
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None


def _tool_target(record: dict[str, Any]) -> str | None:
    part = _optional_dict(record, "part")
    state = _optional_dict(part, "state")
    input_payload = _optional_dict(state, "input")
    for key in ("target", "subagent_type", "filePath", "path", "node_id", "graph_id"):
        value = input_payload.get(key)
        if value is not None:
            return str(value)
    output_target = _tool_output_target(record)
    if output_target is not None:
        return output_target
    return None


def _has_completed_task_result(record: dict[str, Any]) -> bool:
    part = _optional_dict(record, "part")
    if _optional_text(part, "tool") != "task":
        return False
    state = _optional_dict(part, "state")
    if (_optional_text(state, "status") or "").casefold() not in {"completed", "success", "ok"}:
        return False
    output = _optional_text(state, "output") or _optional_text(state, "result")
    if not output:
        return False
    normalized = output.casefold()
    return "<task_result" in normalized or "task_result" in normalized


def _tool_output_target(record: dict[str, Any]) -> str | None:
    part = _optional_dict(record, "part")
    if _optional_text(part, "tool") != "brain_ds_list_workspaces":
        return None
    state = _optional_dict(part, "state")
    if (_optional_text(state, "status") or "").casefold() not in {"completed", "success", "ok"}:
        return None
    output = _optional_text(state, "output")
    if not output:
        return None
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("active_registered") is not True:
        return None
    active_root = payload.get("active_project_root")
    if not active_root:
        return None
    active_root_text = str(active_root)
    workspaces = payload.get("workspaces")
    if isinstance(workspaces, list):
        for workspace in workspaces:
            if not isinstance(workspace, dict) or workspace.get("active") is not True:
                continue
            workspace_path = workspace.get("path") or workspace.get("project_root")
            if workspace_path is not None and _same_path(str(workspace_path), active_root_text):
                return active_root_text
    active_workspace = payload.get("active_workspace")
    if isinstance(active_workspace, dict):
        workspace_path = active_workspace.get("path") or active_workspace.get("project_root")
        if workspace_path is not None and _same_path(str(workspace_path), active_root_text):
            return active_root_text
    return None


def _same_path(left: str, right: str) -> bool:
    return Path(left).resolve(strict=False) == Path(right).resolve(strict=False)


def _is_orchestrator_agent(agent_name: str | None) -> bool:
    return (agent_name or "").casefold() in {"brainds-orchestrator", "brain-ds-orchestrator"}


def _is_brainds_agent(agent_name: str | None) -> bool:
    agent = (agent_name or "").casefold()
    return agent.startswith("brainds-") or agent.startswith("brain-ds-")


def _is_metadata_agent(agent_name: str | None) -> bool:
    return (agent_name or "").casefold() in {"title", "unknown"}


def _optional_text(record: dict[str, Any], key: str) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_dict(record: dict[str, Any], key: str) -> dict[str, Any]:
    value = record.get(key)
    return value if isinstance(value, dict) else {}
