# Blind Agentic Eval Maintainer Runbook

Use this runbook to execute the blind Revenue Ops agentic evaluation manually with OpenCode membership access. The subject agent must only see the generated subject workspace; evaluator-only files stay in the repository for offline scoring.

## Quick path

1. From the repo root, prepare a fresh subject workspace.
2. Open OpenCode in the subject folder and paste the blind prompt exactly.
3. After the run stops, run the one-command collect + score path from the repo root.
4. Read `tmp/blind-agentic-eval/<run_id>/evidence/manifest.json` first, then the deterministic score report.
5. Optional: generate an evaluator-only judge packet for manual advisory review.

This runbook spans the legacy manual harness plus datasource verifier workflows.
The controlled verifier wrapper section below documents only the export-first
wrapper/session/export contract; later verifier-B, model-matrix, and advisory
judge sections are separate established workflows.

## Blind agent flow protocol v1

Protocol version: `blind-agent-flow-v1`

| Rule | Requirement |
|------|-------------|
| Required OpenCode agent | Required OpenCode agent: `brain-ds-orchestrator` |
| Wrong agent | Wrong or fallback agent (`agent=build`) invalidates the run immediately. |
| Conversation proof | The scorer requires normalized events plus a verifiable text exchange between the user and `brain-ds-orchestrator`. |
| Subagent proof | Subagent proof requires identity plus action or tool call attributable to that subagent. |
| Evidence provenance | Generated outputs and `.brain_ds/store.db` must come from the subject workspace unless an explicit override is treated as degraded evidence. |
| Discoverability | Engram topic: `blind-agentic-eval/protocol/v1` mirrors this versioned protocol for future sessions. |

Archive remains blocked until a live run proves orchestrator conversation,
subagent capture, generated subject outputs, subject-local graph provenance, and
protocol discoverability.

Legacy reports may still contain `brainds-orchestrator`; new live runs must use
`brain-ds-orchestrator`.

## Pre-run setup

| Check | Command or action |
|-------|-------------------|
| Repo root | Open a terminal at `C:\Users\sergi\Documents\brain_ds`. |
| Intent check | Run `git status --short` and confirm unrelated work will not be edited. |
| BrainDS setup check | Run `uv run brain_ds check` if the local CLI environment is available. |
| OpenCode access | Confirm your normal OpenCode membership/session can start from a local folder. |
| Evaluator isolation | Do not copy evaluator-only files from `tests/gold/blind_agentic/revops_growth/` into the subject workspace. |

## Create the subject workspace

Run this from `C:\Users\sergi\Documents\brain_ds`:

```powershell
uv run python -m tests.eval.blind_agentic.prepare_subject --scenario revops_growth --run-id <run_id>
```

Expected output location:

```text
tmp/blind-agentic-eval/<run_id>/subject
```

The subject folder contains the synthetic Revenue Ops prompt, source extracts, generated SQLite source DB, and seed graph. It must not contain rubric files, gold files, answer keys, or expected outputs.

## Start OpenCode in the subject folder

Open a separate terminal and change into the generated subject workspace:

```powershell
cd tmp/blind-agentic-eval/<run_id>/subject
opencode
```

Do not start OpenCode from the repo root for the blind run. The current working directory must be the subject folder.

## Datasource live proof command shape

For a `datasource_documentation` live proof, prepare the datasource subject and
start OpenCode with the required BrainDS orchestrator explicitly:

```powershell
uv run python -m tests.eval.blind_agentic.prepare_subject --scenario datasource_documentation --run-id <run_id>
cd tmp/blind-agentic-eval/<run_id>/subject
opencode --agent brain-ds-orchestrator
```

Before graph writes, the orchestrator must switch BrainDS to the subject
workspace with `brain_ds_open_workspace` using the subject path. The required
subject-visible outputs are:

| Path | Requirement |
|------|-------------|
| `generated/source_documentation.md` | Stakeholder source documentation with owner, freshness, and data gaps. |
| `subject/.brain_ds/store.db` | Subject-local graph DB/provenance for the run. |

If the conversation pauses and you need to continue, continue with the same
agent: `opencode --agent brain-ds-orchestrator`. Do not continue with bare `opencode`; it can resume as fallback `agent=build`, which is a fail-closed protocol violation.

### Controlled verifier wrapper

For the export-first wrapper flow, run the verifier from the repo root:

```powershell
uv run python -m tests.eval.blind_agentic.run_opencode_verifier --scenario datasource_documentation --run-id <run_id> --model <provider/model>
```

The wrapper prepares the subject workspace, validates `PROMPT.md`, registers the
subject with a run-local `BRAIN_DS_HOME`, launches `opencode run --agent
brain-ds-orchestrator --format json`, captures `sessionID`, and writes
`opencode-export/session.json` through `opencode export <sessionID>`. Missing or
empty prompts, OpenCode launch failures, missing session IDs, export failures,
and invalid export JSON fail fast with `error: <diagnostic>`.

## Paste this blind prompt exactly

