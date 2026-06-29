# Helios Retail Data Source Documentation Workspace

This folder contains synthetic operational extracts for a BrainDS source-documentation run.
Use `PROMPT.md` and the files under `sources/` to document the source, identify owners,
capture caveats, and map the source into the graph through the orchestrator-led workflow.

## Visible sources

| Source | Business meaning |
|---|---|
| `source_catalog.csv` | Candidate source names, business owner, domain, and refresh cadence |
| `orders.csv` | Order-level transaction facts used by commerce and finance teams |
| `customers.csv` | Customer master attributes used to segment order analysis |
