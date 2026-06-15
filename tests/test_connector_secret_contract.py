"""Secret contract tests for read-only datasource connectors."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from brain_ds.connectors.sqlite_connector import SQLiteConnector
from brain_ds.mcp.grounding import SOURCE_EXPLORATION_CONTRACT


class TestConnectorSecretContract(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "secret-contract.db"
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO users (name) VALUES ('Alice')")
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_secret_ref_stored_as_name_not_value(self) -> None:
        with mock.patch.dict(os.environ, {"BRAINDS_SRC_PWD": "super-secret-value"}, clear=False):
            node_payload = {
                "id": "source-1",
                "label": "Warehouse DB",
                "type": "Data Source",
                "details": {
                    "connection": {
                        "kind": "sqlite",
                        "path": "fixtures/warehouse.db",
                        "secret_ref": "BRAINDS_SRC_PWD",
                    }
                },
            }

            serialized = json.dumps(node_payload)

        self.assertIn("BRAINDS_SRC_PWD", serialized)
        self.assertNotIn("super-secret-value", serialized)

    def test_missing_secret_ref_fails_closed(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            connector = SQLiteConnector(
                self.db_path,
                connection_descriptor={"kind": "sqlite", "path": str(self.db_path), "secret_ref": "BRAINDS_SRC_PWD"},
            )

            with self.assertRaisesRegex(KeyError, "BRAINDS_SRC_PWD"):
                connector.describe()

    def test_readonly_holds_with_secret_ref(self) -> None:
        with mock.patch.dict(os.environ, {"BRAINDS_SRC_PWD": "resolved-secret"}, clear=False):
            connector = SQLiteConnector(
                self.db_path,
                connection_descriptor={"kind": "sqlite", "path": str(self.db_path), "secret_ref": "BRAINDS_SRC_PWD"},
            )

            result = connector.query("SELECT name FROM users", limit=5)
            self.assertEqual(result["rows"], [{"name": "Alice"}])

            conn = connector._open()
            try:
                with self.assertRaisesRegex(sqlite3.OperationalError, "readonly|read-only|query_only"):
                    conn.execute("INSERT INTO users (name) VALUES ('Bob')")
            finally:
                conn.close()

    def test_anti_leak_sentinel_not_in_elicit(self) -> None:
        sentinel = "SENTINEL-LEAK-CANARY-12345"
        with mock.patch.dict(os.environ, {"BRAINDS_SRC_PWD": sentinel}, clear=False):
            connector = SQLiteConnector(
                self.db_path,
                connection_descriptor={"kind": "sqlite", "path": str(self.db_path), "secret_ref": "BRAINDS_SRC_PWD"},
            )
            elicit_dir = Path(self.tmpdir.name) / ".elicit"
            elicit_dir.mkdir()

            artifacts = {
                "node.json": json.dumps(
                    {
                        "details": {
                            "connection": {
                                "kind": "sqlite",
                                "path": str(self.db_path),
                                "secret_ref": "BRAINDS_SRC_PWD",
                            }
                        }
                    }
                ),
                "source-docs-acme-2026-06-14.md": json.dumps(connector.describe()),
            }
            for name, content in artifacts.items():
                (elicit_dir / name).write_text(content, encoding="utf-8")

        for artifact in elicit_dir.rglob("*"):
            if artifact.is_file():
                self.assertNotIn(sentinel, artifact.read_text(encoding="utf-8"))

    def test_source_exploration_contract_mentions_secret_ref(self) -> None:
        serialized = json.dumps(SOURCE_EXPLORATION_CONTRACT)
        self.assertIn("secret_ref", serialized)
        self.assertRegex(serialized, r"(never stored|not persisted)")
