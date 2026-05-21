# Spec: workspace-shell-layout-migration

**Change**: workspace-shell-layout-migration  
**Roadmap**: backend-migration-to-new-ui, Phase A #2  
**Artifact store**: hybrid  
**Engram**: topic_key `sdd/workspace-shell-layout-migration/spec`, obs #868  
**Revision**: 2 — old visual deprecation + new-shell visual language requirements added per obs #869

## Domain Specs

| Domain | File | Type |
|--------|------|------|
| ui-workspace-shell | [specs/ui-workspace-shell/spec.md](specs/ui-workspace-shell/spec.md) | Delta (12 ADDED, 3 MODIFIED) |
| ui-graph-viewer | [specs/ui-graph-viewer/spec.md](specs/ui-graph-viewer/spec.md) | Delta (3 ADDED, 2 MODIFIED) |
| render-context | [specs/render-context/spec.md](specs/render-context/spec.md) | Delta (affirmation only — unchanged) |

## Summary

| Metric | Count |
|--------|-------|
| Requirements (ADDED) | 15 |
| Requirements (MODIFIED) | 5 |
| Scenarios | 42 |
| Test names registered | 38 |
| Domains | 3 |

**Key revision changes (v2)**:
- Old sidebar visual sections are explicitly deprecated as visible UI (WS-9).
- Left rail panels MUST use Section 1 visual language: compact cards, accordions, token-true surfaces, toggle chips, tree rows — no old fieldset/list/raw-block styling (WS-10, WS-11).
- Right panel empty state MUST use restrained `.empty-state` with token styling; detail card MUST use Section 2/5 compact card surfaces (WS-12, GV-3 MODIFIED).
- Layout controls MUST render as new-style `.toggle-card` elements, not old raw blocks (WS-11, GV-4 MODIFIED).
- Tests MUST assert absence of old visual labels/classes and presence of new shell classes (WS-8 expanded with assertions 11–13, WS-8-B, WS-8-C).
- IDs preserved only as hidden/anchor/adapters where JS requires them; visible UI uses new components exclusively.

**Preserved**: RENDER_CONTEXT v1.0.0, renderer.ts, panel modules (source unchanged), 602+ existing tests.  
**Non-goals**: SQLite, multi-vault, contract evolution, AI Actions wiring, token de-duplication.  
**Open questions**: None blocking.  
**Next**: sdd-design (revision needed — old visual deprecation must be reflected in design).