```text
I run Revenue Operations for Northstar Analytics. We have CRM, marketing, billing, product usage, support, and finance extracts, but leadership does not trust our growth KPIs. Please use BrainDS to map the sources, identify the lineage for pipeline, conversion, retention, expansion, and revenue metrics, document assumptions/gaps, and produce a business-ready diagnosis with next actions.
```

During the run:

- Answer only normal operational confirmations needed to proceed.
- Do not mention that this is an evaluation.
- Do not provide rubric, gold, expected-answer, benchmark, or hidden-test context.
- Do not hand-edit generated subject outputs after the agent stops.

## Collect evidence after the run

Return to the repo root terminal at `C:\Users\sergi\Documents\brain_ds` and run:

```powershell
uv run python -m tests.eval.blind_agentic.collect_evidence --scenario revops_growth --run-id <run_id>
```

Preferred one-command path:

```powershell
uv run python -m tests.eval.blind_agentic.collect_and_score --scenario revops_growth --run-id <run_id>
```

Preferred one-command path with an evaluator-only judge packet:

```powershell
uv run python -m tests.eval.blind_agentic.collect_and_score --scenario revops_growth --run-id <run_id> --judge-packet-out tmp/blind-agentic-eval/<run_id>/judge_packet.json
```

If BrainDS wrote graph state to a registered/global workspace instead of the subject folder, pass the real graph DB explicitly:

```powershell
uv run python -m tests.eval.blind_agentic.collect_and_score --scenario revops_growth --run-id <run_id> --graph-db-path <path-to-active-workspace/.brain_ds/store.db>
```

Without a subject `.brain_ds/store.db` or an explicit `--graph-db-path`, collection fails clearly. This is intentional: scoring requires a real graph snapshot and must not silently invent or reuse graph evidence.

If you know where OpenCode wrote transcript/session files, pass them as optional evidence:

```powershell
uv run python -m tests.eval.blind_agentic.collect_evidence --scenario revops_growth --run-id <run_id> --opencode-artifacts-path <path-to-session-artifacts>
```

The collector writes:

| Path | Purpose |
|------|---------|
| `tmp/blind-agentic-eval/<run_id>/evidence/manifest.json` | First file to inspect; lists captured evidence and omissions. |
| `tmp/blind-agentic-eval/<run_id>/evidence/graph/store.db` | Final BrainDS graph snapshot from the subject workspace. |
| `tmp/blind-agentic-eval/<run_id>/evidence/generated/` | Generated markdown/json/text artifacts from the subject run. |
| `tmp/blind-agentic-eval/<run_id>/evidence/git_diff.patch` | Repository diff captured for review context. |
| `tmp/blind-agentic-eval/<run_id>/evidence/file_inventory.json` | Subject workspace file inventory. |

Missing OpenCode transcripts are allowed. The manifest should show `session_transcript.status` as `missing` and `session_transcript.required` as `false`.

OpenCode transcript/export is optional evidence. The repository documents BrainDS MCP workspace selection through `BRAIN_DS_PROJECT_ROOT`, `brain_ds mcp --project-root`, the global `~/.brain_ds/workspaces.json` registry, and the `open_workspace` MCP tool. It does not expose a stable API to query or export a running OpenCode/orchestrator session after the fact. Use explicit file-based capture (`--graph-db-path` and optional `--opencode-artifacts-path`) rather than relying on an undocumented live-session channel.

## Score and read results

Run the offline scorer from the repo root:

```powershell
uv run python -m tests.eval.blind_agentic.score_report --scenario revops_growth --evidence tmp/blind-agentic-eval/<run_id>/evidence --out tmp/blind-agentic-eval/<run_id>/report.json
```

To create the optional manual judge packet during scoring, add `--judge-packet-out`:

```powershell
uv run python -m tests.eval.blind_agentic.score_report --scenario revops_growth --evidence tmp/blind-agentic-eval/<run_id>/evidence --out tmp/blind-agentic-eval/<run_id>/report.json --judge-packet-out tmp/blind-agentic-eval/<run_id>/judge_packet.json
```

For the `datasource_documentation` pathway, the trace is required and must start
with `brain-ds-orchestrator`. Any undelegated BrainDS subagent contact is a
blocking `orchestrator_gate` failure, whether it appears as the first BrainDS
event or later in the trace. Wrong or fallback agents fail closed with no partial
credit. Inspect `manifest.json` field
`freshness_checks` before trusting a datasource score: `subject_local_graph`
must be passed, generated outputs and trace must be captured, and
`artifact_hashes` binds the graph/output/trace artifacts used by the report.

## Datasource verifier-B audit and model comparison

Use the same pathway, fixture family, and report schema for every comparison.
Do not compare a Revenue Ops run to a `datasource_documentation` run, and do not
compare reports with different `freshness.report_schema_version` values.

### Double-verifier audit

Verifier A executes and scores the run. Verifier B reviews A's evidence packet
and writes an evaluator-only JSON audit file outside the subject workspace:

```json
{
  "verifier_b_model": "audit-model-b",
  "confirmations": ["Trace evidence supports the pathway verdict."],
  "challenges": [],
  "refinements": ["Compare only reports with matching fixture versions."]
}
```

Attach that audit while collecting and scoring:

