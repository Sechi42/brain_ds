"""Agent harness parity checker helpers."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str  # PASS | FAIL | SKIP
    detail: str


def _load_json(path: Path) -> dict | None:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _mcp_project_root(entry: dict) -> str | None:
    """Extract the --project-root argument from a Claude or OpenCode MCP entry."""
    command = entry.get("command")
    args = command if isinstance(command, list) else entry.get("args", [])
    if not isinstance(args, list):
        return None
    for i, item in enumerate(args):
        if item == "--project-root" and i + 1 < len(args):
            return str(args[i + 1])
    env = entry.get("env") or entry.get("environment") or {}
    if isinstance(env, dict) and env.get("BRAIN_DS_PROJECT_ROOT") is not None:
        return str(env["BRAIN_DS_PROJECT_ROOT"])
    return None


def check_project_mcp_entries(project_root: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    claude_path = project_root / ".mcp.json"
    opencode_path = project_root / ".opencode" / "opencode.json"

    claude_cfg = _load_json(claude_path)
    claude_entry = (claude_cfg or {}).get("mcpServers", {}).get("brain_ds")
    if claude_entry:
        results.append(CheckResult("claude-mcp-entry", "PASS", str(claude_path)))
    else:
        results.append(
            CheckResult(
                "claude-mcp-entry",
                "FAIL",
                f"No mcpServers.brain_ds in {claude_path} — run 'brain_ds setup --agent both'",
            )
        )

    opencode_cfg = _load_json(opencode_path)
    opencode_entry = (opencode_cfg or {}).get("mcp", {}).get("brain_ds")
    if opencode_entry:
        results.append(CheckResult("opencode-mcp-entry", "PASS", str(opencode_path)))
    else:
        results.append(
            CheckResult(
                "opencode-mcp-entry",
                "FAIL",
                f"No mcp.brain_ds in {opencode_path} — run 'brain_ds setup --agent both'",
            )
        )

    if claude_entry and opencode_entry:
        claude_root = _mcp_project_root(claude_entry)
        opencode_root = _mcp_project_root(opencode_entry)
        if claude_root is not None and claude_root == opencode_root:
            results.append(CheckResult("mcp-roots-aligned", "PASS", f"project root '{claude_root}'"))
        else:
            results.append(
                CheckResult(
                    "mcp-roots-aligned",
                    "FAIL",
                    f"Claude root '{claude_root}' != OpenCode root '{opencode_root}'",
                )
            )
    else:
        results.append(CheckResult("mcp-roots-aligned", "SKIP", "one or both MCP entries missing"))
    return results
