from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from brain_ds import workspaces
from tests.eval.blind_agentic.prepare_subject import PrepareSubjectError, prepare_subject


REQUIRED_ORCHESTRATOR = "brain-ds-orchestrator"
SESSION_ID_ALIASES = ("sessionID", "session_id", "id")


class OpenCodeVerifierError(RuntimeError):
    """Raised when the controlled OpenCode verifier contract cannot proceed."""


@dataclass(frozen=True)
class OpenCodeVerifierResult:
    scenario: str
    run_id: str
    subject_path: Path
    manifest_path: Path
    export_path: Path
    session_id: str


def build_opencode_run_command(
    subject_path: Path | str,
    *,
    agent: str = REQUIRED_ORCHESTRATOR,
    model: str | None = None,
) -> list[str]:
    """Build the only supported controlled OpenCode run command."""

    if agent != REQUIRED_ORCHESTRATOR:
        raise OpenCodeVerifierError(
            f"wrong-agent: expected {REQUIRED_ORCHESTRATOR!r}, got {agent!r}"
        )
    command = [
        "opencode",
        "run",
        "--agent",
        REQUIRED_ORCHESTRATOR,
        "--format",
        "json",
        "--dir",
        Path(subject_path).as_posix(),
    ]
    if model:
        command.extend(["--model", model])
    return command


