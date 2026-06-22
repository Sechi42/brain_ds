"""Suite-wide isolation: keep tests out of the user's real ~/.brain_ds registry."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import cast

import pytest

from brain_ds.mcp.grounding import ARTIFACT_CONTRACT, BRD_GRAPH_PERSISTENCE_CONTRACT
from brain_ds.mcp.tools import (
    add_edge,
    assess_completeness,
    create_graph,
    explore_source,
    generate_brd,
    list_source_connections,
    map_connections,
    run_elicit,
    update_node,
)
from brain_ds.store.graph_store import GraphStore
from tests.fixtures.build_synthetic_source import build_synthetic_source
from tests.fixtures.delegation import FakeDelegator


@pytest.fixture(autouse=True, scope="session")
def _isolated_brain_ds_home():
    with tempfile.TemporaryDirectory() as home:
        previous_home = os.environ.get("BRAIN_DS_HOME")
        previous_guard = os.environ.get("BRAIN_DS_NO_SEED_REBUILD")
        os.environ["BRAIN_DS_HOME"] = home
        # Tell build_synthetic_source() not to rewrite the checked-in seed for
        # any call that omits a target — isolation tests depend on hash stability.
        os.environ["BRAIN_DS_NO_SEED_REBUILD"] = "1"
        try:
            yield
        finally:
            if previous_home is None:
                os.environ.pop("BRAIN_DS_HOME", None)
            else:
                os.environ["BRAIN_DS_HOME"] = previous_home
            if previous_guard is None:
                os.environ.pop("BRAIN_DS_NO_SEED_REBUILD", None)
            else:
                os.environ["BRAIN_DS_NO_SEED_REBUILD"] = previous_guard


@pytest.fixture(scope="session")
def synthetic_source_path() -> Path:
    """Return the checked-in seed path.

    The seed file is read-only by contract — tests that need to write must use
    `writable_synthetic_source_path` instead.  We verify the seed exists and is
    valid but do NOT rebuild it here; that would mutate the tracked file and
    break xdist-safe isolation.
    """
    from tests.fixtures.build_synthetic_source import FIXTURE_PATH

    seed = FIXTURE_PATH.resolve()
    if not seed.exists():
        # Seed missing (e.g. first checkout without git-lfs) — rebuild once.
        build_synthetic_source(target=seed)
    return seed


@pytest.fixture
def writable_synthetic_source_path(tmp_path: Path, synthetic_source_path: Path) -> Path:
    """Return a per-test writable copy of the seed SQLite fixture.

    Each invocation creates a fresh copy inside pytest's `tmp_path` directory,
    so tests that write to the DB cannot interfere with each other or with the
    checked-in seed.  The copy is automatically cleaned up by pytest after the
    test.
    """
    copy = tmp_path / "synthetic_source.db"
    shutil.copy2(synthetic_source_path, copy)
    return copy


def _artifact_body(title: str, payload: dict) -> str:
    import json

    sentinel = ARTIFACT_CONTRACT["canonical_sentinel"]
    return (
        f"# {title}\n\n"
        f"{sentinel}\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```\n"
    )


def _source_docs_body(payload: dict) -> str:
    import json

    sentinel = ARTIFACT_CONTRACT["canonical_sentinel"]
    return (
        "# Source Documentation\n\n"
        "## Outcome title\n"
        "Synthetic source-docs slice for the Acme dry-run fixture.\n\n"
        "## Quick path / summary\n"
        "| object name | type | status | reason-if-skipped |\n"
        "|---|---|---|---|\n"
        "| customers | table | documented | |\n"
        "| orders | table | documented | |\n\n"
        "## Details table\n"
        "| object name | source_type | schema | columns | primary keys | foreign keys | sample row count | type_fields |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| customers | sqlite | main | customer_id:int, name:text, segment:text, region:text | customer_id | (none) | 5 | schema, columns, primary keys, foreign keys, sample row count |\n"
        "| orders | sqlite | main | order_id:int, customer_id:int, order_total:real, status:text, created_at:text | order_id | customer_id -> customers.customer_id | 5 | schema, columns, primary keys, foreign keys, sample row count |\n\n"
        "## Coverage checklist\n"
        "- [x] documented customers\n"
        "- [x] documented orders\n"
        "- [ ] skipped unsupported-json-api (manual contract required)\n\n"
        "## Next step\n"
        "Consolidate these slices and keep the unsupported object as skip-by-design.\n\n"
        f"{sentinel}\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```\n"
    )


@pytest.fixture
def dry_run_elicit_output(tmp_path: Path, synthetic_source_path: Path) -> dict[str, object]:
    org_slug = "acme"
    iso_date = "2026-06-14"
    project_root = tmp_path
    elicit_dir = project_root / ".elicit"
    elicit_dir.mkdir()
    copied_db = project_root / "synthetic_source.db"
    shutil.copyfile(synthetic_source_path, copied_db)

    store = GraphStore(str(project_root / "store.db"))
    written_files: list[str] = []
    delegator = FakeDelegator(synthetic_source_path=str(copied_db))

    def write_artifact(phase: str, payload: dict) -> Path:
        path = elicit_dir / f"{phase}-{org_slug}-{iso_date}.md"
        # Inject artifact_type at top level for all phase-named artifacts so the
        # canonical dual-contract format is upheld without modifying callers.
        full_payload = {"artifact_type": phase, **payload}
        body = _source_docs_body(full_payload) if phase == "source-docs" else _artifact_body(phase.replace("-", " ").title(), full_payload)
        path.write_text(body, encoding="utf-8")
        written_files.append(str(path))
        return path

    def handoff(agent: str, stage: str, refs: list[str]) -> None:
        delegator.delegate(agent=agent, stage=stage, refs=refs)

    try:
        create_graph(store, {"graph_id": org_slug, "name": "Acme", "project": "brain_ds"})
        update_node(
            store,
            {
                "graph_id": org_slug,
                "node_id": f"{org_slug}-organization-acme",
                "label": "Acme",
                "type": "Organization",
                "details": {
                    "what": "Synthetic company for dry-run coverage.",
                    "why": "Exercises BRD wikilinks.",
                    "where": "Test fixture graph.",
                    "learned": "Synthetic only.",
                },
            },
        )
        update_node(
            store,
            {
                "graph_id": org_slug,
                "node_id": f"{org_slug}-role-revenue-ops",
                "label": "Revenue Ops",
                "type": "Role",
                "details": {
                    "what": "Owns the reporting workflow.",
                    "why": "Provides an owner edge for the dry-run.",
                    "where": "Operations.",
                    "learned": "Synthetic owner.",
                },
            },
        )
        update_node(
            store,
            {
                "graph_id": org_slug,
                "node_id": f"{org_slug}-source-synthetic-warehouse",
                "label": "Synthetic Warehouse",
                "type": "Data Source",
                "details": {
                    "what": "Synthetic SQLite warehouse for dry-run coverage.",
                    "why": "Exercises list_source_connections and explore_source end-to-end.",
                    "where": "tests/fixtures cloned into a temp project root.",
                    "learned": "Kind: relational-db; System: sqlite; Database: synthetic_source; Tables/Sheets: customers, orders; Key Columns/Fields: customer_id: primary key; order_total: amount; Purpose: dry-run proof; Owner: Revenue Ops; Refresh: manual; Trust: medium",
                    "connection": {"kind": "sqlite", "path": copied_db.name},
                },
            },
        )

        handoff("brainds-source-explorer", "intake", [str(elicit_dir / f"source-exploration-{org_slug}-{iso_date}.md")])
        connections = list_source_connections(store, {"graph_id": org_slug})
        source_scan = explore_source(
            store,
            {"graph_id": org_slug, "node_id": f"{org_slug}-source-synthetic-warehouse"},
        )
        table_docs: list[dict[str, object]] = []
        for table in ("customers", "orders"):
            table_docs.append(
                explore_source(
                    store,
                    {
                        "graph_id": org_slug,
                        "node_id": f"{org_slug}-source-synthetic-warehouse",
                        "container": "main",
                        "table": table,
                    },
                )
            )
        source_sections = [
            {
                "title": "Overview",
                "content": "Synthetic SQLite warehouse with customers and orders tables.",
                "icon": "info",
                "order": 1,
            },
            {
                "title": "Structure",
                "content": "DB: synthetic_source / schema: main / tables: customers, orders",
                "icon": "database",
                "order": 2,
            },
            {
                "title": "Columns / Fields",
                "content": (
                    "| Column / Field | Type | Meaning | Notes |\n"
                    "|---|---|---|---|\n"
                    "| customer_id | INTEGER | Customer identifier | Primary key |\n"
                    "| name | TEXT | Customer name | Synthetic fixture |\n"
                    "| order_total | REAL | Order revenue | From orders table |"
                ),
                "icon": "table",
                "order": 3,
            },
            {
                "title": "Refresh Cadence",
                "content": "Manual rebuild via tests/fixtures/build_synthetic_source.py.",
                "icon": "clock",
                "order": 4,
            },
        ]
        update_node(
            store,
            {
                "graph_id": org_slug,
                "node_id": f"{org_slug}-source-synthetic-warehouse",
                "card_sections": source_sections,
            },
        )
        source_exploration_path = write_artifact(
            "source-exploration",
            {
                "graph_id": org_slug,
                "connections": connections,
                "source_scan": source_scan,
                "table_docs": table_docs,
            },
        )
        source_docs_path = write_artifact(
            "source-docs",
            {
                "graph_id": org_slug,
                "slice_id": "slice-001",
                "assigned_objects": ["customers", "orders"],
                "documented_nodes": [
                    {
                        "node_id": f"{org_slug}-source-synthetic-warehouse",
                        "label": "Synthetic Warehouse",
                        "type": "Data Source",
                        "card_sections": source_sections,
                    }
                ],
            },
        )

        handoff(
            "brainds-graph-mapper",
            "intake",
            [str(source_docs_path), str(elicit_dir / f"map-{org_slug}-{iso_date}.md")],
        )
        _ = map_connections(store, {})
        completeness_gate = assess_completeness(store, {"graph_id": org_slug})
        add_edge(
            store,
            {
                "graph_id": org_slug,
                "source": f"{org_slug}-role-revenue-ops",
                "target": f"{org_slug}-source-synthetic-warehouse",
                "label": "owns",
                "confidence": 0.91,
                "reasons": ["Synthetic ownership for dry-run proof."],
            },
        )
        map_sections = [
            {
                "title": "Overview",
                "content": "Revenue Ops owns the synthetic warehouse source.",
                "icon": "link",
                "order": 1,
            }
        ]
        update_node(
            store,
            {
                "graph_id": org_slug,
                "node_id": f"{org_slug}-role-revenue-ops",
                "card_sections": map_sections,
            },
        )
        map_path = write_artifact(
            "map",
            {
                "graph_id": org_slug,
                "documented_nodes": [
                    {
                        "node_id": f"{org_slug}-role-revenue-ops",
                        "label": "Revenue Ops",
                        "type": "Role",
                        "card_sections": map_sections,
                    }
                ],
                "edges": [
                    {
                        "source": f"{org_slug}-role-revenue-ops",
                        "target": f"{org_slug}-source-synthetic-warehouse",
                        "label": "owns",
                    }
                ],
                "completeness_gate": completeness_gate,
            },
        )

        handoff("brainds-connection-mapper", "map", [str(map_path)])
        handoff("brainds-brd-writer", "brd", [str(elicit_dir / f"brd-{org_slug}-{iso_date}.md")])
        _ = generate_brd(store, {})
        template = cast(dict[str, object], BRD_GRAPH_PERSISTENCE_CONTRACT["update_node_template"])
        template_sections = cast(list[dict[str, object]], template["card_sections"])
        brd_markdown = (
            "# BRD\n\n"
            "## Executive Summary\n"
            "[[Acme]] depends on [[Synthetic Warehouse]] and [[Revenue Ops]] for the dry-run proof.\n"
        )
        brd_node = {
            "graph_id": org_slug,
            "node_id": f"brd-{org_slug}",
            "label": cast(str, template["label"]),
            "type": cast(str, template["type"]),
            "card_sections": [
                {
                    "title": cast(str, template_sections[0]["title"]),
                    "content": brd_markdown,
                    "order": cast(int, template_sections[0]["order"]),
                    "icon": cast(str, template_sections[0]["icon"]),
                }
            ],
        }
        update_node(store, brd_node)
        brd_path = write_artifact(
            "brd",
            {
                "graph_id": org_slug,
                "markdown": brd_markdown,
                "brd_node": {
                    "node_id": brd_node["node_id"],
                    "label": brd_node["label"],
                    "type": brd_node["type"],
                    "card_sections": brd_node["card_sections"],
                },
                "completeness_gate": completeness_gate,
            },
        )

        handoff("brainds-query-consultant", "brd", [str(brd_path), str(map_path)])
        run_elicit(store, {})

        # Derive backward-compat handoffs list from the delegator's recorded calls.
        # Each entry exposes at least 'agent' and 'prompt' so existing consumers
        # (e.g. test_sub_agent_writes_only_to_elicit) continue to pass unchanged.
        handoffs = delegator.to_handoffs()

        elicit_path = write_artifact(
            "elicit",
            {
                "graph_id": org_slug,
                "synthetic_source_path": str(copied_db),
                "artifact_refs": [
                    str(source_exploration_path),
                    str(source_docs_path),
                    str(map_path),
                    str(brd_path),
                ],
                "handoffs": handoffs,
                "completeness_gate": completeness_gate,
            },
        )

        return {
            "graph_id": org_slug,
            "store_path": store.path,
            "elicit_dir": str(elicit_dir),
            "synthetic_source_path": str(copied_db),
            "handoffs": handoffs,
            "delegation_calls": delegator.calls,
            "written_files": written_files,
            "entry_artifact": str(elicit_path),
        }
    finally:
        store.close()
