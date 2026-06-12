"""Tests for brain_ds/connectors — read-only data-source connectors."""
from __future__ import annotations

import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

from brain_ds.connectors.base import ReadOnlyConnector
from brain_ds.connectors.csv_connector import CsvConnector
from brain_ds.connectors.sqlite_connector import SQLiteConnector, _validate_select_only


class TestReadOnlyConnectorABC(unittest.TestCase):
    """ABC contract: all abstract methods must be declared."""

    def test_cannot_instantiate_base_directly(self) -> None:
        with self.assertRaises(TypeError):
            ReadOnlyConnector()  # type: ignore[abstract]

    def test_required_methods_listed(self) -> None:
        required = {"describe", "list_containers", "list_tables", "get_table_schema", "preview"}
        abstract: set[str] = cast(set[str], getattr(ReadOnlyConnector, "__abstractmethods__", set()))
        self.assertEqual(abstract, required)


class TestSQLiteConnectorBasic(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)")
        conn.execute("INSERT INTO users VALUES (1, 'Alice', 30)")
        conn.execute("INSERT INTO users VALUES (2, 'Bob', 25)")
        conn.execute("CREATE TABLE items (item_id INTEGER, label TEXT)")
        conn.execute("INSERT INTO items VALUES (10, 'Widget')")
        conn.commit()
        conn.close()
        self.connector = SQLiteConnector(self.db_path)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_describe_returns_kind_path_size(self) -> None:
        info = self.connector.describe()
        self.assertEqual(info["kind"], "sqlite")
        self.assertIn("path", info)
        self.assertGreater(info["size_bytes"], 0)
        self.assertIn("sqlite_version", info)

    def test_list_containers_includes_main(self) -> None:
        containers = self.connector.list_containers()
        self.assertIn("main", containers)

    def test_list_tables_returns_user_tables(self) -> None:
        tables = self.connector.list_tables("main")
        self.assertIn("users", tables)
        self.assertIn("items", tables)
        # sqlite_ internal tables are excluded
        for t in tables:
            self.assertFalse(t.startswith("sqlite_"))

    def test_get_table_schema_columns_and_count(self) -> None:
        schema = self.connector.get_table_schema("main", "users")
        col_names = [c["name"] for c in schema["columns"]]
        self.assertIn("id", col_names)
        self.assertIn("name", col_names)
        self.assertIn("age", col_names)
        self.assertEqual(schema["row_count_estimate"], 2)
        # Each column has required keys
        for col in schema["columns"]:
            self.assertIn("name", col)
            self.assertIn("type", col)
            self.assertIn("sample", col)
            self.assertIn("meaning", col)

    def test_preview_returns_rows(self) -> None:
        result = self.connector.preview("main", "users", limit=5)
        self.assertIn("columns", result)
        self.assertIn("rows", result)
        self.assertIn("truncated", result)
        self.assertEqual(len(result["rows"]), 2)
        self.assertFalse(result["truncated"])

    def test_preview_cap_at_50(self) -> None:
        # limit > 50 should be capped at 50
        result = self.connector.preview("main", "users", limit=999)
        # Only 2 rows exist anyway, but truncated should be False
        self.assertFalse(result["truncated"])

    def test_file_not_found_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            SQLiteConnector("/nonexistent/path.db")


