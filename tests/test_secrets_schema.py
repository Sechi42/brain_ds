"""T1.1 — TDD tests for schema.json optional enrichment keys.

Tests MUST be RED before schema.json is updated (T1.2).
After T1.2, they go GREEN.

Covers: A1-R1/R2/R3/R4/R5/R6/R7, A3-R3/R4/R5/R6, CC-1
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

SCHEMA_PATH = Path(__file__).parent.parent / "brain_ds" / "connectors" / "secrets" / "schema.json"


def _load_schema() -> dict:
    with SCHEMA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Backward-compatibility: existing entries must still be valid
# ---------------------------------------------------------------------------

class TestSchemaBackwardCompat:
    """CC-1: existing entries without new keys must still parse cleanly."""

    def test_schema_loads(self):
        schema = _load_schema()
        assert "provider_kinds" in schema

    def test_postgres_still_has_required_fields(self):
        schema = _load_schema()
        pg = schema["provider_kinds"]["postgres"]
        assert "required" in pg
        assert "types" in pg
        for field in ("host", "port", "database", "username", "sslmode"):
            assert field in pg["required"]

    def test_sqlserver_still_has_required_fields(self):
        schema = _load_schema()
        ss = schema["provider_kinds"]["sqlserver"]
        assert "required" in ss
        for field in ("host", "port", "database", "username", "sslmode"):
            assert field in ss["required"]

    def test_aws_secrets_still_has_required_fields(self):
        schema = _load_schema()
        aws = schema["provider_kinds"]["aws-secrets"]
        assert "required" in aws
        for field in ("region", "secret_id"):
            assert field in aws["required"]

    def test_provider_kinds_without_new_keys_are_valid(self):
        """Providers that lack descriptions/placeholders/enums must still load cleanly."""
        schema = _load_schema()
        # sqlite, iam-role, etc. — no new optional keys needed
        for kind_name, kind in schema["provider_kinds"].items():
            assert "required" in kind, f"{kind_name} missing 'required'"
            assert "types" in kind, f"{kind_name} missing 'types'"


# ---------------------------------------------------------------------------
# requires_raw_value flag
# ---------------------------------------------------------------------------

class TestRequiresRawValueFlag:
    """A1-R5/R6: aws-secrets has requires_raw_value=false; others default true."""

    def test_aws_secrets_has_requires_raw_value_false(self):
        schema = _load_schema()
        aws = schema["provider_kinds"]["aws-secrets"]
        assert "requires_raw_value" in aws, \
            "aws-secrets must have requires_raw_value key"
        assert aws["requires_raw_value"] is False, \
            "aws-secrets requires_raw_value must be False"

    def test_postgres_requires_raw_value_absent_or_true(self):
        """postgres does NOT set requires_raw_value=false (absent means true)."""
        schema = _load_schema()
        pg = schema["provider_kinds"]["postgres"]
        raw_flag = pg.get("requires_raw_value", True)
        assert raw_flag is True, \
            "postgres requires_raw_value must be True or absent (defaults to True)"

    def test_sqlserver_requires_raw_value_absent_or_true(self):
        schema = _load_schema()
        ss = schema["provider_kinds"]["sqlserver"]
        raw_flag = ss.get("requires_raw_value", True)
        assert raw_flag is True, \
            "sqlserver requires_raw_value must be True or absent"


# ---------------------------------------------------------------------------
# Enum for sslmode
# ---------------------------------------------------------------------------

EXPECTED_SSLMODE_VALUES = ["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]


class TestEnumsKey:
    """A3-R3/R4/R5/R6: sslmode must have an enum list."""

    def test_postgres_has_enums_key(self):
        schema = _load_schema()
        pg = schema["provider_kinds"]["postgres"]
        assert "enums" in pg, "postgres must have 'enums' map"

    def test_postgres_sslmode_enum_has_six_options(self):
        schema = _load_schema()
        enums = schema["provider_kinds"]["postgres"]["enums"]
        assert "sslmode" in enums, "postgres enums must include sslmode"
        assert enums["sslmode"] == EXPECTED_SSLMODE_VALUES, \
            f"postgres sslmode enum must be {EXPECTED_SSLMODE_VALUES}"

    def test_sqlserver_has_sslmode_enum(self):
        schema = _load_schema()
        ss = schema["provider_kinds"]["sqlserver"]
        assert "enums" in ss, "sqlserver must have 'enums' map"
        assert "sslmode" in ss["enums"], "sqlserver enums must include sslmode"
        assert ss["enums"]["sslmode"] == EXPECTED_SSLMODE_VALUES

    def test_mock_postgres_has_sslmode_enum(self):
        """mock-postgres mirrors postgres for consistency in tests."""
        schema = _load_schema()
        mp = schema["provider_kinds"]["mock-postgres"]
        assert "enums" in mp, "mock-postgres must have 'enums' map"
        assert "sslmode" in mp["enums"]
        assert mp["enums"]["sslmode"] == EXPECTED_SSLMODE_VALUES

    def test_provider_without_enum_has_no_enums_or_empty_enums(self):
        """A3-R6: fields without enum still valid. sqlite has no enums — that's fine."""
        schema = _load_schema()
        sqlite = schema["provider_kinds"]["sqlite"]
        # Either no enums key, or an empty map — both valid
        enums = sqlite.get("enums", {})
        assert isinstance(enums, dict), "enums must be a dict when present"
        assert "path" not in enums, "sqlite 'path' field should NOT have an enum"

    def test_aws_secrets_has_no_sslmode_enum(self):
        """aws-secrets has no sslmode field, so no sslmode enum."""
        schema = _load_schema()
        aws = schema["provider_kinds"]["aws-secrets"]
        enums = aws.get("enums", {})
        assert "sslmode" not in enums, \
            "aws-secrets must not have a sslmode enum"


