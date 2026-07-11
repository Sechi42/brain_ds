from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from brain_ds.mcp.security import ValidationError, validate_tool_input
from brain_ds.ontology.entity_types import EntityType
from brain_ds.ontology.relationship_types import RelationshipType
from brain_ds.mcp.tools import (
    TOOL_REGISTRY,
    add_edge,
    create_graph,
    explore_source,
    generate_brd,
    get_business_dossier,
    get_kpi_dossier,
    get_node,
    import_graph,
    list_data_sources,
    list_graphs,
    list_nodes,
    list_source_connections,
    list_workspaces,
    map_connections,
    manage_clusters,
    query_source,
    run_elicit,
    search_graph,
    snapshot_edges,
    update_node,
)
from brain_ds.connectors.secrets.binding_store import SecretBindingRecord, SecretBindingStore
from brain_ds.connectors.secrets.catalog import SecretCatalog, SecretEntry
from brain_ds.store.graph_store import GraphStore
from brain_ds.store.models import NearestHit


class MCPToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "store.db"
        self.store = GraphStore(str(self.db_path))
        self.graph_id = "graph-tools"
        self.store.meta_repo.save_graph_meta(
            graph_id=self.graph_id,
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="project-tools",
            org="org-tools",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "N-1",
                "label": "Alpha Task",
                "type": "Task",
                "supertype": "Work",
                "parent_id": "ROOT",
                "details": {"summary": "Find mapping evidence"},
            },
        )
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "N-2",
                "label": "Beta Note",
                "type": "Note",
                "supertype": "Knowledge",
                "parent_id": "ROOT",
                "details": {"summary": "Secondary"},
            },
        )
        # B-1: bystander node N-3 + edge N-2→N-3 seeded for isolation regression tests
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "N-3",
                "label": "Gamma Ref",
                "type": "Reference",
                "supertype": "Knowledge",
                "parent_id": "ROOT",
                "details": {"summary": "Bystander target"},
            },
        )
        self.store.upsert_edge(
            self.graph_id,
            {
                "source": "N-2",
                "target": "N-3",
                "label": "references",
                "weight": 0.9,
            },
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def _audit_count(self) -> int:
        row = self.store.conn.execute("SELECT COUNT(*) FROM tools_audit").fetchone()
        return int(row[0])

    def _last_outbox_event(self) -> tuple[str, str, str]:
        row = self.store.conn.execute(
            "SELECT event, graph_id, payload FROM event_outbox WHERE event != 'tool.invoked' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return (row[0], row[1], row[2])

    def _create_import_store(self) -> tuple[tempfile.TemporaryDirectory[str], GraphStore, Path]:
        project_dir = tempfile.TemporaryDirectory()
        store_dir = Path(project_dir.name) / ".brain_ds"
        store_dir.mkdir(parents=True)
        store = GraphStore(str(store_dir / "store.db"))
        return project_dir, store, Path(project_dir.name)

    def _expect_rows(self, result: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
        self.assertIsInstance(result, list)
        return cast(list[dict[str, Any]], result)

    def _expect_error(self, result: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
        self.assertIsInstance(result, dict)
        return cast(dict[str, Any], result)

    def _seed_google_sheets_secret(self, handle: str = "topete_final") -> str:
        catalog = SecretCatalog(self.temp_dir.name)
        catalog.add(
            SecretEntry(
                handle=handle,
                kind="google-sheets-json",
                metadata={
                    "spreadsheet_id": "catalog-spreadsheet-should-not-leak",
                    "sheet_range": "A1:Z",
                    "credential_type": "service_account",
                    "project_id": "safe-project",
                },
            ),
            raw_value="raw-service-account-should-not-leak",
        )
        return f"sec_test_ref_{handle}"

    def _upsert_google_sheets_source(self, node_id: str, details: dict[str, Any]) -> None:
        self.store.upsert_node(
            self.graph_id,
            {
                "id": node_id,
                "label": "ERP Sheet",
                "type": "Data Source",
                "supertype": "data",
                "details": {"source_kind": "google-sheets", **details},
            },
        )

    def _upsert_valid_google_sheets_binding(self, node_id: str, handle: str = "finance") -> None:
        secret_ref = self._seed_google_sheets_secret(handle)
        self._upsert_google_sheets_source(
            node_id,
            {"secret_binding": {"secret_ref": secret_ref, "provider_kind": "google-sheets-json", "validation_status": "valid"}},
        )
        SecretBindingStore(self.temp_dir.name).upsert(
            SecretBindingRecord(
                graph_id=self.graph_id,
                source_node_id=node_id,
                secret_ref_alias=secret_ref,
                internal_secret_id=handle,
                provider_kind="google-sheets-json",
                provider_inputs={"spreadsheet_ref": "erp-2025"},
                provider_mapping={"spreadsheet_id": "private-spreadsheet-id", "sheet_range": "A1:C10"},
                validation_status="valid",
            )
        )

    # B-1: bystander-preservation regression — update_node on N-1 must not mutate N-2 or the N-2→N-3 edge
    def test_update_node_preserves_unrelated_node_and_edge(self) -> None:
        update_node(
            self.store,
            {"graph_id": self.graph_id, "node_id": "N-1", "label": "Alpha-v2"},
        )
        # N-2 fields must be unchanged
        bystander = get_node(self.store, {"graph_id": self.graph_id, "node_id": "N-2"})
        self.assertEqual(bystander["label"], "Beta Note")
        self.assertEqual(bystander["type"], "Note")
        self.assertEqual(bystander["details"]["summary"], "Secondary")
        # Edge N-2→N-3 must still exist with original weight
        edge_rows = self.store.conn.execute(
            "SELECT weight, label FROM edges WHERE graph_id=? AND source=? AND target=?",
            (self.graph_id, "N-2", "N-3"),
        ).fetchall()
        self.assertEqual(len(edge_rows), 1)
        self.assertAlmostEqual(edge_rows[0][0], 0.9, places=4)
        self.assertEqual(edge_rows[0][1], "references")
        # Total node count must be 3 (N-1, N-2, N-3)
        node_count = self.store.conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE graph_id=?", (self.graph_id,)
        ).fetchone()[0]
        self.assertEqual(node_count, 3)

    # B-2: updated node reflects new values
    def test_update_node_write_takes_effect(self) -> None:
        update_node(
            self.store,
            {"graph_id": self.graph_id, "node_id": "N-1", "label": "Alpha-v2"},
        )
        refreshed = get_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1"})
        self.assertEqual(refreshed["label"], "Alpha-v2")

    def test_list_nodes_filters_and_missing_graph_error(self) -> None:
        result = self._expect_rows(list_nodes(self.store, {"graph_id": self.graph_id, "type": "Task"}))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "N-1")

        by_supertype = self._expect_rows(list_nodes(self.store, {"graph_id": self.graph_id, "supertype": "Knowledge"}))
        self.assertEqual(len(by_supertype), 2)  # N-2 (Beta Note) + N-3 (Gamma Ref) both Knowledge

        by_parent = self._expect_rows(list_nodes(self.store, {"graph_id": self.graph_id, "parent_id": "ROOT"}))
        self.assertEqual(len(by_parent), 3)  # N-1, N-2, N-3 all under ROOT

        by_empty_supertype = self._expect_rows(list_nodes(self.store, {"graph_id": self.graph_id, "supertype": "  "}))
        self.assertEqual(len(by_empty_supertype), 3)  # N-1, N-2, N-3

        by_empty_type = self._expect_rows(list_nodes(self.store, {"graph_id": self.graph_id, "type": ""}))
        self.assertEqual(len(by_empty_type), 3)  # N-1, N-2, N-3

        missing_graph = self._expect_error(list_nodes(self.store, {"graph_id": "missing"}))
        self.assertEqual(missing_graph["code"], -32000)
        self.assertEqual(missing_graph["message"], "Graph 'missing' not found")

    def test_get_node_returns_row_and_not_found_error(self) -> None:
        result = get_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1"})
        self.assertEqual(result["id"], "N-1")

        missing = get_node(self.store, {"graph_id": self.graph_id, "node_id": "N-404"})
        self.assertEqual(missing["code"], -32000)
        self.assertEqual(missing["message"], "Node 'N-404' not found in graph 'graph-tools'")

    def test_search_graph_matches_substrings_and_validates_query_type(self) -> None:
        by_label = self._expect_rows(search_graph(self.store, {"graph_id": self.graph_id, "query": "alpha"}))
        self.assertEqual([item["id"] for item in by_label], ["N-1"])

        by_type = self._expect_rows(search_graph(self.store, {"graph_id": self.graph_id, "query": "note"}))
        self.assertEqual([item["id"] for item in by_type], ["N-2"])

        by_details = self._expect_rows(search_graph(self.store, {"graph_id": self.graph_id, "query": "mapping"}))
        self.assertEqual([item["id"] for item in by_details], ["N-1"])

        no_match = self._expect_rows(search_graph(self.store, {"graph_id": self.graph_id, "query": "zzz"}))
        self.assertEqual(no_match, [])

        missing_graph = self._expect_error(search_graph(self.store, {"graph_id": "missing", "query": "x"}))
        self.assertEqual(missing_graph["code"], -32000)
        self.assertEqual(missing_graph["message"], "Graph 'missing' not found")

        invalid = self._expect_error(search_graph(self.store, {"graph_id": self.graph_id, "query": 42}))
        self.assertEqual(invalid["code"], -32602)
        self.assertIn("Expected string for query", invalid["message"])

    def test_tool_registry_and_schema_inventory_match_thirty_three_tools(self) -> None:
        self.assertEqual(len(TOOL_REGISTRY), 33)
        self.assertEqual(TOOL_REGISTRY["snapshot_edges"]["rw"], "read")
        self.assertEqual(TOOL_REGISTRY["get_kpi_dossier"]["rw"], "read")
        self.assertEqual(TOOL_REGISTRY["get_business_dossier"]["rw"], "read")

    def test_explore_source_google_sheets_table_exposes_rich_sheet_profile(self) -> None:
        self._upsert_valid_google_sheets_binding("DS-GSHEETS")
        profile = {
            "title": "Budget",
            "gid": "101",
            "headers": ["month", "amount"],
            "samples": [{"month": "Jan", "amount": 100}],
            "formulas": [{"cell": "B2", "formula": "=SUM(B3:B10)"}],
            "charts": [{"chart_id": 7, "title": "Spend by Month"}],
            "protected_ranges": [{"id": 55, "description": "Headers"}],
            "filter_views": [{"id": 88, "title": "Active budget"}],
            "limitations": ["Apps Script metadata is unavailable from the Sheets API profile"],
            "provenance": {"source": "google-sheets-api"},
        }

        class FakeSheetsConnector:
            def describe(self) -> dict[str, Any]:
                return {"kind": "google-sheets", "profile": {"sheet_count": 1}}

            def list_containers(self) -> list[str]:
                return ["Finance Workbook"]

            def list_tables(self, container: str) -> list[str]:
                return ["Budget"]

            def get_table_schema(self, container: str, table: str) -> dict[str, Any]:
                return {"columns": [{"name": "month"}, {"name": "amount"}], "profile": profile}

            def preview(self, container: str, table: str, limit: int = 5) -> dict[str, Any]:
                return {"columns": ["month", "amount"], "rows": profile["samples"], "profile": profile}

        with patch("brain_ds.mcp.tools._resolve_connector", return_value=FakeSheetsConnector()):
            result = explore_source(
                self.store,
                {
                    "graph_id": self.graph_id,
                    "node_id": "DS-GSHEETS",
                    "container": "Finance Workbook",
                    "table": "Budget",
                },
            )

        self.assertEqual(result["sheet_profile"]["formulas"][0]["formula"], "=SUM(B3:B10)")
        self.assertEqual(result["sheet_profile"]["charts"][0]["title"], "Spend by Month")
        self.assertEqual(result["sheet_profile"]["protected_ranges"][0]["description"], "Headers")
        self.assertEqual(result["sheet_profile"]["filter_views"][0]["title"], "Active budget")
        self.assertIn("Apps Script", result["sheet_profile"]["limitations"][0])
        self.assertEqual(result["sheet_profile"]["provenance"]["source"], "google-sheets-api")

    def test_provider_backed_explore_and_documentation_refuse_untrusted_binding_states(self) -> None:
        secret_ref = self._seed_google_sheets_secret()
        blocked_cases = [
            (
                "DS-LEGACY",
                {
                    "connection": {
                        "kind": "google-sheets-json",
                        "secret_handle": "topete_final",
                        "spreadsheet_id": "legacy-spreadsheet-should-not-leak",
                    }
                },
                None,
            ),
            (
                "DS-SPOOFED",
                {
                    "secret_binding": {
                        "secret_ref": secret_ref,
                        "provider_kind": "google-sheets-json",
                        "validation_status": "valid",
                        "provider_inputs": {"spreadsheet_ref": "graph-spreadsheet-should-not-leak"},
                    },
                    "connection": {
                        "kind": "google-sheets-json",
                        "secret_handle": "spoofed-topete-final",
                        "spreadsheet_id": "spoofed-spreadsheet-should-not-leak",
                    },
                },
                None,
            ),
            (
                "DS-UNVALIDATED",
                {"secret_binding": {"secret_ref": secret_ref, "provider_kind": "google-sheets-json", "validation_status": "unvalidated"}},
                SecretBindingRecord(
                    graph_id=self.graph_id,
                    source_node_id="DS-UNVALIDATED",
                    secret_ref_alias=secret_ref,
                    internal_secret_id="topete_final",
                    provider_kind="google-sheets-json",
                    provider_inputs={"spreadsheet_ref": "unvalidated-ref-should-not-leak"},
                    validation_status="unvalidated",
                ),
            ),
            (
                "DS-INVALID",
                {"secret_binding": {"secret_ref": secret_ref, "provider_kind": "google-sheets-json", "validation_status": "invalid"}},
                SecretBindingRecord(
                    graph_id=self.graph_id,
                    source_node_id="DS-INVALID",
                    secret_ref_alias=secret_ref,
                    internal_secret_id="topete_final",
                    provider_kind="google-sheets-json",
                    provider_inputs={"spreadsheet_ref": "invalid-ref-should-not-leak"},
                    validation_status="invalid",
                ),
            ),
            (
                "DS-MISSING-MAPPING",
                {"secret_binding": {"secret_ref": secret_ref, "provider_kind": "google-sheets-json", "validation_status": "valid"}},
                SecretBindingRecord(
                    graph_id=self.graph_id,
                    source_node_id="DS-MISSING-MAPPING",
                    secret_ref_alias=secret_ref,
                    internal_secret_id="topete_final",
                    provider_kind="google-sheets-json",
                    provider_inputs={"spreadsheet_ref": "missing-mapping-ref-should-not-leak"},
                    validation_status="valid",
                ),
            ),
        ]
        binding_store = SecretBindingStore(self.temp_dir.name)
        for node_id, details, record in blocked_cases:
            self._upsert_google_sheets_source(node_id, details)
            if record is not None:
                binding_store.upsert(record)

        for node_id, _details, _record in blocked_cases:
            for params in (
                {"graph_id": self.graph_id, "node_id": node_id},
                {"graph_id": self.graph_id, "node_id": node_id, "level": "documentation"},
            ):
                with self.subTest(node_id=node_id, params=params):
                    result = explore_source(self.store, params)
                    serialized = json.dumps(result, default=str)
                    self.assertEqual(result["code"], -32000)
                    self.assertIn("validated server-side binding", result["message"])
                    self.assertNotIn("raw-service-account-should-not-leak", serialized)
                    self.assertNotIn("topete_final", serialized)
                    self.assertNotIn("spoofed-topete-final", serialized)
                    self.assertNotIn("spreadsheet-should-not-leak", serialized)

    def test_valid_private_binding_rebuilds_google_sheets_descriptor_for_explore_source(self) -> None:
        secret_ref = self._seed_google_sheets_secret()
        self._upsert_google_sheets_source(
            "DS-VALID",
            {"secret_binding": {"secret_ref": secret_ref, "provider_kind": "google-sheets-json", "validation_status": "valid"}},
        )
        SecretBindingStore(self.temp_dir.name).upsert(
            SecretBindingRecord(
                graph_id=self.graph_id,
                source_node_id="DS-VALID",
                secret_ref_alias=secret_ref,
                internal_secret_id="topete_final",
                provider_kind="google-sheets-json",
                provider_inputs={"spreadsheet_ref": "erp-2025"},
                provider_mapping={"spreadsheet_id": "private-spreadsheet-id", "sheet_range": "A1:C10"},
                validation_status="valid",
            )
        )

        class FakeSheetsConnector:
            def describe(self) -> dict[str, Any]:
                return {"kind": "google-sheets", "title": "ERP"}

            def list_containers(self) -> list[str]:
                return ["ERP Workbook"]

        captured_connection: dict[str, Any] = {}

        def fake_resolve(connection: dict[str, Any], _project_root: Path) -> FakeSheetsConnector:
            captured_connection.update(connection)
            return FakeSheetsConnector()

        with patch("brain_ds.mcp.tools._resolve_connector", side_effect=fake_resolve):
            result = explore_source(self.store, {"graph_id": self.graph_id, "node_id": "DS-VALID"})

        self.assertEqual(result["containers"], ["ERP Workbook"])
        self.assertEqual(captured_connection["kind"], "google-sheets-json")
        self.assertEqual(captured_connection["secret_handle"], "topete_final")
        self.assertEqual(captured_connection["spreadsheet_id"], "private-spreadsheet-id")
        self.assertEqual(captured_connection["sheet_range"], "A1:C10")

    def test_validate_action_persists_private_mapping_used_by_explore_source(self) -> None:
        self._seed_google_sheets_secret("finance")
        self._upsert_google_sheets_source("DS-VALIDATED", {})
        self.store.secret_admin_enabled = True
        candidates = list_source_connections(
            self.store,
            {"graph_id": self.graph_id, "action": "candidate_secrets", "source_node_id": "DS-VALIDATED"},
        )
        secret_ref = candidates["secrets"][0]["secret_ref"]
        list_source_connections(
            self.store,
            {
                "graph_id": self.graph_id,
                "action": "bind",
                "source_node_id": "DS-VALIDATED",
                "secret_ref": secret_ref,
                "provider_inputs": {"spreadsheet_ref": "erp-2025"},
            },
        )

        with patch(
            "brain_ds.connectors.secrets.providers.google_sheets.GoogleSheetsJsonAdapter.probe",
            return_value={"spreadsheet_id": "validated-spreadsheet-id", "title": "ERP 2025"},
        ):
            validation = list_source_connections(
                self.store,
                {"graph_id": self.graph_id, "action": "validate", "source_node_id": "DS-VALIDATED"},
            )
        self.assertEqual(validation["binding"]["validation_status"], "valid")

        captured_connection: dict[str, Any] = {}

        class FakeSheetsConnector:
            def describe(self) -> dict[str, Any]:
                return {"kind": "google-sheets"}

            def list_containers(self) -> list[str]:
                return ["ERP Workbook"]

        def fake_resolve(connection: dict[str, Any], _project_root: Path) -> FakeSheetsConnector:
            captured_connection.update(connection)
            return FakeSheetsConnector()

        with patch("brain_ds.mcp.tools._resolve_connector", side_effect=fake_resolve):
            result = explore_source(self.store, {"graph_id": self.graph_id, "node_id": "DS-VALIDATED"})

        self.assertEqual(result["containers"], ["ERP Workbook"])
        self.assertEqual(captured_connection["spreadsheet_id"], "validated-spreadsheet-id")

    def test_query_source_refuses_legacy_secret_backed_connection_without_valid_private_binding(self) -> None:
        self._upsert_google_sheets_source(
            "DS-QUERY-LEGACY",
            {"connection": {"kind": "aws-postgres", "secret_handle": "topete_final", "database": "warehouse"}},
        )

        result = query_source(self.store, {"graph_id": self.graph_id, "node_id": "DS-QUERY-LEGACY", "sql": "select 1"})
        serialized = json.dumps(result, default=str)

        self.assertEqual(result["code"], -32000)
        self.assertIn("validated server-side binding", result["message"])
        self.assertNotIn("topete_final", serialized)
        self.assertNotIn("warehouse", serialized)

    def test_google_sheets_documentation_bundle_tracks_sheet_coverage_once(self) -> None:
        self._upsert_valid_google_sheets_binding("DS-GSHEETS")
        for node_id, label, status in [
            ("sheet-budget", "Budget", "documented"),
            ("sheet-apps-script", "Apps Script", "unsupported"),
        ]:
            self.store.upsert_node(
                self.graph_id,
                {
                    "id": node_id,
                    "label": label,
                    "type": "Data Container",
                    "supertype": "data-internal",
                    "parent_id": "DS-GSHEETS",
                    "details": {
                        "coverage_status": status,
                        "sheet_profile": {
                            "title": label,
                            "formulas": [{"cell": "B2", "formula": "=B3"}] if label == "Budget" else [],
                            "charts": [{"title": "Spend"}] if label == "Budget" else [],
                            "protected_ranges": [{"description": "Header"}] if label == "Budget" else [],
                            "filter_views": [{"title": "Active"}] if label == "Budget" else [],
                            "limitations": ["Apps Script metadata is unavailable from the Sheets API profile"],
                            "provenance": {"source": "google-sheets-api"},
                        },
                    },
                    "card_sections": [
                        {"title": "Columns / Fields", "content": "| col | type |\n|---|---|\n| month | string |", "order": 1},
                    ],
                },
            )

        result = explore_source(self.store, {"graph_id": self.graph_id, "node_id": "DS-GSHEETS", "level": "documentation"})

        coverage = {table["label"]: table["coverage_status"] for table in result["tables"]}
        self.assertEqual(coverage, {"Apps Script": "unsupported", "Budget": "documented"})
        budget = next(table for table in result["tables"] if table["label"] == "Budget")
        self.assertEqual(budget["sheet_profile"]["formulas"][0]["formula"], "=B3")
        self.assertEqual(budget["sheet_profile"]["charts"][0]["title"], "Spend")
        self.assertEqual(budget["sheet_profile"]["protected_ranges"][0]["description"], "Header")
        self.assertEqual(budget["sheet_profile"]["filter_views"][0]["title"], "Active")
        self.assertIn("Apps Script", budget["limitations"][0])

    def test_explore_source_google_sheets_container_exposes_per_sheet_profiles(self) -> None:
        self._upsert_valid_google_sheets_binding("DS-GSHEETS")
        profiles = {
            "Budget": {
                "title": "Budget",
                "formulas": [{"cell": "B2", "formula": "=SUM(B3:B10)"}],
                "charts": [{"title": "Spend by Month"}],
                "protected_ranges": [{"description": "Headers"}],
                "filter_views": [{"title": "Active budget"}],
                "limitations": ["Apps Script metadata is unavailable from the Sheets API profile"],
                "provenance": {"source": "google-sheets-api"},
            },
            "Forecast": {
                "title": "Forecast",
                "formulas": [],
                "charts": [],
                "protected_ranges": [],
                "filter_views": [],
                "limitations": ["Apps Script metadata is unavailable from the Sheets API profile"],
                "provenance": {"source": "google-sheets-api"},
            },
        }

        class FakeSheetsConnector:
            def describe(self) -> dict[str, Any]:
                return {"kind": "google-sheets"}

            def list_containers(self) -> list[str]:
                return ["Finance Workbook"]

            def list_tables(self, container: str) -> list[str]:
                return ["Budget", "Forecast"]

            def sheet_profile(self, table: str) -> dict[str, Any]:
                return profiles[table]

        with patch("brain_ds.mcp.tools._resolve_connector", return_value=FakeSheetsConnector()):
            result = explore_source(
                self.store,
                {"graph_id": self.graph_id, "node_id": "DS-GSHEETS", "container": "Finance Workbook"},
            )

        self.assertEqual([profile["title"] for profile in result["sheet_profiles"]], ["Budget", "Forecast"])
        self.assertEqual(result["sheet_profiles"][0]["formulas"][0]["formula"], "=SUM(B3:B10)")
        self.assertEqual(result["sheet_profiles"][0]["charts"][0]["title"], "Spend by Month")
        self.assertIn("Apps Script", result["sheet_profiles"][1]["limitations"][0])

    def test_google_sheets_internal_template_names_rich_sheet_surfaces(self) -> None:
        self._upsert_valid_google_sheets_binding("DS-GSHEETS")

        result = explore_source(self.store, {"graph_id": self.graph_id, "node_id": "DS-GSHEETS", "level": "internal"})
        serialized = json.dumps(result["template"], sort_keys=True)

        self.assertIn("formula", serialized)
        self.assertIn("chart", serialized)
        self.assertIn("protected_range", serialized)
        self.assertIn("filter_view", serialized)
        self.assertIn("apps_script_limitation", serialized)

    def test_business_dossier_request_defaults_to_read_only_no_write_contract(self) -> None:
        from brain_ds.dossier.business_models import BusinessDossierRequest

        before_nodes = len(self.store.query_nodes(self.graph_id))
        before_edges = len(self.store.query_edges(self.graph_id))
        before_audit = self._audit_count()

        request = BusinessDossierRequest(graph_id=self.graph_id, query="what is hurting delivery performance?")

        self.assertFalse(request.create_pending_questions)
        self.assertEqual(request.stakeholder_owner, "")
        self.assertEqual(len(self.store.query_nodes(self.graph_id)), before_nodes)
        self.assertEqual(len(self.store.query_edges(self.graph_id)), before_edges)
        self.assertEqual(self._audit_count(), before_audit)

    def test_get_business_dossier_returns_business_first_payload_without_default_writes(self) -> None:
        self.store.upsert_node(
            self.graph_id,
            {"id": "KPI-1", "label": "On-time Delivery", "type": EntityType.KPI.value, "supertype": "metric", "details": {"description": "Delivery performance"}},
        )
        self.store.upsert_node(
            self.graph_id,
            {"id": "DS-1", "label": "Warehouse Events", "type": EntityType.DATA_SOURCE.value, "supertype": "data", "details": {"description": "Raw delivery events"}},
        )
        self.store.upsert_edge(
            self.graph_id,
            {"source": "KPI-1", "target": "DS-1", "label": RelationshipType.MEASURED_BY.value, "weight": 0.9},
        )
        before_nodes = len(self.store.query_nodes(self.graph_id))
        before_edges = len(self.store.query_edges(self.graph_id))
        before_pending = len(self.store.list_pending_questions(self.graph_id))
        before_audit = self._audit_count()

        result = get_business_dossier(self.store, {"graph_id": self.graph_id, "query": "delivery performance"})

        self.assertEqual(result["query"], "delivery performance")
        self.assertEqual(result["dossier"]["kpis"][0]["id"], "KPI-1")
        self.assertEqual(result["pending_questions_created"], [])
        self.assertIn("serialized_for_llm", result)
        self.assertEqual(len(self.store.query_nodes(self.graph_id)), before_nodes)
        self.assertEqual(len(self.store.query_edges(self.graph_id)), before_edges)
        self.assertEqual(len(self.store.list_pending_questions(self.graph_id)), before_pending)
        self.assertEqual(self._audit_count(), before_audit)

    def test_get_business_dossier_rejects_unknown_params_and_empty_query(self) -> None:
        unknown = self._expect_error(
            get_business_dossier(self.store, {"graph_id": self.graph_id, "query": "delivery", "unexpected": True})
        )
        self.assertEqual(unknown["code"], -32602)
        self.assertIn("Unknown parameter: unexpected", unknown["message"])

        empty = self._expect_error(get_business_dossier(self.store, {"graph_id": self.graph_id, "query": "   "}))
        self.assertEqual(empty["code"], -32602)
        self.assertIn("query must not be empty", empty["message"])

    def test_get_business_dossier_explicit_pending_questions_append_only_and_no_edges(self) -> None:
        self.store.upsert_node(
            self.graph_id,
            {"id": "KPI-1", "label": "On-time Delivery", "type": EntityType.KPI.value, "supertype": "metric", "details": {"description": "Delivery performance"}},
        )
        self.store.upsert_node(
            self.graph_id,
            {"id": "DS-1", "label": "Warehouse Events", "type": EntityType.DATA_SOURCE.value, "supertype": "data", "details": {"description": "Raw delivery events"}},
        )
        self.store.upsert_edge(
            self.graph_id,
            {"source": "KPI-1", "target": "DS-1", "label": RelationshipType.MEASURED_BY.value, "weight": 0.2},
        )
        self.store.upsert_node(
            self.graph_id,
            {"id": "Other-1", "label": "Other KPI", "type": EntityType.KPI.value, "supertype": "metric", "details": {}},
        )
        self.store.upsert_node(
            self.graph_id,
            {"id": "Other-2", "label": "Other Source", "type": EntityType.DATA_SOURCE.value, "supertype": "data", "details": {}},
        )
        self.store.upsert_edge(
            self.graph_id,
            {"source": "Other-1", "target": "Other-2", "label": RelationshipType.MEASURED_BY.value, "weight": 0.1},
        )
        before_nodes = len(self.store.query_nodes(self.graph_id))
        before_edges = len(self.store.query_edges(self.graph_id))
        before_pending = len(self.store.list_pending_questions(self.graph_id))

        result = get_business_dossier(
            self.store,
            {
                "graph_id": self.graph_id,
                "query": "delivery performance",
                "create_pending_questions": True,
                "stakeholder_owner": "Operations Lead",
            },
        )

        self.assertEqual(len(result["pending_questions_created"]), 1)
        created = result["pending_questions_created"][0]
        self.assertEqual(created["graph_id"], self.graph_id)
        self.assertEqual(created["target_node_id"], "DS-1")
        self.assertEqual(created["stakeholder_owner"], "Operations Lead")
        self.assertEqual(len(self.store.query_nodes(self.graph_id)), before_nodes)
        self.assertEqual(len(self.store.query_edges(self.graph_id)), before_edges)
        pending = self.store.list_pending_questions(self.graph_id)
        self.assertEqual(len(pending), before_pending + 1)
        self.assertEqual(pending[-1].target_node_id, "DS-1")
        self.assertNotEqual(pending[-1].target_node_id, "Other-2")

    def test_get_kpi_dossier_returns_structured_dossier_without_writes(self) -> None:
        self.store.upsert_node(
            self.graph_id,
            {"id": "KPI-1", "label": "On-time Delivery", "type": EntityType.KPI.value, "supertype": "metric", "details": {"description": "Shipments delivered on time"}},
        )
        self.store.upsert_node(
            self.graph_id,
            {"id": "DS-1", "label": "Warehouse", "type": EntityType.DATA_SOURCE.value, "supertype": "data", "details": {"description": "Warehouse events"}},
        )
        self.store.upsert_edge(
            self.graph_id,
            {"source": "KPI-1", "target": "DS-1", "label": RelationshipType.MEASURED_BY.value, "weight": 0.9},
        )
        before_nodes = len(self.store.query_nodes(self.graph_id))
        before_edges = len(self.store.query_edges(self.graph_id))
        before_audit = self._audit_count()

        result = get_kpi_dossier(self.store, {"graph_id": self.graph_id, "kpi_node_id": "KPI-1"})

        self.assertEqual(result["kpi"]["id"], "KPI-1")
        self.assertEqual(result["data_sources"][0]["id"], "DS-1")
        self.assertIn("serialized_for_llm", result)
        self.assertEqual(len(self.store.query_nodes(self.graph_id)), before_nodes)
        self.assertEqual(len(self.store.query_edges(self.graph_id)), before_edges)
        self.assertEqual(self._audit_count(), before_audit)

    def test_get_kpi_dossier_keeps_pending_lineage_out_of_data_sources(self) -> None:
        self.store.upsert_node(
            self.graph_id,
            {"id": "KPI-1", "label": "On-time Delivery", "type": EntityType.KPI.value, "supertype": "metric", "details": {}},
        )
        self.store.upsert_node(
            self.graph_id,
            {"id": "DS-1", "label": "Warehouse", "type": EntityType.DATA_SOURCE.value, "supertype": "data", "details": {}},
        )
        self.store.upsert_node(
            self.graph_id,
            {"id": "DC-1", "label": "shipments", "type": EntityType.DATA_CONTAINER.value, "supertype": "data-internal", "parent_id": "DS-1", "details": {}},
        )
        self.store.upsert_edge(
            self.graph_id,
            {"source": "KPI-1", "target": "DS-1", "label": RelationshipType.MEASURED_BY.value, "weight": 0.9},
        )
        self.store.append_ledger(
            graph_id=self.graph_id,
            target_id="KPI-1->DC-1:measured-from",
            target_type="edge",
            status="needs-confirmation",
            relationship_label=RelationshipType.MEASURED_FROM.value,
            source_node_id="KPI-1",
            target_node_id="DC-1",
            source_node_type=EntityType.KPI.value,
            target_node_type=EntityType.DATA_CONTAINER.value,
            provenance="generated",
            captured_at="2026-06-26T00:00:00+00:00",
        )

        with patch.object(self.store, "list_pending_confirmations", wraps=self.store.list_pending_confirmations) as pending_spy:
            result = get_kpi_dossier(self.store, {"graph_id": self.graph_id, "kpi_node_id": "KPI-1"})

        pending_spy.assert_called_once_with(self.graph_id)
        self.assertEqual(result["data_sources"][0]["containers"], [])
        self.assertIn(
            {
                "candidate_id": "KPI-1->DC-1:measured-from",
                "from_node": "KPI-1",
                "to_node": "DC-1",
                "relationship": RelationshipType.MEASURED_FROM.value,
                "source": "insert_pending_question",
            },
            result["limitations"]["unconfirmed_lineage"],
        )

    def test_get_kpi_dossier_degrades_gracefully_for_oversized_graph(self) -> None:
        self.store.upsert_node(
            self.graph_id,
            {"id": "KPI-1", "label": "On-time Delivery", "type": EntityType.KPI.value, "supertype": "metric", "details": {}},
        )
        for index in range(1100):
            self.store.upsert_node(
                self.graph_id,
                {
                    "id": f"bulk-{index}",
                    "label": f"Bulk {index}",
                    "type": "Note",
                    "supertype": "knowledge",
                    "details": {},
                },
            )

        with patch("brain_ds.mcp.tools.assess_completeness") as completeness_spy:
            result = get_kpi_dossier(self.store, {"graph_id": self.graph_id, "kpi_node_id": "KPI-1"})

        completeness_spy.assert_not_called()
        self.assertEqual(result["kpi"]["id"], "KPI-1")
        self.assertEqual(result["data_sources"], [])
        self.assertTrue(result["limitations"]["truncated"])
        self.assertIn("graph size", result["limitations"]["truncation_reason"])

    def test_get_kpi_dossier_returns_structured_errors(self) -> None:
        self.store.upsert_node(
            self.graph_id,
            {"id": "DS-1", "label": "Warehouse", "type": EntityType.DATA_SOURCE.value, "supertype": "data", "details": {}},
        )

        non_kpi = self._expect_error(get_kpi_dossier(self.store, {"graph_id": self.graph_id, "kpi_node_id": "DS-1"}))
        self.assertEqual(non_kpi["code"], -32602)
        self.assertIn("DataSource", non_kpi["message"])

        missing_node = self._expect_error(get_kpi_dossier(self.store, {"graph_id": self.graph_id, "kpi_node_id": "missing"}))
        self.assertEqual(missing_node["code"], -32000)
        self.assertIn("Node 'missing' not found", missing_node["message"])

        missing_graph = self._expect_error(get_kpi_dossier(self.store, {"graph_id": "missing", "kpi_node_id": "DS-1"}))
        self.assertEqual(missing_graph["code"], -32000)
        self.assertIn("Graph 'missing' not found", missing_graph["message"])

    def test_update_node_partial_update_audit_and_read_only_rejection(self) -> None:
        before = self.store.query_nodes(self.graph_id, type="Task")[0]
        before_audit = self._audit_count()

        updated = update_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1", "label": "Renamed"})
        self.assertEqual(updated["label"], "Renamed")
        self.assertEqual(updated["type"], "Task")
        self.assertGreater(updated["modified_at"], before.modified_at)
        self.assertEqual(self._audit_count(), before_audit + 1)

        audit_row = self.store.conn.execute(
            "SELECT tool_name, result_status FROM tools_audit ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(audit_row[0], "update_node")
        self.assertEqual(audit_row[1], "ok")

        self.store.close()
        read_only = GraphStore(str(self.db_path), read_only=True)
        try:
            rejected = update_node(read_only, {"graph_id": self.graph_id, "node_id": "N-1", "label": "X"})
            self.assertEqual(rejected["code"], -32000)
            self.assertEqual(rejected["message"], "GraphStore is read-only")
        finally:
            read_only.close()

    def test_update_node_enqueues_node_created(self) -> None:
        created = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "N-new",
                "label": "Gamma",
                "type": "Task",
                "supertype": "Work",
                "details": {"summary": "new"},
            },
        )
        self.assertEqual(created["id"], "N-new")

        event, graph_id, payload = self._last_outbox_event()
        self.assertEqual(event, "node.created")
        self.assertEqual(graph_id, self.graph_id)
        self.assertEqual(json.loads(payload)["id"], "N-new")

    def test_update_node_enqueues_node_updated(self) -> None:
        updated = update_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1", "label": "Renamed"})
        self.assertEqual(updated["label"], "Renamed")

        event, graph_id, payload = self._last_outbox_event()
        self.assertEqual(event, "node.updated")
        self.assertEqual(graph_id, self.graph_id)
        self.assertEqual(json.loads(payload)["id"], "N-1")

    def test_update_node_enqueues_tool_invoked_ok(self) -> None:
        update_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1", "label": "Renamed"})

        row = self.store.conn.execute(
            "SELECT event, graph_id, payload FROM event_outbox WHERE event = 'tool.invoked' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "tool.invoked")
        self.assertEqual(row[1], self.graph_id)
        payload = json.loads(row[2])
        self.assertEqual(payload["tool"], "update_node")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["target_id"], "N-1")
        self.assertIn("N-1", payload["params_summary"])

    def test_update_node_card_sections_persists(self) -> None:
        updated = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "N-1",
                "card_sections": [{"title": "Risks", "content": "Budget overrun", "icon": "", "order": 1}],
            },
        )
        self.assertIn("card_sections", updated)
        self.assertEqual(updated["card_sections"][0]["title"], "Risks")

        reread = get_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1"})
        self.assertEqual(reread["card_sections"][0]["content"], "Budget overrun")

        event, graph_id, payload = self._last_outbox_event()
        self.assertEqual(event, "node.updated")
        self.assertEqual(graph_id, self.graph_id)
        self.assertEqual(json.loads(payload)["card_sections"][0]["title"], "Risks")

    def test_update_node_rejects_unknown_card_section_key_and_keeps_store_clean(self) -> None:
        rejected = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "N-1",
                "card_sections": [{"title": "Risks", "body": "Budget overrun", "icon": "", "order": 1}],
            },
        )

        self.assertEqual(rejected["code"], -32602)
        self.assertIn("body", rejected["message"])

        reread = get_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1"})
        self.assertIsNone(reread.get("card_sections"))

    def test_add_edge_success_and_missing_nodes_log_error(self) -> None:
        before = self._audit_count()
        created = add_edge(
            self.store,
            {
                "graph_id": self.graph_id,
                "source": "N-1",
                "target": "N-2",
                "label": "rel",
                "weight": 0.6,
            },
        )
        self.assertEqual(created["source"], "N-1")
        self.assertEqual(created["target"], "N-2")
        self.assertEqual(self._audit_count(), before + 1)

        ok_row = self.store.conn.execute(
            "SELECT tool_name, result_status FROM tools_audit ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(ok_row[0], "add_edge")
        self.assertEqual(ok_row[1], "ok")

        bad_source = add_edge(
            self.store,
            {"graph_id": self.graph_id, "source": "N-404", "target": "N-2", "label": "rel"},
        )
        self.assertEqual(bad_source["code"], -32000)
        self.assertEqual(bad_source["message"], "Source node 'N-404' not found")

        bad_target = add_edge(
            self.store,
            {"graph_id": self.graph_id, "source": "N-1", "target": "N-404", "label": "rel"},
        )
        self.assertEqual(bad_target["code"], -32000)
        self.assertEqual(bad_target["message"], "Target node 'N-404' not found")

        error_rows = self.store.conn.execute(
            "SELECT result_status FROM tools_audit WHERE tool_name='add_edge' ORDER BY id DESC LIMIT 2"
        ).fetchall()
        self.assertEqual(error_rows[0][0], "error")
        self.assertEqual(error_rows[1][0], "error")

    def test_add_edge_error_receipt(self) -> None:
        add_edge(
            self.store,
            {"graph_id": self.graph_id, "source": "N-404", "target": "N-2", "label": "rel"},
        )
        row = self.store.conn.execute(
            "SELECT event, graph_id, payload FROM event_outbox WHERE event = 'tool.invoked' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "tool.invoked")
        self.assertEqual(row[1], self.graph_id)
        payload = json.loads(row[2])
        self.assertEqual(payload["tool"], "add_edge")
        self.assertEqual(payload["status"], "error")
        self.assertIn("N-404", payload["params_summary"])

    def test_add_edge_enqueues_edge_created(self) -> None:
        created = add_edge(
            self.store,
            {
                "graph_id": self.graph_id,
                "source": "N-1",
                "target": "N-2",
                "label": "rel",
            },
        )
        self.assertEqual(created["source"], "N-1")

        event, graph_id, payload = self._last_outbox_event()
        self.assertEqual(event, "edge.created")
        self.assertEqual(graph_id, self.graph_id)
        self.assertEqual(json.loads(payload)["source"], "N-1")

    def test_add_edge_enqueues_edge_updated(self) -> None:
        add_edge(
            self.store,
            {
                "graph_id": self.graph_id,
                "source": "N-1",
                "target": "N-2",
                "label": "rel",
            },
        )
        updated = add_edge(
            self.store,
            {
                "graph_id": self.graph_id,
                "source": "N-1",
                "target": "N-2",
                "label": "rel-2",
            },
        )
        self.assertEqual(updated["label"], "rel-2")

        event, graph_id, payload = self._last_outbox_event()
        self.assertEqual(event, "edge.updated")
        self.assertEqual(graph_id, self.graph_id)
        self.assertEqual(json.loads(payload)["label"], "rel-2")

    # Task 1.9 — per-tool error tests (split from test_agent_stubs_return_expected_error).
    # Handlers still raise -32001 in PR1; tests stay GREEN until PR2-4 flip them.

    def test_run_elicit_returns_context(self) -> None:
        result = run_elicit(self.store, {})
        # Must not return an error code — R1 spec: no -32001.
        self.assertNotIn("code", result)
        # entity_types length matches live enum — R5.
        self.assertEqual(len(result["entity_types"]), len(list(EntityType)))
        # supertypes is a sorted list with entries.
        supertypes = result["supertypes"]
        self.assertIsInstance(supertypes, list)
        self.assertGreater(len(supertypes), 0)
        self.assertEqual(supertypes, sorted(supertypes))
        # expected_sections keys match entity type values.
        expected_keys = {e.value for e in EntityType}
        self.assertEqual(set(result["expected_sections"].keys()), expected_keys)
        # relationship_types length matches live enum — R5.
        self.assertEqual(len(result["relationship_types"]), len(list(RelationshipType)))
        # base_weights length matches live enum — R5.
        self.assertEqual(len(result["base_weights"]), len(list(RelationshipType)))
        # Category-2 keys are truthy.
        self.assertTrue(result["question_bank"])
        self.assertTrue(result["org_slug_rules"])
        self.assertTrue(result["node_id_format"])
        self.assertTrue(result["node_write_templates"])

    def test_map_connections_returns_context(self) -> None:
        from brain_ds.scoring.engine import ScoringEngine

        result = map_connections(self.store, {})
        # Must not return an error code — R2 spec: no -32001.
        self.assertNotIn("code", result)
        # entity_types length matches live enum — R5.
        self.assertEqual(len(result["entity_types"]), len(list(EntityType)))
        # connection_rules is truthy (non-empty).
        self.assertTrue(result["connection_rules"])
        # relationship_labels length matches live enum — R5.
        self.assertEqual(len(result["relationship_labels"]), len(list(RelationshipType)))
        # scoring_factors length matches ScoringEngine factor_weights — R2.
        self.assertEqual(len(result["scoring_factors"]), len(ScoringEngine().factor_weights))
        # B1 boundary: result MUST NOT contain computed connections or edges keys.
        self.assertNotIn("connections", result)
        self.assertNotIn("edges", result)

    def test_generate_brd_returns_context(self) -> None:
        result = generate_brd(self.store, {})
        # Must not return an error code — R3 spec: no -32001.
        self.assertNotIn("code", result)
        # entity_types length matches live enum — R5.
        self.assertEqual(len(result["entity_types"]), len(list(EntityType)))
        # brd_section_order has 14 entries — design contract.
        self.assertEqual(len(result["brd_section_order"]), 14)
        # section_rules is truthy (non-empty).
        self.assertTrue(result["section_rules"])
        # completeness_matrix_template is truthy.
        self.assertTrue(result["completeness_matrix_template"])
        # B1 boundary: result MUST NOT contain a computed brd or document key.
        self.assertNotIn("brd", result)
        self.assertNotIn("document", result)

    # Task 1.8 — schema validation tests (RED until Task 1.7 adds schemas to TOOL_SCHEMAS).

    def test_run_elicit_valid_input_passes_schema(self) -> None:
        result = validate_tool_input("run_elicit", {})
        self.assertIsInstance(result, dict)

    def test_map_connections_valid_input_passes_schema(self) -> None:
        result = validate_tool_input("map_connections", {})
        self.assertIsInstance(result, dict)

    def test_generate_brd_valid_input_passes_schema(self) -> None:
        result = validate_tool_input("generate_brd", {})
        self.assertIsInstance(result, dict)

    # Task S1 — negative-path schema tests: additionalProperties: False must reject unknown keys.

    def test_run_elicit_invalid_input_raises(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_tool_input("run_elicit", {"bogus": 1})
        self.assertEqual(ctx.exception.code, -32602)

    def test_map_connections_invalid_input_raises(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_tool_input("map_connections", {"bogus": 1})
        self.assertEqual(ctx.exception.code, -32602)

    def test_generate_brd_invalid_input_raises(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_tool_input("generate_brd", {"bogus": 1})
        self.assertEqual(ctx.exception.code, -32602)

    def test_list_graphs_empty_and_populated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty_store = GraphStore(str(Path(tmp) / "store.db"))
            try:
                empty = list_graphs(empty_store, {})
            finally:
                empty_store.close()
            self.assertEqual(empty, [])

        self.store.meta_repo.save_graph_meta(
            graph_id="graph-two",
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="project-two",
            org="org-two",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=3,
            edge_count=1,
            imported_from=None,
            generated_at="",
        )

        populated = list_graphs(self.store, {})
        self.assertEqual(len(populated), 2)
        self.assertTrue(all("id" in graph for graph in populated))
        self.assertTrue(all("org" in graph for graph in populated))
        self.assertTrue(all("project" in graph for graph in populated))
        self.assertTrue(all("node_count" in graph for graph in populated))
        self.assertTrue(all("edge_count" in graph for graph in populated))

    def test_create_graph_tool(self) -> None:
        result = create_graph(
            self.store,
            {"graph_id": "logitrans", "name": "Logitrans", "project": "brain-ds"},
        )

        self.assertEqual(result["id"], "logitrans")
        self.assertEqual(result["org"], "Logitrans")
        self.assertEqual(result["node_count"], 0)
        self.assertEqual(result["edge_count"], 0)

    def test_create_graph_duplicate(self) -> None:
        create_graph(self.store, {"graph_id": "logitrans"})

        duplicate = create_graph(self.store, {"graph_id": "logitrans"})
        self.assertEqual(duplicate["code"], -32000)
        self.assertEqual(duplicate["message"], "Graph 'logitrans' already exists")

    def test_import_graph_tool(self) -> None:
        project_dir, store, project_root = self._create_import_store()
        try:
            payload = {
                "schema_version": "2.0.0",
                "org": "Logitrans",
                "generated_at": "",
                "nodes": [
                    {
                        "id": "ds-1",
                        "label": "ERP",
                        "type": "Data Source",
                        "details": {"owner": "ops"},
                        "supertype": "data",
                        "parent_id": None,
                        "depth": 0,
                    }
                ],
                "edges": [],
                "evidence": [],
            }
            source_path = project_root / "seed.json"
            source_path.write_text(json.dumps(payload), encoding="utf-8")

            result = import_graph(store, {"file_path": str(source_path), "graph_id": "logitrans"})

            self.assertEqual(result["graph_id"], "logitrans")
            self.assertEqual(result["node_count"], 1)
            self.assertEqual(len(store.query_nodes("logitrans")), 1)
        finally:
            store.close()
            project_dir.cleanup()

    def test_import_graph_path_traversal_rejected(self) -> None:
        project_dir, store, project_root = self._create_import_store()
        try:
            outside_dir = Path(project_root).parent
            outside_path = outside_dir / "outside-seed.json"
            outside_path.write_text("{}", encoding="utf-8")

            escaped = import_graph(store, {"file_path": str(project_root / ".." / outside_path.name)})

            self.assertEqual(escaped["code"], -32000)
            self.assertIn("Path traversal", escaped["message"])
        finally:
            if outside_path.exists():
                outside_path.unlink()
            store.close()
            project_dir.cleanup()

    def test_list_data_sources(self) -> None:
        update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "DS-1",
                "label": "ERP",
                "type": "Data Source",
                "supertype": "data",
                "details": {"owner": "ops"},
            },
        )

        result = self._expect_rows(list_data_sources(self.store, {"graph_id": self.graph_id}))

        self.assertEqual([item["id"] for item in result], ["DS-1"])
        typed = self._expect_rows(list_nodes(self.store, {"graph_id": self.graph_id, "type": "Data Source"}))
        self.assertEqual(result, typed)

    def test_update_node_strips_secret_binding_spoof_fields(self) -> None:
        result = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "DS-SPOOF",
                "label": "Spoofed Source",
                "type": "Data Source",
                "details": {
                    "owner": "ops",
                    "secret_binding": {
                        "secret_ref": "sec_topete",
                        "validation_status": "valid",
                        "provider_inputs": {"spreadsheet_ref": "raw-input-ref"},
                    },
                    "connection": {
                        "kind": "google_sheets",
                        "secret_handle": "topete_final",
                        "spreadsheet_id": "real-spreadsheet-id",
                    },
                    "validation_status": "valid",
                    "secret_ref": "sec_topete",
                    "exposure": {"allowed": True},
                },
            },
        )

        self.assertNotIn("code", result)
        self.assertEqual(result["details"], {"owner": "ops"})

    def test_secret_binding_store_projects_redacted_graph_state(self) -> None:
        store = SecretBindingStore(Path(self.temp_dir.name))
        record = SecretBindingRecord(
            graph_id=self.graph_id,
            source_node_id="DS-1",
            secret_ref_alias="sec_topete",
            internal_secret_id="aws:arn:raw-secret",
            provider_kind="google_sheets",
            provider_inputs={"spreadsheet_ref": "sheet-alias"},
            provider_mapping={"spreadsheet_id": "real-spreadsheet-id"},
            validation_status="valid",
            documentation_status="pending",
            writeback_status="idle",
            validation={"validated_at": "2026-07-03T00:00:00Z"},
        )

        store.upsert(record)
        loaded = store.get(self.graph_id, "DS-1")

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.provider_mapping, {"spreadsheet_id": "real-spreadsheet-id"})
        self.assertEqual(
            loaded.to_projection(),
            {
                "secret_ref": "sec_topete",
                "provider_kind": "google_sheets",
                "validation_status": "valid",
                "documentation_status": "pending",
                "writeback_status": "idle",
                "provider_inputs": {"spreadsheet_ref": "sheet-alias"},
                "exposure": {"graph_id": self.graph_id, "allowed": True},
                "validation": {"validated_at": "2026-07-03T00:00:00Z"},
            },
        )

    def test_registry_has_thirty_three_tools_and_reads_do_not_audit(self) -> None:
        names = sorted(TOOL_REGISTRY.keys())
        self.assertEqual(len(names), 33)
        self.assertEqual(
            names,
            [
                "add_edge",
                "assess_completeness",
                "assess_currency",
                "create_graph",
                "delete_edge",
                "delete_node",
                "explore_source",
                "generate_brd",
                "get_business_dossier",
                "get_kpi_dossier",
                "get_node",
                "get_weak_edges",
                "import_graph",
                "insert_pending_question",
                "list_data_sources",
                "list_graphs",
                "list_nodes",
                "list_pending_confirmations",
                "list_secret_handles",
                "list_source_connections",
                "list_workspaces",
                "manage_clusters",
                "map_connections",
                "open_workspace",
                "query_source",
                "resolve_confirmation",
                "retrieve_context",
                "run_elicit",
                "search_graph",
                "snapshot_edges",
                "suggest_connections",
                "update_node",
                "validate_secret_handle",
            ],
        )

        # Task 1.11 — flipped to assertFalse after registry update in Task 1.10.
        self.assertFalse(TOOL_REGISTRY["run_elicit"]["requires_ai_agent"])
        self.assertFalse(TOOL_REGISTRY["map_connections"]["requires_ai_agent"])
        self.assertFalse(TOOL_REGISTRY["generate_brd"]["requires_ai_agent"])

        before = self._audit_count()
        list_nodes(self.store, {"graph_id": self.graph_id})
        get_node(self.store, {"graph_id": self.graph_id, "node_id": "N-1"})
        search_graph(self.store, {"graph_id": self.graph_id, "query": "alpha"})
        after = self._audit_count()
        self.assertEqual(before, after)

    def _seed_google_sheets_secret(self, handle: str = "topete_final") -> None:
        catalog = SecretCatalog(self.temp_dir.name)
        catalog.add(
            SecretEntry(
                handle=handle,
                kind="google-sheets-json",
                metadata={
                    "spreadsheet_id": "raw-spreadsheet-id",
                    "sheet_range": "ERP!A1:Z",
                    "credential_type": "service_account",
                    "project_id": "topete-project",
                    "email_fingerprint": "email-fp",
                    "key_id_fingerprint": "key-fp",
                    "universe_domain": "googleapis.com",
                },
            ),
            raw_value='{"type":"service_account"}',
        )

    def test_source_first_connection_flow_lists_binds_validates_status_and_unbinds_without_leaks(self) -> None:
        self._seed_google_sheets_secret()
        self.store.secret_admin_enabled = True
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "DS-ERP",
                "label": "ERP 2025",
                "type": "Data Source",
                "details": {"source_kind": "google-sheets"},
            },
        )

        candidates = list_source_connections(
            self.store,
            {"graph_id": self.graph_id, "action": "candidate_secrets", "source_node_id": "DS-ERP"},
        )

        self.assertEqual(candidates["status"], "ok")
        self.assertEqual(candidates["source"]["node_id"], "DS-ERP")
        self.assertEqual(len(candidates["secrets"]), 1)
        secret_ref = candidates["secrets"][0]["secret_ref"]
        serialized_candidates = json.dumps(candidates)
        self.assertEqual(candidates["secrets"][0]["provider_kind"], "google-sheets-json")
        self.assertEqual(candidates["secrets"][0]["validation_status"], "unbound")
        self.assertNotIn("topete_final", serialized_candidates)
        self.assertNotIn("raw-spreadsheet-id", serialized_candidates)

        bound = list_source_connections(
            self.store,
            {
                "graph_id": self.graph_id,
                "action": "bind",
                "source_node_id": "DS-ERP",
                "secret_ref": secret_ref,
                "provider_inputs": {"spreadsheet_ref": "erp-2025"},
            },
        )
        self.assertEqual(bound["binding"]["validation_status"], "unvalidated")
        self.assertEqual(bound["binding"]["provider_inputs"], {"spreadsheet_ref": "erp-2025"})

        with patch("brain_ds.connectors.secrets.providers.google_sheets.GoogleSheetsJsonAdapter.probe", return_value={"spreadsheet_id": "raw-spreadsheet-id"}):
            validated = list_source_connections(
                self.store,
                {"graph_id": self.graph_id, "action": "validate", "source_node_id": "DS-ERP"},
            )

        self.assertEqual(validated["binding"]["validation_status"], "valid")
        self.assertEqual(validated["binding"]["validation"]["error_code"], None)
        status = list_source_connections(
            self.store,
            {"graph_id": self.graph_id, "action": "status", "source_node_id": "DS-ERP"},
        )
        self.assertEqual(status["binding"]["validation_status"], "valid")

        unbound = list_source_connections(
            self.store,
            {"graph_id": self.graph_id, "action": "unbind", "source_node_id": "DS-ERP"},
        )
        self.assertEqual(unbound["binding"]["validation_status"], "unbound")
        self.assertIsNone(SecretBindingStore(self.temp_dir.name).get(self.graph_id, "DS-ERP"))
        serialized_flow = json.dumps([bound, validated, status, unbound], default=str)
        self.assertNotIn("topete_final", serialized_flow)
        self.assertNotIn("raw-spreadsheet-id", serialized_flow)

    def test_secret_first_candidates_and_spoof_resistance_use_server_binding_only(self) -> None:
        self._seed_google_sheets_secret()
        self.store.secret_admin_enabled = True
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "DS-ERP",
                "label": "ERP 2025",
                "type": "Data Source",
                "details": {
                    "source_kind": "google-sheets",
                    "secret_binding": {"secret_ref": "spoofed", "validation_status": "valid"},
                    "connection": {"kind": "google-sheets-json", "secret_handle": "topete_final", "spreadsheet_id": "raw-spreadsheet-id"},
                },
            },
        )
        secret_ref = list_source_connections(
            self.store,
            {"graph_id": self.graph_id, "action": "candidate_secrets", "source_node_id": "DS-ERP"},
        )["secrets"][0]["secret_ref"]

        sources = list_source_connections(
            self.store,
            {"graph_id": self.graph_id, "action": "candidate_sources", "secret_ref": secret_ref},
        )

        self.assertEqual(sources["status"], "ok")
        self.assertEqual(sources["sources"], [{"graph_id": self.graph_id, "node_id": "DS-ERP", "label": "ERP 2025", "provider_kind": "google-sheets-json", "validation_status": "unbound"}])
        status = list_source_connections(
            self.store,
            {"graph_id": self.graph_id, "action": "status", "source_node_id": "DS-ERP"},
        )
        self.assertEqual(
            status["binding"],
            {
                "validation_status": "unbound",
                "documentation_status": "not_started",
                "writeback_status": "idle",
                "requires_binding": True,
            },
        )
        serialized = json.dumps([sources, status])
        self.assertNotIn("spoofed", serialized)
        self.assertNotIn("topete_final", serialized)
        self.assertNotIn("raw-spreadsheet-id", serialized)

    def test_source_connection_error_paths_are_redacted(self) -> None:
        self._seed_google_sheets_secret()
        self.store.secret_admin_enabled = True
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "DS-ERP",
                "label": "ERP 2025 raw-spreadsheet-id topete_final",
                "type": "Data Source",
                "details": {"source_kind": "google-sheets"},
            },
        )
        secret_ref = list_source_connections(
            self.store,
            {"graph_id": self.graph_id, "action": "candidate_secrets", "source_node_id": "DS-ERP"},
        )["secrets"][0]["secret_ref"]
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "DS-CSV",
                "label": "CSV export raw-spreadsheet-id topete_final",
                "type": "Data Source",
                "details": {"source_kind": "csv"},
            },
        )

        not_allowlisted = list_source_connections(
            self.store,
            {
                "graph_id": self.graph_id,
                "action": "bind",
                "source_node_id": "DS-CSV",
                "secret_ref": secret_ref,
                "provider_inputs": {"spreadsheet_ref": "erp-2025"},
            },
        )
        self.assertEqual(not_allowlisted["error_code"], "not_allowlisted")
        self.assertNotIn("raw-spreadsheet-id", json.dumps(not_allowlisted))
        self.assertNotIn("topete_final", json.dumps(not_allowlisted))

        missing_mapping = list_source_connections(
            self.store,
            {"graph_id": self.graph_id, "action": "validate", "source_node_id": "DS-ERP"},
        )
        self.assertEqual(missing_mapping["error_code"], "missing_private_mapping")
        self.assertNotIn("raw-spreadsheet-id", json.dumps(missing_mapping))
        self.assertNotIn("topete_final", json.dumps(missing_mapping))

        SecretBindingStore(self.temp_dir.name).upsert(
            SecretBindingRecord(
                graph_id=self.graph_id,
                source_node_id="DS-ERP",
                secret_ref_alias="sec_orphaned_raw-spreadsheet-id_topete_final",
                internal_secret_id="deleted_topete_final",
                provider_kind="google-sheets-json",
                provider_inputs={"spreadsheet_ref": "erp-2025"},
            )
        )
        revalidation_required = list_source_connections(
            self.store,
            {"graph_id": self.graph_id, "action": "validate", "source_node_id": "DS-ERP"},
        )
        serialized = json.dumps(revalidation_required)
        self.assertEqual(revalidation_required["error_code"], "revalidation_required")
        self.assertNotIn("deleted_topete_final", serialized)
        self.assertNotIn("raw-spreadsheet-id", serialized)
        self.assertNotIn("topete_final", serialized)

    def test_manage_clusters_propose_marks_kpi_without_source_as_needs_source(self) -> None:
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "KPI-1",
                "label": "On-time Delivery",
                "type": "KPI",
                "details": {"owner": "Ops", "department": "Logistics", "formula": "on_time / total"},
            },
        )

        result = manage_clusters(
            self.store,
            {
                "graph_id": self.graph_id,
                "action": "propose",
                "payload": {
                    "cluster_id": "cluster-kpi-1",
                    "name": "Delivery KPI cluster",
                    "description": "Tracks delivery reliability.",
                    "primary_anchor_id": "KPI-1",
                    "primary_anchor_type": "KPI",
                    "member_node_ids": ["KPI-1"],
                    "kpi": {"owner": "Ops", "department": "Logistics", "formula": "on_time / total"},
                },
                "reason": "medium-confidence KPI anchor",
                "confidence": 0.62,
            },
        )

        self.assertNotIn("code", result)
        self.assertEqual(result["cluster"]["metadata"]["status"], "needs-source")
        self.assertTrue(result["cluster"]["metadata"]["needs_source"])
        self.assertEqual(result["cluster"]["metadata"]["primary_anchor_id"], "KPI-1")
        self.assertEqual(result["pending_question_ids"], [1])
        pending = self.store.list_pending_questions(self.graph_id)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].target_node_id, "KPI-1")
        self.assertEqual(pending[0].gap_kind, "cluster_source")
        self.assertIn("primary data source", pending[0].question_text)

    def test_manage_clusters_confirm_and_reject_update_lifecycle_without_extra_tools(self) -> None:
        self.store.save_clusters(
            self.graph_id,
            [
                {
                    "id": "cluster-existing",
                    "name": "Existing cluster",
                    "description": "A proposed cluster",
                    "metadata": {"status": "proposed", "needs_source": False},
                }
            ],
        )

        confirmed = manage_clusters(
            self.store,
            {
                "graph_id": self.graph_id,
                "action": "confirm",
                "cluster_id": "cluster-existing",
                "reason": "validated by owner",
            },
        )
        self.assertEqual(confirmed["cluster"]["metadata"]["status"], "confirmed")
        self.assertEqual(confirmed["pending_question_ids"], [])

        rejected = manage_clusters(
            self.store,
            {
                "graph_id": self.graph_id,
                "action": "reject",
                "cluster_id": "cluster-existing",
                "reason": "duplicate candidate",
            },
        )
        self.assertEqual(rejected["cluster"]["metadata"]["status"], "rejected")
        self.assertEqual(rejected["audit_id"], "cluster-existing:reject")

    def test_manage_clusters_reformulate_split_merge_archive_actions(self) -> None:
        self.store.save_clusters(
            self.graph_id,
            [
                {
                    "id": "cluster-a",
                    "name": "Old name",
                    "description": "Old description",
                    "metadata": {"status": "proposed", "needs_source": False},
                },
                {
                    "id": "cluster-b",
                    "name": "Sibling cluster",
                    "metadata": {"status": "proposed", "needs_source": False},
                },
            ],
        )

        reformulated = manage_clusters(
            self.store,
            {
                "graph_id": self.graph_id,
                "action": "reformulate",
                "cluster_id": "cluster-a",
                "payload": {"name": "New name", "description": "New description"},
                "reason": "better business wording",
            },
        )
        self.assertEqual(reformulated["cluster"]["name"], "New name")
        self.assertEqual(reformulated["cluster"]["description"], "New description")
        self.assertEqual(reformulated["cluster"]["metadata"]["status"], "proposed")

        split = manage_clusters(
            self.store,
            {
                "graph_id": self.graph_id,
                "action": "split",
                "cluster_id": "cluster-a",
                "payload": {"new_cluster_id": "cluster-a-split", "name": "Split cluster"},
            },
        )
        self.assertEqual(split["cluster"]["metadata"]["status"], "proposed")
        self.assertEqual(split["related_clusters"][0]["id"], "cluster-a-split")

        merged = manage_clusters(
            self.store,
            {"graph_id": self.graph_id, "action": "merge", "cluster_id": "cluster-a", "payload": {"source_cluster_id": "cluster-b"}},
        )
        self.assertEqual(merged["cluster"]["metadata"]["status"], "proposed")
        self.assertEqual(merged["related_clusters"][0]["metadata"]["status"], "archived")
        self.assertEqual(merged["related_clusters"][0]["metadata"]["archived_reason"], "merged into cluster-a")

        archived = manage_clusters(
            self.store,
            {"graph_id": self.graph_id, "action": "archive", "cluster_id": "cluster-a", "reason": "no longer active"},
        )
        self.assertEqual(archived["cluster"]["metadata"]["status"], "archived")
        self.assertEqual(archived["cluster"]["metadata"]["archived_reason"], "no longer active")


class PaginatedListToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / ".brain_ds" / "store.db"
        self.db_path.parent.mkdir(parents=True)
        self.store = GraphStore(str(self.db_path))
        self.graph_id = "paginated-tools"
        self.store.meta_repo.save_graph_meta(
            graph_id=self.graph_id,
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="project-tools",
            org="org-tools",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_list_source_connections_returns_bounded_page_with_next_offset(self) -> None:
        for index in range(25):
            self.store.upsert_node(
                self.graph_id,
                {
                    "id": f"DS-{index:02d}",
                    "label": f"Source {index:02d}",
                    "type": "Data Source",
                    "details": {"connection": {"kind": "sqlite", "path": f"data/{index}.db"}},
                },
            )

        page = list_source_connections(self.store, {"graph_id": self.graph_id, "limit": 10, "offset": 5})

        self.assertEqual(page["limit"], 10)
        self.assertEqual(page["offset"], 5)
        self.assertEqual(page["next_offset"], 15)
        self.assertEqual(len(page["connections"]), 10)
        self.assertEqual(page["connections"][0]["node_id"], "DS-05")

    def test_list_source_connections_compact_mode_omits_connection_payload(self) -> None:
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "DS-1",
                "label": "Source 1",
                "type": "Data Source",
                "details": {"connection": {"kind": "sqlite", "path": "data/source.db"}},
            },
        )

        page = list_source_connections(self.store, {"graph_id": self.graph_id, "compact": True})

        self.assertEqual(page["connections"], [{"graph_id": self.graph_id, "node_id": "DS-1", "label": "Source 1"}])

    def test_list_workspaces_schema_accepts_pagination_and_compact(self) -> None:
        params = validate_tool_input(
            "list_workspaces",
            {"limit": 20, "offset": 0, "compact": True},
        )

        self.assertEqual(params["limit"], 20)
        self.assertTrue(params["compact"])

    def test_list_workspaces_returns_page_metadata(self) -> None:
        page = list_workspaces(self.store, {"limit": 1, "offset": 0, "compact": True})

        self.assertIn("workspaces", page)
        self.assertEqual(page["limit"], 1)
        self.assertEqual(page["offset"], 0)
        self.assertIn("total", page)


