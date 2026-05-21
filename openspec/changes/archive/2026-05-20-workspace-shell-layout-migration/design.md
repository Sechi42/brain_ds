# Design: Workspace Shell Layout Migration

## Technical Approach
Implement a **New-UI Adapter** shell in `brain_ds/ui/templates/graph_viewer.html`: existing modules and inline handlers keep supplying behavior/data, but the visible UI is rebuilt to match Sections 1–5. Old panels/labels/empty states are **not** preserved as visible blocks. Legacy ids remain only as stable anchors, adapter roots, or hidden compatibility nodes where runtime continuity requires them.

## Architecture Decisions

### Decision: Shell owns visuals; modules own behavior
**Choice**: Search, filters, tree, score, and detail APIs become providers mounted inside new shell cards/accordions.
**Alternatives considered**: Restyle old left/right blocks in place; rewrite modules completely.
**Rationale**: The user rejected the old UI. This preserves runtime hooks without preserving disliked visuals.

### Decision: Preserve ids, expose new shell selectors
**Choice**: Keep required ids (`#node-search`, `#type-filters`, `#legend`, `#score-threshold-slider`, `#toggle-*`, `#zoom-fit`, `#theme-toggle`, `#detail-*`, `#show-more`, `#hide-markdown`, `#network`) while visible UI uses `data-shell-*`, `data-panel-*`, and Section 1/3 classes.
**Alternatives considered**: Full selector rewrite now.
**Rationale**: Tests, inline JS, and `window.brainDsUI.*.mount()` already depend on those anchors.

### Decision: Inspector adapter, not renderer rewrite
**Choice**: `#detail-panel` stays the behavior host, while `renderInspectorShell(state)` maps empty/selected/multi-select content into Section 2/5 inspector accordions and preview/card treatments.
**Alternatives considered**: Keep old visible empty state; refactor `detail-panel.ts` internals first.
**Rationale**: W6/W7 behavior stays intact, but final visuals become the new inspector contract.

## Data Flow
`rail/tab/toolbar action → shellRouter → adapter slot/root → existing module mount or inline renderer → preserved id/state update → network/detail behavior`

`#center-split` still owns `#network`, `#markdown-reader`, overlays, and split behavior. Left and right panels become shell surfaces around those anchors, not the old UI itself.

## File Changes
| File | Action | Description |
|---|---|---|
| `brain_ds/ui/templates/graph_viewer.html` | Modify | Replace visible 3-column chrome with 5-column shell, adapter roots, and new shell selectors |
| `brain_ds/ui/src/panels/detail-panel.ts` | Reuse/adapt | Preserve detail behavior contract; allow shell classification hooks only if needed |
| `tests/test_viewer.py` | Modify | Assert new shell structure, new visual contracts, and preserved ids |
| `tests/test_ui_runtime_behavior.py` | Modify | Keep runtime harnesses aligned with adapter roots and preserved anchors |
| `brain_ds/ui/workspace_storage_contract.py` | Reuse | Keep tab/history contract unchanged |

## Interfaces / Contracts
| Surface | New visible contract | Preserved behavior anchors |
|---|---|---|
| Search | Compact Section 1 command/search surface, not old “Search node” block | `#node-search`, `#search-results` |
| Filters | Grouped cards/chips/toggles, not raw checkbox list | `#type-filters`, `#show-all`, `#hide-all` |
| Score | Compact control row | `#score-threshold-slider`, `#score-badge` |
| Legend | Compact visual key / collapsible card, not bullet list | `#legend` |
| Hierarchy | New shell card around tree interactions | `#tree-panel`, `#tree-filter-chip` |
| Layout | Section 1/3 button catalog patterns; Hierarchical/Physics in panel, zoom/theme in toolbar overflow | `#toggle-hierarchical`, `#toggle-physics`, `#zoom-fit`, `#theme-toggle`, `#show-more`, `#hide-markdown` |
| Inspector | Section 2/5 accordion + preview/card empty/selected states; old empty copy is fallback-only | `#detail-panel`, `#detail-title`, `#detail-meta`, `#detail-body`, `#detail-collapse`, `#detail-close` |

## Testing Strategy
| Layer | What to Test | Approach |
|---|---|---|
| Unit | `refs` map, route config, inspector classifier | DOM-light adapter tests |
| Integration | Single active panel, mount/unmount continuity, toolbar/layout redistribution | Template/runtime harness assertions |
| E2E | Drawer behavior, focus trap, empty vs selected inspector states, preserved ids under new shell | Existing Python + JS runtime tests |

## Migration / Rollout
1. Add shell scaffold, `data-shell-*` selectors, and adapter roots.
2. Replace left-side visuals route-by-route with new cards/accordions; keep ids mounted inside them.
3. Replace right detail visuals with inspector adapter for empty, selected, and multi-select states.
4. Generalize current mobile slideover logic to both shell panels at `<=1100px`.
5. Update structural/runtime tests and remove visible legacy chrome.

No backend or data migration is required. Rollback is a template/test revert.

## Open Questions
None.

## Result Contract
- `status`: success
- `executive_summary`: Revised design now makes the shell the visual owner and existing modules the behavior providers, so the live viewer keeps runtime continuity without preserving old UI visuals.
- `artifacts`: `openspec/changes/workspace-shell-layout-migration/design.md`; Engram `sdd/workspace-shell-layout-migration/design`
- `next_recommended`: `sdd-tasks`
- `risks`: adapter misclassification of detail content; hidden-anchor drift; runtime tests coupled to legacy DOM depth
- `skill_resolution`: `injected` — cognitive-doc-design, ui-design, spectacular-frontend-ui rules
