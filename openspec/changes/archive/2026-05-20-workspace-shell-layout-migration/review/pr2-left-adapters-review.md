# PR2 — Left Adapters Review

**Change**: workspace-shell-layout-migration  
**Slice**: PR2 — left rail + L-panel adapters  
**Status**: Implementation complete — awaiting user visual review  

---

## What to inspect

Open `pr2-left-adapters-preview.html` in a browser (see command below).

### Left rail

- Five `.rail-icon` buttons (44×44 each) with Lucide icons: folder, search, filter, network, layout
- First icon (`file-tree`) is active: `aria-selected="true"` — should show accent-mora highlight + 2px left-edge indicator (via `_shared.css` `::before` pseudo)
- Remaining icons are inactive: muted color, hover shows `var(--bg-panel-hover)` background
- Focus ring: `2px var(--accent-mora)` outline on keyboard focus
- `role="tablist"` / `aria-orientation="vertical"` on the nav — rail is semantically a vertical tablist
- Rail-icon clicks are **stubs only** — no panel-switching behavior yet (follow-up PRs)

### L-panel header

- 44px header bar: "Graph Controls" title (left) + collapse chevron button (right)
- Collapse button is 44×44 (WCAG 2.5.5 compliant), aria-label="Collapse left panel"
- Header carries `role="region"` + `aria-label="Left panel controls"`

### Controls body (graph controls)

- Controls aside is **visible** (hidden attribute removed in PR2)
- Legacy IDs still present: `#node-search`, `#type-filters`, `#legend`, `#tree-panel`, `#toggle-hierarchical`, `#toggle-physics`, `#score-threshold-slider`, `#score-badge`
- Runtime JS (panels/*.ts, interactions/score-filter.ts) continues to mount into these IDs — no runtime behavior change

### Deprecation continuity

- `.compat-topbar` element still has `hidden` attribute and CSS `display: none` — PR1 deprecation maintained

---

## Out of scope for PR2

- **Right rail / inspector** (`.rail[data-rail-side='right']`, `#detail-panel`, `.right-panel-shell`) — PR3
- **Responsive drawers** (`@media (max-width:1100px)` slide-over behavior) — PR3
- **Rail-icon click BEHAVIOR** (panel routing, panel switching animations) — follow-up PRs
- **Status chip** (org-code badge at bottom of rail per section-1) — deferred, budget risk
- **File-tree panel content** (tree rows, accordion, vault structure) — follow-up PRs

---

## Live viewer PowerShell command

Open the preview in your default browser from the project root:

```powershell
Start-Process "openspec\changes\workspace-shell-layout-migration\review\pr2-left-adapters-preview.html"
```

Or navigate directly in the browser to:

```
C:\Users\evolu\Desktop\Master\brain_ds\openspec\changes\workspace-shell-layout-migration\review\pr2-left-adapters-preview.html
```

---

## Side-by-side comparison reference

Section-1 ground truth:

```
C:\Users\evolu\Desktop\Master\brain_ds\brain_ds\ui\design\sections\section-1-left-shell.html
```

Open both files in browser tabs to compare the left rail icons, active indicator, and panel header pattern.

---

## Test results

- **90 passed** (77 PR1/PR1.5 baseline + 13 PR2 new assertions)
- 0 regressions in existing tests
- `tests/test_render_context_golden.py` — pre-existing failures (out of PR2 scope)

## Files changed

| File | Change |
|------|--------|
| `brain_ds/ui/templates/graph_viewer.html` | Left rail structure (section-1 icons), L-panel header, controls un-hidden, PR2 CSS block |
| `tests/test_viewer.py` | 13 new PR2 assertions (`TestWorkspaceShellPr2LeftAdapters`) |
| `openspec/.../pr2-left-adapters-preview.html` | Standalone review preview |
| `openspec/.../pr2-left-adapters-review.md` | This file |
