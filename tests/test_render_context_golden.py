import json
import unittest
from pathlib import Path

from brain_ds.ontology import Graph
from brain_ds.ui.render_context import WorkspaceContext, build_render_context
from brain_ds.ui.workspace_storage_contract import (
    LOCKED_UTC_SECONDS_PATTERN,
    TAB_MODEL_FIELDS,
)


UPDATE_GOLDEN = False
SUPERTYPES = ("actor", "data", "process", "problem", "risk", "metric", "solution")


def _fixture_root() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


def _load_graph_payload(supertype: str) -> dict:
    fixture_path = _fixture_root() / "graph_inputs" / f"{supertype}.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def _build_context_for(supertype: str) -> dict:
    graph_input_path = _fixture_root() / "graph_inputs" / f"{supertype}.json"
    workspace = WorkspaceContext.from_root_and_graph(
        (_fixture_root() / "graph_inputs").resolve(),
        graph_input_path.resolve(),
    )
    return build_render_context(Graph.from_v1(_load_graph_payload(supertype)), workspace=workspace)


def _golden_path(supertype: str) -> Path:
    return _fixture_root() / "render_context" / f"{supertype}.json"


def _assert_against_golden(testcase: unittest.TestCase, supertype: str) -> None:
    context = _build_context_for(supertype)
    golden_path = _golden_path(supertype)

    if UPDATE_GOLDEN:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(json.dumps(context, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    testcase.assertEqual(context, expected)


class TestRenderContextGolden(unittest.TestCase):
    def test_golden_fixture_actor(self):
        _assert_against_golden(self, "actor")

    def test_golden_fixture_data(self):
        _assert_against_golden(self, "data")

    def test_golden_fixture_process(self):
        _assert_against_golden(self, "process")

    def test_golden_fixture_problem(self):
        _assert_against_golden(self, "problem")

    def test_golden_fixture_risk(self):
        _assert_against_golden(self, "risk")

    def test_golden_fixture_metric(self):
        _assert_against_golden(self, "metric")

    def test_golden_fixture_solution(self):
        _assert_against_golden(self, "solution")

    def test_tab_model_schema_fields_documented(self):
        self.assertEqual(
            TAB_MODEL_FIELDS,
            ("id", "label", "graphPath", "active", "closeable", "openedAt"),
        )

    def test_tab_model_opened_at_regex_is_locked_to_utc_seconds(self):
        self.assertEqual(
            LOCKED_UTC_SECONDS_PATTERN,
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        )


if __name__ == "__main__":
    unittest.main()
