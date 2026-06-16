"""Pure invariants for the agentic source documentation pipeline."""

from __future__ import annotations

from collections import Counter
import re
from pathlib import Path
from typing import Iterable, Iterator

EXPECTED_DELIVERABLE_SECTION_LABELS: tuple[str, ...] = (
    "Outcome title",
    "Quick path / summary",
    "Details table",
    "Coverage checklist",
    "Next step",
)

PIPELINE_ARTIFACT_TYPES: tuple[str, ...] = (
    "recon",
    "plan",
    "source-docs",
    "consolidation",
    "dry-run",
)

PROHIBITED_GRAPH_WRITE_ACTIONS: tuple[str, ...] = ("update_node", "add_edge")

_H2_HEADING_RE = re.compile(r"(?m)^##\s+(?P<title>.+?\S)\s*$")
_FENCED_BLOCK_RE = re.compile(r"```(?:[a-zA-Z0-9_-]+)?\n.*?\n```", re.DOTALL)


def _normalize_heading(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


_EXPECTED_DELIVERABLE_SECTIONS = tuple(_normalize_heading(label) for label in EXPECTED_DELIVERABLE_SECTION_LABELS)


def _strip_fenced_blocks(markdown: str) -> str:
    return _FENCED_BLOCK_RE.sub("", markdown)


def _split_sections(markdown: str) -> list[tuple[str, str]]:
    cleaned = _strip_fenced_blocks(markdown)
    sections: list[tuple[str, str]] = []
    current_title: str | None = None
    current_body: list[str] = []

    for line in cleaned.splitlines():
        match = _H2_HEADING_RE.match(line)
        if match:
            if current_title is not None:
                sections.append((current_title, "\n".join(current_body).strip()))
            current_title = match.group("title").strip()
            current_body = []
            continue
        if current_title is not None:
            current_body.append(line)

    if current_title is not None:
        sections.append((current_title, "\n".join(current_body).strip()))
    return sections


def _contains_any(text: str, tokens: Iterable[str]) -> bool:
    lowered = text.casefold()
    return any(token in lowered for token in tokens)


def _ensure_keywords(text: str, keywords: Iterable[str], *, label: str) -> None:
    missing = [keyword for keyword in keywords if keyword not in text.casefold()]
    if missing:
        raise AssertionError(f"{label} must include {', '.join(missing)}")


def assert_deliverable_shape(markdown: str) -> None:
    """Assert the 5-section pipeline-artifact contract.

    This helper is intentionally scoped to source-documentation pipeline artifacts.
    BRD/map canonical outputs have their own contracts and must not use it.
    """

    sections = _split_sections(markdown)
    section_titles = tuple(_normalize_heading(title) for title, _ in sections)
    if section_titles != _EXPECTED_DELIVERABLE_SECTIONS:
        raise AssertionError(
            "Expected exactly 5 sections for pipeline artifacts only "
            f"{EXPECTED_DELIVERABLE_SECTION_LABELS}; got {len(sections)} sections: {tuple(title for title, _ in sections)}. "
            "Do not use this helper on BRD/map canonical outputs."
        )

    for title, body in sections:
        if not body.strip():
            raise AssertionError(f"Section '{title}' must not be empty")

    quick_path = sections[1][1]
    _ensure_keywords(quick_path, ("object name", "type", "status", "reason"), label="Quick path / summary")
    if "|" not in quick_path:
        raise AssertionError("Quick path / summary must be a table")

    details = sections[2][1]
    _ensure_keywords(details, ("source_type", "type_fields"), label="Details table")
    if "|" not in details:
        raise AssertionError("Details table must be a table")
    if not (
        _contains_any(details, ("schema", "columns", "primary key", "foreign key", "sample row count"))
        or _contains_any(details, ("tab/file name", "headers", "column count", "row count estimate", "inferred types"))
    ):
        raise AssertionError(
            "Details table must include either SQL fields (schema, columns, primary keys, foreign keys, sample row count) "
            "or sheet/CSV fields (tab/file name, headers, column count, row count estimate, inferred types)"
        )

    checklist = sections[3][1]
    if not re.search(r"\[[ xX]\]", checklist):
        raise AssertionError("Coverage checklist must contain checkbox markers")
    if not _contains_any(checklist, ("documented", "skipped", "unsupported")):
        raise AssertionError("Coverage checklist must mention documented, skipped, or unsupported objects")

    next_step = sections[4][1]
    if not _contains_any(next_step, ("consolidate", "wait", "escalate")):
        raise AssertionError("Next step must give a handoff instruction (consolidate / wait / escalate)")


def assert_pipeline_artifact_trail_shape(artifact_paths: Iterable[Path]) -> None:
    """Assert every pipeline artifact file uses the 5-section contract."""

    for artifact_path in artifact_paths:
        try:
            assert_deliverable_shape(artifact_path.read_text(encoding="utf-8"))
        except AssertionError as exc:  # pragma: no cover - rewrap for path context
            raise AssertionError(f"{artifact_path.name}: {exc}") from exc


def _flatten_objects(items: Iterable[object]) -> Iterator[str]:
    for item in items:
        if isinstance(item, str):
            yield item
            continue
        try:
            iterator = iter(item)  # type: ignore[call-overload]
        except TypeError:
            yield str(item)
            continue
        for nested in iterator:
            yield str(nested)


def _completeness_report(
    expected_objects: Iterable[object],
    observed_objects: Iterable[object],
    *,
    skipped_objects: Iterable[object] = (),
) -> dict[str, object]:
    expected_list = [str(item) for item in expected_objects]
    observed_list = [str(item) for item in _flatten_objects(observed_objects)]
    skipped_list = [str(item) for item in skipped_objects]

    observed_with_skips = observed_list + skipped_list
    expected_set = set(expected_list)
    observed_set = set(observed_with_skips)
    duplicate_objects = tuple(sorted(obj for obj, count in Counter(observed_with_skips).items() if count > 1))
    missing_objects = tuple(sorted(expected_set - observed_set))
    unexpected_objects = tuple(sorted(observed_set - expected_set))

    return {
        "expected_objects": tuple(sorted(expected_set)),
        "observed_objects": tuple(sorted(observed_set)),
        "skipped_objects": tuple(sorted(set(skipped_list))),
        "missing_objects": missing_objects,
        "duplicate_objects": duplicate_objects,
        "unexpected_objects": unexpected_objects,
        "is_complete": not missing_objects and not duplicate_objects and not unexpected_objects,
        "has_warnings": bool(skipped_list),
    }


def evaluate_plan_completeness(
    recon_inventory: Iterable[object],
    plan_slices: Iterable[object],
    *,
    skipped_objects: Iterable[object] = (),
) -> dict[str, object]:
    """Evaluate recon_inventory == union(plan_slices)."""

    return _completeness_report(recon_inventory, plan_slices, skipped_objects=skipped_objects)


def evaluate_consolidation_completeness(
    plan_objects: Iterable[object],
    delivered_objects: Iterable[object],
    *,
    skipped_objects: Iterable[object] = (),
) -> dict[str, object]:
    """Evaluate union(delivered docs + skipped-by-design) == plan slices."""

    return _completeness_report(plan_objects, delivered_objects, skipped_objects=skipped_objects)


plan_completeness = evaluate_plan_completeness
consolidation_completeness = evaluate_consolidation_completeness
check_plan_completeness = evaluate_plan_completeness
check_consolidation_completeness = evaluate_consolidation_completeness


def assert_no_graph_writes(actions: Iterable[object], *, label: str) -> None:
    """Assert that a recon/dry-run trace contains no graph write actions."""

    flattened = tuple(_flatten_objects(actions))
    violations = tuple(
        action for action in flattened if any(token in action.casefold() for token in PROHIBITED_GRAPH_WRITE_ACTIONS)
    )
    if violations:
        raise AssertionError(
            f"{label} must not include graph write actions: {', '.join(sorted(set(violations)))}"
        )
