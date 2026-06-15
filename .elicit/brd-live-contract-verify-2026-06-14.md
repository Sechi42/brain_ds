# Business Requirements Document

---

## Header

| Field | Value |
|---|---|
| **Status** | PARTIAL |
| **Version** | 1.0 |
| **Organization** | [[Live Contract Verify]] |
| **Date** | 2026-06-14 |
| **Dataset Fingerprint** | Organization: 1 · Data Source: 3 (sparse) · Department: 0 · Role: 0 · Heuristic: 0 · Tacit Knowledge: 0 · Problem/Improvement Area: 0 · Project: 0 · Risk: 0 · Decision: 0 · KPI: 0 · Solution: 0 |
| **Completeness Gate** | PARTIAL — 10 entity types missing; run elicit-context to close gaps |

---

## 1. Executive Summary

[[Live Contract Verify]] is a synthetic test organization used to validate the brain_ds dual-contract artifact pipeline end-to-end. The organization's data estate currently consists of a single SQLite database ([[orders-db]]) containing two tables: [[customers]] (customer reference dimension) and [[orders]] (sales transaction fact table). Both tables hold 5 rows of synthetic fixture data.

This BRD is **PARTIAL**: organizational actors (Departments, Roles), process context (Heuristics, Decisions, Projects), analytical targets (KPIs, Solutions), and risk/improvement knowledge are not yet captured in the graph. Ten entity types require elicitation before a complete BRD can be produced. Sections that cannot be populated are marked `[NEEDS DATA]` with actionable elicitation prompts.

---

## 2. Current State Analysis

### Data Estate

[[Live Contract Verify]] currently operates one documented data source:

**[[orders-db]]** — SQLite database at `tests/fixtures/synthetic_source.db`. Contains two tables:

- **[[customers]]**: Reference dimension table identifying each customer account by name, commercial segment (`Enterprise`, `SMB`, `Mid Market`) and geographic region (`LATAM`, `North America`, `EMEA`). 5 rows (synthetic). Joins to [[orders]] via `customer_id`.
- **[[orders]]**: Fact table recording individual sales transactions. Each row captures `order_id`, `customer_id` (FK to [[customers]]), `order_total` (REAL; range observed: 980.0–12,500.5; currency unit unconfirmed), `status` (`fulfilled`, `pending`, `cancelled`), and `created_at` (ISO-8601 TEXT — must be cast for date arithmetic). 5 rows (synthetic).

### Known Data Quality Issues

- Row counts are synthetic (5 each); production volume is unknown.
- `segment` and `region` in [[customers]] are free-text with no enforced constraint; canonical lists unconfirmed.
- `order_total` in [[orders]]: currency unit unspecified; decimal precision unverified.
- `created_at` stored as TEXT, not DATE — consumers must cast explicitly.
- `status` enumeration in [[orders]] may have additional values in production beyond the 3 observed.
- No null values observed in either table across all 5 rows (sample too small to confirm production nullability patterns).
- Owner and refresh cadence for all three data sources are unknown.

### Organizational Context

[NEEDS DATA: No Department or Role entities present. To populate this section, answer: (1) Which departments own or consume [[orders-db]]? (2) What roles are responsible for data quality, ingestion, and analysis of [[customers]] and [[orders]]?]

---

## 3. Requirements

### Confirmed Data Requirements

| # | Requirement | Source Node | Priority | Notes |
|---|---|---|---|---|
| R-01 | Canonical `segment` value list for [[customers]] | [[customers]] | High | Free-text field; enumeration unconfirmed |
| R-02 | Canonical `region` value list for [[customers]] | [[customers]] | High | Free-text field; enumeration unconfirmed |
| R-03 | Currency unit for `order_total` in [[orders]] | [[orders]] | High | Observed REAL values; unit missing |
| R-04 | Full canonical `status` enumeration for [[orders]] | [[orders]] | Medium | 3 values observed; production may have more |
| R-05 | Production row volume for [[customers]] and [[orders]] | [[orders-db]] | Medium | Current 5-row count is synthetic fixture only |
| R-06 | Refresh cadence for [[orders-db]] | [[orders-db]] | Medium | Batch, CDC, streaming, or manual unknown |
| R-07 | Owner / data platform team for [[orders-db]] | [[orders-db]] | Medium | Listed as "unknown" on all three source nodes |
| R-08 | Confirm whether FK `customer_id` is enforced or inferred | [[orders]] | Low | No constraint observed; may be a soft join |
| R-09 | Confirm `created_at` time-component behavior in production | [[orders]] | Low | Only date component observed in fixture |