class TestSQLiteConnectorQuery(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "query_test.db"
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("CREATE TABLE data (x INTEGER, y TEXT)")
        for i in range(10):
            conn.execute("INSERT INTO data VALUES (?, ?)", (i, f"row{i}"))
        conn.commit()
        conn.close()
        self.connector = SQLiteConnector(self.db_path)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_select_query_returns_results(self) -> None:
        result = self.connector.query("SELECT * FROM data ORDER BY x", limit=5)
        self.assertEqual(len(result["rows"]), 5)
        self.assertTrue(result["truncated"])
        self.assertIn("x", result["columns"])

    def test_select_with_cte(self) -> None:
        result = self.connector.query("WITH t AS (SELECT x FROM data) SELECT * FROM t LIMIT 3")
        self.assertEqual(len(result["rows"]), 3)

    def test_cap_at_200(self) -> None:
        # Create more than 200 rows to test cap
        conn = sqlite3.connect(str(self.db_path))
        for i in range(300):
            conn.execute("INSERT INTO data VALUES (?, ?)", (i + 1000, f"extra{i}"))
        conn.commit()
        conn.close()
        result = self.connector.query("SELECT * FROM data", limit=300)
        self.assertLessEqual(len(result["rows"]), 200)

    def test_insert_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.connector.query("INSERT INTO data VALUES (99, 'bad')")

    def test_update_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.connector.query("UPDATE data SET y = 'bad' WHERE x = 1")

    def test_delete_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.connector.query("DELETE FROM data")

    def test_drop_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.connector.query("DROP TABLE data")

    def test_attach_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.connector.query("ATTACH ':memory:' AS mem")

    def test_multiple_statements_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.connector.query("SELECT 1; SELECT 2")

    def test_comment_stripping_does_not_bypass(self) -> None:
        # -- comment before INSERT should not bypass check
        with self.assertRaises(ValueError):
            self.connector.query("-- valid comment\nINSERT INTO data VALUES (99, 'bad')")

    def test_block_comment_stripping(self) -> None:
        # Block comment before SELECT is fine
        result = self.connector.query("/* comment */ SELECT x FROM data LIMIT 1")
        self.assertEqual(len(result["rows"]), 1)


class TestValidateSelectOnly(unittest.TestCase):
    """Unit tests for the select-only validation function."""

    def test_select_ok(self) -> None:
        _validate_select_only("SELECT 1")  # should not raise

    def test_with_select_ok(self) -> None:
        _validate_select_only("WITH cte AS (SELECT 1) SELECT * FROM cte")

    def test_insert_raises(self) -> None:
        with self.assertRaises(ValueError):
            _validate_select_only("INSERT INTO t VALUES (1)")

    def test_pragma_raises(self) -> None:
        with self.assertRaises(ValueError):
            _validate_select_only("PRAGMA journal_mode = WAL")

    def test_multiple_semicolons_raises(self) -> None:
        with self.assertRaises(ValueError):
            _validate_select_only("SELECT 1; DROP TABLE t")

    def test_fts_injection_special_chars_select_ok(self) -> None:
        # Query containing FTS-special chars is validated as SELECT — no crash
        _validate_select_only('SELECT * FROM t WHERE label MATCH "fix auth bug"')

    def test_parentheses_in_select_ok(self) -> None:
        _validate_select_only("SELECT COUNT(*) FROM t WHERE (x = 1 OR y = 2)")


class TestCsvConnectorBasic(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.csv_path = Path(self.tmpdir.name) / "data.csv"
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "age", "score"])
            writer.writerow(["Alice", "30", "9.5"])
            writer.writerow(["Bob", "25", "8.0"])
            writer.writerow(["Carol", "35", "7.5"])
        self.connector = CsvConnector(self.csv_path)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_describe_returns_kind_path(self) -> None:
        info = self.connector.describe()
        self.assertEqual(info["kind"], "csv")
        self.assertIn("path", info)
        self.assertGreater(info["column_count"], 0)

    def test_list_containers_returns_stem(self) -> None:
        containers = self.connector.list_containers()
        self.assertEqual(containers, ["data"])

    def test_list_tables_returns_data(self) -> None:
        tables = self.connector.list_tables("data")
        self.assertEqual(tables, ["data"])

    def test_get_table_schema_columns(self) -> None:
        schema = self.connector.get_table_schema("data", "data")
        col_names = [c["name"] for c in schema["columns"]]
        self.assertIn("name", col_names)
        self.assertIn("age", col_names)
        self.assertIn("score", col_names)
        # age is all integers
        age_col = next(c for c in schema["columns"] if c["name"] == "age")
        self.assertEqual(age_col["type"], "INTEGER")
        # score is float
        score_col = next(c for c in schema["columns"] if c["name"] == "score")
        self.assertEqual(score_col["type"], "REAL")

    def test_preview_returns_rows(self) -> None:
        result = self.connector.preview("data", "data", limit=2)
        self.assertEqual(len(result["rows"]), 2)
        self.assertTrue(result["truncated"])
        self.assertIn("name", result["columns"])

    def test_preview_respects_limit_cap(self) -> None:
        result = self.connector.preview("data", "data", limit=999)
        # Only 3 data rows, all returned
        self.assertEqual(len(result["rows"]), 3)
        self.assertFalse(result["truncated"])

    def test_bom_handling(self) -> None:
        bom_path = Path(self.tmpdir.name) / "bom.csv"
        with open(bom_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "value"])
            writer.writerow(["1", "hello"])
        connector = CsvConnector(bom_path)
        schema = connector.get_table_schema("bom", "data")
        col_names = [c["name"] for c in schema["columns"]]
        # BOM should be stripped — first column should be "id" not "﻿id"
        self.assertNotIn("﻿id", col_names)
        self.assertIn("id", col_names)

    def test_file_not_found_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            CsvConnector("/nonexistent/file.csv")


