from __future__ import annotations

from types import SimpleNamespace
import unittest

from brain_ds.dossier.models import (
    ActorFacet,
    DataContainerFacet,
    DataSourceFacet,
    KpiDossier,
    LimitationsFacet,
    ProcessFacet,
)


def node(node_id: str, label: str, node_type: str, details: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(id=node_id, label=label, type=node_type, details=details or {"description": f"{label} business meaning"})


class DossierSerializationTests(unittest.TestCase):
    def test_serialized_dossier_shape_always_includes_top_level_keys(self) -> None:
        from brain_ds.dossier.serialization import serialize_dossier

        payload = serialize_dossier(KpiDossier(kpi=node("kpi", "On-time Delivery", "KPI")))

        self.assertEqual(list(payload), ["kpi", "data_sources", "actors", "processes", "limitations", "serialized_for_llm"])
        self.assertEqual(payload["data_sources"], [])
        self.assertEqual(payload["actors"], [])
        self.assertEqual(payload["processes"], [])
        self.assertEqual(payload["limitations"]["unmapped_sources"], [])
        self.assertIs(payload["limitations"]["truncated"], False)

    def test_summary_names_kpi_support_and_limitations(self) -> None:
        from brain_ds.dossier.serialization import build_summary, serialize_dossier

        dossier = KpiDossier(
            kpi=node("kpi", "Churn", "KPI"),
            data_sources=[
                DataSourceFacet(
                    node=node("ds", "CRM", "DataSource"),
                    containers=[DataContainerFacet(node=node("dc", "customers", "DataContainer"), fields=[node("field", "cancelled_at", "DataField")])],
                )
            ],
            actors=[ActorFacet(node=node("role", "Retention Manager", "Role"))],
            processes=[ProcessFacet(node=node("heur", "Cancellation Rule", "Heuristic"))],
            limitations=LimitationsFacet(unmapped_sources=[{"description": "No finance source mapped"}]),
        )

        summary = build_summary(dossier)
        self.assertIn("Churn", summary)
        self.assertIn("CRM", summary)
        self.assertIn("customers", summary)
        self.assertIn("cancelled_at", summary)
        self.assertIn("Retention Manager", summary)
        self.assertIn("Cancellation Rule", summary)
        self.assertIn("No finance source mapped", summary)
        self.assertEqual(serialize_dossier(dossier)["serialized_for_llm"], summary)

    def test_descriptions_use_semantic_description_not_raw_sql(self) -> None:
        from brain_ds.dossier.serialization import serialize_dossier

        dossier = KpiDossier(
            kpi=node("kpi", "Revenue", "KPI"),
            data_sources=[
                DataSourceFacet(
                    node=node("ds", "Warehouse", "DataSource"),
                    containers=[
                        DataContainerFacet(
                            node=node("dc", "orders", "DataContainer", {"description": "Customer order facts", "ddl": "CREATE TABLE orders"}),
                            fields=[node("field", "net_amount", "DataField", {"description": "Net order value", "ddl": "DECIMAL(18,2)"})],
                        )
                    ],
                )
            ],
        )

        source = serialize_dossier(dossier)["data_sources"][0]
        self.assertEqual(source["containers"][0]["description"], "Customer order facts")
        self.assertEqual(source["containers"][0]["fields"][0]["description"], "Net order value")
        self.assertNotIn("CREATE TABLE", str(source))

    def test_oversized_dossier_is_truncated_deterministically_under_cap(self) -> None:
        from brain_ds.dossier.serialization import _MAX_PAYLOAD_BYTES, serialize_dossier

        fields = [node(f"f{i}", f"field_{i}", "DataField", {"description": "x" * 2000}) for i in range(200)]
        dossier = KpiDossier(
            kpi=node("kpi", "Large KPI", "KPI"),
            data_sources=[DataSourceFacet(node=node("ds", "Big Warehouse", "DataSource"), containers=[DataContainerFacet(node=node("dc", "wide_table", "DataContainer"), fields=fields)])],
        )

        payload = serialize_dossier(dossier)
        encoded = len(__import__("json").dumps(payload, sort_keys=True).encode("utf-8"))
        self.assertLessEqual(encoded, _MAX_PAYLOAD_BYTES)
        self.assertTrue(payload["limitations"]["truncated"])
        self.assertIn("Dropped", payload["limitations"]["truncation_reason"])
        self.assertLess(len(payload["data_sources"][0]["containers"][0]["fields"]), len(fields))

    def test_oversized_non_data_sections_are_truncated_under_cap(self) -> None:
        from brain_ds.dossier.serialization import _MAX_PAYLOAD_BYTES, serialize_dossier

        huge = "x" * (_MAX_PAYLOAD_BYTES // 2)
        dossier = KpiDossier(
            kpi=node("kpi", "Large KPI", "KPI", {"description": huge}),
            actors=[ActorFacet(node=node("role", "Ops Owner", "Role", {"description": huge}))],
            processes=[ProcessFacet(node=node("heur", "Forecast Rule", "Heuristic", {"description": huge}))],
            limitations=LimitationsFacet(
                unmapped_sources=[{"description": huge, "gap_type": "unmapped_source", "source": "assess_completeness"}],
                weak_edges=[{"from_node": "kpi", "to_node": "ds", "relationship": "measured-by", "confidence": 0.1, "source": huge}],
                currency=[{"description": huge, "criticality": "high", "source": "assess_currency"}],
            ),
            summary=huge,
        )

        payload = serialize_dossier(dossier)
        encoded = len(__import__("json").dumps(payload, sort_keys=True).encode("utf-8"))

        self.assertLessEqual(encoded, _MAX_PAYLOAD_BYTES)
        self.assertTrue(payload["limitations"]["truncated"])
        self.assertIn("under 256 KiB", payload["limitations"]["truncation_reason"])


if __name__ == "__main__":
    unittest.main()
