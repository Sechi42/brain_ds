# Contributing to brain_ds

## Test profiles

The test suite uses named profiles to balance feedback speed and coverage depth.
Run them via:

```bash
uv run python scripts/test_profiles.py <profile>
```

| Profile | Command | What it runs | Target time | When to use |
|---------|---------|--------------|-------------|-------------|
| `fast` | `uv run python scripts/test_profiles.py fast` | Unit tests only — excludes `slow`, `integration`, `live`, `e2e` | < 20 s | TDD tight loops; PR-slice verify on unit-only changes |
| `changed` | `uv run python scripts/test_profiles.py changed` | Tests matching changed files; falls back to `full` for global file changes | varies | Focused PR verify covering changed modules |
| `full` | `uv run python scripts/test_profiles.py full` | Full Python suite minus `live`/`e2e` | ~ 135 s | Merge gates; config-change verify; archive step |
| `live` | `uv run python scripts/test_profiles.py live` | Only `@pytest.mark.live` tests (real external service calls) | varies | Final acceptance before release |
| `e2e` | `uv run python scripts/test_profiles.py e2e` | Playwright UI tests only | varies | Release validation of the offline graph viewer |

### Skip reporting

Every profile prints which layers it did NOT run at exit, for example:

```
[test_profiles] skipped: changed, full, live, e2e
```

SDD `verify` reports MUST include this line so reviewers know which layers were
exercised and which were explicitly deferred.

### Profile selection policy

| Situation | Profile |
|-----------|---------|
| PR slice touches only unit code | `fast` |
| PR slice touches module boundaries or config | `changed` |
| PR slice modifies `pyproject.toml`, `conftest.py`, or grounding | `full` |
| Archive / merge gate | `full` + `live` |
| Explicit user request for full coverage | `full` |

### Markers

The four test markers are registered in `pyproject.toml`.  Unknown markers fail
the run (escalated from warning to error):

| Marker | Meaning |
|--------|---------|
| `slow` | Intentionally slow test; excluded from `fast` |
| `integration` | Crosses module/process boundaries; excluded from `fast` |
| `live` | Requires a live external service; excluded from `fast` and `full` |
| `e2e` | UI/Playwright end-to-end; excluded from all Python profiles |

### Direct pytest equivalents

If you prefer to call pytest directly:

```bash
# fast
uv run pytest -m "not slow and not integration and not live and not e2e"

# full (Python suite, no external services)
uv run pytest -m "not live and not e2e"

# live only
uv run pytest -m live

# full gate with coverage
uv run pytest -m "not live and not e2e" --cov=brain_ds --cov-report=term-missing --cov-fail-under=87
```

### Parallelization

`pytest-xdist` is installed and **safe to use**. All fixtures are isolated:
`synthetic_source_path` is read-only (never mutated by tests) and every test
that writes to a DB gets an independent `tmp_path` copy via
`writable_synthetic_source_path`.  The migration cache in `graph_store.py` is
process-local, so xdist workers cannot share or corrupt each other's cache.

```bash
# Parallel run — safe on all profiles except live/e2e
uv run pytest -n auto -m "not live and not e2e"

# Parallel fast profile
uv run pytest -n 4 -m "not slow and not integration and not live and not e2e"
```

**When NOT to parallelize**: `live` and `e2e` tests depend on real external
services or Playwright state; run them sequentially (`-n0` or without `-n`).

**Skip-report note**: SDD `verify` reports MUST state the `-n` value used (or
`sequential`) alongside the profile name so reviewers know whether parallelism
was exercised. Example: `fast profile, -n 4`.

## Code style

- Python: `uv run ruff check .` (lint) and `uv run ruff format .` (format)
- Types: `uv run mypy brain_ds` (advisory, not a gate)
- Tests: `unittest.TestCase` style; place in `tests/test_<module>.py`

## Commit discipline

Use work-unit commits: each commit bundles test + implementation + docs for
one deliverable unit.  Do not batch file-type changes across units.
