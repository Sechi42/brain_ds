"""RED tests for evidence repository behavior."""

from __future__ import annotations

import sqlite3
import unittest

from brain_ds.store.migrations import apply_pending, configure_connection
from brain_ds.store.repository import EvidenceRepository, GraphMetaRepository


class EvidenceRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        configure_connection(self.conn)
        apply_pending(self.conn)
        self.meta = GraphMetaRepository(self.conn)
        self.repo = EvidenceRepository(self.conn)
        self.meta.save_graph_meta(
            graph_id="graph-v",
            workspace_root="/tmp/ws",
            workspace_path="/tmp/ws/project-v",
            project="project-v",
            org="org-v",
            schema_version="2.0.0",
            contract_version="1.0.0",
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at="",
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_search_evidence_substring_match(self) -> None:
        self.repo.save_evidence(
            "graph-v",
            [
                {"id": "ev-1", "type": "note", "source": "doc", "content": "migration steps"},
                {"id": "ev-2", "type": "note", "source": "doc", "content": "other text"},
            ],
        )

        rows = self.repo.search_evidence("graph-v", content_substr="migr")

        self.assertEqual([row.id for row in rows], ["ev-1"])

    def test_search_evidence_without_filter_returns_all(self) -> None:
        self.repo.save_evidence(
            "graph-v",
            [
                {"id": "ev-3", "type": "note", "source": "doc", "content": "a"},
                {"id": "ev-4", "type": "note", "source": "doc", "content": "b"},
            ],
        )

        rows = self.repo.search_evidence("graph-v")

        self.assertEqual({row.id for row in rows}, {"ev-3", "ev-4"})
