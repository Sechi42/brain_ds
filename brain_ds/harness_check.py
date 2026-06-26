"""Agent harness parity checker helpers."""
from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# R1 — Agent-definition constants
# ---------------------------------------------------------------------------

EXPECTED_MCP_TOOL_COUNT = 33

SUBAGENT_NAMES: tuple[str, ...] = (
    "brainds-source-explorer",
    "brainds-graph-mapper",
    "brainds-connection-mapper",
    "brainds-brd-writer",
    "brainds-semantic-verifier",
    "brainds-currency-elicitor",
    "brainds-kpi-composer",
)

CLAUDE_AGENT_FILES: dict[str, str] = {
    slug: f"{slug}.md" for slug in SUBAGENT_NAMES
}

# Required tool grants per agent.
# graph-mapper intentionally has NO Write (encoded by absence — no negative assertion).
# semantic-verifier intentionally has NO Write, NO update_node, NO add_edge (read-only advisory).
REQUIRED_AGENT_GRANTS: dict[str, set[str]] = {
    "brainds-connection-mapper": {"Write"},
    "brainds-brd-writer": {"Write", "mcp__brain_ds__generate_brd"},
    "brainds-source-explorer": {"Write", "mcp__brain_ds__explore_source"},
    "brainds-graph-mapper": {"mcp__brain_ds__update_node", "mcp__brain_ds__add_edge"},
    "brainds-semantic-verifier": {
        "mcp__brain_ds__get_node",
        "mcp__brain_ds__list_nodes",
        "mcp__brain_ds__search_graph",
        "mcp__brain_ds__snapshot_edges",
        "mcp__plugin_engram_engram__mem_save",
    },
    "brainds-currency-elicitor": {
        "Write",
        "mcp__brain_ds__assess_currency",
        "mcp__brain_ds__insert_pending_question",
        "mcp__brain_ds__retrieve_context",
        "mcp__brain_ds__resolve_confirmation",
        "mcp__brain_ds__update_node",
        "mcp__brain_ds__add_edge",
        "mcp__plugin_engram_engram__mem_save",
    },
    "brainds-kpi-composer": {
        "mcp__brain_ds__get_kpi_dossier",
        "mcp__brain_ds__suggest_connections",
        "mcp__brain_ds__insert_pending_question",
        "mcp__brain_ds__list_pending_confirmations",
        "mcp__brain_ds__resolve_confirmation",
        "mcp__brain_ds__add_edge",
    },
}

