"""Repositories for graph store aggregates."""

from __future__ import annotations

import sqlite3
import hashlib
import json
from math import fsum, sqrt
from datetime import datetime, timedelta, timezone
from typing import cast

from .errors import CorruptVectorError, GraphNotFoundError
from .models import (
    ClusterMemberRow,
    ClusterMetadataV1,
    ClusterRow,
    EdgeRow,
    EmbeddingRow,
    EvidenceRow,
    GraphMeta,
    LedgerRow,
    NearestHit,
    NodeRow,
    PendingQuestionRow,
)
from .serialization import decode_json, decode_vector, encode_json, encode_vector
from .migrations import _normalize_text, _extract_text_from_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rank_cosine_hits(query: list[float], rows: list[EmbeddingRow], *, k: int) -> list[NearestHit]:
    """Rank embedding rows by cosine similarity to a query vector."""
    query_norm = sqrt(fsum(value * value for value in query))
    if query_norm == 0.0:
        raise CorruptVectorError("Query vector has zero norm")

    best_scores: dict[str, float] = {}
    for row in rows:
        candidate = decode_vector(row.vector, dimensions=row.dimensions)
        candidate_norm = sqrt(fsum(value * value for value in candidate))
        if candidate_norm == 0.0:
            continue

        score = fsum(a * b for a, b in zip(query, candidate)) / (query_norm * candidate_norm)
        previous = best_scores.get(row.target_id)
        if previous is None or score > previous:
            best_scores[row.target_id] = score

    limit = max(int(k), 0)
    ranked = sorted(best_scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return [NearestHit(target_id=target_id, score=score) for target_id, score in ranked]


def _fts_upsert(conn: sqlite3.Connection, graph_id: str, node_id: str, label: str, details_json: str | None, sections_json: str | None) -> None:
    """Update the nodes_fts index for one node (delete then insert)."""
    try:
        conn.execute(
            "DELETE FROM nodes_fts WHERE graph_id = ? AND node_id = ?",
            (graph_id, node_id),
        )
        conn.execute(
            "INSERT INTO nodes_fts(graph_id, node_id, label, details_text, sections_text) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                graph_id,
                node_id,
                _normalize_text(label or ""),
                _normalize_text(_extract_text_from_json(details_json)),
                _normalize_text(_extract_text_from_json(sections_json)),
            ),
        )
    except Exception:
        # FTS table may not exist (read-only store or very old migration state).
        # Silently skip — search falls back to Python scan.
        pass


def _fts_delete(conn: sqlite3.Connection, graph_id: str, node_id: str) -> None:
    """Remove one node from the nodes_fts index."""
    try:
        conn.execute(
            "DELETE FROM nodes_fts WHERE graph_id = ? AND node_id = ?",
            (graph_id, node_id),
        )
    except Exception:
        pass


def _schema_baseline_last_documented_at(details: dict) -> str | None:
    baseline = details.get("schema_baseline") if isinstance(details, dict) else None
    if not isinstance(baseline, dict):
        return None
    value = baseline.get("last_documented_at")
    return str(value) if value is not None else None


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[start : start + size] for start in range(0, len(values), size)]


class GraphMetaRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save_graph_meta(
        self,
        *,
        graph_id: str,
        workspace_root: str,
        workspace_path: str,
        project: str,
        org: str,
        schema_version: str,
        contract_version: str,
        node_count: int,
        edge_count: int,
        imported_from: str | None,
        generated_at: str | None,
    ) -> None:
        now = _utc_now()
        self.conn.execute(
            """
            INSERT INTO graphs(
                id, workspace_root, workspace_path, project, org, schema_version,
                contract_version, node_count, edge_count, imported_from, generated_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                workspace_root=excluded.workspace_root,
                workspace_path=excluded.workspace_path,
                project=excluded.project,
                org=excluded.org,
                schema_version=excluded.schema_version,
                contract_version=excluded.contract_version,
                node_count=excluded.node_count,
                edge_count=excluded.edge_count,
                imported_from=excluded.imported_from,
                generated_at=excluded.generated_at,
                updated_at=excluded.updated_at
            """,
            (
                graph_id,
                workspace_root,
                workspace_path,
                project,
                org,
                schema_version,
                contract_version,
                node_count,
                edge_count,
                imported_from,
                generated_at,
                now,
                now,
            ),
        )
        self.conn.commit()

    def list_graphs(self, *, include_hidden: bool = False) -> list[GraphMeta]:
        where = "" if include_hidden else "WHERE hidden = 0"
        rows = self.conn.execute(
            f"""
            SELECT id, workspace_root, workspace_path, project, org, schema_version,
                   contract_version, node_count, edge_count, imported_from,
                   generated_at, created_at, updated_at
              FROM graphs
             {where}
          ORDER BY updated_at DESC, rowid DESC, id ASC
            """
        ).fetchall()
        return [GraphMeta(*row) for row in rows]

    def set_hidden(self, graph_id: str, hidden: bool) -> None:
        cur = self.conn.execute(
            "UPDATE graphs SET hidden = ? WHERE id = ?",
            (1 if hidden else 0, graph_id),
        )
        self.conn.commit()
        if cur.rowcount == 0:
            raise GraphNotFoundError(f"Graph '{graph_id}' not found")

    def delete_graph(self, graph_id: str) -> None:
        cur = self.conn.execute("DELETE FROM graphs WHERE id = ?", (graph_id,))
        self.conn.commit()
        if cur.rowcount == 0:
            raise GraphNotFoundError(f"Graph '{graph_id}' not found")


class NodeRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save_nodes(self, graph_id: str, nodes: list[dict]) -> None:
        self._validate_parent_ids(graph_id, nodes)
        for node in nodes:
            now = _utc_now()
            existing = self.conn.execute(
                "SELECT created_at, modified_at FROM nodes WHERE graph_id = ? AND id = ?",
                (graph_id, node["id"]),
            ).fetchone()
            if existing:
                created_at = existing[0]
                existing_modified = datetime.fromisoformat(existing[1])
                now_dt = datetime.fromisoformat(now)
                if now_dt <= existing_modified:
                    now = (existing_modified + timedelta(microseconds=1)).isoformat()
            else:
                created_at = now
            node_type = str(node["type"])
            self.conn.execute(
                """
                INSERT INTO nodes(
                    graph_id, id, label, type, supertype, details, card_sections,
                    editable_fields, evidence_ids, layout_hint, parent_id, depth,
                    created_at, modified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(graph_id, id) DO UPDATE SET
                    label=excluded.label,
                    type=excluded.type,
                    supertype=excluded.supertype,
                    details=excluded.details,
                    card_sections=excluded.card_sections,
                    editable_fields=excluded.editable_fields,
                    evidence_ids=excluded.evidence_ids,
                    layout_hint=excluded.layout_hint,
                    parent_id=excluded.parent_id,
                    depth=excluded.depth,
                    modified_at=excluded.modified_at
                """,
                (
                    graph_id,
                    node["id"],
                    node["label"],
                    node_type,
                    node.get("supertype"),
                    encode_json(node.get("details", {})),
                    encode_json(node.get("card_sections")) if node.get("card_sections") is not None else None,
                    encode_json(node.get("editable_fields")) if node.get("editable_fields") is not None else None,
                    encode_json(node.get("evidence_ids")) if node.get("evidence_ids") is not None else None,
                    encode_json(node.get("layout_hint")) if node.get("layout_hint") is not None else None,
                    node.get("parent_id"),
                    int(node.get("depth", 0)),
                    created_at,
                    now,
                ),
            )
            # Keep FTS index in sync
            details_json = encode_json(node.get("details", {}))
            sections_json = encode_json(node.get("card_sections")) if node.get("card_sections") is not None else None
            _fts_upsert(self.conn, graph_id, node["id"], node["label"], details_json, sections_json)
        self.conn.commit()

    def query_nodes(
        self,
        graph_id: str,
        *,
        type: str | None = None,
        supertype: str | None = None,
        parent_id: str | None = None,
    ) -> list[NodeRow]:
        sql = """
            SELECT graph_id, id, label, type, supertype, details, card_sections,
                   editable_fields, evidence_ids, layout_hint, parent_id, depth,
                   created_at, modified_at
              FROM nodes
             WHERE graph_id = ?
        """
        params: list[object] = [graph_id]
        if type is not None:
            sql += " AND lower(type) = lower(?)"
            params.append(type)
        if supertype is not None:
            sql += " AND supertype = ?"
            params.append(supertype)
        if parent_id is not None:
            sql += " AND parent_id = ?"
            params.append(parent_id)
        sql += " ORDER BY id ASC"
        rows = self.conn.execute(sql, params).fetchall()
        return [
            NodeRow(
                graph_id=row[0],
                id=row[1],
                label=row[2],
                type=row[3],
                supertype=row[4],
                details=decode_json(row[5]) or {},
                card_sections=decode_json(row[6]),
                editable_fields=decode_json(row[7]),
                evidence_ids=decode_json(row[8]),
                layout_hint=decode_json(row[9]),
                parent_id=row[10],
                depth=int(row[11]),
                created_at=row[12],
                modified_at=row[13],
            )
            for row in rows
        ]

    def upsert_node(self, graph_id: str, node_input: dict) -> None:
        now = _utc_now()
        existing_row = self.conn.execute(
            """
            SELECT label, type, supertype, details, card_sections, editable_fields,
                   evidence_ids, layout_hint, parent_id, depth, created_at, modified_at
              FROM nodes
             WHERE graph_id = ? AND id = ?
            """,
            (graph_id, node_input["id"]),
        ).fetchone()
        if existing_row is not None:
            existing_modified = datetime.fromisoformat(existing_row[11])
            now_dt = datetime.fromisoformat(now)
            if now_dt <= existing_modified:
                now = (existing_modified + timedelta(microseconds=1)).isoformat()

        payload = {
            "label": node_input.get("label") if existing_row is None else node_input.get("label", existing_row[0]),
            "type": node_input.get("type") if existing_row is None else node_input.get("type", existing_row[1]),
            "supertype": node_input.get("supertype") if existing_row is None else node_input.get("supertype", existing_row[2]),
            "details": (
                encode_json(node_input.get("details", {}))
                if existing_row is None
                else encode_json(node_input["details"]) if "details" in node_input else existing_row[3]
            ),
            "card_sections": (
                encode_json(node_input.get("card_sections")) if node_input.get("card_sections") is not None else None
            )
            if existing_row is None
            else (
                encode_json(node_input["card_sections"]) if "card_sections" in node_input and node_input["card_sections"] is not None else (None if "card_sections" in node_input else existing_row[4])
            ),
            "editable_fields": (
                encode_json(node_input.get("editable_fields")) if node_input.get("editable_fields") is not None else None
            )
            if existing_row is None
            else (
                encode_json(node_input["editable_fields"]) if "editable_fields" in node_input and node_input["editable_fields"] is not None else (None if "editable_fields" in node_input else existing_row[5])
            ),
            "evidence_ids": (
                encode_json(node_input.get("evidence_ids")) if node_input.get("evidence_ids") is not None else None
            )
            if existing_row is None
            else (
                encode_json(node_input["evidence_ids"]) if "evidence_ids" in node_input and node_input["evidence_ids"] is not None else (None if "evidence_ids" in node_input else existing_row[6])
            ),
            "layout_hint": (
                encode_json(node_input.get("layout_hint")) if node_input.get("layout_hint") is not None else None
            )
            if existing_row is None
            else (
                encode_json(node_input["layout_hint"]) if "layout_hint" in node_input and node_input["layout_hint"] is not None else (None if "layout_hint" in node_input else existing_row[7])
            ),
            "parent_id": node_input.get("parent_id") if existing_row is None else node_input.get("parent_id", existing_row[8]),
            "depth": int(node_input.get("depth", 0)) if existing_row is None else int(node_input.get("depth", existing_row[9])),
            "created_at": now if existing_row is None else existing_row[10],
        }

        self.conn.execute(
            """
            INSERT INTO nodes(
                graph_id, id, label, type, supertype, details, card_sections,
                editable_fields, evidence_ids, layout_hint, parent_id, depth,
                created_at, modified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(graph_id, id) DO UPDATE SET
                label=COALESCE(excluded.label, nodes.label),
                type=COALESCE(excluded.type, nodes.type),
                supertype=COALESCE(excluded.supertype, nodes.supertype),
                details=COALESCE(excluded.details, nodes.details),
                card_sections=COALESCE(excluded.card_sections, nodes.card_sections),
                editable_fields=COALESCE(excluded.editable_fields, nodes.editable_fields),
                evidence_ids=COALESCE(excluded.evidence_ids, nodes.evidence_ids),
                layout_hint=COALESCE(excluded.layout_hint, nodes.layout_hint),
                parent_id=COALESCE(excluded.parent_id, nodes.parent_id),
                depth=COALESCE(excluded.depth, nodes.depth),
                modified_at=excluded.modified_at
            """,
            (
                graph_id,
                node_input["id"],
                payload["label"],
                payload["type"],
                payload["supertype"],
                payload["details"],
                payload["card_sections"],
                payload["editable_fields"],
                payload["evidence_ids"],
                payload["layout_hint"],
                payload["parent_id"],
                payload["depth"],
                payload["created_at"],
                now,
            ),
        )
        # Keep FTS index in sync after upsert
        _fts_upsert(
            self.conn,
            graph_id,
            node_input["id"],
            cast(str, payload["label"] or ""),
            cast(str | None, payload["details"]),
            cast(str | None, payload["card_sections"]),
        )
        self.conn.commit()

    def delete_nodes(self, graph_id: str) -> None:
        self.conn.execute("DELETE FROM nodes WHERE graph_id = ?", (graph_id,))
        try:
            self.conn.execute("DELETE FROM nodes_fts WHERE graph_id = ?", (graph_id,))
        except Exception:
            pass
        self.conn.commit()

    def delete_node(self, graph_id: str, node_id: str) -> int:
        cur = self.conn.execute(
            "DELETE FROM nodes WHERE graph_id = ? AND id = ?",
            (graph_id, node_id),
        )
        _fts_delete(self.conn, graph_id, node_id)
        self.conn.commit()
        return int(cur.rowcount or 0)

    def _validate_parent_ids(self, graph_id: str, nodes: list[dict]) -> None:
        existing_ids = {
            row[0]
            for row in self.conn.execute("SELECT id FROM nodes WHERE graph_id = ?", (graph_id,)).fetchall()
        }
        incoming_ids = {item["id"] for item in nodes}
        valid_ids = existing_ids | incoming_ids
        for item in nodes:
            parent_id = item.get("parent_id")
            if parent_id is None:
                continue
            if parent_id not in valid_ids:
                raise ValueError(f"Node '{item['id']}' references missing parent '{parent_id}'")


class EdgeRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save_edges(self, graph_id: str, edges: list[dict]) -> None:
        counters: dict[tuple[str, str], int] = {}
        for edge in edges:
            source = edge["source"]
            target = edge["target"]
            key = (source, target)
            counters[key] = counters.get(key, 0) + 1
            edge_id = edge.get("edge_id") or f"{source}->{target}#{counters[key]}"
            self.conn.execute(
                """
                INSERT INTO edges(
                    graph_id, edge_id, source, target, label, weight, reasons, evidence_ids, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(graph_id, edge_id) DO UPDATE SET
                    source=excluded.source,
                    target=excluded.target,
                    label=excluded.label,
                    weight=excluded.weight,
                    reasons=excluded.reasons,
                    evidence_ids=excluded.evidence_ids
                """,
                (
                    graph_id,
                    edge_id,
                    source,
                    target,
                    str(edge["label"]),
                    edge.get("weight"),
                    encode_json(edge.get("reasons")) if edge.get("reasons") is not None else None,
                    encode_json(edge.get("evidence_ids")) if edge.get("evidence_ids") is not None else None,
                    _utc_now(),
                ),
            )
        self.conn.commit()

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
        sql = """
            SELECT graph_id, edge_id, source, target, label, weight, reasons, evidence_ids, created_at
              FROM edges
             WHERE graph_id = ?
        """
        params: list[object] = [graph_id]
        if source is not None:
            sql += " AND source = ?"
            params.append(source)
        if target is not None:
            sql += " AND target = ?"
            params.append(target)
        if labels:
            placeholders = ", ".join("?" for _ in labels)
            sql += f" AND label IN ({placeholders})"
            params.extend(labels)
        if min_weight is not None:
            sql += " AND weight >= ?"
            params.append(min_weight)
        if max_weight is not None:
            sql += " AND weight <= ?"
            params.append(max_weight)
        if has_evidence is True:
            sql += " AND evidence_ids IS NOT NULL AND evidence_ids != '[]'"
        elif has_evidence is False:
            sql += " AND (evidence_ids IS NULL OR evidence_ids = '[]')"
        if cursor is not None:
            last_label, last_edge_id = cursor
            sql += " AND (label > ? OR (label = ? AND edge_id > ?))"
            params.extend([last_label, last_label, last_edge_id])
        if order_by == "label_edge_id":
            sql += " ORDER BY label ASC, edge_id ASC"
        else:
            sql += " ORDER BY edge_id ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(max(int(limit), 0))
        rows = self.conn.execute(sql, params).fetchall()
        return [
            EdgeRow(
                graph_id=row[0],
                edge_id=row[1],
                source=row[2],
                target=row[3],
                label=row[4],
                weight=row[5],
                reasons=decode_json(row[6]),
                evidence_ids=decode_json(row[7]),
                created_at=row[8],
            )
            for row in rows
        ]

    def upsert_edge(self, graph_id: str, edge_input: dict) -> None:
        edge_id = edge_input.get("edge_id")
        if edge_id is None:
            source = edge_input["source"]
            target = edge_input["target"]
            count = self.conn.execute(
                "SELECT COUNT(*) FROM edges WHERE graph_id = ? AND source = ? AND target = ?",
                (graph_id, source, target),
            ).fetchone()[0]
            edge_id = f"{source}->{target}#{count + 1}"

        existing = self.conn.execute(
            """
            SELECT source, target, label, weight, reasons, evidence_ids
              FROM edges
             WHERE graph_id = ? AND edge_id = ?
            """,
            (graph_id, edge_id),
        ).fetchone()

        source = edge_input.get("source") if existing is None else edge_input.get("source", existing[0])
        target = edge_input.get("target") if existing is None else edge_input.get("target", existing[1])
        label = edge_input.get("label") if existing is None else edge_input.get("label", existing[2])
        weight = edge_input.get("weight") if existing is None else edge_input.get("weight", existing[3])
        reasons = (
            encode_json(edge_input.get("reasons")) if edge_input.get("reasons") is not None else None
        ) if existing is None else (
            encode_json(edge_input["reasons"]) if "reasons" in edge_input and edge_input["reasons"] is not None else (None if "reasons" in edge_input else existing[4])
        )
        evidence_ids = (
            encode_json(edge_input.get("evidence_ids")) if edge_input.get("evidence_ids") is not None else None
        ) if existing is None else (
            encode_json(edge_input["evidence_ids"]) if "evidence_ids" in edge_input and edge_input["evidence_ids"] is not None else (None if "evidence_ids" in edge_input else existing[5])
        )

        self.conn.execute(
            """
            INSERT INTO edges(
                graph_id, edge_id, source, target, label, weight, reasons, evidence_ids, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(graph_id, edge_id) DO UPDATE SET
                source=COALESCE(excluded.source, edges.source),
                target=COALESCE(excluded.target, edges.target),
                label=COALESCE(excluded.label, edges.label),
                weight=COALESCE(excluded.weight, edges.weight),
                reasons=COALESCE(excluded.reasons, edges.reasons),
                evidence_ids=COALESCE(excluded.evidence_ids, edges.evidence_ids)
            """,
            (graph_id, edge_id, source, target, label, weight, reasons, evidence_ids, _utc_now()),
        )
        self.conn.commit()

    def delete_edge(self, graph_id: str, source: str, target: str) -> int:
        cur = self.conn.execute(
            "DELETE FROM edges WHERE graph_id = ? AND source = ? AND target = ?",
            (graph_id, source, target),
        )
        self.conn.commit()
        return int(cur.rowcount or 0)


class AuditRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def log_audit(
        self,
        tool_name: str,
        tool_input: dict,
        result_status: str,
        *,
        caller_id: str | None = None,
    ) -> None:
        if result_status not in {"ok", "error"}:
            raise ValueError("result_status must be 'ok' or 'error'")
        input_hash = hashlib.sha256(json.dumps(tool_input, sort_keys=True).encode()).hexdigest()
        self.conn.execute(
            """
            INSERT INTO tools_audit(timestamp, tool_name, input_hash, result_status, caller_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (_utc_now(), tool_name, input_hash, result_status, caller_id),
        )
        self.conn.commit()


class OutboxRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def enqueue_event(self, event: str, graph_id: str, payload: dict) -> None:
        self.conn.execute(
            """
            INSERT INTO event_outbox(event, graph_id, payload, created_at, published)
            VALUES (?, ?, ?, ?, 0)
            """,
            (event, graph_id, encode_json(payload), _utc_now()),
        )
        self.conn.commit()

    def get_unpublished_events(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT id, event, graph_id, payload, created_at, published
              FROM event_outbox
             WHERE published = 0
          ORDER BY id ASC
             LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "id": row[0],
                "event": row[1],
                "graph_id": row[2],
                "payload": row[3],
                "created_at": row[4],
                "published": row[5],
            }
            for row in rows
        ]

    def mark_published(self, event_ids: list[int]) -> None:
        if not event_ids:
            return
        placeholders = ", ".join("?" for _ in event_ids)
        self.conn.execute(
            f"UPDATE event_outbox SET published = 1 WHERE id IN ({placeholders})",
            event_ids,
        )
        self.conn.commit()

    def purge_published_events(self) -> None:
        self.conn.execute("DELETE FROM event_outbox WHERE published = 1")
        self.conn.commit()


class EvidenceRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save_evidence(self, graph_id: str, evidence: list[dict]) -> None:
        for item in evidence:
            self.conn.execute(
                """
                INSERT INTO evidence(graph_id, id, type, source, content, provenance, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(graph_id, id) DO UPDATE SET
                    type=excluded.type,
                    source=excluded.source,
                    content=excluded.content,
                    provenance=excluded.provenance,
                    timestamp=excluded.timestamp
                """,
                (
                    graph_id,
                    item["id"],
                    item["type"],
                    item["source"],
                    item["content"],
                    encode_json(item.get("provenance")) if item.get("provenance") is not None else None,
                    item.get("timestamp"),
                ),
            )
        self.conn.commit()

    def search_evidence(
        self,
        graph_id: str,
        *,
        content_substr: str | None = None,
    ) -> list[EvidenceRow]:
        sql = """
            SELECT graph_id, id, type, source, content, provenance, timestamp
              FROM evidence
             WHERE graph_id = ?
        """
        params: list[object] = [graph_id]
        if content_substr:
            sql += " AND content LIKE ?"
            params.append(f"%{content_substr}%")
        sql += " ORDER BY id ASC"
        rows = self.conn.execute(sql, params).fetchall()
        return [
            EvidenceRow(
                graph_id=row[0],
                id=row[1],
                type=row[2],
                source=row[3],
                content=row[4],
                provenance=decode_json(row[5]),
                timestamp=row[6],
            )
            for row in rows
        ]


class ClusterRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save_clusters(self, graph_id: str, clusters: list[dict]) -> None:
        self._validate_parent_ids(graph_id, clusters)
        for cluster in clusters:
            self.conn.execute(
                """
                INSERT INTO clusters(graph_id, id, name, description, parent_id, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(graph_id, id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    parent_id=excluded.parent_id,
                    metadata=excluded.metadata
                """,
                (
                    graph_id,
                    cluster["id"],
                    cluster["name"],
                    cluster.get("description"),
                    cluster.get("parent_id"),
                    encode_json(cluster.get("metadata")) if cluster.get("metadata") is not None else None,
                    _utc_now(),
                ),
            )
        self.conn.commit()

    def save_members(self, graph_id: str, members: list[dict]) -> None:
        for member in members:
            self.conn.execute(
                """
                INSERT INTO cluster_members(graph_id, cluster_id, node_id, weight)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(graph_id, cluster_id, node_id) DO UPDATE SET
                    weight=excluded.weight
                """,
                (graph_id, member["cluster_id"], member["node_id"], member.get("weight")),
            )
        self.conn.commit()

    def update_cluster_lifecycle(
        self,
        graph_id: str,
        cluster_id: str,
        status: str,
        *,
        reason: str | None = None,
    ) -> None:
        if status not in ClusterMetadataV1.VALID_STATUSES:
            raise ValueError(f"Unsupported cluster status: {status}")
        row = self.conn.execute(
            "SELECT metadata FROM clusters WHERE graph_id = ? AND id = ?",
            (graph_id, cluster_id),
        ).fetchone()
        if row is None:
            raise ValueError(f"Cluster {cluster_id!r} not found")
        metadata = decode_json(row[0]) or {}
        metadata["status"] = status
        if status == "archived" and reason is not None:
            metadata["archived_reason"] = reason
        self.conn.execute(
            "UPDATE clusters SET metadata = ? WHERE graph_id = ? AND id = ?",
            (encode_json(metadata), graph_id, cluster_id),
        )
        self.conn.commit()

    def query_clusters(self, graph_id: str) -> list[ClusterRow]:
        rows = self.conn.execute(
            """
            SELECT graph_id, id, name, description, parent_id, metadata, created_at
              FROM clusters
             WHERE graph_id = ?
          ORDER BY id ASC
            """,
            (graph_id,),
        ).fetchall()
        return [
            ClusterRow(
                graph_id=row[0],
                id=row[1],
                name=row[2],
                description=row[3],
                parent_id=row[4],
                metadata=decode_json(row[5]),
                created_at=row[6],
            )
            for row in rows
        ]

    def list_members(self, graph_id: str, *, cluster_id: str | None = None) -> list[ClusterMemberRow]:
        sql = """
            SELECT graph_id, cluster_id, node_id, weight
              FROM cluster_members
             WHERE graph_id = ?
        """
        params: list[object] = [graph_id]
        if cluster_id is not None:
            sql += " AND cluster_id = ?"
            params.append(cluster_id)
        sql += " ORDER BY cluster_id ASC, node_id ASC"
        rows = self.conn.execute(sql, params).fetchall()
        return [ClusterMemberRow(*row) for row in rows]

    def _validate_parent_ids(self, graph_id: str, clusters: list[dict]) -> None:
        existing_ids = {
            row[0]
            for row in self.conn.execute("SELECT id FROM clusters WHERE graph_id = ?", (graph_id,)).fetchall()
        }
        incoming_ids = {item["id"] for item in clusters}
        valid_ids = existing_ids | incoming_ids
        for item in clusters:
            parent_id = item.get("parent_id")
            if parent_id is None:
                continue
            if parent_id not in valid_ids:
                raise ValueError(
                    f"Cluster '{item['id']}' references missing parent '{parent_id}'"
                )


class EmbeddingRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert_embedding(
        self,
        graph_id: str,
        target_type: str,
        target_id: str,
        model: str,
        vector: list[float],
    ) -> None:
        dimensions = len(vector)
        existing = self.conn.execute(
            "SELECT dimensions FROM embeddings WHERE graph_id = ? AND model = ? LIMIT 1",
            (graph_id, model),
        ).fetchone()
        if existing is not None and int(existing[0]) != dimensions:
            raise CorruptVectorError(
                f"Vector dimension mismatch for graph '{graph_id}' model '{model}': "
                f"expected {existing[0]}, got {dimensions}"
            )

        self.conn.execute(
            """
            INSERT INTO embeddings(graph_id, target_type, target_id, model, dimensions, vector, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(graph_id, target_type, target_id, model) DO UPDATE SET
                dimensions=excluded.dimensions,
                vector=excluded.vector
            """,
            (
                graph_id,
                target_type,
                target_id,
                model,
                dimensions,
                encode_vector(vector),
                _utc_now(),
            ),
        )
        self.conn.commit()

    def has_embedding(
        self,
        graph_id: str,
        target_type: str,
        target_id: str,
        model: str,
    ) -> bool:
        """Return True when an embedding row exists for this (graph, type, target, model)."""
        row = self.conn.execute(
            """
            SELECT 1 FROM embeddings
             WHERE graph_id = ? AND target_type = ? AND target_id = ? AND model = ?
             LIMIT 1
            """,
            (graph_id, target_type, target_id, model),
        ).fetchone()
        return row is not None

    def nearest_embeddings(
        self,
        graph_id: str,
        target_id: str,
        *,
        k: int = 10,
        model: str | None = None,
    ) -> list[NearestHit]:
        target_row = self._load_target(graph_id=graph_id, target_id=target_id, model=model)
        if target_row is None:
            raise CorruptVectorError(
                f"Target embedding not found for graph '{graph_id}', target '{target_id}'"
            )

        query = decode_vector(target_row.vector, dimensions=target_row.dimensions)
        query_norm = sqrt(fsum(value * value for value in query))
        if query_norm == 0.0:
            raise CorruptVectorError(f"Target embedding '{target_id}' has zero norm")

        candidates = self._load_candidates(
            graph_id=graph_id,
            model=target_row.model,
            dimensions=target_row.dimensions,
            target_id=target_id,
        )
        return _rank_cosine_hits(query, candidates, k=k)

    def nearest_to_vector(
        self,
        graph_id: str,
        vector: list[float],
        *,
        k: int = 10,
    ) -> list[NearestHit]:
        dimensions = len(vector)
        query_norm = sqrt(fsum(value * value for value in vector))
        if query_norm == 0.0:
            raise CorruptVectorError("Query vector has zero norm")

        rows = self.conn.execute(
            """
            SELECT id, graph_id, target_type, target_id, model, dimensions, vector, created_at
              FROM embeddings
             WHERE graph_id = ?
               AND dimensions = ?
             ORDER BY id ASC
            """,
            (graph_id, dimensions),
        ).fetchall()
        if not rows:
            return []

        candidates = [EmbeddingRow(*row) for row in rows]
        return _rank_cosine_hits(vector, candidates, k=k)

    def _load_target(self, *, graph_id: str, target_id: str, model: str | None) -> EmbeddingRow | None:
        sql = """
            SELECT id, graph_id, target_type, target_id, model, dimensions, vector, created_at
              FROM embeddings
             WHERE graph_id = ? AND target_id = ?
        """
        params: list[object] = [graph_id, target_id]
        if model is not None:
            sql += " AND model = ?"
            params.append(model)
        sql += " ORDER BY id ASC LIMIT 1"
        row = self.conn.execute(sql, params).fetchone()
        return EmbeddingRow(*row) if row is not None else None

    def _load_candidates(
        self,
        *,
        graph_id: str,
        model: str,
        dimensions: int,
        target_id: str,
    ) -> list[EmbeddingRow]:
        rows = self.conn.execute(
            """
            SELECT id, graph_id, target_type, target_id, model, dimensions, vector, created_at
              FROM embeddings
             WHERE graph_id = ?
               AND model = ?
               AND dimensions = ?
               AND target_id != ?
             ORDER BY id ASC
            """,
            (graph_id, model, dimensions, target_id),
        ).fetchall()
        return [EmbeddingRow(*row) for row in rows]


class PendingQuestionRepository:
    """Repository for deferred currency-elicitation questions.

    Pending questions are not ledger facts. They use their own table so inserts
    and resolutions cannot affect confidence_ledger currency evidence.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def insert(
        self,
        graph_id: str,
        *,
        target_node_id: str | None,
        gap_kind: str,
        entity_type: str | None,
        question_text: str,
        stakeholder_owner: str | None,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO pending_questions(
                graph_id, target_node_id, gap_kind, entity_type, question_text,
                stakeholder_owner, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                graph_id,
                target_node_id,
                gap_kind,
                entity_type,
                question_text,
                stakeholder_owner,
                _utc_now(),
            ),
        )
        self.conn.commit()

        return cursor.lastrowid  # type: ignore[return-value]

    def list(self, graph_id: str, *, status: str = "pending") -> list[PendingQuestionRow]:
        rows = self.conn.execute(
            """
            SELECT id, graph_id, target_node_id, gap_kind, entity_type,
                   question_text, stakeholder_owner, status, created_at,
                   resolved_at, resolved_by
              FROM pending_questions
             WHERE graph_id = ?
               AND status = ?
          ORDER BY id ASC
            """,
            (graph_id, status),
        ).fetchall()
        return [PendingQuestionRow(*row) for row in rows]

    def resolve(self, pending_id: int, *, outcome: str, resolved_by: str) -> PendingQuestionRow:
        resolved_at = _utc_now()
        cursor = self.conn.execute(
            """
            UPDATE pending_questions
               SET status = ?, resolved_at = ?, resolved_by = ?
             WHERE id = ?
            """,
            (outcome, resolved_at, resolved_by, pending_id),
        )
        self.conn.commit()
        if cursor.rowcount == 0:
            raise ValueError(f"Pending question {pending_id!r} not found")

        row = self.conn.execute(
            """
            SELECT id, graph_id, target_node_id, gap_kind, entity_type,
                   question_text, stakeholder_owner, status, created_at,
                   resolved_at, resolved_by
              FROM pending_questions
             WHERE id = ?
            """,
            (pending_id,),
        ).fetchone()
        return PendingQuestionRow(*row)


class LedgerRepository:
    """Append-only repository for the confidence_ledger table.

    Constructed with a sqlite3.Connection that already has PRAGMA foreign_keys=ON
    (set by configure_connection / GraphStore.__init__).  No connection lifecycle
    of its own — the caller owns the connection.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def append(
        self,
        graph_id: str,
        *,
        target_id: str,
        status: str,
        provenance: str,
        captured_at: str,
        target_type: str = "edge",
        initial_confidence: float | None = None,
        current_confidence: float | None = None,
        relationship_label: str | None = None,
        source_node_id: str | None = None,
        target_node_id: str | None = None,
        source_node_type: str | None = None,
        target_node_type: str | None = None,
        evidence_ids: list | None = None,
        captured_by: str | None = None,
        confirmed_at: str | None = None,
        confirmed_by: str | None = None,
        flagged_reason: str | None = None,
        gold_rationale: str | None = None,
        # Node-fact descriptor fields (v7); NULL for edge rows.
        fact_label: str | None = None,
        fact_path: str | None = None,
        fact_value: str | None = None,
        fact_subject_type: str | None = None,
    ) -> int:
        """Insert one row and return its auto-incremented id.

        Pure INSERT — never ON CONFLICT/REPLACE.  JSON-encodes evidence_ids.
        Auto-commits after the insert (own advisory commit, isolated from any
        prior upsert_edge commit).
        """
        cursor = self.conn.execute(
            """
            INSERT INTO confidence_ledger(
                graph_id, target_type, target_id, status,
                initial_confidence, current_confidence,
                relationship_label,
                source_node_id, target_node_id,
                source_node_type, target_node_type,
                evidence_ids, captured_by, captured_at,
                confirmed_at, confirmed_by,
                flagged_reason, gold_rationale,
                provenance,
                fact_label, fact_path, fact_value, fact_subject_type
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?,
                ?,
                ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?,
                ?,
                ?, ?, ?, ?
            )
            """,
            (
                graph_id,
                target_type,
                target_id,
                status,
                initial_confidence,
                current_confidence,
                relationship_label,
                source_node_id,
                target_node_id,
                source_node_type,
                target_node_type,
                encode_json(evidence_ids) if evidence_ids is not None else None,
                captured_by,
                captured_at,
                confirmed_at,
                confirmed_by,
                flagged_reason,
                gold_rationale,
                provenance,
                fact_label,
                fact_path,
                fact_value,
                fact_subject_type,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def query_by_graph(
        self,
        graph_id: str,
        *,
        status: str | None = None,
        target_type: str = "edge",
    ) -> list[LedgerRow]:
        """Return all rows for graph_id, ordered by id ASC.

        Optional status filter.  Includes ALL historical rows (full audit trail).
        """
        sql = """
            SELECT
                id, graph_id, target_type, target_id, status,
                initial_confidence, current_confidence,
                relationship_label,
                source_node_id, target_node_id,
                source_node_type, target_node_type,
                evidence_ids, captured_by, captured_at,
                confirmed_at, confirmed_by,
                flagged_reason, gold_rationale,
                provenance,
                fact_label, fact_path, fact_value, fact_subject_type
              FROM confidence_ledger
             WHERE graph_id = ?
               AND target_type = ?
        """
        params: list[object] = [graph_id, target_type]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY id ASC"
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_model(r) for r in rows]

    def query_latest_per_target(
        self,
        graph_id: str,
        *,
        target_type: str = "edge",
    ) -> list[LedgerRow]:
        """Return the latest (highest id) row per target_id.

        Uses a correlated MAX(id) subquery so the idx_ledger_latest composite
        index (graph_id, target_type, target_id, id) can resolve recency without
        a full-table scan.
        """
        sql = """
            SELECT
                id, graph_id, target_type, target_id, status,
                initial_confidence, current_confidence,
                relationship_label,
                source_node_id, target_node_id,
                source_node_type, target_node_type,
                evidence_ids, captured_by, captured_at,
                confirmed_at, confirmed_by,
                flagged_reason, gold_rationale,
                provenance,
                fact_label, fact_path, fact_value, fact_subject_type
              FROM confidence_ledger
             WHERE id IN (
                 SELECT MAX(id)
                   FROM confidence_ledger
                  WHERE graph_id = ?
                    AND target_type = ?
                  GROUP BY target_id
             )
             ORDER BY id ASC
        """
        rows = self.conn.execute(sql, (graph_id, target_type)).fetchall()
        return [self._row_to_model(r) for r in rows]

    def query_latest_for_targets(
        self,
        graph_id: str,
        target_ids: list[str],
        *,
        target_type: str = "edge",
    ) -> dict[str, LedgerRow]:
        """Return latest ledger rows keyed by target_id for the requested targets.

        Empty input short-circuits without SQL. Missing targets are absent from
        the returned mapping. Large target sets are chunked below SQLite's
        default variable limit while preserving one batched query per chunk.
        """
        deduped_target_ids = list(dict.fromkeys(target_ids))
        if not deduped_target_ids:
            return {}

        latest: dict[str, LedgerRow] = {}
        chunk_size = 900
        for start in range(0, len(deduped_target_ids), chunk_size):
            chunk = deduped_target_ids[start : start + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            sql = f"""
                SELECT
                    id, graph_id, target_type, target_id, status,
                    initial_confidence, current_confidence,
                    relationship_label,
                    source_node_id, target_node_id,
                    source_node_type, target_node_type,
                    evidence_ids, captured_by, captured_at,
                    confirmed_at, confirmed_by,
                    flagged_reason, gold_rationale,
                    provenance,
                    fact_label, fact_path, fact_value, fact_subject_type
                  FROM confidence_ledger
                 WHERE id IN (
                     SELECT MAX(id)
                       FROM confidence_ledger
                      WHERE graph_id = ?
                        AND target_type = ?
                        AND target_id IN ({placeholders})
                      GROUP BY target_id
                 )
                 ORDER BY id ASC
            """
            rows = self.conn.execute(sql, [graph_id, target_type, *chunk]).fetchall()
            for row in rows:
                model = self._row_to_model(row)
                latest[model.target_id] = model
        return latest

    def query_node_currency_evidence(
        self,
        graph_id: str,
        node_ids: list[str],
    ) -> dict[str, dict[str, object]]:
        """Return batched node currency evidence keyed by node id."""
        deduped_node_ids = list(dict.fromkeys(node_ids))
        if not deduped_node_ids:
            return {}

        node_rows = []
        for chunk in _chunks(deduped_node_ids, 900):
            placeholders = ",".join("?" for _ in chunk)
            node_rows.extend(
                self.conn.execute(
                    f"""
                    SELECT id, type, details, created_at, modified_at
                      FROM nodes
                     WHERE graph_id = ?
                       AND id IN ({placeholders})
                     ORDER BY id ASC
                    """,
                    [graph_id, *chunk],
                ).fetchall()
            )
        latest_nodes = self.query_latest_for_targets(
            graph_id,
            deduped_node_ids,
            target_type="node",
        )
        edge_rows_by_id = {}
        for chunk in _chunks(deduped_node_ids, 450):
            placeholders = ",".join("?" for _ in chunk)
            for row in self.conn.execute(
                f"""
                SELECT edge_id, source, target
                  FROM edges
                 WHERE graph_id = ?
                   AND (source IN ({placeholders}) OR target IN ({placeholders}))
                 ORDER BY edge_id ASC
                """,
                [graph_id, *chunk, *chunk],
            ).fetchall():
                edge_rows_by_id[str(row[0])] = row
        edge_rows = sorted(edge_rows_by_id.values(), key=lambda row: str(row[0]))
        latest_edges = self.query_latest_for_targets(
            graph_id,
            [str(row[0]) for row in edge_rows],
            target_type="edge",
        )

        evidence = {
            str(row[0]): {
                "node_id": str(row[0]),
                "entity_type": str(row[1]),
                "schema_baseline_last_documented_at": _schema_baseline_last_documented_at(
                    decode_json(row[2]) or {}
                ),
                "created_at": row[3],
                "modified_at": row[4],
                "edge_evidence": {},
            }
            for row in node_rows
        }
        for node_id, ledger in latest_nodes.items():
            if node_id not in evidence:
                continue
            evidence[node_id].update(
                {
                    "ledger_status": ledger.status,
                    "ledger_captured_at": ledger.captured_at,
                    "ledger_confirmed_at": ledger.confirmed_at,
                }
            )
        for edge_id, source, target in edge_rows:
            edge_ledger = latest_edges.get(str(edge_id))
            payload = {
                "edge_id": str(edge_id),
                "source": str(source),
                "target": str(target),
                "ledger_status": edge_ledger.status if edge_ledger is not None else None,
                "ledger_captured_at": edge_ledger.captured_at if edge_ledger is not None else None,
                "ledger_confirmed_at": edge_ledger.confirmed_at if edge_ledger is not None else None,
            }
            for node_id in (str(source), str(target)):
                if node_id in evidence:
                    cast(dict[str, object], evidence[node_id]["edge_evidence"])[str(edge_id)] = payload
        return evidence

    def query_by_status(
        self,
        graph_id: str,
        statuses: list[str],
        *,
        target_type: str = "edge",
    ) -> list[LedgerRow]:
        """Return latest rows per target_id where the latest status is in statuses."""
        latest = self.query_latest_per_target(graph_id, target_type=target_type)
        return [r for r in latest if r.status in statuses]

    def list_pending_confirmations(self, graph_id: str) -> list[LedgerRow]:
        """Return latest rows across ALL target_types whose latest status is 'needs-confirmation'.

        Ordered by id ASC.  Already-resolved targets are excluded (their latest row
        has a non-pending status so the CTE filters them out).
        """
        sql = """
            WITH latest AS (
                SELECT MAX(id) AS max_id
                  FROM confidence_ledger
                 WHERE graph_id = ?
                 GROUP BY target_type, target_id
            )
            SELECT
                id, graph_id, target_type, target_id, status,
                initial_confidence, current_confidence,
                relationship_label,
                source_node_id, target_node_id,
                source_node_type, target_node_type,
                evidence_ids, captured_by, captured_at,
                confirmed_at, confirmed_by,
                flagged_reason, gold_rationale,
                provenance,
                fact_label, fact_path, fact_value, fact_subject_type
              FROM confidence_ledger
             WHERE id IN (SELECT max_id FROM latest)
               AND status = 'needs-confirmation'
             ORDER BY id ASC
        """
        rows = self.conn.execute(sql, (graph_id,)).fetchall()
        return [self._row_to_model(r) for r in rows]

    _VALID_OUTCOMES = {"confirmed", "invalidated", "abstain"}

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
        """Resolve a pending confirmation by appending a new human verdict row.

        Validates:
        - outcome is one of confirmed/invalidated/abstain (raises ValueError otherwise)
        - latest row for (graph_id, target_type, target_id) exists and has
          status='needs-confirmation' (raises ValueError otherwise)

        Then APPENDS a new row (never UPDATEs).  Returns:
          {"appended_id": int, "previous_id": int, "status": outcome}
        """
        if outcome not in self._VALID_OUTCOMES:
            raise ValueError(
                f"Invalid outcome {outcome!r}. Must be one of: "
                + ", ".join(sorted(self._VALID_OUTCOMES))
            )

        # Load latest row for this (graph_id, target_type, target_id)
        sql = """
            SELECT id, status
              FROM confidence_ledger
             WHERE graph_id = ?
               AND target_type = ?
               AND target_id = ?
             ORDER BY id DESC
             LIMIT 1
        """
        row = self.conn.execute(sql, (graph_id, target_type, target_id)).fetchone()
        if row is None:
            raise ValueError(
                f"No pending confirmation found for "
                f"(graph_id={graph_id!r}, target_type={target_type!r}, target_id={target_id!r})"
            )
        previous_id, latest_status = row[0], row[1]
        if latest_status != "needs-confirmation":
            raise ValueError(
                f"Latest row for target_id={target_id!r} has status={latest_status!r}, "
                f"which is not 'needs-confirmation' — already resolved or not flagged"
            )

        appended_id = self.append(
            graph_id=graph_id,
            target_type=target_type,
            target_id=target_id,
            status=outcome,
            provenance="hand_labeled",
            captured_at=_utc_now(),
            captured_by="human",
            confirmed_by=resolved_by,
            confirmed_at=_utc_now(),
            gold_rationale=gold_rationale,
        )
        return {"appended_id": appended_id, "previous_id": previous_id, "status": outcome}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_model(row: tuple) -> LedgerRow:
        return LedgerRow(
            id=row[0],
            graph_id=row[1],
            target_type=row[2],
            target_id=row[3],
            status=row[4],
            initial_confidence=row[5],
            current_confidence=row[6],
            relationship_label=row[7],
            source_node_id=row[8],
            target_node_id=row[9],
            source_node_type=row[10],
            target_node_type=row[11],
            evidence_ids=decode_json(row[12]),
            captured_by=row[13],
            captured_at=row[14],
            confirmed_at=row[15],
            confirmed_by=row[16],
            flagged_reason=row[17],
            gold_rationale=row[18],
            provenance=row[19],
            fact_label=row[20] if len(row) > 20 else None,
            fact_path=row[21] if len(row) > 21 else None,
            fact_value=row[22] if len(row) > 22 else None,
            fact_subject_type=row[23] if len(row) > 23 else None,
        )
