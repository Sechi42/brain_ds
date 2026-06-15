# Map — live-contract-verify — 2026-06-14

## Completeness Gate

`assess_completeness` returned **`pre_mapping_recommendation: elicit`**.

10 entity types have zero nodes: Department, Role, Heuristic, Tacit Knowledge, Problem / Improvement Area, Project, Risk, Decision, KPI, Solution. Per the completeness gate rule, Phase 2 cross-cutting mapping is **blocked**. Run elicit-context before the next mapping pass.

## Phase 1 — Structural Edges (present in graph)

| Source | Label | Target |
|---|---|---|
| customers | depends-on | orders-db |
| orders | depends-on | orders-db |
| orders | uses | customers |
| organization (Live Contract Verify) | owns | orders-db |

## Phase 2 — Cross-Cutting Edges

Blocked. `pre_mapping_recommendation` is `elicit`. No cross-cutting edges mapped.

## Edges Added This Pass

None. `suggest_connections` on the org node returned 0 candidates above threshold 0.5.

## Deferred Candidates

None above threshold to defer.

## Gaps (for orchestrator)

- 10 missing entity types — elicit-context pass required before BRD generation will produce a non-hollow result.
- All 3 Data Source nodes are underspecified (no `where`/`learned` fields populated).

<!-- canonical-payload -->

```json
{"artifact_type":"map","graph_id":"live-contract-verify","documented_nodes":[{"node_id":"live-contract-verify-data-source-orders-db","label":"orders-db","type":"Data Source","card_sections":[{"title":"Lineage","content":"Upstream dependency for both customers and orders data sources. Owned by the Live Contract Verify organization.","icon":"link","order":1}]},{"node_id":"live-contract-verify-data-source-customers","label":"customers","type":"Data Source","card_sections":[{"title":"Lineage","content":"Depends on orders-db. Used by orders.","icon":"link","order":1}]},{"node_id":"live-contract-verify-data-source-orders","label":"orders","type":"Data Source","card_sections":[{"title":"Lineage","content":"Depends on orders-db. Uses customers.","icon":"link","order":1}]},{"node_id":"live-contract-verify-organization-live-contract-verify","label":"Live Contract Verify","type":"Organization","card_sections":[{"title":"Overview","content":"Root organization node for the live-contract-verify graph.","icon":"info","order":1}]}],"edges":[{"source":"live-contract-verify-data-source-customers","target":"live-contract-verify-data-source-orders-db","label":"depends-on"},{"source":"live-contract-verify-data-source-orders","target":"live-contract-verify-data-source-orders-db","label":"depends-on"},{"source":"live-contract-verify-data-source-orders","target":"live-contract-verify-data-source-customers","label":"uses"},{"source":"live-contract-verify-organization-live-contract-verify","target":"live-contract-verify-data-source-orders-db","label":"owns"}],"completeness_gate":{"pre_mapping_recommendation":"elicit"}}
```