[NEEDS DATA: Business/functional requirements (beyond data quality) cannot be derived without KPI, Problem, Project, and Role entities. Elicit those types to extend this table.]

---

## 4. Data Sources & Dependencies

### Documented Sources

| Source | Engine | Path | Tables | Rows (sample) | Owner | Cadence |
|---|---|---|---|---|---|---|
| [[orders-db]] | SQLite | `tests/fixtures/synthetic_source.db` | `customers`, `orders` | 5 each | unknown | unknown |
| [[customers]] | SQLite (table) | `main.customers` | — | 5 | unknown | unknown |
| [[orders]] | SQLite (table) | `main.orders` | — | 5 | unknown | unknown |

### Lineage

- [[Live Contract Verify]] owns [[orders-db]]
- [[orders-db]] contains [[customers]]
- [[orders-db]] contains [[orders]]
- [[orders]] references [[customers]] via `customer_id` (inferred FK)

### Open Gaps on Sources

- Canonical value lists for `segment`, `region`, `status` fields
- Currency unit for `order_total`
- Production volume, refresh cadence, and ownership for all three sources
- Whether `customer_id` is system-generated or sourced from an upstream CRM

---

## 5. Stakeholder Impact

[NEEDS DATA: No Department or Role entities are present in the graph. To populate this section, answer: (1) Which teams or roles consume data from [[orders-db]]? (2) Who are the primary decision-makers for changes to [[customers]] or [[orders]] schema? (3) Are there external stakeholders (customers, regulators) affected by this data?]

---

## 6. Solution Options

[NEEDS DATA: No Solution entities are present in the graph. Solutions cannot be evaluated without first capturing Problems/Improvement Areas and KPIs. To populate this section: (1) Run elicit-context to capture Problem entities, (2) Define target KPIs, (3) Then propose Solution entities linked to those problems and metrics.]

---

## 7. ADR Log

[NEEDS DATA: No Decision entities are present in the graph. To populate this section, answer: (1) What architectural or data decisions have been made regarding [[orders-db]]? (2) Were there alternatives considered for the SQLite storage engine? (3) Were any decisions made about the `customer_id` FK enforcement strategy?]

---

## 8. Data Provenance

### Source Lineage Graph

```
[[Live Contract Verify]]
  └── owns ──► [[orders-db]]  (SQLite · tests/fixtures/synthetic_source.db)
                  ├── contains ──► [[customers]]  (dimension · 5 rows synthetic)
                  └── contains ──► [[orders]]     (fact · 5 rows synthetic)
                                       └── references ──► [[customers]] via customer_id (inferred FK)
```

### Provenance Notes

- All three data source nodes were documented from a live SQLite exploration of `tests/fixtures/synthetic_source.db`.
- Row counts (5 each) reflect the synthetic fixture; production volumes are unconfirmed.
- The FK relationship `orders.customer_id → customers.customer_id` is inferred from column naming and observed data; no SQLite `FOREIGN KEY` constraint was observed (SQLite does not enforce FKs by default).
- Ownership chain beyond [[Live Contract Verify]] is undocumented.

---

## 9. Risk Register

[NEEDS DATA: No Risk entities are present in the graph. To populate this section, answer: (1) What are the operational risks of relying on [[orders-db]] as a SQLite file? (2) What happens if [[customers]] and [[orders]] diverge (orphaned customer_id values)? (3) Are there compliance or data-privacy risks associated with customer name and segment data in [[customers]]?]

---

## 10. Cross-Dept Overlap Map

[NEEDS DATA: No Department entities are present in the graph. To populate this section, answer: (1) Which departments share access to [[orders-db]]? (2) Are there overlapping ownership or reporting responsibilities between departments for [[customers]] or [[orders]] data?]