def run_verifier(
    *,
    scenario: str,
    run_id: str,
    output_root: Path | str = Path("tmp") / "blind-agentic-eval",
    repo_root: Path | str | None = None,
    model: str | None = None,
) -> OpenCodeVerifierResult:
    """Prepare, run, export, and manifest a controlled OpenCode verifier session."""

    root = Path(repo_root) if repo_root is not None else Path.cwd()
    output = Path(output_root)
    run_root = output / run_id
    diagnostics = run_root / "diagnostics"
    export_dir = run_root / "opencode-export"
    brain_ds_home = run_root / "brain_ds_home"
    manifest_path = run_root / "opencode-verifier-manifest.json"
    for wrapper_artifact in (diagnostics, export_dir, brain_ds_home):
        if wrapper_artifact.exists():
            shutil.rmtree(wrapper_artifact)
    manifest_path.unlink(missing_ok=True)
    diagnostics.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)
    brain_ds_home.mkdir(parents=True, exist_ok=True)

    workspace = prepare_subject(
        scenario=scenario,
        run_id=run_id,
        output_root=output,
        repo_root=root,
    )
    subject = workspace.subject_path
    prompt_path = subject / "PROMPT.md"
    prompt = _read_prompt(prompt_path, subject)

    env = {**os.environ, "BRAIN_DS_HOME": str(brain_ds_home)}
    registration = _register_subject_workspace(subject, env=env)

    run_command = build_opencode_run_command(subject, model=model)
    run_completed = _run_opencode_command(
        run_command,
        phase="opencode-run",
        input=prompt,
        capture_output=True,
        text=True,
        cwd=subject,
        env=env,
    )
    run_stdout = diagnostics / "opencode-run.stdout.jsonl"
    run_stderr = diagnostics / "opencode-run.stderr.txt"
    run_stdout_text = _output_text(run_completed.stdout)
    run_stderr_text = _output_text(run_completed.stderr)
    run_stdout.write_text(run_stdout_text, encoding="utf-8")
    run_stderr.write_text(run_stderr_text, encoding="utf-8")
    if run_completed.returncode != 0:
        raise OpenCodeVerifierError(f"opencode-run-failed: exit {run_completed.returncode}")

    session_id, session_alias = _extract_session_id(run_stdout_text)
    if not session_id:
        raise OpenCodeVerifierError("missing-sessionID: OpenCode run did not emit a session identifier")

    export_command = ["opencode", "export", session_id]
    export_completed = _run_opencode_command(
        export_command,
        phase="opencode-export",
        capture_output=True,
        text=True,
        cwd=subject,
        env=env,
    )
    export_stderr = diagnostics / "opencode-export.stderr.txt"
    export_stdout_text = _output_text(export_completed.stdout)
    export_stderr_text = _output_text(export_completed.stderr)
    export_stderr.write_text(export_stderr_text, encoding="utf-8")
    if export_completed.returncode != 0:
        raise OpenCodeVerifierError(f"export-failed: exit {export_completed.returncode}")

    export_path = export_dir / "session.json"
    _write_valid_export(export_stdout_text, export_path)

    manifest = {
        "scenario": scenario,
        "run_id": run_id,
        "subject_path": subject.as_posix(),
        "brain_ds_home": brain_ds_home.as_posix(),
        "prompt_path": prompt_path.as_posix(),
        "session_id": session_id,
        "session_id_source_alias": session_alias,
        "workspace_registration": registration,
        "opencode_run": {
            "command": run_command,
            "stdout_path": run_stdout.relative_to(run_root).as_posix(),
            "stderr_path": run_stderr.relative_to(run_root).as_posix(),
            "returncode": run_completed.returncode,
        },
        "opencode_export": {
            "command": export_command,
            "path": export_path.as_posix(),
            "stderr_path": export_stderr.relative_to(run_root).as_posix(),
            "returncode": export_completed.returncode,
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return OpenCodeVerifierResult(
        scenario=scenario,
        run_id=run_id,
        subject_path=subject,
        manifest_path=manifest_path,
        export_path=export_path,
        session_id=session_id,
    )


def _read_prompt(prompt_path: Path, subject: Path) -> str:
    if not prompt_path.is_file():
        raise OpenCodeVerifierError(f"missing-prompt: {prompt_path}")
    prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise OpenCodeVerifierError(f"missing-prompt: empty prompt at {prompt_path}")
    gate = (
        "\n\nVerifier contract: coordinate with brain-ds-orchestrator. "
        f"Use BrainDS MCP action brain_ds_open_workspace with path {subject.as_posix()} "
        "before any graph-writing BrainDS action."
    )
    return f"{prompt}{gate}\n"


def _register_subject_workspace(subject: Path, *, env: dict[str, str]) -> dict[str, Any]:
    previous = os.environ.get("BRAIN_DS_HOME")
    os.environ["BRAIN_DS_HOME"] = env["BRAIN_DS_HOME"]
    try:
        entry = workspaces.register_workspace(subject, name=f"blind-agentic-{subject.parent.name}")
        registry_path = workspaces.registry_path()
    finally:
        if previous is None:
            os.environ.pop("BRAIN_DS_HOME", None)
        else:
            os.environ["BRAIN_DS_HOME"] = previous
    return {
        "status": "registered",
        "path": Path(entry["path"]).as_posix(),
        "registry_path": registry_path.as_posix(),
    }


def _run_opencode_command(
    command: list[str],
    *,
    phase: str,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    launch_command = _resolve_opencode_launch_command(command)
    run_kwargs = dict(kwargs)
    if run_kwargs.get("text") or run_kwargs.get("universal_newlines"):
        run_kwargs.setdefault("encoding", "utf-8")
        run_kwargs.setdefault("errors", "replace")
    try:
        return subprocess.run(launch_command, **run_kwargs)
    except OSError as exc:
        raise OpenCodeVerifierError(f"{phase}-launch-failed: {exc}") from exc


def _resolve_opencode_launch_command(command: list[str]) -> list[str]:
    if not command or command[0] != "opencode":
        return command
    executable = shutil.which("opencode")
    if executable is None:
        return command
    return [executable, *command[1:]]


def _output_text(output: str | bytes | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


def _extract_session_id(stdout: str) -> tuple[str | None, str | None]:
    for payload in _json_objects(stdout):
        found = _find_session_id(payload)
        if found[0]:
            return found
    return None, None


def _json_objects(text: str) -> list[Any]:
    values: list[Any] = []
    stripped = text.strip()
    if not stripped:
        return values
    try:
        values.append(json.loads(stripped))
        return values
    except json.JSONDecodeError:
        pass
    for line in stripped.splitlines():
        try:
            values.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return values


def _find_session_id(value: Any) -> tuple[str | None, str | None]:
    if isinstance(value, dict):
        session = value.get("session")
        if isinstance(session, dict):
            nested = session.get("id")
            if isinstance(nested, str) and nested.strip():
                return nested.strip(), "session.id"
        for alias in SESSION_ID_ALIASES:
            candidate = value.get(alias)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip(), alias
        for child in value.values():
            found = _find_session_id(child)
            if found[0]:
                return found
    if isinstance(value, list):
        for child in value:
            found = _find_session_id(child)
            if found[0]:
                return found
    return None, None


def _write_valid_export(stdout: str, export_path: Path) -> None:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise OpenCodeVerifierError("export-invalid-json: opencode export did not emit JSON") from exc
    export_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a controlled OpenCode blind-agent verifier.")
    for name in ("--scenario", "--run-id"):
        parser.add_argument(name, required=True)
    parser.add_argument("--model")
    parser.add_argument("--output-root", type=Path, default=Path("tmp") / "blind-agentic-eval")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        result = run_verifier(**vars(args))
    except (OpenCodeVerifierError, PrepareSubjectError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Verifier manifest: {result.manifest_path}")
    print(f"OpenCode export: {result.export_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
