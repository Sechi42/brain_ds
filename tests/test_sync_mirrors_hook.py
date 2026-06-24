"""Tests for the hybrid mirror-sync PostToolUse hook (scripts/sync_mirrors_hook.py)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_HOOK_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sync_mirrors_hook.py"
_spec = importlib.util.spec_from_file_location("sync_mirrors_hook", _HOOK_PATH)
assert _spec and _spec.loader
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


def _make_skill(root: Path, name: str, body: str) -> Path:
    src = root / "skills" / name / "SKILL.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(body, encoding="utf-8")
    return src


def test_class_a_autocopies_drifted_skill_mirror(tmp_path: Path) -> None:
    src = _make_skill(tmp_path, "demo", "canonical content\n")
    mirror = tmp_path / ".opencode" / "skills" / "demo" / "SKILL.md"
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text("stale\n", encoding="utf-8")

    msg = hook._sync_skill("skills/demo/SKILL.md", tmp_path)

    assert msg is not None and "Auto-copied" in msg
    assert mirror.read_bytes() == src.read_bytes()


def test_class_a_silent_when_already_in_sync(tmp_path: Path) -> None:
    _make_skill(tmp_path, "demo", "same\n")
    mirror = tmp_path / ".opencode" / "skills" / "demo" / "SKILL.md"
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text("same\n", encoding="utf-8")

    assert hook._sync_skill("skills/demo/SKILL.md", tmp_path) is None


def test_class_b_paths_recognised() -> None:
    assert hook._is_class_b(".claude/agents/brainds-connection-mapper.md")
    assert hook._is_class_b("prompts/brainds-source-explorer.md")
    assert hook._is_class_b("brain_ds/mcp/grounding.py")
    assert hook._is_class_b("CLAUDE.md")
    assert not hook._is_class_b("brain_ds/store/repository.py")
    assert not hook._is_class_b("skills/demo/SKILL.md")


def test_claude_mode_emits_additionalcontext_json(tmp_path: Path, capsys, monkeypatch) -> None:
    src = _make_skill(tmp_path, "demo", "fresh\n")
    mirror = tmp_path / ".opencode" / "skills" / "demo" / "SKILL.md"
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text("old\n", encoding="utf-8")
    payload = json.dumps(
        {"tool_input": {"file_path": str(src)}, "cwd": str(tmp_path)}
    )
    monkeypatch.setattr("sys.stdin", _StringStdin(payload))
    monkeypatch.setattr("sys.argv", ["sync_mirrors_hook.py"])

    assert hook.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "Auto-copied" in out["hookSpecificOutput"]["additionalContext"]


def test_opencode_mode_uses_argv_and_stderr(tmp_path: Path, capsys, monkeypatch) -> None:
    src = _make_skill(tmp_path, "demo", "fresh\n")
    mirror = tmp_path / ".opencode" / "skills" / "demo" / "SKILL.md"
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text("old\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["sync_mirrors_hook.py", str(src)])

    assert hook.main() == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == ""  # no Claude JSON in OpenCode mode
    assert "Auto-copied" in captured.err  # advisory goes to stderr
    assert mirror.read_bytes() == src.read_bytes()


def test_main_emits_nothing_for_unrelated_file(tmp_path: Path, capsys, monkeypatch) -> None:
    payload = json.dumps(
        {"tool_input": {"file_path": str(tmp_path / "src" / "thing.py")}, "cwd": str(tmp_path)}
    )
    monkeypatch.setattr("sys.stdin", _StringStdin(payload))
    monkeypatch.setattr("sys.argv", ["sync_mirrors_hook.py"])
    assert hook.main() == 0
    assert capsys.readouterr().out.strip() == ""


class _StringStdin:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        return self._text