class TestFTS5SearchIntegration(unittest.TestCase):
    """Integration tests for FTS5 search via store.search_nodes_fts."""

    def setUp(self) -> None:
        import tempfile
        from brain_ds.store.graph_store import GraphStore

        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "fts_test.db"
        self.store = GraphStore(str(self.db_path))
        self.graph_id = "g1"
        self.store.meta_repo.save_graph_meta(
            graph_id=self.graph_id,
            workspace_root=self.tmpdir.name,
            workspace_path=self.tmpdir.name,
            project="test",
            org="test-org",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )

    def tearDown(self) -> None:
        self.store.close()
        self.tmpdir.cleanup()

    def _upsert(self, node_id: str, label: str, details: dict) -> None:
        self.store.upsert_node(self.graph_id, {
            "id": node_id,
            "label": label,
            "type": "Data Source",
            "supertype": "data",
            "details": details,
        })

    def test_basic_label_search(self) -> None:
        self._upsert("n1", "Ventas ERP", {"system": "SAP"})
        self._upsert("n2", "Marketing DB", {"system": "Salesforce"})
        ids = self.store.search_nodes_fts(self.graph_id, "ventas")
        self.assertIsNotNone(ids)
        assert ids is not None
        self.assertIn("n1", ids)
        self.assertNotIn("n2", ids)

    def test_accent_insensitive_search(self) -> None:
        self._upsert("n1", "Operación de Ventas", {"what": "sistema de ventas"})
        self._upsert("n2", "Marketing DB", {"system": "Other"})
        # Search without accent should find node with accent
        ids = self.store.search_nodes_fts(self.graph_id, "operacion")
        self.assertIsNotNone(ids)
        assert ids is not None
        self.assertIn("n1", ids)
        # Search with accent should also work
        ids2 = self.store.search_nodes_fts(self.graph_id, "Operación")
        self.assertIsNotNone(ids2)
        assert ids2 is not None
        self.assertIn("n1", ids2)

    def test_fts_injection_safety(self) -> None:
        # FTS special chars (quotes, parens, stars) should not crash
        self._upsert("n1", "auth bug fix", {"what": "security fix"})
        # These queries should not raise — they may return empty or results
        for dangerous_query in [
            '"fix auth bug"',
            '(auth OR bug)',
            'auth*',
            'auth AND bug',
            '"',
        ]:
            try:
                result = self.store.search_nodes_fts(self.graph_id, dangerous_query)
                # Result is None (FTS unavailable) or list — no crash
                self.assertIn(type(result), (list, type(None)))
            except Exception as exc:
                self.fail(f"FTS injection query {dangerous_query!r} raised: {exc}")

    def test_prefix_matching(self) -> None:
        self._upsert("n1", "Reportes Financieros", {"what": "datos financieros"})
        ids = self.store.search_nodes_fts(self.graph_id, "financ")
        self.assertIsNotNone(ids)
        assert ids is not None
        self.assertIn("n1", ids)

    def test_search_on_details_text(self) -> None:
        self._upsert("n1", "ERP Node", {"system": "SAP", "what": "datos de produccion"})
        ids = self.store.search_nodes_fts(self.graph_id, "produccion")
        self.assertIsNotNone(ids)
        assert ids is not None
        self.assertIn("n1", ids)

    def test_fallback_when_fts_unavailable(self) -> None:
        # Drop the FTS table to simulate unavailable FTS
        self.store.conn.execute("DROP TABLE IF EXISTS nodes_fts")
        self.store.conn.commit()
        result = self.store.search_nodes_fts(self.graph_id, "anything")
        # Should return None (FTS unavailable)
        self.assertIsNone(result)

    def test_delete_node_removes_from_fts(self) -> None:
        self._upsert("n1", "ToDelete", {"what": "temporary"})
        ids_before = self.store.search_nodes_fts(self.graph_id, "todelete")
        self.assertIsNotNone(ids_before)
        assert ids_before is not None
        self.assertIn("n1", ids_before)
        self.store.delete_node(self.graph_id, "n1")
        ids_after = self.store.search_nodes_fts(self.graph_id, "todelete")
        self.assertNotIn("n1", ids_after or [])