---

## 11. Project Portfolio

[NEEDS DATA: No Project entities are present in the graph. To populate this section, answer: (1) What projects are currently consuming or modifying [[orders-db]]? (2) Are there planned projects to migrate [[orders-db]] to a production-grade store? (3) What is the timeline for resolving the open data quality gaps in [[customers]] and [[orders]]?]

---

## 12. KPI Dashboard

[NEEDS DATA: No KPI entities are present in the graph. To populate this section, define KPIs that this data estate should support. Example prompts: (1) What revenue metrics should [[orders]] power? (2) What fulfillment rate targets exist for the `status` field in [[orders]]? (3) What customer segmentation metrics are derived from [[customers]].`segment` and `.region`?]

---

## 13. Improvement Roadmap

[NEEDS DATA: No Solution entities are present in the graph. To populate this section: (1) Capture Problem/Improvement Area entities first, (2) Define KPIs as targets, (3) Then propose Solution entities. Candidate improvement areas inferred from data quality gaps: schema enforcement for `segment`/`region`/`status` enumerations; DATE typing for `created_at`; FK enforcement for `customer_id`; production data volume confirmation.]

---

## 14. Appendix

### Completeness Matrix

| Entity Type | Count | BRD Status |
|---|---|---|
| Organization | 1 | present |
| Data Source | 3 | sparse (owner + cadence unknown on all) |
| Department | 0 | missing |
| Role | 0 | missing |
| Heuristic | 0 | missing |
| Tacit Knowledge | 0 | missing |
| Problem / Improvement Area | 0 | missing |
| Project | 0 | missing |
| Risk | 0 | missing |
| Decision | 0 | missing |
| KPI | 0 | missing |
| Solution | 0 | missing |

### Next Steps to Reach COMPLETE BRD

1. Run `elicit-context` for [[Live Contract Verify]] to capture Department, Role, Problem/Improvement Area, Risk, Decision, KPI, Project, Heuristic, and Tacit Knowledge entities.
2. Resolve [[orders-db]] owner and refresh cadence (ask data platform team).
3. Confirm canonical value lists for `segment`, `region`, `status` fields.
4. Confirm currency unit for `order_total` in [[orders]].
5. Re-run `generate-brd --save` once the matrix reaches COMPLETE.

