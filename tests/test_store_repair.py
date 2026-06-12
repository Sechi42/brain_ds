"""Tests for mojibake repair over stored graph text."""

import sqlite3

from brain_ds.store.graph_store import GraphStore
from brain_ds.store.repair import looks_mojibake, repair_store, repair_text


def test_repair_text_fixes_single_pass_mojibake():
    assert repair_text("actualizaciÃ³n") == "actualización"
    assert repair_text("seÃ±al de gestiÃ³n") == "señal de gestión"


def test_repair_text_fixes_double_encoded_mojibake():
    double = "actualización".encode("utf-8").decode("cp1252").encode("utf-8").decode("cp1252")
    assert repair_text(double) == "actualización"


def test_repair_text_leaves_clean_text_untouched():
    assert repair_text("actualización") == "actualización"
    assert repair_text("plain ascii") == "plain ascii"
    assert not looks_mojibake("actualización")


def test_repair_store_fixes_node_cells_and_creates_backup(tmp_path):
    db_path = tmp_path / ".brain_ds" / "store.db"
    db_path.parent.mkdir(parents=True)
    store = GraphStore(str(db_path))
    store.create_graph("g1", name="demo", project="demo", workspace_root=str(tmp_path))
    store.upsert_node(
        "g1",
        {
            "id": "ds-ventas",
            "label": "ActualizaciÃ³n de ventas",
            "type": "Data Source",
            "details": {"summary": "informaciÃ³n de gestiÃ³n"},
        },
    )
    store.close()

    report = repair_store(db_path)

    assert report.cells_repaired >= 2
    assert report.backup_path is not None

    conn = sqlite3.connect(str(db_path))
    label, details = conn.execute(
        "SELECT label, details FROM nodes WHERE id = 'ds-ventas'"
    ).fetchone()
    conn.close()
    assert label == "Actualización de ventas"
    assert "información de gestión" in details


def test_repair_store_dry_run_writes_nothing(tmp_path):
    db_path = tmp_path / ".brain_ds" / "store.db"
    db_path.parent.mkdir(parents=True)
    store = GraphStore(str(db_path))
    store.create_graph("g1", name="demo", project="demo", workspace_root=str(tmp_path))
    store.upsert_node("g1", {"id": "n1", "label": "gestiÃ³n", "type": "KPI"})
    store.close()

    report = repair_store(db_path, dry_run=True)

    assert report.cells_repaired == 1
    assert report.backup_path is None
    conn = sqlite3.connect(str(db_path))
    (label,) = conn.execute("SELECT label FROM nodes WHERE id = 'n1'").fetchone()
    conn.close()
    assert label == "gestiÃ³n"
