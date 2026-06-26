"""GraphStore orchestrator over sqlite repositories."""

from __future__ import annotations

import logging
import sqlite3
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from brain_ds.ontology.graph_model import CardSection, Edge, EvidenceRecord, Graph, Node

from .errors import GraphAlreadyExistsError, GraphNotFoundError, IncompatibleStoreError, StoreError
from .migrations import MIGRATIONS, apply_pending, configure_connection
from .models import ClusterMemberRow, ClusterRow, EdgeRow, EvidenceRow, GraphMeta, NearestHit, NodeRow
from .repository import (
    AuditRepository,
    ClusterRepository,
    EdgeRepository,
    EmbeddingRepository,
    EvidenceRepository,
    GraphMetaRepository,
    LedgerRepository,
    NodeRepository,
    OutboxRepository,
    PendingQuestionRepository,
)

_CONTRACT_VERSION = "1.0.0"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-process migration cache
# ---------------------------------------------------------------------------
# Maps resolved absolute DB path -> (schema_version, file_mtime) that were
# current after the last successful apply_pending() call for that path.  When
# a new GraphStore is opened against an already-seen path, we skip
# apply_pending only when BOTH the cached version equals len(MIGRATIONS) AND
# the file's current mtime matches the cached mtime.  A changed mtime means
# the DB file was replaced (deleted+recreated, backup restore) — in that case
# we invalidate the cache entry and re-run apply_pending.
#
# This is a module-level dict so it survives across multiple GraphStore
# instances within the same Python process, eliminating redundant migration
# checks during test runs (and normal server usage).
#
# Thread safety note: dict reads/writes in CPython are GIL-protected for
# simple key lookups and assignments, which is sufficient here because the
# worst-case race is two concurrent first-opens, both calling apply_pending
# and then writing the same version to the cache — idempotent and harmless.
#
# Caller note: callers should pass resolved (absolute) paths to avoid symlink
# aliasing — two distinct symlinks to the same inode would produce two cache
# entries but refer to the same DB.  resolve_store_path() in the workspace
# registry always canonicalizes, so production paths are safe.
_migrated_paths: dict[str, tuple[int, float]] = {}


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
                self._apply_pending_cached(path)
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
        self.outbox_repo = OutboxRepository(self.conn)
        self.ledger_repo = LedgerRepository(self.conn)
        self.pending_question_repo = PendingQuestionRepository(self.conn)

    def _apply_pending_cached(self, path: str) -> None:
        """Run apply_pending once per process per DB path.

        The first open for a given absolute path runs apply_pending() normally
        and records the current schema version in the module-level
        `_migrated_paths` cache.  Subsequent opens with the same path skip
        apply_pending entirely when the cached version matches the number of
        known MIGRATIONS (i.e. schema is fully up-to-date for this process).

        In-memory databases (``path == ":memory:"``) are never cached because
        each connection creates a distinct, ephemeral database.
        """
        if path == ":memory:":
            apply_pending(self.conn)
            return

        canonical = str(Path(path).resolve())
        expected_version = len(MIGRATIONS)

        # Capture mtime BEFORE opening/writing so we have the "identity stamp"
        # of the file as it existed when this open began.
        p = Path(canonical)
        open_mtime: float | None = p.stat().st_mtime if p.exists() else None
        cached = _migrated_paths.get(canonical)

        if (
            cached is not None
            and cached[0] == expected_version
            and cached[1] == open_mtime
        ):
            # Schema fully migrated and file identity unchanged — skip.
            return

        # First open, or mtime changed (file replaced/restored) — re-run.
        apply_pending(self.conn)
        # Flush WAL so the mtime we record reflects the post-migration state.
        self.conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        settled_mtime: float | None = p.stat().st_mtime if p.exists() else open_mtime
        _migrated_paths[canonical] = (expected_version, settled_mtime)

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

    def import_json(
        self,
        source: dict[str, Any],
        *,
        graph_id: str | None = None,
        workspace_root: str | None = None,
    ) -> str:
        graph = Graph.from_v1(source)
        imported_from = str(source.get("imported_from")) if source.get("imported_from") else None
        return self.save_graph(
            graph,
            graph_id=graph_id,
            workspace_root=workspace_root or "",
            imported_from=imported_from,
        )

    def create_graph(
        self,
        graph_id: str,
        *,
        name: str | None = None,
        project: str = "",
        workspace_root: str = "",
        workspace_path: str = "",
    ) -> str:
        self._ensure_writable()
        exists = self.conn.execute("SELECT 1 FROM graphs WHERE id = ?", (graph_id,)).fetchone()
        if exists is not None:
            raise GraphAlreadyExistsError(f"Graph '{graph_id}' already exists")

        self.meta_repo.save_graph_meta(
            graph_id=graph_id,
            workspace_root=workspace_root,
            workspace_path=workspace_path,
            project=project,
            org=name or graph_id,
            schema_version="2.0.0",
            contract_version=_CONTRACT_VERSION,
            node_count=0,
            edge_count=0,
            imported_from=None,
            generated_at=None,
        )
        return graph_id

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
        meta = next(meta for meta in self.meta_repo.list_graphs(include_hidden=True) if meta.id == graph_id)

        # Defensive read: edge rows are written without ontology validation
        # (MCP add_edge / outbox writes accept free-text labels), so a single
        # unknown RelationshipType must not blank the whole graph — skip it.
        edges = []
        for row in edge_rows:
            try:
                edges.append(self._edge_from_row(row))
            except ValueError as exc:
                logger.warning(
                    "Skipping edge %s->%s in graph %s: %s",
                    row.source, row.target, graph_id, exc,
                )

        return Graph(
            schema_version=meta.schema_version,
            org=meta.org,
            generated_at=meta.generated_at or "",
            nodes=[self._node_from_row(row) for row in node_rows],
            edges=edges,
            evidence=[self._evidence_from_row(row) for row in evidence_rows],
        )

    def list_graphs(self) -> list[GraphMeta]:
        return self._guard_closed(lambda: self.meta_repo.list_graphs())

    def get_graph_edge_count(self, graph_id: str) -> int:
        """Return the cached edge count for *graph_id* from the graphs table.

        This is a fast single-row lookup against the ``edge_count`` column that
        is maintained by ``import_graph`` and ``refresh_graph_counts``.  It does
        NOT require a full ``COUNT(*)`` scan of the edges table, making it safe
        to call as a pre-flight check on large graphs.

        Raises :exc:`~brain_ds.store.models.GraphNotFoundError` when *graph_id*
        is not registered.
        """
        def _fetch() -> int:
            row = self.conn.execute(
                "SELECT edge_count FROM graphs WHERE id = ?",
                (graph_id,),
            ).fetchone()
            if row is None:
                raise GraphNotFoundError(f"Graph '{graph_id}' not found")
            return int(row[0])

        return self._guard_closed(_fetch)

    def hide_graph(self, graph_id: str) -> None:
        """Soft-delete: mark the graph hidden so list_graphs excludes it.

        The row and all attached data remain in SQLite. The operation is
        reversible by calling set_hidden(graph_id, False) directly on the repo.
        """
        self._ensure_writable()
        self.meta_repo.set_hidden(graph_id, True)

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
        labels: list[str] | None = None,
        min_weight: float | None = None,
        max_weight: float | None = None,
        has_evidence: bool | None = None,
        order_by: str = "edge_id",
        limit: int | None = None,
        cursor: tuple[str, str] | None = None,
    ) -> list[EdgeRow]:
        self._assert_graph_exists(graph_id)
        return self.edge_repo.query_edges(
            graph_id,
            source=source,
            target=target,
            labels=labels,
            min_weight=min_weight,
            max_weight=max_weight,
            has_evidence=has_evidence,
            order_by=order_by,
            limit=limit,
            cursor=cursor,
        )

    def query_clusters(self, graph_id: str) -> list[ClusterRow]:
        self._assert_graph_exists(graph_id)
        return self.cluster_repo.query_clusters(graph_id)

    def save_clusters(self, graph_id: str, clusters: list[dict[str, Any]]) -> None:
        self._ensure_writable()
        self._assert_graph_exists(graph_id)
        self.cluster_repo.save_clusters(graph_id, clusters)

    def save_cluster_members(self, graph_id: str, members: list[dict[str, Any]]) -> None:
        self._ensure_writable()
        self._assert_graph_exists(graph_id)
        self.cluster_repo.save_members(graph_id, members)

    def list_cluster_members(self, graph_id: str, *, cluster_id: str | None = None) -> list[ClusterMemberRow]:
        self._assert_graph_exists(graph_id)
        return self.cluster_repo.list_members(graph_id, cluster_id=cluster_id)

    def update_cluster_lifecycle(
        self,
        graph_id: str,
        cluster_id: str,
        status: str,
        *,
        reason: str | None = None,
    ) -> None:
        self._ensure_writable()
        self._assert_graph_exists(graph_id)
        self.cluster_repo.update_cluster_lifecycle(graph_id, cluster_id, status, reason=reason)

    def search_nodes_fts(self, graph_id: str, query: str) -> list[str] | None:
        """Return node IDs matching query via FTS5, or None if FTS unavailable.

        Returns None when the nodes_fts table doesn't exist (older stores) or
        when FTS5 is not compiled in. Callers should fall back to Python scan.

        The query is normalised (accent-stripped, lowercased) and each token is
        wrapped in double-quotes to avoid FTS5 operator injection. Prefix
        matching is appended (*) so "oper" matches "operacion".
        """
        normalized = unicodedata.normalize("NFD", query.lower())
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")

        tokens = normalized.split()
        if not tokens:
            return []

        # Wrap each token in double-quotes for FTS5 (prevents operator injection)
        # and append * for prefix matching
        fts_query = " ".join(f'"{t}"*' for t in tokens)

        try:
            rows = self.conn.execute(
                "SELECT node_id FROM nodes_fts WHERE graph_id = ? AND nodes_fts MATCH ?",
                (graph_id, fts_query),
            ).fetchall()
            return [row[0] for row in rows]
        except sqlite3.OperationalError:
            # FTS table not found or FTS5 not available
            return None

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
        self._refresh_graph_counts(graph_id)

    def upsert_edge(self, graph_id: str, edge_input: dict[str, Any]) -> None:
        self._ensure_writable()
        self._assert_graph_exists(graph_id)
        self.edge_repo.upsert_edge(graph_id, edge_input)
        self._refresh_graph_counts(graph_id)

    def delete_node(self, graph_id: str, node_id: str) -> int:
        self._ensure_writable()
        self._assert_graph_exists(graph_id)
        deleted = self.node_repo.delete_node(graph_id, node_id)
        self._refresh_graph_counts(graph_id)
        return deleted

    def delete_edge(self, graph_id: str, source: str, target: str) -> int:
        self._ensure_writable()
        self._assert_graph_exists(graph_id)
        deleted = self.edge_repo.delete_edge(graph_id, source, target)
        self._refresh_graph_counts(graph_id)
        return deleted

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

    def enqueue_event(self, event: str, graph_id: str, payload: dict[str, Any]) -> None:
        self._ensure_writable()
        self.outbox_repo.enqueue_event(event, graph_id, payload)

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

    def nearest_to_vector(
        self,
        graph_id: str,
        vector: list[float],
        *,
        k: int = 10,
    ) -> list[NearestHit]:
        self._assert_graph_exists(graph_id)
        return self.embedding_repo.nearest_to_vector(graph_id, vector, k=k)

    def _node_to_row_input(self, node: Node) -> dict[str, Any]:
        entity_type = node.entity_type
        payload = {
            "id": node.id,
            "label": node.label,
            "type": entity_type.value,
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
        relationship_type = edge.relationship_type
        return {
            "source": edge.source,
            "target": edge.target,
            "label": relationship_type.value,
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

    def _card_section_from_dict(self, section: Any) -> CardSection | None:
        if not isinstance(section, dict):
            return None
        content = section.get("content")
        if content is None and section.get("body") is not None:
            content = section.get("body")
        return CardSection(
            title=str(section.get("title", "")),
            content="" if content is None else str(content),
            icon=str(section.get("icon", "")),
            order=int(section.get("order", 0) or 0),
        )

    def _node_from_row(self, row: NodeRow) -> Node:
        card_sections = None
        if row.card_sections is not None:
            card_sections = [
                section
                for item in row.card_sections
                if (section := self._card_section_from_dict(item)) is not None
            ]
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

    def _refresh_graph_counts(self, graph_id: str) -> None:
        self.conn.execute(
            """
            UPDATE graphs
               SET node_count = (SELECT COUNT(*) FROM nodes WHERE graph_id = ?),
                   edge_count = (SELECT COUNT(*) FROM edges WHERE graph_id = ?),
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = ?
            """,
            (graph_id, graph_id, graph_id),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Ledger pass-throughs (thin delegation to LedgerRepository)
    # ------------------------------------------------------------------

    def append_ledger(self, graph_id: str, **kwargs) -> int:
        """Append one row to confidence_ledger for graph_id.

        Calls _ensure_writable() before delegating so read-only stores raise
        consistently.  The ledger commit is advisory-isolated from any prior
        edge write.
        """
        self._ensure_writable()
        return self.ledger_repo.append(graph_id, **kwargs)

    def query_ledger_latest(self, graph_id: str, **kwargs):
        """Return the latest ledger row per target_id for graph_id."""
        self._assert_graph_exists(graph_id)
        return self.ledger_repo.query_latest_per_target(graph_id, **kwargs)

    def query_ledger_latest_for_targets(self, graph_id: str, target_ids: list[str], **kwargs):
        """Return latest ledger rows keyed by target_id for selected targets."""
        self._assert_graph_exists(graph_id)
        return self.ledger_repo.query_latest_for_targets(graph_id, target_ids, **kwargs)

    def query_node_currency_evidence(self, graph_id: str, node_ids: list[str]):
        """Return batched node currency evidence for temporal freshness assessment."""
        self._assert_graph_exists(graph_id)
        return self.ledger_repo.query_node_currency_evidence(graph_id, node_ids)

    def insert_pending_question(
        self,
        graph_id: str,
        *,
        target_node_id: str | None,
        gap_kind: str,
        entity_type: str | None,
        question_text: str,
        stakeholder_owner: str | None,
    ) -> int:
        """Persist a deferred elicitation question without touching the ledger."""
        self._ensure_writable()
        self._assert_graph_exists(graph_id)
        return self.pending_question_repo.insert(
            graph_id,
            target_node_id=target_node_id,
            gap_kind=gap_kind,
            entity_type=entity_type,
            question_text=question_text,
            stakeholder_owner=stakeholder_owner,
        )

    def list_pending_questions(self, graph_id: str, *, status: str = "pending"):
        """Return deferred elicitation questions for this graph and status."""
        self._assert_graph_exists(graph_id)
        return self.pending_question_repo.list(graph_id, status=status)

    def resolve_pending_question(self, pending_id: int, *, outcome: str, resolved_by: str):
        """Resolve a pending question without writing confidence_ledger rows."""
        self._ensure_writable()
        return self.pending_question_repo.resolve(
            pending_id,
            outcome=outcome,
            resolved_by=resolved_by,
        )

    def query_ledger(self, graph_id: str, *, status: str | None = None, **kwargs):
        """Return full ledger history for graph_id (all rows, optional status filter)."""
        self._assert_graph_exists(graph_id)
        return self.ledger_repo.query_by_graph(graph_id, status=status, **kwargs)

    def list_pending_confirmations(self, graph_id: str):
        """Return latest-per-target rows across all target_types whose latest status
        is 'needs-confirmation', ordered id ASC.  Graph-wide; already-resolved targets
        are excluded.
        """
        self._assert_graph_exists(graph_id)
        return self.ledger_repo.list_pending_confirmations(graph_id)

    def resolve_confirmation(
        self,
        graph_id: str,
        *,
        target_type: str,
        target_id: str,
        outcome: str,
        resolved_by: str,
        gold_rationale: str,
    ) -> dict:
        """Resolve a pending confirmation by appending a human verdict row.

        Delegates to LedgerRepository.resolve_confirmation after ensuring the
        store is writable.  Never updates prior rows (append-only contract).

        Returns {"appended_id": int, "previous_id": int, "status": outcome}.
        Raises ValueError for invalid outcome or missing/non-pending latest row.
        """
        self._ensure_writable()
        self._assert_graph_exists(graph_id)
        return self.ledger_repo.resolve_confirmation(
            graph_id,
            target_type=target_type,
            target_id=target_id,
            outcome=outcome,
            resolved_by=resolved_by,
            gold_rationale=gold_rationale,
        )