```powershell
uv run python -m tests.eval.blind_agentic.collect_and_score --scenario datasource_documentation --run-id <run_id> --verifier-a-model execution-model-a --verifier-b-audit tmp/blind-agentic-eval/<run_id>/verifier_b_audit.json
```

The JSON report adds `double_verifier` with `verifier_a_model`,
`verifier_b_model`, `audit_status`, `confirmations`, `challenges`, and
`refinements`. A run with any challenge is marked `challenged`; otherwise it is
`refined` when refinements exist or `confirmed` when only confirmations exist.

### Same-pathway model matrix

After each model has produced its own `report.json`, build the comparison
matrix from existing reports:

```powershell
uv run python -m tests.eval.blind_agentic.collect_and_score --scenario datasource_documentation --run-id datasource-model-matrix --model-run model-a=tmp/blind-agentic-eval/model-a/report.json --model-run model-b=tmp/blind-agentic-eval/model-b/report.json --comparison-out tmp/blind-agentic-eval/datasource-model-matrix/model_matrix.json
```

The `model_matrix.json` output contains:

| Field | Purpose |
|-------|---------|
| `comparison_status` | `comparable` only after scenario, pathway, schema, prompt, fixture, and rubric metadata match. |
| `pathway_id` | The shared pathway all model runs used. |
| `report_schema_version` | The shared report schema required for side-by-side interpretation. |
| `runs[]` | One row per `--model-run` with label, run id, model, deterministic status, freshness status, blocking failures, and score. |

### Stacked slice context

This PR4 workflow assumes previous `agentic-conversation-verifier-harness`
slices have already landed in order: PR1 schema/fixtures, PR2 gate/freshness,
and PR3 scoring/report lanes. Review PR4 as only the comparison + audit slice;
future harness pathways remain out of scope.

## Optional manual advisory judge

The deterministic lane is authoritative. The advisory judge is non-blocking and must never change the deterministic score, status, or CI outcome. This workflow is intentionally offline: do not require API keys, local models, live LLM services, or CI judging.

### Quick path

1. Generate `tmp/blind-agentic-eval/<run_id>/judge_packet.json` with `--judge-packet-out`.
2. Give only that evaluator-only packet to a human/manual judge workflow.
3. Save the response as `tmp/blind-agentic-eval/<run_id>/judge_response.json`.
4. Re-run scoring with the response:

```powershell
uv run python -m tests.eval.blind_agentic.score_report --scenario revops_growth --evidence tmp/blind-agentic-eval/<run_id>/evidence --out tmp/blind-agentic-eval/<run_id>/report.json --judge-response tmp/blind-agentic-eval/<run_id>/judge_response.json
```

Or use the collect + score wrapper when collecting fresh evidence:

```powershell
uv run python -m tests.eval.blind_agentic.collect_and_score --scenario revops_growth --run-id <run_id> --judge-response tmp/blind-agentic-eval/<run_id>/judge_response.json
```

### Response contract

The judge response is file-based JSON:

| Field | Required | Purpose |
|-------|----------|---------|
| `judge_model` | Yes | Human-readable judge/workflow name. |
| `evidence_hash` | Yes | Must exactly match the packet `evidence_hash`. |
| `verdict` | Yes | Advisory verdict such as `pass`, `review`, or `fail`. |
| `axis_findings` | Yes | Per-axis advisory notes; may be an empty list. |
| `disagreements` | Yes | Places where the advisory judge disagrees with deterministic scoring; may be empty. |
| `rationale` | Yes | Short explanation of the advisory verdict. |

A hash mismatch rejects the advisory verdict. This protects evidence binding: a response for one run cannot be applied to another run.

### Lane separation rules

- Deterministic report fields remain authoritative for pass/review/fail status.
- Advisory findings appear only under `advisory_judge` and `disagreements`.
- Missing judge responses are valid; the report marks the advisory lane as absent.
- Evaluator-only packet and response files must stay outside the subject workspace.

Read outputs in this order:

1. `tmp/blind-agentic-eval/<run_id>/evidence/manifest.json` - confirm minimum evidence was accepted and anti-contamination passed.
2. `tmp/blind-agentic-eval/<run_id>/report.json` - inspect deterministic and advisory lanes side-by-side.
3. `tmp/blind-agentic-eval/<run_id>/report.md` - read the deterministic rationale and optional disagreement notes.
4. `tmp/blind-agentic-eval/<run_id>/evidence/generated/` - review the subject artifacts referenced by the report.

## Isolation checklist

- [ ] OpenCode was launched from `tmp/blind-agentic-eval/<run_id>/subject`, not the repo root.
- [ ] The pasted prompt matched this runbook exactly.
- [ ] Evaluator-only files remained under `tests/gold/blind_agentic/revops_growth/`.
- [ ] The subject workspace did not include rubric, gold, answer key, expected output, benchmark, or hidden test content.
- [ ] `manifest.json` recorded any missing optional transcript artifacts without rejecting the run.

## Next step

Keep the run folder until scoring and review are complete. Delete `tmp/blind-agentic-eval/<run_id>/` only after the maintainer no longer needs evidence.
