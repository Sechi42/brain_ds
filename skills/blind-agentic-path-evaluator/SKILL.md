---
name: blind-agentic-path-evaluator
description: >
  Runs a transparent one-path blind agentic evaluation protocol for BrainDS agent behavior.
  Trigger: when launching a verifier to evaluate one BrainDS path with deterministic evidence plus behavioral analysis.
license: Apache-2.0
metadata:
  author: gentleman-programming
  version: "1.0"
---

## When to Use

- Use when the orchestrator delegates a blind-agentic evaluation for exactly one path.
- Use only after the orchestrator provides a context packet or asks the user for missing launch inputs.
- Do not use for matrix comparisons, batch path runs, or multiple paths in one agent context.

## Critical Patterns

| Rule | Requirement |
|------|-------------|
| Orchestrator packet required | Start from an orchestrator context packet containing path, scenario, OpenCode Go model, report destination, run label, artifact refs, protocol version, and visibility limits. |
| Ask before execution | If path, OpenCode Go model, report destination, or run label is missing, ask the user for the missing field before running anything. |
| One path only | Evaluate exactly one path. Do not evaluate multiple paths in one agent context; reject comparative or comma-separated path requests. |
| Cognitive benchmark first | Read and understand the selected target flow, fixtures, runbook, and available deterministic artifacts before judging behavior. Use that benchmark as the basis for behavioral analysis. |
| Evidence-grounded analysis | Behavioral analysis must cite evidence references and must name omissions, opaque gaps, and visibility limits. Never claim hidden subagent reasoning. |
| User-selected report destination | Full report destination must be user-selected: file, Engram, or both. MUST save concise key points to Engram for every completed evaluation, regardless of the full-report destination. |

## Required Context Packet

```json
{
  "path_id": "graph-qa",
  "scenario": "revops_growth",
  "model": "provider/model",
  "report_destination": "file|engram|both",
  "run_label": "human-readable-run",
  "artifact_refs": [],
  "protocol_version": "blind-agentic-path-evaluator.v1",
  "visibility_limits": [],
  "one_path_only": true
}
```

## Report Contract

Before report writing, read and understand the selected target flow and use it as the cognitive benchmark before judging behavior.

The full report must include:

- deterministic summary and status
- evidence references
- conversation, tool, and delegation/subagent behavior analysis
- good
- bad
- learned
- improvable
- non-improvable constraints
- improvement plan
- omissions and visibility limits

## Persistence Contract

- MUST save concise key points to Engram for every completed evaluation.
- The full report is written to the user-selected destination: file, Engram, or both.
- Engram key points are mandatory even when the user selects file-only full-report output.

## Commands

```bash
uv run pytest tests/test_blind_agentic_eval_plan.py tests/test_blind_agentic_path_evaluator_contract.py -q
python -m tests.eval.blind_agentic.run_opencode_verifier --path-id graph-qa --run-id <run-label> --model <opencode-go-model>
python -m tests.eval.blind_agentic.collect_and_score --path-id graph-qa --run-id <run-label>
```

## Resources

- **Artifacts**: Read SDD artifacts from Engram for the active change before evaluating.
- **Evidence**: Use the generated manifest, report, trace, and OpenCode export when available.
