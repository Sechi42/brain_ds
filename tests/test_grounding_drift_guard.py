"""Drift guard for the MCP grounding harness.

The grounding module (``brain_ds/mcp/grounding.py``) mixes two kinds of context:

* Category-1 context is *derived at runtime* from the ontology enums, so it can
  never drift.
* Category-2 context is *hand-maintained* Python constants that reference entity
  types by their literal string value (question banks, write templates, BRD
  fingerprints). These DO drift: adding or renaming an ``EntityType`` silently
  leaves the Category-2 constants stale, and the harness returns context that no
  longer matches the ontology.

These tests make that drift a hard failure instead of a silent one. When they go
red, update ``brain_ds/mcp/grounding.py`` (and the skill prose it mirrors) so the
harness stays in sync. See the "Harness maintenance" section in ``CLAUDE.md``.
"""

from __future__ import annotations

import unittest

from brain_ds.mcp import grounding
from brain_ds.ontology.entity_types import EntityType

# EntityTypes that intentionally have NO elicitation question bank entry.
# Adding a new EntityType that should be elicited means adding it to
# QUESTION_BANK; adding one that should not means listing it here. Either way
# the choice is explicit and reviewed.
ELICIT_EXEMPT_TYPES: frozenset[str] = frozenset(
    {
        "Project",  # captured via map/brd synthesis, not the elicit interview
        "Risk",  # derived during mapping, not directly elicited
        "Unknown",  # fallback bucket, never elicited
    }
)


def _entity_values() -> set[str]:
    return {e.value for e in EntityType}


class GroundingEntityNameValidityTests(unittest.TestCase):
    """Every hand-maintained entity-name string must be a real EntityType value.

    This catches renames and typos: rename an EntityType in the ontology and any
    stale Category-2 reference fails here, pointing straight at what to fix.
    """

    def test_question_bank_keys_are_valid_entity_types(self) -> None:
        invalid = set(grounding.QUESTION_BANK) - _entity_values()
        self.assertEqual(
            invalid,
            set(),
            f"QUESTION_BANK references unknown entity types: {sorted(invalid)}",
        )

    def test_node_write_template_type_keys_are_valid_entity_types(self) -> None:
        # "generic" is the shared fallback template, not an entity type.
        type_keys = set(grounding.NODE_WRITE_TEMPLATES) - {"generic"}
        invalid = type_keys - _entity_values()
        self.assertEqual(
            invalid,
            set(),
            f"NODE_WRITE_TEMPLATES references unknown entity types: {sorted(invalid)}",
        )

    def test_dataset_fingerprint_order_entries_are_valid_entity_types(self) -> None:
        fingerprint = grounding.COMPLETENESS_MATRIX_TEMPLATE["dataset_fingerprint_order"]
        invalid = set(fingerprint) - _entity_values()
        self.assertEqual(
            invalid,
            set(),
            f"dataset_fingerprint_order references unknown entity types: {sorted(invalid)}",
        )


class GroundingEntityCoverageTests(unittest.TestCase):
    """Every EntityType must be consciously handled by the elicit harness.

    Add a new EntityType to the ontology and this fails until you either give it
    a QUESTION_BANK entry or explicitly exempt it in ELICIT_EXEMPT_TYPES. That is
    the self-maintaining contract: new context cannot land without the harness
    being updated to acknowledge it.
    """

    def test_every_entity_type_is_elicited_or_exempt(self) -> None:
        covered = set(grounding.QUESTION_BANK) | set(ELICIT_EXEMPT_TYPES)
        missing = _entity_values() - covered
        self.assertEqual(
            missing,
            set(),
            (
                "These EntityTypes are neither in grounding.QUESTION_BANK nor "
                f"ELICIT_EXEMPT_TYPES: {sorted(missing)}. Add a question bank entry "
                "or exempt them, then update the mirrored skill prose."
            ),
        )

    def test_exempt_types_are_real_and_not_double_listed(self) -> None:
        # Exemptions must be valid entity types...
        invalid = set(ELICIT_EXEMPT_TYPES) - _entity_values()
        self.assertEqual(
            invalid,
            set(),
            f"ELICIT_EXEMPT_TYPES lists unknown entity types: {sorted(invalid)}",
        )
        # ...and must not also carry a question bank entry (contradictory state).
        contradictory = set(ELICIT_EXEMPT_TYPES) & set(grounding.QUESTION_BANK)
        self.assertEqual(
            contradictory,
            set(),
            f"Types are both exempt and in QUESTION_BANK: {sorted(contradictory)}",
        )


if __name__ == "__main__":
    unittest.main()
