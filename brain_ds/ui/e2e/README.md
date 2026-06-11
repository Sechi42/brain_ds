# Ecosystem Validation (exe → MCP → store → browser)

This directory contains Playwright specs for validating the brain_ds ecosystem at different levels.

## Specs

| Spec | What it validates | Requires running server? |
|------|-------------------|--------------------------|
| `smoke.spec.ts` | Template HTML structure (static) | No — uses `page.setContent` |
| `ecosystem.spec.ts` | Live server → browser flow | **Yes** — expects server on port 7777 |

## Running ecosystem validation

### Prerequisites

The ecosystem spec expects a brain_ds server running on `http://127.0.0.1:7777`.

**Start the server (port 7777):**

```bash
# From project root
.venv\Scripts\brain_ds.EXE ui --port 7777 --project-root e2e-sandbox
```

Or using Python directly:

```bash
python -m brain_ds ui --port 7777 --project-root e2e-sandbox
```

### Run the spec

```bash
pnpm --dir brain_ds/ui e2e:ecosystem
```

To point the same validation at another already-running exe/server:

```powershell
$env:BRAIN_DS_ECOSYSTEM_URL="http://127.0.0.1:7777"; pnpm --dir brain_ds/ui e2e:ecosystem
```

### Full validation flow (manual)

1. **Start MCP server** (validates exe + MCP protocol):
   ```bash
   e2e-sandbox\_mcp_smoke.py
   ```

2. **Start UI server** (validates store → browser):
   ```bash
   .venv\Scripts\brain_ds.EXE ui --port 7777 --project-root e2e-sandbox
   ```

3. **Run Playwright ecosystem spec** (validates served page):
   ```bash
   pnpm --dir brain_ds/ui e2e:ecosystem
   ```

4. **Agent/MCP mutation checkpoint** (manual-assisted): ask the agent to mutate the graph through the configured MCP server, then keep the browser open and confirm the detail panel/live graph updates without a manual refresh.

## What is NOT validated automatically

- **MCP → store mutation sync**: The ecosystem spec validates the server serves pages and API responds, but does NOT trigger MCP mutations and verify WebSocket push to the browser. This requires a full agent-driven flow.
- **Agent orchestration**: End-to-end agent calls (MCP tool → store update → WS broadcast → browser re-render) are not covered by automated specs.

For full agent integration testing, use the MCP smoke test (`e2e-sandbox/_mcp_smoke.py`) combined with manual browser observation or a dedicated agent test harness.
