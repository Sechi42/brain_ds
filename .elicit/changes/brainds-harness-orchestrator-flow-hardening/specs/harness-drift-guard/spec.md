# Delta for harness-drift-guard

> Slice 1 of `brainds-harness-orchestrator-flow-hardening`. Generalizes the
> Category-2 drift guard so that adding a new constant fails the build until
> it is consciously classified as swept or exempt.

## ADDED Requirements

### Requirement: Category-2 drift guard enumerates every constant

The drift guard in `tests/test_grounding_drift_guard.py` MUST classify every
Category-2 constant in `brain_ds/mcp/grounding.py` as either "swept" or
"explicitly exempt" via a discoverable registry. A meta-test MUST assert
that:

- Every module-level dict or list constant declared in `grounding.py` whose
  name matches the Category-2 pattern (e.g. UPPER_SNAKE_CASE top-level
  assignments to `dict` or `list`) is either swept by the existing guard
  logic OR listed in a `CATEGORY2_EXEMPT` set with a one-line rationale
  comment.
- If a new constant is added that is neither swept nor exempt, the meta-test
  fails with a message naming the constant.

#### Scenario: a new Category-2 constant fails until classified

- GIVEN the drift guard is registered
- WHEN a new module-level dict constant (e.g. `NEW_CONSTANT_XYZ = {"a": 1}`)
  is added to `brain_ds/mcp/grounding.py` and is neither swept by the guard
  logic nor added to `CATEGORY2_EXEMPT`
- THEN the meta-test fails with a message that names `NEW_CONSTANT_XYZ` and
  instructs the author to add it to the swept set or to `CATEGORY2_EXEMPT`
  with a rationale

#### Scenario: a consciously-exempt constant passes

- GIVEN the drift guard is registered
- WHEN a new module-level dict constant is added to `grounding.py` and
  classified by adding it to `CATEGORY2_EXEMPT` with a one-line rationale
  comment
- THEN the meta-test passes

### Requirement: Sweep detects entity-name-shaped tokens

When the drift guard sweeps a Category-2 constant, the sweep MUST walk
nested `str`, `list`, and `dict` values, and MUST flag any token that
matches the entity-name shape used elsewhere in the harness (e.g. values
returned by the existing `_entity_values()` helper for `EntityType`) if that
token is not a real `EntityType.value`.

#### Scenario: stale entity name in a constant is caught

- GIVEN a Category-2 constant in `grounding.py` whose nested string value
  is the literal `"StaleEntity"` (or any token shaped like an entity name)
  AND `"StaleEntity"` is not a value of `EntityType`
- WHEN the drift guard sweeps that constant
- THEN the sweep reports a drift entry naming the constant, the path within
  it, and the stale token

### Requirement: Drift guard exits non-zero on any drift

The drift guard test file MUST exit with a non-zero status when any drift
is reported, so CI and `brain_ds check` reflect drift as a build failure
rather than a warning.

#### Scenario: drift guard failure is observable in CI

- GIVEN the drift guard is registered in the test suite
- WHEN the suite is invoked via `uv run pytest
  tests/test_grounding_drift_guard.py` against a working tree that
  introduces one drift
- THEN the process exits non-zero and the failure message names the
  offending constant and token
