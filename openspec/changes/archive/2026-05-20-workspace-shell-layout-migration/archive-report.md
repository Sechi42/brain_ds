# Archive Report: workspace-shell-layout-migration

**Date**: 2026-05-20
**Change**: `workspace-shell-layout-migration`
**Roadmap**: `backend-migration-to-new-ui` — Phase A · #2
**Artifact store mode**: hybrid
**Verdict**: ✅ CLEAN PASS — viewer 113/113, remediation 6/6, runtime 1/1; 7 pre-existing golden fixture failures unrelated

---

## Verification Status

| Check | Result |
|-------|--------|
| Tasks total | 14 |
| Tasks complete | 14 (100%) |
| Viewer tests | 113/113 pass |
| Remediation tests | 6/6 pass |
| Runtime harness | 1/1 pass |
| Full suite | 653/660 pass — 7 unrelated golden fixture failures (pre-existing, not regressions) |
| Spec compliance | 39/42 compliant, 1/42 partial (GV-2 stub-only panel routing), 0/42 not compliant |
| CRITICAL findings | None |
| WARNING findings | None |
| SUGGESTION findings | 4 (all deferred/out-of-scope) |
| **Verdict** | **PASS** |

## Verification Upgrades

- Initial verification: **PASS WITH WARNINGS** (W1–W7)
- After remediation: **PASS** — all 7 warnings closed
- User accepted the revised high-fidelity remediation preview (obs #890)
- Clean-pass memory recorded (obs #891)

## Delivered Behavior

### What shipped

1. **5-column workspace shell** — `grid-template-columns: 48px minmax(220px,300px) minmax(0,1fr) minmax(280px,360px) 48px` replacing the former 3-column flat grid
2. **Center chrome** — tab strip (36px, 1 static tab + new-tab button), toolbar (44px, view-label + overflow with zoom-fit/theme-toggle), canvas area
3. **Left rail + new UI panels** — 5-icon `role="tablist"` (search, filters, tree, hierarchy, layout), panel router calling existing `.mount()`/`.unmount()`, Section 1 visual rebuild (`.panel-card`, `[data-accordion-section]`, `.toggle-card`, `.toggle-chip`, `.tree-row`)
4. **Right rail + inspector** — gear-only rail, 4-section accordion (`<details>` — Properties open by default, Metadata, Related, AI-actions placeholder), Section 2/5 visual style (compact `--bg-panel` surfaces, `--border-subtle`, `--accent-mora-muted`)
5. **Old visible UI removed** — old `.sidebar-left`, fieldset/legend filter groups, `#show-all`/`#hide-all`, raw score-threshold block, old `#viewer-empty-state`, raw hierarchy `<ul>`, raw layout blocks all replaced by new shell components
6. **High-fidelity review artifacts** — 6 review previews (PR1, PR1.5, PR2, PR3, PR4, remediation) plus revised remediation preview that passed visual acceptance
7. **Responsive breakpoint** — ≤1100px rails persist at 48px, panels become overlay drawers (`z-index: 1000`)
8. **Token accessibility discipline** — `var(--bg-*)` / `var(--border-*)` / `var(--text-*)` / `var(--accent-*)` tokens exclusively, 44×44px touch targets, `prefers-reduced-motion` support

### What stayed unchanged

- `build_render_context` output — byte-identical, v1.0.0 consumed as-is
- `renderer.ts`, `popover.ts`, `context-menu.ts`, `score-filter.ts` — zero lines changed
- `main.ts` module registry — zero diff
- `template_renderer.py` — unchanged
- All 602+ pre-existing tests — still green
- `#network` canvas mount ID — same element, same `vis-network` behavior

## Engram & Filesystem Traceability

| Artifact | Engram ID | Topic Key | Filesystem |
|----------|-----------|-----------|------------|
| Exploration | #862 | `sdd/workspace-shell-layout-migration/explore` | `archive/.../exploration.md` |
| Proposal | #863 | `sdd/workspace-shell-layout-migration/proposal` | `archive/.../proposal.md` |
| Spec v2 | #868 | `sdd/workspace-shell-layout-migration/spec` | `archive/.../spec.md`, `archive/.../specs/*.md` |
| Design v2 | #865 | `sdd/workspace-shell-layout-migration/design` | `archive/.../design.md` |
| Tasks | #872 | `sdd/workspace-shell-layout-migration/tasks` | `archive/.../tasks.md` |
| Apply progress | #876 | `sdd/workspace-shell-layout-migration/apply-progress` | `archive/.../apply-progress.md` |
| Verify report | #883 | `sdd/workspace-shell-layout-migration/verify-report` | `archive/.../verify-report.md` |
| Clean-pass memory | #891 | `sdd/workspace-shell-layout-migration/clean-pass-after-remediation` | — |
| User-approved preview | #890 | `sdd/workspace-shell-layout-migration/remediation-preview-approved` | `archive/.../review/remediation-old-ui-removal-preview.html` |
| Preview rejection | #888 | `sdd/workspace-shell-layout-migration/remediation-preview-rejected` | — |
| Old UI rejection | #869 | `preference/workspace-shell-new-ui-not-old-visuals` | — |
| **This archive report** | #892 | `sdd/workspace-shell-layout-migration/archive-report` | `archive/.../archive-report.md` |

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| `ui-workspace-shell` | Created (new domain) | 12 requirements (WS-1 through WS-12), 29 test names |
| `ui-graph-viewer` | Created (new domain) | 5 requirements (GV-1 through GV-5), 14 test names |
| `render-context` | Unchanged | Delta affirmation: no ADDED/MODIFIED/REMOVED requirements |

**Source of truth files**:
- `openspec/specs/ui-workspace-shell/spec.md`
- `openspec/specs/ui-graph-viewer/spec.md`
- `openspec/specs/render-context/spec.md` (unchanged)

## Out-of-Scope Follow-ups (non-blocking)

| Item | Context |
|------|---------|
| Full-feature panel routing (GV-2 partial) | Current routing is stub-only; real module mount routing deferred |
| CSS token de-duplication (`--theme-*` vs `--bg-*`) | Two parallel token systems coexist; cleanup deferred |
| AI Actions wiring | Placeholder accordion stub with disabled buttons |
| Tab persistence + multi-tab | Phase A #3 `sqlite-graph-store` territory |
| 7 golden fixture failures | Pre-existing, unrelated to shell migration |

## Roadmap Next Step

**Phase A #3: `sqlite-graph-store`** — Establish SQLite as the canonical project-scoped persistence layer (schemas, migrations, indices for nodes/edges/clusters/embeddings). This change will consume the workspace shell from #2 without further template changes.

---

## Result Contract

- **status**: success
- **executive_summary**: Archived `workspace-shell-layout-migration` — 5-column workspace shell shipped replacing the 3-column flat grid with full visual deprecation of old UI, 14/14 tasks complete, 113/113 viewer tests green, 7 pre-existing unrelated golden failures noted. User accepted the revised high-fidelity remediation preview.
- **artifacts**: Archive at `openspec/changes/archive/2026-05-20-workspace-shell-layout-migration/` (9 artifacts + 3 delta specs + 6 review previews + remediation preview). Main specs updated: `openspec/specs/ui-workspace-shell/spec.md`, `openspec/specs/ui-graph-viewer/spec.md`. Engram topic `sdd/workspace-shell-layout-migration/archive-report` #892.
- **next_recommended**: Phase A #3 `sqlite-graph-store` — roadmap entry #3
- **risks**: None blocking. 7 pre-existing unrelated golden fixture failures. GV-2 panel routing is stub-only (partial compliance).
- **skill_resolution**: injected — cognitive-doc-design, ui-design, spectacular-frontend-ui
