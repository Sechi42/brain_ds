from __future__ import annotations

import dataclasses
import inspect
import unittest


class DossierModelTests(unittest.TestCase):
    def test_dossier_dtos_are_importable(self) -> None:
        from brain_ds.dossier.models import (
            ActorFacet,
            DataContainerFacet,
            DataSourceFacet,
            DossierGapInputs,
            DossierGraphView,
            KpiDossier,
            LimitationsFacet,
            ProcessFacet,
        )

        self.assertEqual(DossierGraphView.__name__, "DossierGraphView")
        self.assertEqual(DossierGapInputs.__name__, "DossierGapInputs")
        self.assertEqual(KpiDossier.__name__, "KpiDossier")
        self.assertEqual(DataSourceFacet.__name__, "DataSourceFacet")
        self.assertEqual(DataContainerFacet.__name__, "DataContainerFacet")
        self.assertEqual(ActorFacet.__name__, "ActorFacet")
        self.assertEqual(ProcessFacet.__name__, "ProcessFacet")
        self.assertEqual(LimitationsFacet.__name__, "LimitationsFacet")

    def test_dossier_dtos_are_frozen_and_slotted_dataclasses(self) -> None:
        from brain_ds.dossier.models import (
            ActorFacet,
            DataContainerFacet,
            DataSourceFacet,
            DossierGapInputs,
            DossierGraphView,
            KpiDossier,
            LimitationsFacet,
            ProcessFacet,
        )

        for dto in (
            DossierGraphView,
            DossierGapInputs,
            KpiDossier,
            DataSourceFacet,
            DataContainerFacet,
            ActorFacet,
            ProcessFacet,
            LimitationsFacet,
        ):
            with self.subTest(dto=dto.__name__):
                self.assertTrue(dataclasses.is_dataclass(dto))
                self.assertTrue(dto.__dataclass_params__.frozen)
                self.assertIn("__slots__", dto.__dict__)

    def test_models_have_no_io_adapter_imports(self) -> None:
        import brain_ds.dossier.models as models

        source = inspect.getsource(models)
        self.assertNotIn("brain_ds.mcp", source)
        self.assertNotIn("brain_ds.store", source)
        self.assertNotIn("brain_ds.ui", source)

    def test_dto_field_contract_matches_design(self) -> None:
        from brain_ds.dossier.models import (
            ActorFacet,
            DataContainerFacet,
            DataSourceFacet,
            DossierGapInputs,
            DossierGraphView,
            KpiDossier,
            LimitationsFacet,
            ProcessFacet,
        )

        expected_fields = {
            DossierGraphView: ["nodes_by_id", "adjacency", "children_by_parent", "edges", "ledger_status_by_target"],
            DossierGapInputs: ["completeness", "currency", "weak_edges", "unconfirmed_lineage"],
            KpiDossier: ["kpi", "data_sources", "actors", "processes", "limitations", "summary"],
            DataSourceFacet: ["node", "containers", "lineage_source"],
            DataContainerFacet: ["node", "fields", "lineage_source"],
            ActorFacet: ["node"],
            ProcessFacet: ["node"],
            LimitationsFacet: [
                "unmapped_sources",
                "unconfirmed_lineage",
                "missing_ownership",
                "missing_process",
                "completeness",
                "currency",
                "weak_edges",
                "truncated",
                "truncation_reason",
            ],
        }

        for dto, fields in expected_fields.items():
            with self.subTest(dto=dto.__name__):
                self.assertEqual([field.name for field in dataclasses.fields(dto)], fields)


if __name__ == "__main__":
    unittest.main()