<!-- canonical-payload -->
```json
{"artifact_type":"brd","graph_id":"live-contract-verify","markdown":"# Business Requirements Document\n\n---\n\n## Header\n\n| Field | Value |\n|---|---|\n| **Status** | PARTIAL |\n| **Version** | 1.0 |\n| **Organization** | [[Live Contract Verify]] |\n| **Date** | 2026-06-14 |\n| **Dataset Fingerprint** | Organization: 1 · Data Source: 3 (sparse) · Department: 0 · Role: 0 · Heuristic: 0 · Tacit Knowledge: 0 · Problem/Improvement Area: 0 · Project: 0 · Risk: 0 · Decision: 0 · KPI: 0 · Solution: 0 |\n| **Completeness Gate** | PARTIAL — 10 entity types missing; run elicit-context to close gaps |\n\n---\n\n## 1. Executive Summary\n\n[[Live Contract Verify]] is a synthetic test organization used to validate the brain_ds dual-contract artifact pipeline end-to-end. The organization's data estate currently consists of a single SQLite database ([[orders-db]]) containing two tables: [[customers]] (customer reference dimension) and [[orders]] (sales transaction fact table). Both tables hold 5 rows of synthetic fixture data.\n\nThis BRD is **PARTIAL**: organizational actors (Departments, Roles), process context (Heuristics, Decisions, Projects), analytical targets (KPIs, Solutions), and risk/improvement knowledge are not yet captured in the graph. Ten entity types require elicitation before a complete BRD can be produced. Sections that cannot be populated are marked `[NEEDS DATA]` with actionable elicitation prompts.\n\n---\n\n## 2. Current State Analysis\n\n### Data Estate\n\n[[Live Contract Verify]] currently operates one documented data source:\n\n**[[orders-db]]** — SQLite database at `tests/fixtures/synthetic_source.db`. Contains two tables:\n\n- **[[customers]]**: Reference dimension table identifying each customer account by name, commercial segment (`Enterprise`, `SMB`, `Mid Market`) and geographic region (`LATAM`, `North America`, `EMEA`). 5 rows (synthetic). Joins to [[orders]] via `customer_id`.\n- **[[orders]]**: Fact table recording individual sales transactions. Each row captures `order_id`, `customer_id` (FK to [[customers]]), `order_total` (REAL; range observed: 980.0–12,500.5; currency unit unconfirmed), `status` (`fulfilled`, `pending`, `cancelled`), and `created_at` (ISO-8601 TEXT — must be cast for date arithmetic). 5 rows (synthetic).\n\n### Known Data Quality Issues\n\n- Row counts are synthetic (5 each); production volume is unknown.\n- `segment` and `region` in [[customers]] are free-text with no enforced constraint; canonical lists unconfirmed.\n- `order_total` in [[orders]]: currency unit unspecified; decimal precision unverified.\n- `created_at` stored as TEXT, not DATE — consumers must cast explicitly.\n- `status` enumeration in [[orders]] may have additional values in production beyond the 3 observed.\n- No null values observed in either table across all 5 rows (sample too small to confirm production nullability patterns).\n- Owner and refresh cadence for all three data sources are unknown.\n\n### Organizational Context\n\n[NEEDS DATA: No Department or Role entities present. To populate this section, answer: (1) Which departments own or consume [[orders-db]]? (2) What roles are responsible for data quality, ingestion, and analysis of [[customers]] and [[orders]]?]\n\n---\n\n## 3. Requirements\n\n### Confirmed Data Requirements\n\n| # | Requirement | Source Node | Priority | Notes |\n|---|---|---|---|---|\n| R-01 | Canonical `segment` value list for [[customers]] | [[customers]] | High | Free-text field; enumeration unconfirmed |\n| R-02 | Canonical `region` value list for [[customers]] | [[customers]] | High | Free-text field; enumeration unconfirmed |\n| R-03 | Currency unit for `order_total` in [[orders]] | [[orders]] | High | Observed REAL values; unit missing |\n| R-04 | Full canonical `status` enumeration for [[orders]] | [[orders]] | Medium | 3 values observed; production may have more |\n| R-05 | Production row volume for [[customers]] and [[orders]] | [[orders-db]] | Medium | Current 5-row count is synthetic fixture only |\n| R-06 | Refresh cadence for [[orders-db]] | [[orders-db]] | Medium | Batch, CDC, streaming, or manual unknown |\n| R-07 | Owner / data platform team for [[orders-db]] | [[orders-db]] | Medium | Listed as \"unknown\" on all three source nodes |\n| R-08 | Confirm whether FK `customer_id` is enforced or inferred | [[orders]] | Low | No constraint observed; may be a soft join |\n| R-09 | Confirm `created_at` time-component behavior in production | [[orders]] | Low | Only date component observed in fixture |\n\n[NEEDS DATA: Business/functional requirements (beyond data quality) cannot be derived without KPI, Problem, Project, and Role entities. Elicit those types to extend this table.]\n\n---\n\n## 4. Data Sources & Dependencies\n\n### Documented Sources\n\n| Source | Engine | Path | Tables | Rows (sample) | Owner | Cadence |\n|---|---|---|---|---|---|---|\n| [[orders-db]] | SQLite | `tests/fixtures/synthetic_source.db` | `customers`, `orders` | 5 each | unknown | unknown |\n| [[customers]] | SQLite (table) | `main.customers` | — | 5 | unknown | unknown |\n| [[orders]] | SQLite (table) | `main.orders` | — | 5 | unknown | unknown |\n\n### Lineage\n\n- [[Live Contract Verify]] owns [[orders-db]]\n- [[orders-db]] contains [[customers]]\n- [[orders-db]] contains [[orders]]\n- [[orders]] references [[customers]] via `customer_id` (inferred FK)\n\n### Open Gaps on Sources\n\n- Canonical value lists for `segment`, `region`, `status` fields\n- Currency unit for `order_total`\n- Production volume, refresh cadence, and ownership for all three sources\n- Whether `customer_id` is system-generated or sourced from an upstream CRM\n\n---\n\n## 5. Stakeholder Impact\n\n[NEEDS DATA: No Department or Role entities are present in the graph. To populate this section, answer: (1) Which teams or roles consume data from [[orders-db]]? (2) Who are the primary decision-makers for changes to [[customers]] or [[orders]] schema? (3) Are there external stakeholders (customers, regulators) affected by this data?]\n\n---\n\n## 6. Solution Options\n\n[NEEDS DATA: No Solution entities are present in the graph. Solutions cannot be evaluated without first capturing Problems/Improvement Areas and KPIs. To populate this section: (1) Run elicit-context to capture Problem entities, (2) Define target KPIs, (3) Then propose Solution entities linked to those problems and metrics.]\n\n---\n\n## 7. ADR Log\n\n[NEEDS DATA: No Decision entities are present in the graph. To populate this section, answer: (1) What architectural or data decisions have been made regarding [[orders-db]]? (2) Were there alternatives considered for the SQLite storage engine? (3) Were any decisions made about the `customer_id` FK enforcement strategy?]\n\n---\n\n## 8. Data Provenance\n\n### Source Lineage Graph\n\n```\n[[Live Contract Verify]]\n  └── owns ──► [[orders-db]]  (SQLite · tests/fixtures/synthetic_source.db)\n                  ├── contains ──► [[customers]]  (dimension · 5 rows synthetic)\n                  └── contains ──► [[orders]]     (fact · 5 rows synthetic)\n                                       └── references ──► [[customers]] via customer_id (inferred FK)\n```\n\n### Provenance Notes\n\n- All three data source nodes were documented from a live SQLite exploration of `tests/fixtures/synthetic_source.db`.\n- Row counts (5 each) reflect the synthetic fixture; production volumes are unconfirmed.\n- The FK relationship `orders.customer_id → customers.customer_id` is inferred from column naming and observed data; no SQLite `FOREIGN KEY` constraint was observed (SQLite does not enforce FKs by default).\n- Ownership chain beyond [[Live Contract Verify]] is undocumented.\n\n---\n\n## 9. Risk Register\n\n[NEEDS DATA: No Risk entities are present in the graph. To populate this section, answer: (1) What are the operational risks of relying on [[orders-db]] as a SQLite file? (2) What happens if [[customers]] and [[orders]] diverge (orphaned customer_id values)? (3) Are there compliance or data-privacy risks associated with customer name and segment data in [[customers]]?]\n\n---\n\n## 10. Cross-Dept Overlap Map\n\n[NEEDS DATA: No Department entities are present in the graph. To populate this section, answer: (1) Which departments share access to [[orders-db]]? (2) Are there overlapping ownership or reporting responsibilities between departments for [[customers]] or [[orders]] data?]\n\n---\n\n## 11. Project Portfolio\n\n[NEEDS DATA: No Project entities are present in the graph. To populate this section, answer: (1) What projects are currently consuming or modifying [[orders-db]]? (2) Are there planned projects to migrate [[orders-db]] to a production-grade store? (3) What is the timeline for resolving the open data quality gaps in [[customers]] and [[orders]]?]\n\n---\n\n## 12. KPI Dashboard\n\n[NEEDS DATA: No KPI entities are present in the graph. To populate this section, define KPIs that this data estate should support. Example prompts: (1) What revenue metrics should [[orders]] power? (2) What fulfillment rate targets exist for the `status` field in [[orders]]? (3) What customer segmentation metrics are derived from [[customers]].`segment` and `.region`?]\n\n---\n\n## 13. Improvement Roadmap\n\n[NEEDS DATA: No Solution entities are present in the graph. To populate this section: (1) Capture Problem/Improvement Area entities first, (2) Define KPIs as targets, (3) Then propose Solution entities. Candidate improvement areas inferred from data quality gaps: schema enforcement for `segment`/`region`/`status` enumerations; DATE typing for `created_at`; FK enforcement for `customer_id`; production data volume confirmation.]\n\n---\n\n## 14. Appendix\n\n### Completeness Matrix\n\n| Entity Type | Count | BRD Status |\n|---|---|---|\n| Organization | 1 | present |\n| Data Source | 3 | sparse (owner + cadence unknown on all) |\n| Department | 0 | missing |\n| Role | 0 | missing |\n| Heuristic | 0 | missing |\n| Tacit Knowledge | 0 | missing |\n| Problem / Improvement Area | 0 | missing |\n| Project | 0 | missing |\n| Risk | 0 | missing |\n| Decision | 0 | missing |\n| KPI | 0 | missing |\n| Solution | 0 | missing |\n\n### Next Steps to Reach COMPLETE BRD\n\n1. Run `elicit-context` for [[Live Contract Verify]] to capture Department, Role, Problem/Improvement Area, Risk, Decision, KPI, Project, Heuristic, and Tacit Knowledge entities.\n2. Resolve [[orders-db]] owner and refresh cadence (ask data platform team).\n3. Confirm canonical value lists for `segment`, `region`, `status` fields.\n4. Confirm currency unit for `order_total` in [[orders]].\n5. Re-run `generate-brd --save` once the matrix reaches COMPLETE.\n","brd_node":{"node_id":"brd-live-contract-verify","label":"BRD","type":"Unknown","card_sections":[{"title":"Contenido","content":"# Business Requirements Document\n\n---\n\n## Header\n\n| Field | Value |\n|---|---|\n| **Status** | PARTIAL |\n| **Version** | 1.0 |\n| **Organization** | [[Live Contract Verify]] |\n| **Date** | 2026-06-14 |\n| **Dataset Fingerprint** | Organization: 1 · Data Source: 3 (sparse) · Department: 0 · Role: 0 · Heuristic: 0 · Tacit Knowledge: 0 · Problem/Improvement Area: 0 · Project: 0 · Risk: 0 · Decision: 0 · KPI: 0 · Solution: 0 |\n| **Completeness Gate** | PARTIAL — 10 entity types missing; run elicit-context to close gaps |\n\n---\n\n## 1. Executive Summary\n\n[[Live Contract Verify]] is a synthetic test organization used to validate the brain_ds dual-contract artifact pipeline end-to-end. The organization's data estate currently consists of a single SQLite database ([[orders-db]]) containing two tables: [[customers]] (customer reference dimension) and [[orders]] (sales transaction fact table). Both tables hold 5 rows of synthetic fixture data.\n\nThis BRD is **PARTIAL**: organizational actors (Departments, Roles), process context (Heuristics, Decisions, Projects), analytical targets (KPIs, Solutions), and risk/improvement knowledge are not yet captured in the graph. Ten entity types require elicitation before a complete BRD can be produced. Sections that cannot be populated are marked `[NEEDS DATA]` with actionable elicitation prompts.\n\n---\n\n## 2. Current State Analysis\n\n### Data Estate\n\n[[Live Contract Verify]] currently operates one documented data source:\n\n**[[orders-db]]** — SQLite database at `tests/fixtures/synthetic_source.db`. Contains two tables:\n\n- **[[customers]]**: Reference dimension table identifying each customer account by name, commercial segment (`Enterprise`, `SMB`, `Mid Market`) and geographic region (`LATAM`, `North America`, `EMEA`). 5 rows (synthetic). Joins to [[orders]] via `customer_id`.\n- **[[orders]]**: Fact table recording individual sales transactions. Each row captures `order_id`, `customer_id` (FK to [[customers]]), `order_total` (REAL; range observed: 980.0–12,500.5; currency unit unconfirmed), `status` (`fulfilled`, `pending`, `cancelled`), and `created_at` (ISO-8601 TEXT — must be cast for date arithmetic). 5 rows (synthetic).\n\n### Known Data Quality Issues\n\n- Row counts are synthetic (5 each); production volume is unknown.\n- `segment` and `region` in [[customers]] are free-text with no enforced constraint; canonical lists unconfirmed.\n- `order_total` in [[orders]]: currency unit unspecified; decimal precision unverified.\n- `created_at` stored as TEXT, not DATE — consumers must cast explicitly.\n- `status` enumeration in [[orders]] may have additional values in production beyond the 3 observed.\n- No null values observed in either table across all 5 rows (sample too small to confirm production nullability patterns).\n- Owner and refresh cadence for all three data sources are unknown.\n\n### Organizational Context\n\n[NEEDS DATA: No Department or Role entities present. To populate this section, answer: (1) Which departments own or consume [[orders-db]]? (2) What roles are responsible for data quality, ingestion, and analysis of [[customers]] and [[orders]]?]\n\n---\n\n## 3. Requirements\n\n### Confirmed Data Requirements\n\n| # | Requirement | Source Node | Priority | Notes |\n|---|---|---|---|---|\n| R-01 | Canonical `segment` value list for [[customers]] | [[customers]] | High | Free-text field; enumeration unconfirmed |\n| R-02 | Canonical `region` value list for [[customers]] | [[customers]] | High | Free-text field; enumeration unconfirmed |\n| R-03 | Currency unit for `order_total` in [[orders]] | [[orders]] | High | Observed REAL values; unit missing |\n| R-04 | Full canonical `status` enumeration for [[orders]] | [[orders]] | Medium | 3 values observed; production may have more |\n| R-05 | Production row volume for [[customers]] and [[orders]] | [[orders-db]] | Medium | Current 5-row count is synthetic fixture only |\n| R-06 | Refresh cadence for [[orders-db]] | [[orders-db]] | Medium | Batch, CDC, streaming, or manual unknown |\n| R-07 | Owner / data platform team for [[orders-db]] | [[orders-db]] | Medium | Listed as \"unknown\" on all three source nodes |\n| R-08 | Confirm whether FK `customer_id` is enforced or inferred | [[orders]] | Low | No constraint observed; may be a soft join |\n| R-09 | Confirm `created_at` time-component behavior in production | [[orders]] | Low | Only date component observed in fixture |\n\n[NEEDS DATA: Business/functional requirements (beyond data quality) cannot be derived without KPI, Problem, Project, and Role entities. Elicit those types to extend this table.]\n\n---\n\n## 4. Data Sources & Dependencies\n\n### Documented Sources\n\n| Source | Engine | Path | Tables | Rows (sample) | Owner | Cadence |\n|---|---|---|---|---|---|---|\n| [[orders-db]] | SQLite | `tests/fixtures/synthetic_source.db` | `customers`, `orders` | 5 each | unknown | unknown |\n| [[customers]] | SQLite (table) | `main.customers` | — | 5 | unknown | unknown |\n| [[orders]] | SQLite (table) | `main.orders` | — | 5 | unknown | unknown |\n\n### Lineage\n\n- [[Live Contract Verify]] owns [[orders-db]]\n- [[orders-db]] contains [[customers]]\n- [[orders-db]] contains [[orders]]\n- [[orders]] references [[customers]] via `customer_id` (inferred FK)\n\n### Open Gaps on Sources\n\n- Canonical value lists for `segment`, `region`, `status` fields\n- Currency unit for `order_total`\n- Production volume, refresh cadence, and ownership for all three sources\n- Whether `customer_id` is system-generated or sourced from an upstream CRM\n\n---\n\n## 5. Stakeholder Impact\n\n[NEEDS DATA: No Department or Role entities are present in the graph. To populate this section, answer: (1) Which teams or roles consume data from [[orders-db]]? (2) Who are the primary decision-makers for changes to [[customers]] or [[orders]] schema? (3) Are there external stakeholders (customers, regulators) affected by this data?]\n\n---\n\n## 6. Solution Options\n\n[NEEDS DATA: No Solution entities are present in the graph. Solutions cannot be evaluated without first capturing Problems/Improvement Areas and KPIs. To populate this section: (1) Run elicit-context to capture Problem entities, (2) Define target KPIs, (3) Then propose Solution entities linked to those problems and metrics.]\n\n---\n\n## 7. ADR Log\n\n[NEEDS DATA: No Decision entities are present in the graph. To populate this section, answer: (1) What architectural or data decisions have been made regarding [[orders-db]]? (2) Were there alternatives considered for the SQLite storage engine? (3) Were any decisions made about the `customer_id` FK enforcement strategy?]\n\n---\n\n## 8. Data Provenance\n\n### Source Lineage Graph\n\n```\n[[Live Contract Verify]]\n  └── owns ──► [[orders-db]]  (SQLite · tests/fixtures/synthetic_source.db)\n                  ├── contains ──► [[customers]]  (dimension · 5 rows synthetic)\n                  └── contains ──► [[orders]]     (fact · 5 rows synthetic)\n                                       └── references ──► [[customers]] via customer_id (inferred FK)\n```\n\n### Provenance Notes\n\n- All three data source nodes were documented from a live SQLite exploration of `tests/fixtures/synthetic_source.db`.\n- Row counts (5 each) reflect the synthetic fixture; production volumes are unconfirmed.\n- The FK relationship `orders.customer_id → customers.customer_id` is inferred from column naming and observed data; no SQLite `FOREIGN KEY` constraint was observed (SQLite does not enforce FKs by default).\n- Ownership chain beyond [[Live Contract Verify]] is undocumented.\n\n---\n\n## 9. Risk Register\n\n[NEEDS DATA: No Risk entities are present in the graph. To populate this section, answer: (1) What are the operational risks of relying on [[orders-db]] as a SQLite file? (2) What happens if [[customers]] and [[orders]] diverge (orphaned customer_id values)? (3) Are there compliance or data-privacy risks associated with customer name and segment data in [[customers]]?]\n\n---\n\n## 10. Cross-Dept Overlap Map\n\n[NEEDS DATA: No Department entities are present in the graph. To populate this section, answer: (1) Which departments share access to [[orders-db]]? (2) Are there overlapping ownership or reporting responsibilities between departments for [[customers]] or [[orders]] data?]\n\n---\n\n## 11. Project Portfolio\n\n[NEEDS DATA: No Project entities are present in the graph. To populate this section, answer: (1) What projects are currently consuming or modifying [[orders-db]]? (2) Are there planned projects to migrate [[orders-db]] to a production-grade store? (3) What is the timeline for resolving the open data quality gaps in [[customers]] and [[orders]]?]\n\n---\n\n## 12. KPI Dashboard\n\n[NEEDS DATA: No KPI entities are present in the graph. To populate this section, define KPIs that this data estate should support. Example prompts: (1) What revenue metrics should [[orders]] power? (2) What fulfillment rate targets exist for the `status` field in [[orders]]? (3) What customer segmentation metrics are derived from [[customers]].`segment` and `.region`?]\n\n---\n\n## 13. Improvement Roadmap\n\n[NEEDS DATA: No Solution entities are present in the graph. To populate this section: (1) Capture Problem/Improvement Area entities first, (2) Define KPIs as targets, (3) Then propose Solution entities. Candidate improvement areas inferred from data quality gaps: schema enforcement for `segment`/`region`/`status` enumerations; DATE typing for `created_at`; FK enforcement for `customer_id`; production data volume confirmation.]\n\n---\n\n## 14. Appendix\n\n### Completeness Matrix\n\n| Entity Type | Count | BRD Status |\n|---|---|---|\n| Organization | 1 | present |\n| Data Source | 3 | sparse (owner + cadence unknown on all) |\n| Department | 0 | missing |\n| Role | 0 | missing |\n| Heuristic | 0 | missing |\n| Tacit Knowledge | 0 | missing |\n| Problem / Improvement Area | 0 | missing |\n| Project | 0 | missing |\n| Risk | 0 | missing |\n| Decision | 0 | missing |\n| KPI | 0 | missing |\n| Solution | 0 | missing |\n\n### Next Steps to Reach COMPLETE BRD\n\n1. Run `elicit-context` for [[Live Contract Verify]] to capture Department, Role, Problem/Improvement Area, Risk, Decision, KPI, Project, Heuristic, and Tacit Knowledge entities.\n2. Resolve [[orders-db]] owner and refresh cadence (ask data platform team).\n3. Confirm canonical value lists for `segment`, `region`, `status` fields.\n4. Confirm currency unit for `order_total` in [[orders]].\n5. Re-run `generate-brd --save` once the matrix reaches COMPLETE.\n","order":0,"icon":""}]},"completeness_gate":{"pre_mapping_recommendation":"elicit"}}
```