class ExploreSourceDocumentationLevelTests(unittest.TestCase):
    """DDS-4/DDS-5: explore_source level='documentation' returns joined doc bundle."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        store_dir = Path(self.temp_dir.name) / ".brain_ds"
        store_dir.mkdir(parents=True)
        self.store = GraphStore(str(store_dir / "store.db"))
        self.graph_id = "ds-docs-graph"
        self.store.meta_repo.save_graph_meta(
            graph_id=self.graph_id,
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="project-docs",
            org="org-docs",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        # Data Source node
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "ds-1",
                "label": "Warehouse DB",
                "type": "Data Source",
                "details": {
                    "what": "Main warehouse",
                    "connection": {"kind": "sqlite", "path": "data/store.db"},
                },
            },
        )
        # Child table-level node with columns card section
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "tbl-orders",
                "label": "orders",
                "type": "Unknown",
                "parent_id": "ds-1",
                "card_sections": [
                    {
                        "title": "Columns / Fields",
                        "content": "| col | type |\n|---|---|\n| id | int |",
                        "icon": "table",
                        "order": 1,
                    },
                    {
                        "title": "Purpose",
                        "content": "Order tracking table.",
                        "icon": "info",
                        "order": 2,
                    },
                ],
            },
        )
        # Add an edge to create a relationship
        self.store.upsert_edge(
            self.graph_id,
            {"source": "ds-1", "target": "tbl-orders", "label": "uses", "weight": 0.9},
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_explore_source_documentation_level_returns_bundle(self):
        from brain_ds.mcp.tools import explore_source

        result = explore_source(
            self.store,
            {"graph_id": self.graph_id, "node_id": "ds-1", "level": "documentation"},
        )
        self.assertNotIn("code", result, f"Expected success, got error: {result}")
        self.assertEqual(result["level"], "documentation")

    def test_explore_source_documentation_level_contains_tables(self):
        from brain_ds.mcp.tools import explore_source

        result = explore_source(
            self.store,
            {"graph_id": self.graph_id, "node_id": "ds-1", "level": "documentation"},
        )
        self.assertIn("tables", result)
        self.assertEqual(len(result["tables"]), 1)

    def test_explore_source_documentation_level_table_entry_has_columns_markdown(self):
        from brain_ds.mcp.tools import explore_source

        result = explore_source(
            self.store,
            {"graph_id": self.graph_id, "node_id": "ds-1", "level": "documentation"},
        )
        orders = result["tables"][0]
        self.assertEqual(orders["node_id"], "tbl-orders")
        self.assertIn("columns_markdown", orders)
        self.assertIn("| id | int |", orders["columns_markdown"])

    def test_explore_source_documentation_level_tool_count(self):
        """Business dossier tool moves registry count to 33 while explore_source remains additive-free."""
        self.assertEqual(len(TOOL_REGISTRY), 33)

    def test_snapshot_edges_defaults_to_bounded_stable_page(self) -> None:
        self.store.upsert_edge(
            self.graph_id,
            {"source": "N-1", "target": "N-2", "label": "alpha", "weight": 0.2, "evidence_ids": ["e-1"]},
        )
        self.store.upsert_edge(
            self.graph_id,
            {"source": "N-1", "target": "N-3", "label": "alpha", "weight": 0.8, "evidence_ids": []},
        )

        result = snapshot_edges(self.store, {"graph_id": self.graph_id, "limit": 2})

        self.assertEqual(result["graph_id"], self.graph_id)
        self.assertEqual(result["mode"], "sample")
        self.assertEqual(result["limit"], 2)
        self.assertEqual([edge["edge_id"] for edge in result["edges"]], ["N-1->N-2#1", "N-1->N-3#1"])
        self.assertIsNotNone(result["next_cursor"])

    def test_snapshot_edges_filters_and_rejects_invalid_depth(self) -> None:
        self.store.upsert_edge(
            self.graph_id,
            {"source": "N-1", "target": "N-2", "label": "uses", "weight": 0.7, "evidence_ids": ["e-1"]},
        )
        self.store.upsert_edge(
            self.graph_id,
            {"source": "N-2", "target": "N-3", "label": "depends-on", "weight": 0.3, "evidence_ids": []},
        )

        filtered = snapshot_edges(
            self.store,
            {"graph_id": self.graph_id, "label": ["uses"], "min_weight": 0.5, "has_evidence": True},
        )
        self.assertEqual([edge["label"] for edge in filtered["edges"]], ["uses"])

        invalid = snapshot_edges(
            self.store,
            {"graph_id": self.graph_id, "neighborhood": {"node_id": "N-1", "depth": 4, "direction": "both"}},
        )
        self.assertIsInstance(invalid, dict)
        self.assertEqual(invalid["code"], -32602)
        self.assertIn("depth", invalid["message"])

    def test_explore_source_schema_accepts_level_param(self):
        """DDS-4: explore_source schema must accept optional level string."""
        from brain_ds.mcp.security import TOOL_SCHEMAS, validate_tool_input

        result = validate_tool_input(
            "explore_source",
            {
                "graph_id": self.graph_id,
                "node_id": "ds-1",
                "level": "documentation",
            },
            TOOL_SCHEMAS["explore_source"],
        )
        self.assertEqual(result["level"], "documentation")


class DataSourceInternalHierarchyToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / ".brain_ds" / "store.db"
        self.db_path.parent.mkdir(parents=True)
        self.store = GraphStore(str(self.db_path))
        self.graph_id = "internal-hierarchy"
        self.store.meta_repo.save_graph_meta(
            graph_id=self.graph_id,
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="project-internal",
            org="org-internal",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "ds-1",
                "label": "Warehouse",
                "type": "Data Source",
                "supertype": "data",
                "details": {"connection": {"kind": "sqlite", "path": "warehouse.db"}},
            },
        )
        update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "ds-2",
                "label": "Reporting",
                "type": "Data Source",
                "supertype": "data",
                "details": {"connection": {"kind": "csv", "path": "reporting.csv"}},
            },
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_update_node_accepts_parent_id_depth_for_internal_child_under_data_source(self) -> None:
        created = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "schema-main",
                "label": "main",
                "type": "DataContainer",
                "parent_id": "ds-1",
                "depth": 1,
                "details": {"kind": "schema"},
            },
        )

        self.assertEqual(created["parent_id"], "ds-1")
        self.assertEqual(created["depth"], 1)
        self.assertEqual(created["details"]["kind"], "schema")

    def test_update_node_allows_internal_descendant_with_data_source_ancestor(self) -> None:
        update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "schema-main",
                "label": "main",
                "type": "DataContainer",
                "parent_id": "ds-1",
                "depth": 1,
                "details": {"kind": "schema"},
            },
        )

        field = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "field-order-id",
                "label": "order_id",
                "type": "DataField",
                "parent_id": "schema-main",
                "depth": 2,
                "details": {"kind": "column"},
            },
        )

        self.assertEqual(field["parent_id"], "schema-main")
        self.assertEqual(field["details"]["kind"], "column")

    def test_update_node_rejects_internal_child_without_data_source_ancestor(self) -> None:
        result = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "orphan-table",
                "label": "orders",
                "type": "DataContainer",
                "parent_id": "missing-parent",
                "depth": 1,
                "details": {"kind": "table"},
            },
        )

        self.assertEqual(result["code"], -32000)
        self.assertIn("scope_violation", result["message"])

    def test_update_node_rejects_internal_child_whose_parent_chain_cycles(self) -> None:
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "cycle-a",
                "label": "cycle a",
                "type": "DataContainer",
                "parent_id": "cycle-b",
                "depth": 1,
                "details": {"kind": "schema"},
            },
        )
        self.store.upsert_node(
            self.graph_id,
            {
                "id": "cycle-b",
                "label": "cycle b",
                "type": "DataContainer",
                "parent_id": "cycle-a",
                "depth": 1,
                "details": {"kind": "table"},
            },
        )

        result = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "cycle-field",
                "label": "field",
                "type": "DataField",
                "parent_id": "cycle-a",
                "depth": 2,
                "details": {"kind": "column"},
            },
        )

        self.assertEqual(result["code"], -32000)
        self.assertIn("scope_violation", result["message"])
        self.assertIn("cycle", result["message"])

    def test_update_node_validates_container_and_field_detail_kinds(self) -> None:
        bad_container = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "bad-container",
                "label": "bad",
                "type": "DataContainer",
                "parent_id": "ds-1",
                "depth": 1,
                "details": {"kind": "column"},
            },
        )
        bad_field = update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "bad-field",
                "label": "bad",
                "type": "DataField",
                "parent_id": "ds-1",
                "depth": 1,
                "details": {"kind": "table"},
            },
        )

        self.assertEqual(bad_container["code"], -32602)
        self.assertIn("DataContainer details.kind", bad_container["message"])
        self.assertEqual(bad_field["code"], -32602)
        self.assertIn("DataField details.kind", bad_field["message"])

    def test_list_nodes_filters_internal_nodes_by_details_kind_and_source_id(self) -> None:
        for node_id, source_id, kind in (
            ("ds1-orders", "ds-1", "table"),
            ("ds1-customers", "ds-1", "view"),
            ("ds2-orders", "ds-2", "table"),
        ):
            update_node(
                self.store,
                {
                    "graph_id": self.graph_id,
                    "node_id": node_id,
                    "label": node_id,
                    "type": "DataContainer",
                    "parent_id": source_id,
                    "depth": 1,
                    "details": {"kind": kind},
                },
            )

        rows = list_nodes(
            self.store,
            {
                "graph_id": self.graph_id,
                "type": "DataContainer",
                "details_kind": "table",
                "source_id": "ds-1",
            },
        )

        self.assertEqual([row["id"] for row in rows], ["ds1-orders"])

    def test_explore_source_internal_returns_source_template_and_nested_subtree(self) -> None:
        update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "schema-main",
                "label": "main",
                "type": "DataContainer",
                "parent_id": "ds-1",
                "depth": 1,
                "details": {"kind": "schema"},
            },
        )
        update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "table-orders",
                "label": "orders",
                "type": "DataContainer",
                "parent_id": "schema-main",
                "depth": 2,
                "details": {"kind": "table"},
            },
        )
        update_node(
            self.store,
            {
                "graph_id": self.graph_id,
                "node_id": "column-id",
                "label": "id",
                "type": "DataField",
                "parent_id": "table-orders",
                "depth": 3,
                "details": {"kind": "column"},
            },
        )

        result = explore_source(
            self.store,
            {"graph_id": self.graph_id, "node_id": "ds-1", "level": "internal"},
        )

        self.assertEqual(result["level"], "internal")
        self.assertEqual(result["source"]["node_id"], "ds-1")
        self.assertEqual(result["template"]["source_kind"], "relational-db")
        self.assertEqual(result["internal_subtree"][0]["id"], "schema-main")
        self.assertEqual(result["internal_subtree"][0]["children"][0]["id"], "table-orders")
        self.assertEqual(result["internal_subtree"][0]["children"][0]["children"][0]["id"], "column-id")

    def test_source_kind_hierarchy_templates_are_derived_into_grounding_context(self) -> None:
        from brain_ds.mcp import grounding

        templates = grounding.SOURCE_KIND_HIERARCHY_TEMPLATES
        self.assertEqual(templates["relational-db"][0]["kind"], "schema")
        self.assertIn("column", templates["relational-db"][1]["children"][0]["children"])
        self.assertIn("Data Source Hierarchy Documentation", grounding.NODE_WRITE_TEMPLATES["Data Source"]["hierarchy_template"])
        self.assertIn("relational-db", grounding.NODE_WRITE_TEMPLATES["Data Source"]["hierarchy_template"])


class SourceDocumentationBundleContractTests(unittest.TestCase):
    """DDS-7: SOURCE_DOCUMENTATION_BUNDLE_CONTRACT must be registered in grounding."""

    def test_constant_exists(self):
        from brain_ds.mcp import grounding

        self.assertTrue(hasattr(grounding, "SOURCE_DOCUMENTATION_BUNDLE_CONTRACT"))

    def test_constant_is_dict(self):
        from brain_ds.mcp import grounding

        self.assertIsInstance(grounding.SOURCE_DOCUMENTATION_BUNDLE_CONTRACT, dict)

    def test_constant_has_required_keys(self):
        from brain_ds.mcp import grounding

        contract = grounding.SOURCE_DOCUMENTATION_BUNDLE_CONTRACT
        for key in ("description", "mcp_call", "response_shape", "agent_answerability"):
            with self.subTest(key=key):
                self.assertIn(key, contract)

    def test_constant_in_elicit_context(self):
        from brain_ds.mcp import grounding

        ctx = grounding.elicit_context()
        self.assertIn("source_documentation_bundle_contract", ctx)

    def test_constant_in_map_connections_context(self):
        from brain_ds.mcp import grounding

        ctx = grounding.map_connections_context()
        self.assertIn("source_documentation_bundle_contract", ctx)


class RetrieveContextHandlerContractTests(unittest.TestCase):
    """R-01 / R-02 / R-03 / R-09 handler contract tests for retrieve_context (PR2 Brick D)."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / ".brain_ds" / "store.db"
        self.db_path.parent.mkdir(parents=True)
        self.store = GraphStore(str(self.db_path))
        self.graph_id = "g-retrieve"
        self.store.meta_repo.save_graph_meta(
            graph_id=self.graph_id,
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="p-retrieve",
            org="o-retrieve",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        self.store.upsert_node(self.graph_id, {"id": "N1", "label": "Alpha Process", "type": "Task", "supertype": "Work"})
        self.store.upsert_node(self.graph_id, {"id": "N2", "label": "Beta Source", "type": "Process", "supertype": "Business"})
        self.store.upsert_edge(self.graph_id, {"source": "N1", "target": "N2", "label": "feeds", "weight": 0.8, "evidence_ids": []})

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def _call(self, params: dict) -> dict:
        from brain_ds.mcp.tools import retrieve_context
        return retrieve_context(self.store, params)

    def test_r01_missing_both_query_and_focal_node_id_returns_validation_error(self) -> None:
        """R-01: at least one of query/focal_node_id is required; omitting both → error -32602."""
        result = self._call({"graph_id": self.graph_id})
        self.assertIsInstance(result, dict)
        self.assertIn("code", result)
        self.assertEqual(result["code"], -32602)
        self.assertIn("At least one of", result["message"])
        # No database read should have occurred — error is caught before store access.

    def test_r02_depth_three_is_rejected_before_store_query(self) -> None:
        """R-02: depth=3 is rejected with a validation error before any store read."""
        result = self._call({"graph_id": self.graph_id, "query": "alpha", "depth": 3})
        self.assertIsInstance(result, dict)
        self.assertIn("code", result)
        self.assertEqual(result["code"], -32602)
        self.assertIn("depth must be 1 or 2", result["message"])

    def test_r03_all_seven_output_fields_present_on_success(self) -> None:
        """R-03: a successful call returns all 7 required top-level fields."""
        result = self._call({"graph_id": self.graph_id, "query": "alpha"})
        seven_fields = ("anchors", "subgraph", "hierarchy_paths", "serialized_for_llm", "dense_used")
        for field in seven_fields:
            with self.subTest(field=field):
                self.assertIn(field, result)
        self.assertIn("nodes", result["subgraph"])
        self.assertIn("edges_with_reliability", result["subgraph"])

    def test_r09_focal_node_id_not_found_returns_clear_error(self) -> None:
        """R-09: focal_node_id pointing to a non-existent node → error -32000 with id and graph_id."""
        result = self._call({"graph_id": self.graph_id, "focal_node_id": "missing-node-xyz"})
        self.assertIsInstance(result, dict)
        self.assertIn("code", result)
        self.assertEqual(result["code"], -32000)
        self.assertIn("missing-node-xyz", result["message"])
        self.assertIn(self.graph_id, result["message"])


class _FakeEmbeddingModelForRetrieve:
    """Minimal deterministic fake satisfying EmbeddingModel protocol for retrieve_context tests."""

    @property
    def name(self) -> str:
        return "fake-retrieve"

    def embed(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


# ---------------------------------------------------------------------------
# W-1: no store read on invalid input (R-01 / R-02)
# ---------------------------------------------------------------------------


class RetrieveContextNoStoreReadOnInvalidInputTests(unittest.TestCase):
    """W-1: validation errors (R-01, R-02) fire BEFORE any database read (zero SQL traced)."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / ".brain_ds" / "store.db"
        self.db_path.parent.mkdir(parents=True)
        self.store = GraphStore(str(self.db_path))
        self.graph_id = "g-w1"
        self.store.meta_repo.save_graph_meta(
            graph_id=self.graph_id,
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="p-w1",
            org="o-w1",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        self.store.upsert_node(
            self.graph_id,
            {"id": "N1", "label": "Alpha Process", "type": "Task", "supertype": "Work"},
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def _call(self, params: dict) -> dict:
        from brain_ds.mcp.tools import retrieve_context
        return retrieve_context(self.store, params)

    def test_w1a_r01_missing_both_inputs_returns_error_and_zero_sql(self) -> None:
        """W-1a/R-01: neither query nor focal_node_id → -32602 error, ZERO SQL on the connection."""
        all_sql: list[str] = []
        self.store.conn.set_trace_callback(all_sql.append)
        try:
            result = self._call({"graph_id": self.graph_id})
        finally:
            self.store.conn.set_trace_callback(None)

        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("code"), -32602, f"Expected -32602; got: {result}")
        self.assertIn("At least one of", result.get("message", ""))
        self.assertEqual(
            all_sql,
            [],
            f"Expected zero SQL for R-01 validation error; got {len(all_sql)} statement(s):\n"
            + "\n".join(all_sql[:5]),
        )

    def test_w1b_r02_depth_three_returns_error_and_zero_sql(self) -> None:
        """W-1b/R-02: depth=3 (out-of-bounds) → -32602 error, ZERO SQL on the connection."""
        all_sql: list[str] = []
        self.store.conn.set_trace_callback(all_sql.append)
        try:
            result = self._call({"graph_id": self.graph_id, "query": "alpha", "depth": 3})
        finally:
            self.store.conn.set_trace_callback(None)

        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("code"), -32602, f"Expected -32602; got: {result}")
        self.assertIn("depth must be 1 or 2", result.get("message", ""))
        self.assertEqual(
            all_sql,
            [],
            f"Expected zero SQL for R-02 validation error; got {len(all_sql)} statement(s):\n"
            + "\n".join(all_sql[:5]),
        )


# ---------------------------------------------------------------------------
# W-2: dense/embedding branch without a real model
# ---------------------------------------------------------------------------


class RetrieveContextDensePathTests(unittest.TestCase):
    """W-2: dense path in retrieve_context using FakeEmbeddingModel + mocked nearest_to_vector."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / ".brain_ds" / "store.db"
        self.db_path.parent.mkdir(parents=True)
        self.store = GraphStore(str(self.db_path))
        self.graph_id = "g-w2"
        self.store.meta_repo.save_graph_meta(
            graph_id=self.graph_id,
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="p-w2",
            org="o-w2",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        # N1: lexical match for "Alpha"
        self.store.upsert_node(
            self.graph_id,
            {"id": "N1", "label": "Alpha Process", "type": "Task", "supertype": "Work"},
        )
        # N2: dense-only node (zero token overlap with query "Alpha")
        self.store.upsert_node(
            self.graph_id,
            {"id": "N2", "label": "Dense Only Node", "type": "Role", "supertype": "Business"},
        )
        self.store.upsert_edge(
            self.graph_id,
            {"source": "N1", "target": "N2", "label": "relates", "weight": 0.7, "evidence_ids": []},
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def _call(self, params: dict) -> dict:
        from brain_ds.mcp.tools import retrieve_context
        return retrieve_context(self.store, params)

    def test_w2a_dense_path_sets_dense_used_true_and_surfaces_dense_anchor(self) -> None:
        """W-2a: FakeEmbeddingModel + nearest_to_vector returning N2 → dense_used=True, N2 in anchors."""
        fake_model = _FakeEmbeddingModelForRetrieve()
        dense_hits = [NearestHit(target_id="N2", score=0.95)]

        with patch("brain_ds.mcp.tools.get_default_model", return_value=fake_model), \
             patch.object(self.store, "nearest_to_vector", return_value=dense_hits):
            result = self._call({"graph_id": self.graph_id, "query": "Alpha"})

        self.assertNotIn("code", result, f"Expected success, got error: {result}")
        self.assertTrue(result.get("dense_used"), "dense_used must be True when model is available and hits returned")
        anchor_ids = [a["id"] for a in result.get("anchors", [])]
        self.assertIn("N2", anchor_ids, "Dense-only anchor N2 must appear in anchors after RRF fusion")

    def test_w2b_degradation_model_none_dense_used_false(self) -> None:
        """W-2b/EMB-S2: get_default_model()=None → retrieve_context succeeds with dense_used=False."""
        with patch("brain_ds.mcp.tools.get_default_model", return_value=None):
            result = self._call({"graph_id": self.graph_id, "query": "Alpha"})

        self.assertNotIn("code", result, f"Expected success, got error: {result}")
        self.assertFalse(result.get("dense_used"), "dense_used must be False when no model available")
        # Lexical path still returns a valid response with all required fields.
        for field in ("anchors", "subgraph", "dense_used", "serialized_for_llm"):
            with self.subTest(field=field):
                self.assertIn(field, result)

    def test_w2c_dense_empty_hits_falls_back_to_lexical_dense_used_false(self) -> None:
        """W-2c: model present but nearest_to_vector returns [] → lexical-only, dense_used=False."""
        fake_model = _FakeEmbeddingModelForRetrieve()

        with patch("brain_ds.mcp.tools.get_default_model", return_value=fake_model), \
             patch.object(self.store, "nearest_to_vector", return_value=[]):
            result = self._call({"graph_id": self.graph_id, "query": "Alpha"})

        self.assertNotIn("code", result, f"Expected success, got error: {result}")
        self.assertFalse(result.get("dense_used"), "dense_used must be False when dense_hits is empty")


# ---------------------------------------------------------------------------
# W-3: per-edge ledger_status in edges_with_reliability
# ---------------------------------------------------------------------------


class RetrieveContextEdgeLedgerStatusTests(unittest.TestCase):
    """W-3: every item in edges_with_reliability carries ledger_status and tier; both tier branches exercised."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / ".brain_ds" / "store.db"
        self.db_path.parent.mkdir(parents=True)
        self.store = GraphStore(str(self.db_path))
        self.graph_id = "g-w3"
        self.store.meta_repo.save_graph_meta(
            graph_id=self.graph_id,
            workspace_root=self.temp_dir.name,
            workspace_path=self.temp_dir.name,
            project="p-w3",
            org="o-w3",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        self.store.upsert_node(
            self.graph_id,
            {"id": "N1", "label": "Alpha Anchor", "type": "Task", "supertype": "Work"},
        )
        self.store.upsert_node(
            self.graph_id,
            {"id": "N2", "label": "Beta Target", "type": "Process", "supertype": "Business"},
        )
        self.store.upsert_node(
            self.graph_id,
            {"id": "N3", "label": "Gamma Target", "type": "Role", "supertype": "Work"},
        )
        # Edge E1: N1→N2 — no ledger row → ledger_status=None, tier=2
        self.store.upsert_edge(
            self.graph_id,
            {"source": "N1", "target": "N2", "label": "feeds", "weight": 0.8, "evidence_ids": []},
        )
        # Edge E2: N1→N3 — confirmed ledger row → ledger_status="confirmed", tier=1
        self.store.upsert_edge(
            self.graph_id,
            {"source": "N1", "target": "N3", "label": "triggers", "weight": 0.6, "evidence_ids": []},
        )
        # Find E2's edge_id and write a confirmed ledger row
        edges = self.store.query_edges(self.graph_id)
        confirmed_edge = next((e for e in edges if e.label == "triggers"), None)
        assert confirmed_edge is not None, "triggers edge must exist after upsert"
        self.store.append_ledger(
            self.graph_id,
            target_id=confirmed_edge.edge_id,
            target_type="edge",
            status="confirmed",
            provenance="hand_labeled",
            captured_at="2026-01-01T00:00:00+00:00",
            confirmed_at="2026-01-01T00:00:00+00:00",
            confirmed_by="test-user",
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def _call(self, params: dict) -> dict:
        from brain_ds.mcp.tools import retrieve_context
        return retrieve_context(self.store, params)

    def test_w3_every_edge_has_ledger_status_key(self) -> None:
        """W-3: every item in edges_with_reliability must contain ledger_status and tier."""
        result = self._call({"graph_id": self.graph_id, "focal_node_id": "N1"})

        self.assertNotIn("code", result, f"Expected success, got error: {result}")
        edges = result.get("subgraph", {}).get("edges_with_reliability", [])
        self.assertGreater(len(edges), 0, "Expected at least one edge in subgraph")

        for i, edge in enumerate(edges):
            with self.subTest(edge_index=i, label=edge.get("label")):
                self.assertIn("ledger_status", edge, f"Edge[{i}] missing ledger_status key")
                self.assertIn("tier", edge, f"Edge[{i}] missing tier key")

    def test_w3_confirmed_edge_has_tier_one(self) -> None:
        """W-3: edge with confirmed ledger row appears with tier=1 in edges_with_reliability."""
        result = self._call({"graph_id": self.graph_id, "focal_node_id": "N1"})

        self.assertNotIn("code", result, f"Expected success, got error: {result}")
        edges = result.get("subgraph", {}).get("edges_with_reliability", [])
        confirmed = [e for e in edges if e.get("label") == "triggers"]
        self.assertEqual(len(confirmed), 1, "Expected exactly one 'triggers' edge in subgraph")
        self.assertEqual(confirmed[0]["ledger_status"], "confirmed")
        self.assertEqual(confirmed[0]["tier"], 1)

    def test_w3_no_ledger_row_edge_has_tier_two(self) -> None:
        """W-3: edge without any ledger row appears with ledger_status=None and tier=2."""
        result = self._call({"graph_id": self.graph_id, "focal_node_id": "N1"})

        self.assertNotIn("code", result, f"Expected success, got error: {result}")
        edges = result.get("subgraph", {}).get("edges_with_reliability", [])
        no_ledger = [e for e in edges if e.get("label") == "feeds"]
        self.assertEqual(len(no_ledger), 1, "Expected exactly one 'feeds' edge in subgraph")
        self.assertIsNone(no_ledger[0]["ledger_status"])
        self.assertEqual(no_ledger[0]["tier"], 2)

    def test_w3_both_tier_branches_present(self) -> None:
        """W-3: both tier=1 (confirmed) and tier=2 (no-ledger) branches exercised in one call."""
        result = self._call({"graph_id": self.graph_id, "focal_node_id": "N1"})

        self.assertNotIn("code", result, f"Expected success, got error: {result}")
        edges = result.get("subgraph", {}).get("edges_with_reliability", [])
        tiers = {e["tier"] for e in edges}
        self.assertIn(1, tiers, "tier=1 (confirmed) must appear")
        self.assertIn(2, tiers, "tier=2 (no-ledger) must appear")


if __name__ == "__main__":
    unittest.main()