class TestSearchGraphWithFTS(unittest.TestCase):
    """Integration tests for the search_graph MCP tool with FTS + fallback."""

    def setUp(self) -> None:
        import tempfile
        from brain_ds.store.graph_store import GraphStore
        from brain_ds.mcp.tools import search_graph

        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "search_test.db"
        self.store = GraphStore(str(self.db_path))
        self.graph_id = "sg1"
        self.store.meta_repo.save_graph_meta(
            graph_id=self.graph_id,
            workspace_root=self.tmpdir.name,
            workspace_path=self.tmpdir.name,
            project="test",
            org="test-org",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )
        self.search_graph = search_graph

    def tearDown(self) -> None:
        self.store.close()
        self.tmpdir.cleanup()

    def _upsert(self, node_id: str, label: str, details: dict) -> None:
        self.store.upsert_node(self.graph_id, {
            "id": node_id,
            "label": label,
            "type": "Data Source",
            "supertype": "data",
            "details": details,
        })

    def _expect_rows(self, result: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
        self.assertIsInstance(result, list)
        return cast(list[dict[str, Any]], result)

    def test_accent_insensitive_search_graph(self) -> None:
        self._upsert("n1", "Gestión de Ventas", {"what": "ERP principal"})
        self._upsert("n2", "Marketing Data", {"what": "analytics"})
        # Search without accent
        result = self._expect_rows(self.search_graph(self.store, {"graph_id": self.graph_id, "query": "gestion"}))
        ids = [r["id"] for r in result]
        self.assertIn("n1", ids)
        self.assertNotIn("n2", ids)

    def test_fts_injection_does_not_crash(self) -> None:
        self._upsert("n1", "security fix", {"what": "auth bug"})
        for q in ['"fix auth bug"', '(security)', 'security*', 'fix AND auth']:
            result = self.search_graph(self.store, {"graph_id": self.graph_id, "query": q})
            # Must be list (possibly empty) or an error dict — never a crash
            self.assertIsInstance(result, (list, dict))

    def test_fallback_python_scan(self) -> None:
        self._upsert("n1", "Análisis de datos", {"what": "important"})
        # Drop FTS table to force fallback
        self.store.conn.execute("DROP TABLE IF EXISTS nodes_fts")
        self.store.conn.commit()
        result = self._expect_rows(self.search_graph(self.store, {"graph_id": self.graph_id, "query": "analisis"}))
        ids = [r["id"] for r in result]
        self.assertIn("n1", ids)


if __name__ == "__main__":
    unittest.main()
