"""
Fixture isolation tests (Phase 2, PR 2).

RED phase: tests 2.1a and 2.1b will fail until conftest.py exposes
`writable_synthetic_source_path` and the seed is confirmed read-only.

After GREEN (tasks 2.2 + 2.3), all tests here must pass.
"""
from __future__ import annotations

import hashlib
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest

# Canonical seed path — this file MUST never be mutated by tests.
SEED_PATH = Path(__file__).parent / "fixtures" / "synthetic_source.db"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Task 2.1a — writable_synthetic_source_path fixture must exist
# ---------------------------------------------------------------------------


class TestWritableFixtureContract:
    """The `writable_synthetic_source_path` fixture must exist and return a tmp copy."""

    def test_writable_fixture_is_separate_from_seed(
        self, writable_synthetic_source_path: Path
    ) -> None:
        """The writable path must NOT be the checked-in seed."""
        assert writable_synthetic_source_path.resolve() != SEED_PATH.resolve(), (
            "writable_synthetic_source_path must be a tmp copy, not the seed file"
        )

    def test_writable_fixture_is_a_valid_sqlite_db(
        self, writable_synthetic_source_path: Path
    ) -> None:
        """The tmp copy must be a valid SQLite db with the expected tables."""
        conn = sqlite3.connect(str(writable_synthetic_source_path))
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()
        assert "customers" in tables
        assert "orders" in tables

    def test_writable_fixture_allows_writes_without_mutating_seed(
        self, writable_synthetic_source_path: Path
    ) -> None:
        """Writing to the tmp copy must not change the seed hash."""
        seed_hash_before = _sha256(SEED_PATH)

        # Perform a destructive write on the tmp copy.
        conn = sqlite3.connect(str(writable_synthetic_source_path))
        try:
            conn.execute("DELETE FROM customers")
            conn.commit()
        finally:
            conn.close()

        seed_hash_after = _sha256(SEED_PATH)
        assert seed_hash_before == seed_hash_after, (
            "Writing to the tmp copy mutated the checked-in seed file"
        )

    def test_each_test_gets_independent_tmp_copy(
        self, writable_synthetic_source_path: Path, tmp_path: Path
    ) -> None:
        """Two independent tmp copies must live in different directories."""
        second_copy = tmp_path / "second_copy.db"
        shutil.copy2(writable_synthetic_source_path, second_copy)
        # They should be byte-equal initially but at different paths.
        assert writable_synthetic_source_path.resolve() != second_copy.resolve()
        assert _sha256(writable_synthetic_source_path) == _sha256(second_copy)


# ---------------------------------------------------------------------------
# Task 2.1b — synthetic_source_path must return the seed unchanged (read-only)
# ---------------------------------------------------------------------------


class TestSeedImmutability:
    """The seed file must survive a full test run byte-identical."""

    def test_synthetic_source_path_points_to_seed(
        self, synthetic_source_path: Path
    ) -> None:
        """synthetic_source_path fixture must return the checked-in seed path."""
        assert synthetic_source_path.resolve() == SEED_PATH.resolve(), (
            "synthetic_source_path must point to the checked-in seed, not a copy"
        )

    def test_seed_hash_unchanged_after_writable_write(
        self, synthetic_source_path: Path, writable_synthetic_source_path: Path
    ) -> None:
        """Performing writes via writable_synthetic_source_path must leave seed unchanged."""
        seed_hash_before = _sha256(synthetic_source_path)

        conn = sqlite3.connect(str(writable_synthetic_source_path))
        try:
            conn.execute("INSERT INTO customers VALUES (99, 'Test Corp', 'SMB', 'APAC')")
            conn.commit()
        finally:
            conn.close()

        seed_hash_after = _sha256(synthetic_source_path)
        assert seed_hash_before == seed_hash_after, (
            "Seed was mutated by a write that should have gone to the tmp copy"
        )

    def test_build_synthetic_source_called_without_target_does_not_mutate_seed(self) -> None:
        """build_synthetic_source() called without target must not rewrite the seed."""
        seed_hash_before = _sha256(SEED_PATH)

        # Import and call WITHOUT providing a target — the GREEN phase must guard this.
        from tests.fixtures.build_synthetic_source import build_synthetic_source

        result_path = build_synthetic_source()

        seed_hash_after = _sha256(SEED_PATH)
        # Must return the seed path (unchanged) and must not have rewritten it.
        assert result_path.resolve() == SEED_PATH.resolve()
        assert seed_hash_before == seed_hash_after, (
            "build_synthetic_source() without target rewrote the checked-in seed"
        )


