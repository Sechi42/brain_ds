"""GraphStore orchestrator over sqlite repositories."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any

from brain_ds.ontology.graph_model import CardSection, Edge, EvidenceRecord, Graph, Node

from .errors import GraphNotFoundError, IncompatibleStoreError, StoreError
from .migrations import MIGRATIONS, apply_pending, configure_connection
from .models import ClusterRow, EdgeRow, EvidenceRow, GraphMeta, NearestHit, NodeRow
from .repository import (
    ClusterRepository,
    AuditRepository,
    EmbeddingRepository,
    EdgeRepository,
    EvidenceRepository,
    GraphMetaRepository,
    NodeRepository,
)

_CONTRACT_VERSION = "1.0.0"


class GraphStore:
    def __init__(self, path: str, *, read_only: bool = False, allow_cross_thread: bool = False):
        self.path = path
        self.read_only = read_only
        self._closed = False
        self.conn = self._connect(path=path, read_only=read_only, allow_cross_thread=allow_cross_thread)
        try:
            configure_connection(self.conn)
            if read_only:
                self._assert_read_only_schema_compatible()
            else:
                apply_pending(self.conn)
        except Exception:
            self.conn.close()
            raise

        self.meta_repo = GraphMetaRepository(self.conn)
        self.node_repo = NodeRepository(self.conn)
        self.edge_repo = EdgeRepository(self.conn)
        self.evidence_repo = EvidenceRepository(self.conn)
        self.cluster_repo = ClusterRepository(self.conn)
        self.embedding_repo = EmbeddingRepository(self.conn)
        self.audit_repo = AuditRepository(self.conn)

    def _connect(self, *, path: str, read_only: bool, allow_cross_thread: bool) -> sqlite3.Connection:
        check_same_thread = not allow_cross_thread
        if read_only:
            uri = f"file:{Path(path).as_posix()}?mode=ro"
            return sqlite3.connect(uri, uri=True, check_same_thread=check_same_thread)
        return sqlite3.connect(path, check_same_thread=check_same_thread)

    def __enter__(self) -> "GraphStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.conn.close()
        self._closed = True

    def import_json(self, source: dict[str, Any], *, workspace_root: str | None = None) -> str:
        graph = Graph.from_v1(source)
        imported_from = str(source.get("imported_from")) if source.get("imported_from") else None
        return self.save_graph(graph, workspace_root=workspace_root or "", imported_from=imported_from)

    def export_json(self, graph_id: str) -> dict[str, Any]:
        return self.load_graph(graph_id).to_dict()

    def save_graph(
        self,
        graph: Graph,
        *,
        graph_id: str | None = None,
        workspace_root: str = "",
        workspace_path: str = "",
        project: str = "",
        imported_from: str | None = None,
    ) -> str:
        self._ensure_writable()
        save_id = graph_id or str(uuid.uuid4())

        self.meta_repo.save_graph_meta(
            graph_id=save_id,
            workspace_root=workspace_root,
            workspace_path=workspace_path,
            project=project,
            org=graph.org,
            schema_version=graph.schema_version,
            contract_version=_CONTRACT_VERSION,
            node_count=len(graph.nodes),
            edge_count=len(graph.edges),
            imported_from=imported_from,
            generated_at=graph.generated_at,
        )

        self.node_repo.delete_nodes(save_id)
        self.node_repo.save_nodes(save_id, [self._node_to_row_input(node) for node in graph.nodes])
        self.edge_repo.save_edges(save_id, [self._edge_to_row_input(edge) for edge in graph.edges])
        self.evidence_repo.save_evidence(
            save_id, [self._evidence_to_row_input(record) for record in graph.evidence]
        )
        return save_id

    def load_graph(self, graph_id: str) -> Graph:
        self._assert_graph_exists(graph_id)

        node_rows = self.node_repo.query_nodes(graph_id)
        edge_rows = self.edge_repo.query_edges(graph_id)
        evidence_rows = self.evidence_repo.search_evidence(graph_id)
        meta = next(meta for meta in self.meta_repo.list_graphs() if meta.id == graph_id)

        return Graph(
            schema_version=meta.schema_version,
            org=meta.org,
            generated_at=meta.generated_at or "",
            nodes=[self._node_from_row(row) for row in node_rows],
            edges=[self._edge_from_row(row) for row in edge_rows],
            evidence=[self._evidence_from_row(row) for row in evidence_rows],
        )

    def list_graphs(self) -> list[GraphMeta]:
        return self._guard_closed(lambda: self.meta_repo.list_graphs())

    def delete_graph(self, graph_id: str) -> None:
        self._ensure_writable()
        self.meta_repo.delete_graph(graph_id)

    def query_nodes(
        self,
        graph_id: str,
        *,
        type: str | None = None,
        supertype: str | None = None,
        parent_id: str | None = None,
    ) -> list[NodeRow]:
        self._assert_graph_exists(graph_id)
        return self.node_repo.query_nodes(
            graph_id,
            type=type,
            supertype=supertype,
            parent_id=parent_id,
        )

    def query_edges(
        self,
        graph_id: str,
        *,
        source: str | None = None,
        target: str | None = None,
    ) -> list[EdgeRow]:
        self._assert_graph_exists(graph_id)
        return self.edge_repo.query_edges(graph_id, source=source, target=target)

    def query_clusters(self, graph_id: str) -> list[ClusterRow]:
        self._assert_graph_exists(graph_id)
        return self.cluster_repo.query_clusters(graph_id)

    def search_evidence(self, graph_id: str, *, content_substr: str | None = None) -> list[EvidenceRow]:
        self._assert_graph_exists(graph_id)
        return self.evidence_repo.search_evidence(graph_id, content_substr=content_substr)

    def upsert_embedding(
        self,
        graph_id: str,
        target_type: str,
        target_id: str,
        model: str,
        vector: list[float],
    ) -> None:
        self._ensure_writable()
        self._assert_graph_exists(graph_id)
        self.embedding_repo.upsert_embedding(graph_id, target_type, target_id, model, vector)

    def upsert_node(self, graph_id: str, node_input: dict[str, Any]) -> None:
        self._ensure_writable()
        self._assert_graph_exists(graph_id)
        self.node_repo.upsert_node(graph_id, node_input)

    def upsert_edge(self, graph_id: str, edge_input: dict[str, Any]) -> None:
        self._ensure_writable()
        self._assert_graph_exists(graph_id)
        self.edge_repo.upsert_edge(graph_id, edge_input)

    def log_audit(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        result_status: str,
        *,
        caller_id: str | None = None,
    ) -> None:
        self._ensure_writable()
        self.audit_repo.log_audit(tool_name, tool_input, result_status, caller_id=caller_id)

    def nearest_embeddings(
        self,
        graph_id: str,
        target_id: str,
        *,
        k: int = 10,
        model: str | None = None,
    ) -> list[NearestHit]:
        self._assert_graph_exists(graph_id)
        return self.embedding_repo.nearest_embeddings(graph_id, target_id, k=k, model=model)

    def _node_to_row_input(self, node: Node) -> dict[str, Any]:
        payload = {
            "id": node.id,
            "label": node.label,
            "type": node.type.value,
            "details": node.details,
            "supertype": node.supertype,
            "evidence_ids": node.evidence_ids,
            "editable_fields": node.editable_fields,
            "layout_hint": node.layout_hint,
            "parent_id": node.parent_id,
            "depth": node.depth,
        }
        if node.card_sections is not None:
            payload["card_sections"] = [
                {
                    "title": section.title,
                    "content": section.content,
                    "icon": section.icon,
                    "order": section.order,
                }
                for section in node.card_sections
            ]
        return payload

    def _edge_to_row_input(self, edge: Edge) -> dict[str, Any]:
        return {
            "source": edge.source,
            "target": edge.target,
            "label": edge.label.value,
            "weight": edge.weight,
            "reasons": edge.reasons,
            "evidence_ids": edge.evidence_ids,
            "edge_id": edge.edge_id,
        }

    def _evidence_to_row_input(self, record: EvidenceRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "type": record.type,
            "source": record.source,
            "content": record.content,
            "provenance": record.provenance,
            "timestamp": record.timestamp,
        }

    def _node_from_row(self, row: NodeRow) -> Node:
        card_sections = None
        if row.card_sections is not None:
            card_sections = [CardSection(**section) for section in row.card_sections]
        return Node(
            id=row.id,
            label=row.label,
            type=row.type,
            details=row.details,
            supertype=row.supertype,
            card_sections=card_sections,
            evidence_ids=row.evidence_ids,
            editable_fields=row.editable_fields,
            layout_hint=row.layout_hint,
            parent_id=row.parent_id,
            depth=row.depth,
        )

    def _edge_from_row(self, row: EdgeRow) -> Edge:
        return Edge(
            source=row.source,
            target=row.target,
            label=row.label,
            weight=row.weight,
            reasons=row.reasons,
            evidence_ids=row.evidence_ids,
            edge_id=row.edge_id,
        )

    def _evidence_from_row(self, row: EvidenceRow) -> EvidenceRecord:
        return EvidenceRecord(
            id=row.id,
            type=row.type,
            source=row.source,
            content=row.content,
            provenance=row.provenance,
            timestamp=row.timestamp or "",
        )

    def _assert_graph_exists(self, graph_id: str) -> None:
        exists = self.conn.execute("SELECT 1 FROM graphs WHERE id = ?", (graph_id,)).fetchone()
        if exists is None:
            raise GraphNotFoundError(f"Graph '{graph_id}' not found")

    def _ensure_writable(self) -> None:
        if self.read_only:
            raise StoreError("GraphStore is read-only")

    def _assert_read_only_schema_compatible(self) -> None:
        latest = len(MIGRATIONS)
        table = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'store_meta'"
        ).fetchone()
        if table is None:
            raise IncompatibleStoreError("Database schema is not initialized")

        row = self.conn.execute(
            "SELECT value FROM store_meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            raise IncompatibleStoreError("Database schema version missing")

        try:
            current = int(row[0])
        except (TypeError, ValueError) as exc:
            raise IncompatibleStoreError("Database schema version is invalid") from exc

        if current != latest:
            raise IncompatibleStoreError(
                f"Read-only store schema version {current} is incompatible with expected {latest}"
            )

    def _guard_closed(self, callback):
        try:
            return callback()
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
