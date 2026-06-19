from __future__ import annotations

import json
import os
import subprocess
import sys
from enum import Enum
from pathlib import Path


class Style(Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


def apply_setup(project_root: Path, *, agent: str = "both") -> dict:
    from .setup import apply_setup as setup_apply_setup

    return setup_apply_setup(project_root, agent=agent)


def mascot() -> str:
    return r"""
        o-- ROLES --o------ DATA SOURCES --o
       / \          \      /              / \
  DEPARTMENTS o------o DECISIONS o------o BUSINESS RELATIONSHIPS
              \        \        /        /
               o--------o------o--------o

                    .-~~~~~~-.
                 .-'  HIPPO   `-.
                /   _      _      \
           ____/___/ \____/ \______\____
          /____      (oo)       ________/
               \__  .-""-.  __/
                  \________/
""".strip("\n")


def banner(command: str | None = None) -> str:
    suffix = f" :: {command}" if command else ""
    return "\n".join(
        [
            "BrainDS" + suffix,
            "Enterprise Data & Knowledge Mapper",
            "organizational context brain for AI agents",
        ]
    )


def branded_print(message: str, *, style: Style = Style.INFO, quiet: bool = False) -> None:
    if quiet:
        return
    prefixes = {
        Style.INFO: "[BrainDS]",
        Style.SUCCESS: "[BrainDS OK]",
        Style.WARNING: "[BrainDS WARN]",
        Style.ERROR: "[BrainDS ERROR]",
    }
    print(f"{prefixes[style]} {message}")


def _installer_script_path(project_root: Path) -> Path:
    script_name = "install-opencode.ps1" if os.name == "nt" else "install-opencode.sh"
    project_script = project_root / script_name
    if project_script.exists():
        return project_script
    return Path(__file__).resolve().parents[2] / script_name


def _run_opencode_installer(
    project_root: Path,
    *,
    scope: str,
    agent_deploy: bool,
    dry_run: bool,
) -> dict:
    script = _installer_script_path(project_root)
    if not script.exists():
        raise FileNotFoundError(f"OpenCode installer not found: {script}")

    if dry_run:
        return {
            "mode": scope,
            "agent_deploy": agent_deploy,
            "returncode": 0,
            "skipped": True,
            "script": str(script),
        }

    if script.suffix == ".ps1":
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Global" if scope == "global" else "-Project",
        ]
        if agent_deploy:
            command.append("-Agent")
    else:
        command = ["bash", str(script), "--global" if scope == "global" else "--project"]
        if agent_deploy:
            command.append("--agent")

    completed = subprocess.run(
        command,
        cwd=str(script.parent),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "mode": scope,
        "agent_deploy": agent_deploy,
        "returncode": completed.returncode,
        "script": str(script),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _needs_opencode_install(agent: str) -> bool:
    return agent in {"opencode", "both"}


def _agents_for(agent: str) -> list[str]:
    if agent == "both":
        return ["claude", "opencode"]
    return [agent]


def _dry_run_setup_summary(project_root: Path, *, agent: str) -> dict:
    from .setup import CHECKLIST_LINES

    return {
        "project_root": str(project_root),
        "agents": _agents_for(agent),
        "written": [],
        "checklist": list(CHECKLIST_LINES),
    }


def run_onboard(args) -> int:
    project_root = Path(args.project_root or ".").resolve()
    agent = args.agent
    quiet = bool(args.quiet or args.json)

    if agent not in {"claude", "opencode", "both"}:
        print(f"Invalid agent target: {agent}", file=sys.stderr)
        return 2

    if not quiet:
        print(mascot())
        print(banner("onboard"))
        branded_print(f"Resolved project root: {project_root}")

    if args.dry_run:
        setup_result = _dry_run_setup_summary(project_root, agent=agent)
    else:
        try:
            setup_result = apply_setup(project_root, agent=agent)
        except Exception as exc:  # pragma: no cover - defensive CLI boundary
            print(f"BrainDS setup failed: {exc}", file=sys.stderr)
            return 3

    opencode_install = None
    if _needs_opencode_install(agent):
        try:
            opencode_install = _run_opencode_installer(
                project_root,
                scope=args.install_scope,
                agent_deploy=args.agent_deploy,
                dry_run=args.dry_run,
            )
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 3

        if opencode_install["returncode"] != 0:
            reason = opencode_install.get("stderr") or opencode_install.get("stdout") or "OpenCode installer failed"
            print(reason, file=sys.stderr)
            return max(3, int(opencode_install["returncode"]))

    payload = dict(setup_result)
    payload["opencode_install"] = opencode_install

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    for path in setup_result["written"]:
        branded_print(f"Config target written: {path}", style=Style.SUCCESS, quiet=quiet)
    if opencode_install is not None:
        mode = opencode_install["mode"]
        branded_print(f"OpenCode installer completed ({mode})", style=Style.SUCCESS, quiet=quiet)
    for line in setup_result["checklist"]:
        branded_print(line, quiet=quiet)

    return 0
