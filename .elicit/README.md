# `.elicit/` lifecycle contract

`.elicit/` is the local artifact store for active brain_ds cycles. It mirrors `DELEGATION_PROTOCOL.artifact_keys`: active files live at `.elicit/<phase>-<org-slug>-<ISO-date>.md`, archived files move byte-identically under `.elicit/changes/<change-name>/`.

## Quick path

1. Write active-cycle artifacts as `.elicit/<phase>-<org-slug>-<ISO-date>.md`.
2. Use only these phases: `elicit`, `source-exploration`, `source-docs`, `map`, `brd`, `verify`, `archive`.
3. After `brd`, run the `verify` gate; the gate writes `verify-<slug>-<date>.md` on pass.
4. Archive the completed cycle only after `verify` passes: move every phase file into `.elicit/changes/<change-name>/`.

## Details

| Topic | Decision |
|---|---|
| Naming | Active artifacts use `.elicit/<phase>-<org-slug>-<ISO-date>.md`. |
| Source of truth | The lifecycle is grounded in `DELEGATION_PROTOCOL.artifact_keys`. |
| Completion rule | A cycle is complete when a BRD is written OR the orchestrator explicitly closes the cycle. |
| Archive rule | Archived files keep the original filename and move byte-identically under `.elicit/changes/<change-name>/`. |

## Phase ownership

| Phase | Owner sub-agent |
|---|---|
| `elicit` | `brainds-orchestrator` |
| `source-exploration` | `brainds-source-explorer` |
| `source-docs` | `brainds-source-explorer` |
| `map` | `brainds-connection-mapper` |
| `brd` | `brainds-brd-writer` |
| `verify` | `brainds-orchestrator` |
| `archive` | `brainds-orchestrator` |

`brainds-graph-mapper` supports the `map` phase by consolidating source documentation before graph writes, but the lifecycle owner for the persisted `map` artifact stays `brainds-connection-mapper` per the Slice 2 spec.

## Archive checklist

- [ ] Confirm the cycle reached completion (`brd` written or explicit orchestrator closure).
- [ ] Move all active-cycle phase files into `.elicit/changes/<change-name>/`.
- [ ] Keep each filename unchanged during the move.
- [ ] Leave no completed-cycle phase files at the `.elicit/` root.

## Next step

See `docs/SDD_FLOW.md` for the human-readable orchestration flow that uses this lifecycle.