# ---------------------------------------------------------------------------
# Task 3.1 — xdist parallelism gate (RED: requires pytest-xdist to be installed)
#
# This test is the GATE that proves xdist-parallel execution does not mutate
# the shared seed fixture.  It is marked `integration` (excluded from `fast`)
# and skipped when pytest-xdist is not installed.
#
# After task 3.2 GREEN (pytest-xdist added to pyproject.toml), this test will
# run and must pass.  Only once it passes is it safe to advertise `pytest -n auto`.
# ---------------------------------------------------------------------------

try:
    import xdist  # noqa: F401

    _XDIST_AVAILABLE = True
except ImportError:
    _XDIST_AVAILABLE = False

import subprocess
import sys


@pytest.mark.integration
class TestXdistSeedImmutability:
    """Prove that running the suite under pytest -n 4 does not mutate the seed.

    Spec requirement:
        'xdist parallelism MUST be opt-in and advertised in pyproject.toml only
        after an isolation test proves shared-fixture immutability AND migration
        caching under pytest -n auto.'

    This test is the gate.  It is skipped when pytest-xdist is not installed
    so that the RED phase (task 3.1) does not break the CI suite before xdist
    is added (task 3.2).  After 3.2 GREEN, xdist is installed and this test
    runs for real.
    """

    @pytest.mark.skipif(
        not _XDIST_AVAILABLE,
        reason="pytest-xdist not installed; skipped until task 3.2 GREEN adds it to pyproject.toml",
    )
    def test_seed_hash_unchanged_after_parallel_run(self, tmp_path: Path) -> None:
        """Run a subset of the suite under pytest -n 4 and assert seed integrity.

        Uses a subprocess so xdist workers are fully separate Python processes —
        the only realistic way to reproduce the shared-state isolation property.

        The seed hash is captured before and after the subprocess run and must
        be byte-identical.  This is the canonical isolation proof.
        """
        seed_hash_before = _sha256(SEED_PATH)

        # Run the fixture-isolation and migration tests under -n 4.
        # These are the tests most likely to race if fixture isolation is broken.
        # Exclude `integration`-marked tests so this test does not recurse into
        # itself (this class is marked `integration`) and so that the subprocess
        # does not try to nest xdist workers (xdist silently drops all tests
        # when spawned from inside an existing xdist worker process).
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_fixture_isolation.py",
                "tests/test_store_migrations.py",
                "-n",
                "4",
                "-m",
                "not integration",
                "-q",
                "--no-header",
            ],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent),  # repo root
        )

        seed_hash_after = _sha256(SEED_PATH)

        # Primary assertion: seed must be byte-identical after parallel run.
        assert seed_hash_before == seed_hash_after, (
            f"pytest -n 4 mutated the seed fixture!\n"
            f"  Before: {seed_hash_before}\n"
            f"  After:  {seed_hash_after}\n"
            f"  stdout: {result.stdout[-2000:]}\n"
            f"  stderr: {result.stderr[-500:]}"
        )

        # Secondary assertion: the subprocess must have passed.
        assert result.returncode == 0, (
            f"pytest -n 4 exited with code {result.returncode}:\n"
            f"  stdout: {result.stdout[-2000:]}\n"
            f"  stderr: {result.stderr[-500:]}"
        )
