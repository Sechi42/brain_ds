"""Hybrid auto-sync hook for brain_ds cross-client mirrors.

Runs on every file edit. Branches by mirror class:

- Class A (byte-identical): ``skills/<name>/SKILL.md`` -> ``.opencode/skills/<name>/SKILL.md``.
  These are required to be byte-identical, so the hook AUTO-COPIES on edit. Safe.

- Class B (hand-authored semantic variants): ``.claude/agents/brainds-*.md`` <->
  ``prompts/brainds-*.md``, ``brain_ds/mcp/grounding.py`` (DELEGATION_PROTOCOL is the
  cross-client source of truth), and the doc tool-count files (``CLAUDE.md``,
  ``README.md``, ``INSTALL.md``). A blind copy here would destroy the per-client
  rendering, so the hook NEVER rewrites — it runs the harness mirror checks and
  surfaces any drift back to the agent as advisory context.

Dual client support (the hook never blocks the edit; always exits 0):

- Claude Code (PostToolUse hook): reads the tool payload JSON on stdin and replies
  through the ``additionalContext`` channel so the agent sees the result in-turn.
- OpenCode (``experimental.hook.file_edited``): the edited path arrives as argv[1]
  (``$FILE`` substitution), there is no payload stdin and no additionalContext
  channel, so advisories are written to stderr instead.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

# brain_ds is importable because the hook is configured to run under `uv run`.
from brain_ds.harness_check import check_agent_files, check_skills_mirror

# Class B trigger paths (relative, POSIX form). Editing any of these means a
# cross-client mirror MAY have drifted; we verify rather than rewrite.
_CLASS_B_EXACT = {
    "brain_ds/mcp/grounding.py",
    "claude.md",
    "readme.md",
    "install.md",
}
_CLASS_B_PREFIXES = (
    ".claude/agents/brainds-",
    "prompts/brainds-",
)


def _emit(context: str, *, claude_mode: bool) -> None:
    """Surface an advisory without blocking the edit.

    Claude Code consumes ``additionalContext`` JSON on stdout; OpenCode has no such
    channel, so we write a plain message to stderr (which OpenCode logs/surfaces).
    """
    if claude_mode:
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": context,
                }
            },
            sys.stdout,
        )
        sys.stdout.write("\n")
    else:
        sys.stderr.write(context + "\n")


def _project_root(payload: dict) -> Path:
    cwd = payload.get("cwd")
    return Path(cwd).resolve() if cwd else Path.cwd().resolve()


def _rel(path: Path, root: Path) -> str | None:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None


def _sync_skill(rel: str, root: Path) -> str | None:
    """Class A: byte-identical copy skills/<name>/SKILL.md -> .opencode mirror."""
    parts = rel.split("/")
    # Expect skills/<name>/SKILL.md
    if len(parts) != 3 or parts[0] != "skills" or parts[2] != "SKILL.md":
        return None
    source = root / rel
    mirror = root / ".opencode" / "skills" / parts[1] / "SKILL.md"
    if not source.is_file():
        return None
    if mirror.is_file() and mirror.read_bytes() == source.read_bytes():
        return None  # already in sync — stay silent
    mirror.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, mirror)
    return (
        f"[brain_ds mirror sync] Auto-copied `{rel}` to "
        f"`.opencode/skills/{parts[1]}/SKILL.md` (byte-identical Class-A mirror)."
    )


def _is_class_b(rel: str) -> bool:
    if rel.lower() in _CLASS_B_EXACT:
        return True
    return any(rel.startswith(p) for p in _CLASS_B_PREFIXES)


def _flag_class_b_drift(root: Path) -> str | None:
    """Class B: verify, never rewrite. Report drift from the harness checks."""
    drift = [
        r
        for r in (*check_skills_mirror(root), *check_agent_files(root))
        if r.status == "FAIL"
    ]
    if not drift:
        return None
    lines = "\n".join(f"- {r.name}: {r.detail}" for r in drift)
    return (
        "[brain_ds mirror sync] You edited a Class-B file whose cross-client mirror "
        "is hand-authored (agent prompt / OpenCode prompt / grounding / docs). These "
        "are NOT auto-copied because blind copy destroys the per-client rendering. "
        "`brain_ds check` reports drift you must reconcile manually:\n"
        f"{lines}\n"
        "Source of truth for delegation prose: DELEGATION_PROTOCOL in "
        "brain_ds/mcp/grounding.py."
    )


def _run(file_path: str, root: Path, *, claude_mode: bool) -> int:
    rel = _rel(Path(file_path), root)
    if rel is None:
        return 0  # edit outside the project — not our concern

    message = _sync_skill(rel, root)
    if message is None and _is_class_b(rel):
        message = _flag_class_b_drift(root)

    if message:
        _emit(message, claude_mode=claude_mode)
    return 0


def main() -> int:
    # OpenCode mode: the edited path is passed as argv[1] ($FILE). No stdin payload.
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return _run(sys.argv[1], Path.cwd().resolve(), claude_mode=False)

    # Claude Code mode: the tool payload arrives as JSON on stdin.
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("path")
    if not file_path:
        return 0

    return _run(file_path, _project_root(payload), claude_mode=True)


if __name__ == "__main__":
    raise SystemExit(main())