# ---------------------------------------------------------------------------
# descriptions and placeholders (A1)
# ---------------------------------------------------------------------------

class TestDescriptionsAndPlaceholders:
    """A1-R1/R2/R7: optional description/placeholder maps per provider kind."""

    def test_aws_secrets_has_descriptions(self):
        schema = _load_schema()
        aws = schema["provider_kinds"]["aws-secrets"]
        assert "descriptions" in aws, "aws-secrets must have 'descriptions' map"

    def test_aws_secrets_region_has_description(self):
        schema = _load_schema()
        aws = schema["provider_kinds"]["aws-secrets"]
        descs = aws.get("descriptions", {})
        assert "region" in descs, "aws-secrets descriptions must include 'region'"
        assert descs["region"], "aws-secrets region description must be non-empty"

    def test_aws_secrets_secret_id_has_description(self):
        schema = _load_schema()
        aws = schema["provider_kinds"]["aws-secrets"]
        descs = aws.get("descriptions", {})
        assert "secret_id" in descs, "aws-secrets descriptions must include 'secret_id'"

    def test_aws_secrets_has_placeholders(self):
        schema = _load_schema()
        aws = schema["provider_kinds"]["aws-secrets"]
        assert "placeholders" in aws, "aws-secrets must have 'placeholders' map"

    def test_aws_secrets_region_has_placeholder(self):
        schema = _load_schema()
        aws = schema["provider_kinds"]["aws-secrets"]
        placeholders = aws.get("placeholders", {})
        assert "region" in placeholders, "aws-secrets placeholders must include 'region'"
        assert placeholders["region"], "aws-secrets region placeholder must be non-empty"

    def test_aws_secrets_secret_id_has_placeholder(self):
        schema = _load_schema()
        aws = schema["provider_kinds"]["aws-secrets"]
        placeholders = aws.get("placeholders", {})
        assert "secret_id" in placeholders

    def test_descriptions_are_optional_for_other_providers(self):
        """A1-R7: providers without descriptions/placeholders must still load."""
        schema = _load_schema()
        # sqlite, iam-role etc. may not have descriptions — that's fine
        for kind_name in ("sqlite", "iam-role", "iam-credential"):
            kind = schema["provider_kinds"][kind_name]
            # Simply accessing the kind without error is the test
            assert "required" in kind
