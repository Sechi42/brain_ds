from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brain_ds.connectors.secrets import SecretCatalog, SecretEntry
from brain_ds.mcp.tools import TOOL_REGISTRY, validate_secret_handle
from brain_ds.store.graph_store import GraphStore

CANARY = "mcp-contract-secret-canary"


def _store(tmp_path: Path) -> GraphStore:
    db_dir = tmp_path / ".brain_ds"
    db_dir.mkdir(parents=True)
    store = GraphStore(str(db_dir / "store.db"))
    store.meta_repo.save_graph_meta(graph_id="g", workspace_root=str(tmp_path), workspace_path=str(tmp_path), project="p", org="o", schema_version="2.0.0", contract_version="1.0.0", node_count=0, edge_count=0, imported_from=None, generated_at="")
    store.upsert_node("g", {"id": "N1", "label": "Contract Source", "type": "Data Source", "supertype": "Technology", "details": {"connection": {"kind": "sqlite", "path": "missing.db"}}})
    store.upsert_node("g", {"id": "N2", "label": "Contract Target", "type": "Process", "supertype": "Business"})
    store.upsert_node("g", {"id": "KPI1", "label": "Contract KPI", "type": "KPI", "supertype": "metric", "details": {"description": "Contract metric"}})
    SecretCatalog(tmp_path).add(SecretEntry(handle="contract_pg", kind="postgres", metadata={"host": "db.local", "port": 5432, "database": "warehouse", "username": "etl", "sslmode": "require", "secret_ref": "BRAINDS_CONTRACT_PWD"}), raw_value=CANARY)
    return store


def _params(name: str, tmp_path: Path) -> dict[str, Any]:
    base = {"graph_id": "g"}
    samples: dict[str, dict[str, Any]] = {
        "list_graphs": {}, "create_graph": {"graph_id": "created", "name": "Created", "project": "p"}, "import_graph": {"file_path": str(tmp_path / "missing.json")},
        "list_nodes": base, "list_data_sources": base, "get_node": {**base, "node_id": "N1"}, "get_kpi_dossier": {**base, "kpi_node_id": "KPI1"}, "get_business_dossier": {**base, "query": "contract"}, "search_graph": {**base, "query": "contract"},
        "update_node": {**base, "node_id": "N2", "label": "Updated"}, "add_edge": {**base, "source": "N1", "target": "N2", "label": "feeds"},
        "delete_node": {**base, "node_id": "missing"}, "delete_edge": {**base, "source": "N1", "target": "N2"}, "suggest_connections": {**base, "node_id": "N1"},
        "assess_completeness": base, "get_weak_edges": base, "snapshot_edges": base, "list_workspaces": {}, "open_workspace": {"path": str(tmp_path)},
        "run_elicit": {}, "map_connections": {}, "generate_brd": {}, "list_source_connections": base, "explore_source": {**base, "node_id": "N1"},
        "query_source": {**base, "node_id": "N1", "sql": "SELECT 1", "limit": 1}, "list_secret_handles": {"agent_scope": "workspace_admin"},
        "validate_secret_handle": {"handle": "contract_pg", "agent_scope": "workspace_admin"},
        "list_pending_confirmations": base,
        "resolve_confirmation": {**base, "target_type": "node", "target_id": "N1", "outcome": "confirmed", "resolved_by": "alice", "gold_rationale": "test"},
        "retrieve_context": {**base, "focal_node_id": "N1"},
        "assess_currency": base,
        "insert_pending_question": {**base, "target_node_id": "N2", "gap_kind": "staleness", "entity_type": "Process", "question_text": "Is this process current?", "stakeholder_owner": "owner"},
        "manage_clusters": {**base, "action": "propose", "payload": {"cluster_id": "c-contract", "name": "Contract cluster", "primary_anchor_id": "N2", "primary_anchor_type": "KPI", "member_node_ids": ["N2"], "kpi": {"description": "Contract metric", "formula": "x / y", "owner": "owner", "department": "ops", "source": "N1"}}},
    }
    return samples[name]


def test_tool_registry_handlers_return_structured_contracts_without_secret_leak(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        observed = {name: spec["handler"](store, _params(name, tmp_path)) for name, spec in TOOL_REGISTRY.items()}
        assert set(observed) == set(TOOL_REGISTRY)
        for name, result in observed.items():
            assert result is not None, name
            if isinstance(result, dict) and "code" in result:
                assert isinstance(result["message"], str) and result["message"], name
        assert "connection_rules" in observed["map_connections"]
        assert "artifact_contract" in observed["generate_brd"]
        assert "artifact_contract" in observed["run_elicit"] or "code" in observed["run_elicit"]
        assert CANARY not in json.dumps(observed, default=str)
    finally:
        store.close()


def test_secret_validation_not_found_does_not_echo_unregistered_handle(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.secret_admin_enabled = True
        missing_handle = "aws-user-provided-unregistered-handle"
        result = validate_secret_handle(store, {"handle": missing_handle, "agent_scope": "workspace_admin", "probe": True})
        assert result == {"valid": False, "status": "not_found", "reason": "Secret handle is not registered in this workspace."}
        assert missing_handle not in json.dumps(result)
    finally:
        store.close()


def test_source_connection_tool_description_uses_binding_candidate_contract() -> None:
    description = TOOL_REGISTRY["list_source_connections"]["description"]

    assert "binding candidates" in description
    assert "redacted source connection status" in description
    assert "connection descriptors" not in description


def test_source_connection_action_contract_has_no_helper_tools() -> None:
    action_schema = TOOL_REGISTRY["list_source_connections"]["schema"]["properties"]["action"]

    assert action_schema == {"type": "string"}
    assert "list_source_connections" in TOOL_REGISTRY
    assert "bind_source_connection" not in TOOL_REGISTRY
    assert "validate_source_connection" not in TOOL_REGISTRY
    assert "status_source_connection" not in TOOL_REGISTRY
    assert "unbind_source_connection" not in TOOL_REGISTRY
