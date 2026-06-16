from __future__ import annotations

import pytest

from brain_ds.mcp import grounding
from brain_ds.pipeline.invariants import (
    assert_deliverable_shape,
    assert_no_graph_writes,
    evaluate_consolidation_completeness,
    evaluate_plan_completeness,
    assert_pipeline_artifact_trail_shape,
)


def _pipeline_markdown(details_table: str, *, extra_heading: str = "") -> str:
    extra = f"\n## {extra_heading}\nExtra section.\n" if extra_heading else ""
    return f"""# Source docs

## Outcome title
Source docs slice for acme — source-docs artifact

## Quick path / summary
| object name | type | status | reason-if-skipped |
|---|---|---|---|
| orders | table | documented | |
| audit_log | table | skipped | access denied |

## Details table
{details_table}

## Coverage checklist
- [x] documented orders
- [ ] skipped audit_log (access denied)

## Next step
Consolidate these slices.

```json
{{"artifact_type": "source-docs", "graph_id": "acme"}}
```
{extra}"""


def test_assert_deliverable_shape_accepts_sql_pipeline_artifact() -> None:
    markdown = _pipeline_markdown(
        """| object name | source_type | schema | columns | primary keys | foreign keys | sample row count | type_fields |
|---|---|---|---|---|---|---|---|
| orders | sqlite | public | order_id:int, customer_id:int | order_id | customer_id -> customers.id | 12 | schema, columns, primary keys, foreign keys, sample row count |"""
    )

    assert_deliverable_shape(markdown)


def test_assert_deliverable_shape_accepts_sheet_pipeline_artifact() -> None:
    markdown = _pipeline_markdown(
        """| object name | source_type | tab/file name | headers | column count | row count estimate | inferred types | type_fields |
|---|---|---|---|---|---|---|---|
| report.csv | csv | report.csv | id,name,amount | 3 | 100 | int,str,decimal | tab/file name, headers, column count, row count estimate, inferred types |"""
    )

    assert_deliverable_shape(markdown)


def test_assert_deliverable_shape_rejects_brd_canonical_body() -> None:
    markdown = "\n".join(
        [
            "# BRD",
            *[f"## Section {index}" for index in range(1, 15)],
            "```json",
            '{"artifact_type": "brd"}',
            "```",
        ]
    )

    with pytest.raises(AssertionError, match="pipeline artifacts only|BRD|5 sections"):
        assert_deliverable_shape(markdown)


def test_assert_deliverable_shape_rejects_map_canonical_body() -> None:
    markdown = "\n".join(
        [
            "# Map",
            *[f"## Map section {index}" for index in range(1, 8)],
            "```json",
            '{"artifact_type": "map"}',
            "```",
        ]
    )

    with pytest.raises(AssertionError, match="pipeline artifacts only|map|5 sections"):
        assert_deliverable_shape(markdown)


def test_assert_deliverable_shape_rejects_sixth_section_before_json_block() -> None:
    markdown = _pipeline_markdown(
        """| object name | source_type | schema | columns | primary keys | foreign keys | sample row count | type_fields |
|---|---|---|---|---|---|---|---|
| orders | sqlite | public | order_id:int, customer_id:int | order_id | customer_id -> customers.id | 12 | schema, columns, primary keys, foreign keys, sample row count |""",
        extra_heading="Unexpected section",
    )

    with pytest.raises(AssertionError, match="exactly 5 sections|pipeline artifacts only"):
        assert_deliverable_shape(markdown)


def test_assert_deliverable_shape_rejects_numbered_heading() -> None:
    markdown = _pipeline_markdown(
        """| object name | source_type | schema | columns | primary keys | foreign keys | sample row count | type_fields |
|---|---|---|---|---|---|---|---|
| orders | sqlite | public | order_id:int, customer_id:int | order_id | customer_id -> customers.id | 12 | schema, columns, primary keys, foreign keys, sample row count |""",
    ).replace("## Outcome title", "## 1. Outcome Title")

    with pytest.raises(AssertionError, match=r"1\. Outcome Title|exactly 5 sections"):
        assert_deliverable_shape(markdown)


def test_assert_pipeline_artifact_trail_shape_rejects_bad_file(tmp_path) -> None:
    good = tmp_path / "source-docs-acme-2026-06-14.md"
    bad = tmp_path / "source-docs-acme-2026-06-15.md"

    good.write_text(
        _pipeline_markdown(
            """| object name | source_type | schema | columns | primary keys | foreign keys | sample row count | type_fields |
|---|---|---|---|---|---|---|---|
| orders | sqlite | public | order_id:int, customer_id:int | order_id | customer_id -> customers.id | 12 | schema, columns, primary keys, foreign keys, sample row count |""",
        ),
        encoding="utf-8",
    )
    bad.write_text(
        _pipeline_markdown(
            """| object name | source_type | schema | columns | primary keys | foreign keys | sample row count | type_fields |
|---|---|---|---|---|---|---|---|
| orders | sqlite | public | order_id:int, customer_id:int | order_id | customer_id -> customers.id | 12 | schema, columns, primary keys, foreign keys, sample row count |""",
        ).replace("## Outcome title", "## 1. Outcome Title"),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="source-docs-acme-2026-06-15.md|Outcome title"):
        assert_pipeline_artifact_trail_shape([good, bad])


def test_plan_completeness_allows_exact_partition() -> None:
    report = evaluate_plan_completeness(
        ["orders", "audit_log", "unsupported-json-api"],
        [{"orders"}, {"audit_log"}, {"unsupported-json-api"}],
    )

    assert report["is_complete"] is True
    assert report["missing_objects"] == ()
    assert report["duplicate_objects"] == ()
    assert report["unexpected_objects"] == ()


def test_plan_completeness_reports_missing_and_duplicate_objects() -> None:
    report = evaluate_plan_completeness(
        ["orders", "audit_log"],
        [{"orders"}, {"orders"}],
    )

    assert report["is_complete"] is False
    assert report["missing_objects"] == ("audit_log",)
    assert report["duplicate_objects"] == ("orders",)


def test_consolidation_completeness_counts_skipped_objects_as_covered() -> None:
    report = evaluate_consolidation_completeness(
        ["orders", "audit_log", "unsupported-unstructured"],
        [{"orders"}],
        skipped_objects=("audit_log", "unsupported-unstructured"),
    )

    assert report["is_complete"] is True
    assert report["missing_objects"] == ()
    assert report["skipped_objects"] == ("audit_log", "unsupported-unstructured")
    assert report["has_warnings"] is True


def test_consolidation_completeness_reports_missing_supported_object() -> None:
    report = evaluate_consolidation_completeness(
        ["orders", "audit_log"],
        [{"orders"}],
    )

    assert report["is_complete"] is False
    assert report["missing_objects"] == ("audit_log",)
    assert report["duplicate_objects"] == ()


def test_assert_no_graph_writes_accepts_dry_run_recipe() -> None:
    assert_no_graph_writes(grounding.DELEGATION_PROTOCOL["dry_run"]["steps"], label="dry-run recipe")


def test_assert_no_graph_writes_rejects_graph_write_actions() -> None:
    with pytest.raises(AssertionError, match="update_node|add_edge|graph write"):
        assert_no_graph_writes(["recon", "update_node", "add_edge"], label="dry-run recipe")
