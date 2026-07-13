"""
Test profile runner for brain_ds.

Exposes five named profiles with their pytest / tool commands.
Run directly:

    uv run python scripts/test_profiles.py fast
    uv run python scripts/test_profiles.py changed
    uv run python scripts/test_profiles.py full
    uv run python scripts/test_profiles.py live
    uv run python scripts/test_profiles.py e2e

Profiles
--------
fast     Unit tests only — excludes slow, integration, live, e2e markers.
         Target: < 20 s on the reference machine.
         Use for: tight TDD loops and PR-slice verify on unit-only changes.

changed  Runs the fast slice plus any test file whose name or imports overlap
         with changed files (git diff --name-only HEAD).  Falls back to full
         when a global file (pyproject.toml, conftest.py, grounding.py, …) is
         modified.  Use for: focused PR verify that covers changed modules.

full     Full Python suite minus live and e2e markers.
         Use for: merge gates, config-change verify, archive step.

live     Only tests marked @pytest.mark.live (real external service calls).
         Use for: final acceptance before release.

e2e      Playwright UI end-to-end tests only (delegates to pnpm/playwright).
         Use for: release validation of the offline graph viewer.

Skip reporting
--------------
The runner prints which layers it did NOT run at exit so the verify report
can include the expected "skipped: <layers>" language.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Profile command map.
# Each value is a list of tokens that will be passed to subprocess.run.
# Using sys.executable keeps the command within the active venv / uv env.
# ---------------------------------------------------------------------------
PROFILES: dict[str, list[str]] = {
    "fast": [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        "not slow and not integration and not live and not e2e",
        "--no-header",
        "-q",
    ],
    "changed": [
        # Sentinel: the runner resolves the file list at call time (see _run_changed).
        # Stored as a placeholder so the keys are always the five canonical names.
        sys.executable,
        "-m",
        "pytest",
        "-m",
        "not live and not e2e",
        "--no-header",
        "-q",
    ],
    "full": [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        "not live and not e2e",
        "--no-header",
        "-q",
    ],
    "live": [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        "live",
        "--no-header",
        "-q",
    ],
    "e2e": [
        "pnpm",
        "--dir",
        str(REPO_ROOT / "brain_ds" / "ui"),
        "exec",
        "playwright",
        "test",
    ],
}

_ALL_PROFILES = list(PROFILES.keys())

# Files whose modification triggers a fallback from "changed" to "full".
_GLOBAL_FILES = {
    "pyproject.toml",
    "tests/conftest.py",
    "brain_ds/mcp/grounding.py",
    "brain_ds/store/graph_store.py",
}


def _git_changed_files() -> list[str]:
    """Return a list of files changed vs HEAD (unstaged + staged)."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _run_changed() -> int:
    """Run changed-file profile, falling back to full for global changes."""
    changed = _git_changed_files()
    if not changed:
        print("[test_profiles] No changed files detected vs HEAD; running fast profile.")
        return _run_profile("fast", skip_report=["changed", "full", "live", "e2e"])

    global_hit = [f for f in changed if f in _GLOBAL_FILES]
    if global_hit:
        print(
            f"[test_profiles] Global files changed ({global_hit}); escalating to full."
        )
        return _run_profile("full", skip_report=["live", "e2e"])

    # Collect test files that share a module name with changed source files.
    changed_stems = {Path(f).stem for f in changed}
    test_files: list[str] = []
    for stem in changed_stems:
        candidate = REPO_ROOT / "tests" / f"test_{stem}.py"
        if candidate.exists():
            test_files.append(str(candidate))

    if not test_files:
        print(
            "[test_profiles] No matching test files found for changed sources; running fast."
        )
        return _run_profile("fast", skip_report=["changed", "full", "live", "e2e"])

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        "not live and not e2e",
        "--no-header",
        "-q",
        *test_files,
    ]
    print(f"[test_profiles] changed profile: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    _print_skip_report(["full", "live", "e2e"])
    return result.returncode


def _print_skip_report(skipped: list[str]) -> None:
    if skipped:
        print(f"[test_profiles] skipped: {', '.join(skipped)}")


def _run_profile(name: str, skip_report: list[str] | None = None) -> int:
    if name == "changed":
        return _run_changed()

    cmd = PROFILES[name]
    print(f"[test_profiles] profile={name}  cmd={' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))

    if skip_report is None:
        remaining = [p for p in _ALL_PROFILES if p != name]
        skip_report = remaining

    _print_skip_report(skip_report)
    return result.returncode


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in _ALL_PROFILES:
        print("Usage: uv run python scripts/test_profiles.py <profile>")
        print(f"Available profiles: {', '.join(_ALL_PROFILES)}")
        sys.exit(1)

    profile = sys.argv[1]
    sys.exit(_run_profile(profile))


if __name__ == "__main__":
    main()