_FRONTMATTER_NAME_RE = re.compile(r"^\s*name\s*:\s*(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str  # PASS | FAIL | WARNING | SKIP
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


def check_skills_mirror(project_root: Path) -> list[CheckResult]:
    canonical = project_root / "skills"
    mirror = project_root / ".opencode" / "skills"
    if not canonical.is_dir():
        return [CheckResult("skills-mirror-parity", "SKIP", "no skills/ folder in this project")]
    drifted: list[str] = []
    for skill_file in sorted(canonical.glob("*/SKILL.md")):
        mirrored = mirror / skill_file.parent.name / "SKILL.md"
        if not mirrored.is_file() or mirrored.read_bytes() != skill_file.read_bytes():
            drifted.append(skill_file.parent.name)
    if drifted:
        return [
            CheckResult(
                "skills-mirror-parity",
                "FAIL",
                f"skills/ vs .opencode/skills/ drift: {', '.join(drifted)} — re-run install-opencode",
            )
        ]
    return [CheckResult("skills-mirror-parity", "PASS", "skills/ == .opencode/skills/ (byte-identical)")]


def _default_deployed_skills_root() -> Path:
    override = os.environ.get("BRAIN_DS_OPENCODE_SKILLS_ROOT")
    if override:
        return Path(override)
    return Path.home() / ".config" / "opencode" / "skills"


def _first_repo_only_snippet(repo_text: str, deployed_text: str) -> str:
    deployed_lines = {line.strip() for line in deployed_text.splitlines() if line.strip()}
    for line in repo_text.splitlines():
        snippet = line.strip()
        if snippet and snippet not in deployed_lines:
            return snippet[:140]
    return "content differs"


def check_deployed_skill_freshness(
    project_root: Path,
    *,
    deployed_skills_root: Path | None = None,
) -> list[CheckResult]:
    """Warn when repo skill files are newer than the deployed OpenCode copies."""
    canonical = project_root / "skills"
    deployed_root = deployed_skills_root or _default_deployed_skills_root()
    if not canonical.is_dir():
        return [CheckResult("deployed-skill-freshness", "SKIP", "no skills/ folder in this project")]
    if not deployed_root.is_dir():
        return [CheckResult("deployed-skill-freshness", "SKIP", f"deployed skills root not found: {deployed_root}")]

    stale: list[str] = []
    for skill_file in sorted(canonical.glob("*/SKILL.md")):
        deployed_file = deployed_root / skill_file.parent.name / "SKILL.md"
        if not deployed_file.is_file():
            stale.append(f"{skill_file.parent.name}: missing deployed SKILL.md")
            continue
        repo_text = skill_file.read_text(encoding="utf-8-sig")
        deployed_text = deployed_file.read_text(encoding="utf-8-sig")
        if repo_text != deployed_text:
            stale.append(f"{skill_file.parent.name}: repo-only snippet '{_first_repo_only_snippet(repo_text, deployed_text)}'")

    if stale:
        return [
            CheckResult(
                "deployed-skill-freshness",
                "WARNING",
                "deployed OpenCode skill stale vs repo: " + "; ".join(stale),
            )
        ]
    return [CheckResult("deployed-skill-freshness", "PASS", f"deployed skills fresh: {deployed_root}")]


def _parse_agent_frontmatter(path: Path) -> dict[str, object]:
    """Parse YAML-ish frontmatter from a Claude agent .md file.

    Handles UTF-8 BOM and CRLF/CR line endings robustly.
    Returns dict with keys ``name`` (str | None) and ``tools`` (list[str]).
    """
    raw = path.read_text(encoding="utf-8-sig")
    # Normalise line endings so split on "\\n" works regardless of CRLF/CR
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    parts = text.split("---")
    # Frontmatter is between the first and second "---" delimiters
    if len(parts) < 3:
        return {"name": None, "tools": []}
    frontmatter = parts[1]

    # Extract name:
    name_match = _FRONTMATTER_NAME_RE.search(frontmatter)
    name: str | None = name_match.group(1).strip() if name_match else None

    # Extract tools — handle both block list and inline list formats
    tools: list[str] = []
    in_tools = False
    for line in frontmatter.splitlines():
        stripped = line.strip()
        if re.match(r"^tools\s*:", stripped):
            # Could be inline "tools: [A, B]" or start of block list
            inline = re.match(r"^tools\s*:\s*\[(.+)\]", stripped)
            if inline:
                tools = [t.strip() for t in inline.group(1).split(",") if t.strip()]
                in_tools = False
            else:
                in_tools = True
            continue
        if in_tools:
            if stripped.startswith("- "):
                tools.append(stripped[2:].strip())
            elif stripped and not stripped.startswith("#"):
                # New top-level key encountered — end of tools block
                in_tools = False

    return {"name": name, "tools": tools}


def check_agent_files(project_root: Path) -> list[CheckResult]:
    """Check each sub-agent .md file exists, name matches slug, and has required tool grants.

    Yields one CheckResult per check type per agent:
    - ``agent-file-{slug}``  — file exists
    - ``agent-name-{slug}``  — name: frontmatter matches slug
    - ``agent-tools-{slug}`` — all REQUIRED_AGENT_GRANTS present

    query-consultant prompt mirror → always SKIP (never FAIL for absence).
    """
    results: list[CheckResult] = []
    agent_dir = project_root / ".claude" / "agents"

    for slug in SUBAGENT_NAMES:
        filename = CLAUDE_AGENT_FILES[slug]
        agent_path = agent_dir / filename

        # --- file presence ---
        if not agent_path.is_file():
            results.append(
                CheckResult(
                    f"agent-file-{slug}",
                    "FAIL",
                    f"{agent_path} not found — run install-opencode or restore the file",
                )
            )
            # Skip further checks for this agent — nothing to parse
            results.append(CheckResult(f"agent-name-{slug}", "SKIP", "file missing"))
            results.append(CheckResult(f"agent-tools-{slug}", "SKIP", "file missing"))
            continue

        results.append(CheckResult(f"agent-file-{slug}", "PASS", str(agent_path)))

        # --- parse frontmatter ---
        fm = _parse_agent_frontmatter(agent_path)
        agent_name = fm["name"]
        agent_tools: set[str] = set(fm["tools"])  # type: ignore[arg-type]

        # --- name check ---
        if agent_name == slug:
            results.append(CheckResult(f"agent-name-{slug}", "PASS", f"name: {agent_name}"))
        else:
            results.append(
                CheckResult(
                    f"agent-name-{slug}",
                    "FAIL",
                    f"name: '{agent_name}' does not match expected slug '{slug}'",
                )
            )

        # --- tool grants check ---
        required = REQUIRED_AGENT_GRANTS.get(slug, set())
        missing = required - agent_tools
        if not missing:
            results.append(
                CheckResult(f"agent-tools-{slug}", "PASS", f"all required grants present: {sorted(required)}")
            )
        else:
            results.append(
                CheckResult(
                    f"agent-tools-{slug}",
                    "FAIL",
                    f"missing required tool grant(s): {sorted(missing)}",
                )
            )

    # query-consultant prompt mirror → always SKIP
    query_consultant_mirror = project_root / "prompts" / "brainds-query-consultant.md"
    if query_consultant_mirror.is_file():
        results.append(
            CheckResult(
                "agent-prompt-mirror-brainds-query-consultant",
                "SKIP",
                "query-consultant has no mirror (by design) — present but not verified",
            )
        )
    else:
        results.append(
            CheckResult(
                "agent-prompt-mirror-brainds-query-consultant",
                "SKIP",
                "prompts/brainds-query-consultant.md absent — SKIP (by design, not a failure)",
            )
        )

    return results


def _run_all_checks(project_root: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    for check in (check_project_mcp_entries, check_skills_mirror, check_deployed_skill_freshness, check_agent_files):
        results.extend(check(project_root))
    return results


def _summarize_statuses(results: Iterable[CheckResult]) -> tuple[int, int, int, int]:
    passed = failed = warnings = skipped = 0
    for result in results:
        if result.status == "PASS":
            passed += 1
        elif result.status == "FAIL":
            failed += 1
        elif result.status == "WARNING":
            warnings += 1
        else:
            skipped += 1
    return passed, failed, warnings, skipped


def harness_check_main(project_root: Path) -> int:
    root = project_root.resolve()
    results = _run_all_checks(root)
    for result in results:
        print(f"[{result.status}] {result.name}: {result.detail}")

    passed, failed, warnings, skipped = _summarize_statuses(results)
    print(f"Summary: {passed} PASS, {failed} FAIL, {warnings} WARNING, {skipped} SKIP")
    return 1 if failed else 0
