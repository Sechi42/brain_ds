"""
Tests for pytest marker registration and test profile runner.

RED phase: these tests MUST fail before pyproject.toml markers and
scripts/test_profiles.py exist.

After GREEN (1.2 + 1.3), all tests here must pass.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

# Repository root — two levels up from this file (tests/test_test_profiles.py)
REPO_ROOT = Path(__file__).parent.parent


class MarkerRegistrationTests(unittest.TestCase):
    """Assert that pyproject.toml registers the four required markers."""

    def _read_pyproject_markers(self) -> list[str]:
        """Return the list of marker *name* prefixes from pyproject.toml."""
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]

        pyproject = REPO_ROOT / "pyproject.toml"
        with open(pyproject, "rb") as fh:
            data = tomllib.load(fh)

        raw: list[str] = (
            data.get("tool", {})
            .get("pytest", {})
            .get("ini_options", {})
            .get("markers", [])
        )
        # Each entry is "<name>: <description>"; extract the name part.
        return [entry.split(":")[0].strip() for entry in raw]

    def test_slow_marker_registered(self) -> None:
        self.assertIn("slow", self._read_pyproject_markers())

    def test_integration_marker_registered(self) -> None:
        self.assertIn("integration", self._read_pyproject_markers())

    def test_live_marker_registered(self) -> None:
        self.assertIn("live", self._read_pyproject_markers())

    def test_e2e_marker_registered(self) -> None:
        self.assertIn("e2e", self._read_pyproject_markers())

    def test_filterwarnings_escalates_unknown_markers(self) -> None:
        """pyproject.toml must escalate PytestUnknownMarkWarning to error."""
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]

        pyproject = REPO_ROOT / "pyproject.toml"
        with open(pyproject, "rb") as fh:
            data = tomllib.load(fh)

        filterwarnings: list[str] = (
            data.get("tool", {})
            .get("pytest", {})
            .get("ini_options", {})
            .get("filterwarnings", [])
        )
        # At least one entry must match the error::pytest.PytestUnknownMarkWarning pattern.
        matches = [
            entry
            for entry in filterwarnings
            if "PytestUnknownMarkWarning" in entry and entry.startswith("error")
        ]
        self.assertTrue(
            matches,
            msg=(
                "pyproject.toml [tool.pytest.ini_options] filterwarnings must contain "
                "an entry like 'error::pytest.PytestUnknownMarkWarning' — got: "
                f"{filterwarnings!r}"
            ),
        )

    def test_unknown_marker_causes_nonzero_exit(self) -> None:
        """A synthetic test using an unregistered marker must make pytest exit non-zero."""
        # Write a tiny temp test file that uses an unregistered marker.
        import tempfile

        # Sentinel must NOT start with an underscore: pytest raises an
        # AttributeError at collection for any marker name beginning with "_",
        # which is a separate code path from the PytestUnknownMarkWarning
        # escalation we actually want to exercise here.
        bad_test = (
            "import pytest\n"
            "\n"
            "@pytest.mark.brainds_unregistered_xyz_sentinel\n"
            "def test_dummy():\n"
            "    pass\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            prefix="test_bad_marker_",
            dir=REPO_ROOT / "tests",
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(bad_test)

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    str(tmp_path),
                    "--no-header",
                    "-q",
                ],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
            )
            self.assertNotEqual(
                result.returncode,
                0,
                msg=(
                    "pytest must exit non-zero when an unknown marker is used. "
                    f"stdout={result.stdout!r} stderr={result.stderr!r}"
                ),
            )
            # Prove the non-zero exit is caused by the filterwarnings escalation
            # (PytestUnknownMarkWarning -> error), not by an unrelated failure.
            # Without the filterwarnings entry in pyproject.toml this assertion
            # would fail even though the exit code might still be non-zero.
            combined_output = result.stdout + result.stderr
            self.assertIn(
                "PytestUnknownMarkWarning",
                combined_output,
                msg=(
                    "Non-zero exit must come from the unknown-marker escalation. "
                    f"stdout={result.stdout!r} stderr={result.stderr!r}"
                ),
            )
        finally:
            tmp_path.unlink(missing_ok=True)


class ProfileRunnerModuleTests(unittest.TestCase):
    """Assert that scripts/test_profiles.py exists and exposes the five profiles."""

    EXPECTED_PROFILES = {"fast", "changed", "full", "live", "e2e"}
    RUNNER_PATH = REPO_ROOT / "scripts" / "test_profiles.py"

    def _load_module(self):
        """Dynamically import scripts/test_profiles.py without installing it."""
        spec = importlib.util.spec_from_file_location(
            "test_profiles", self.RUNNER_PATH
        )
        self.assertIsNotNone(
            spec,
            msg=f"Could not find {self.RUNNER_PATH} — run task 1.3 to create it.",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def test_runner_file_exists(self) -> None:
        self.assertTrue(
            self.RUNNER_PATH.exists(),
            msg=f"scripts/test_profiles.py must exist at {self.RUNNER_PATH}",
        )

    def test_profiles_dict_contains_all_five(self) -> None:
        mod = self._load_module()
        self.assertTrue(
            hasattr(mod, "PROFILES"),
            msg="scripts/test_profiles.py must expose a PROFILES dict.",
        )
        missing = self.EXPECTED_PROFILES - set(mod.PROFILES.keys())
        self.assertFalse(
            missing,
            msg=f"PROFILES dict is missing keys: {missing}",
        )

    def test_fast_profile_excludes_slow_integration_live_e2e(self) -> None:
        mod = self._load_module()
        fast_cmd: list[str] = mod.PROFILES["fast"]
        joined = " ".join(fast_cmd)
        for marker in ("slow", "integration", "live", "e2e"):
            self.assertIn(
                marker,
                joined,
                msg=f"fast profile command must reference '{marker}' exclusion — got: {joined!r}",
            )

    def test_e2e_profile_uses_playwright(self) -> None:
        mod = self._load_module()
        e2e_cmd: list[str] = mod.PROFILES["e2e"]
        joined = " ".join(e2e_cmd)
        self.assertIn(
            "playwright",
            joined,
            msg=f"e2e profile must invoke playwright — got: {joined!r}",
        )


class ContributingDocPolicyTests(unittest.TestCase):
    """Task 3.4 — assert CONTRIBUTING.md contains required project conventions.

    RED phase: fails until CONTRIBUTING.md is updated with parallelization
    conventions (task 3.3 CORRECTED SCOPE — project doc, not skill prose).

    Asserts:
    - All five test profiles are documented.
    - Parallelization convention is present (-n auto / -n 4).
    - Skip-report language is present (reviewers must know which layers ran).

    IMPORTANT: This test points at CONTRIBUTING.md (project documentation),
    NOT at any skill file.  Per the user override, skill prose was NOT modified.
    """

    CONTRIBUTING_PATH = REPO_ROOT / "CONTRIBUTING.md"
    FIVE_PROFILES = ("fast", "changed", "full", "live", "e2e")

    def _read_contributing(self) -> str:
        self.assertTrue(
            self.CONTRIBUTING_PATH.exists(),
            msg=f"CONTRIBUTING.md must exist at {self.CONTRIBUTING_PATH}",
        )
        return self.CONTRIBUTING_PATH.read_text(encoding="utf-8")

    def test_all_five_profiles_documented(self) -> None:
        """CONTRIBUTING.md must mention each of the five test profiles."""
        content = self._read_contributing()
        missing = [p for p in self.FIVE_PROFILES if p not in content]
        self.assertFalse(
            missing,
            msg=(
                f"CONTRIBUTING.md is missing documentation for profiles: {missing}. "
                "All five profiles (fast, changed, full, live, e2e) must be present."
            ),
        )

    def test_parallelization_convention_present(self) -> None:
        """CONTRIBUTING.md must document that -n auto / -n 4 is safe to use."""
        content = self._read_contributing()
        has_n_auto = "-n auto" in content
        has_n_4 = "-n 4" in content
        self.assertTrue(
            has_n_auto or has_n_4,
            msg=(
                "CONTRIBUTING.md must document pytest parallelization convention "
                "(-n auto or -n 4). "
                "Add a 'Parallelization' section explaining that fixtures are "
                "isolated and the seed is immutable."
            ),
        )

    def test_skip_report_language_present(self) -> None:
        """CONTRIBUTING.md must explain the skip-report expectation."""
        content = self._read_contributing()
        # Accept any of the canonical skip-report phrases.
        skip_phrases = ("skip", "skipped", "skip report", "skip-report")
        has_skip_language = any(phrase in content.lower() for phrase in skip_phrases)
        self.assertTrue(
            has_skip_language,
            msg=(
                "CONTRIBUTING.md must contain skip-report language so that "
                "SDD verify reports can document which layers were exercised "
                "vs deferred. Expected phrases like 'skip', 'skipped', or "
                "'skip report'."
            ),
        )

    def test_parallelization_section_notes_isolation(self) -> None:
        """The parallelization section must note why it is safe (fixture isolation)."""
        content = self._read_contributing()
        # 'isolated' is the key word — tests get isolated fixtures.
        self.assertIn(
            "isolated",
            content.lower(),
            msg=(
                "CONTRIBUTING.md parallelization section must explain WHY it is "
                "safe (fixtures are isolated / seed is immutable). "
                "Add at least one occurrence of 'isolated' in the doc."
            ),
        )


if __name__ == "__main__":
    unittest.main()
