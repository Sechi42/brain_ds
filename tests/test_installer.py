import os
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import stat


ROOT = Path(__file__).resolve().parents[1]


def usable_bash() -> str | None:
    bash_path = shutil.which("bash")
    if not bash_path:
        return None
    probe = subprocess.run([bash_path, "--version"], capture_output=True, text=True)
    if probe.returncode != 0:
        return None
    return bash_path


def seed_project(root: Path) -> None:
    for name, content in (
        ("elicit-context", "# elicit\n"),
        ("map-connections", "# map\n"),
    ):
        skill_dir = root / "skills" / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    atl = root / ".atl"
    atl.mkdir(parents=True, exist_ok=True)
    (atl / "skill-registry.md").write_text(
        """# Skill Registry

## User Skills

| Trigger | Skill | Path |
|---------|-------|------|
| local trigger | elicit-context | C:\\stale\\skills\\elicit-context\\SKILL.md |
| local trigger | map-connections | C:\\stale\\skills\\map-connections\\SKILL.md |
""",
        encoding="utf-8",
    )


def seed_global_opencode(home: Path) -> Path:
    cfg_dir = home / ".config" / "opencode"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg = cfg_dir / "opencode.json"
    cfg.write_text(
        """{
  "agent": {
    "gentle-orchestrator": {
      "mode": "primary",
      "model": "gpt-5.5",
      "tools": {
        "read": true
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    return cfg


def seed_sdd_commands(home: Path) -> list[Path]:
    commands = home / ".config" / "opencode" / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for name in (
        "sdd-new",
        "sdd-continue",
        "sdd-ff",
        "sdd-explore",
        "sdd-apply",
        "sdd-verify",
        "sdd-archive",
        "sdd-init",
        "sdd-onboard",
    ):
        p = commands / f"{name}.md"
        p.write_text(f"# {name}\n", encoding="utf-8")
        paths.append(p)
    return paths


def seed_bin(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "opencode.cmd").write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
    (path / "git.cmd").write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="brain-ds-installer-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / "install-opencode.ps1", self.repo / "install-opencode.ps1")
        shutil.copy(ROOT / "install-opencode.sh", self.repo / "install-opencode.sh")
        shutil.copy(ROOT / "brain_ds.cmd", self.repo / "brain_ds.cmd")
        shutil.copy(ROOT / "brain_ds.sh", self.repo / "brain_ds.sh")
        shutil.copy(ROOT / "brain_ds.ps1", self.repo / "brain_ds.ps1")
        shutil.copytree(ROOT / "commands", self.repo / "commands")
        seed_project(self.repo)
        self.bin = self.tmp / "bin"
        self.home = self.tmp / "home"
        self.home.mkdir(parents=True, exist_ok=True)
        seed_bin(self.bin)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_ps1(self, *args: str):
        ps = Path(os.environ.get("WINDIR", "C:\\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        env = os.environ.copy()
        env["PATH"] = str(self.bin)
        env["HOME"] = str(self.home)
        env["USERPROFILE"] = str(self.home)
        cmd = [str(ps), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.repo / "install-opencode.ps1"), *args]
        return subprocess.run(cmd, capture_output=True, text=True, env=env)

    def run_sh(self, *args: str):
        bash_path = usable_bash()
        if not bash_path:
            self.skipTest("bash not available in test environment")
        env = os.environ.copy()
        env["PATH"] = str(self.bin)
        env["HOME"] = str(self.home)
        cmd = [bash_path, str(self.repo / "install-opencode.sh"), *args]
        return subprocess.run(cmd, capture_output=True, text=True, env=env)

    def test_non_tty_defaults_project_mode(self):
        result = self.run_ps1()
        self.assertEqual(result.returncode, 0)
        self.assertTrue((self.repo / ".opencode" / "skills" / "elicit-context" / "SKILL.md").exists())

    def test_global_flag_installs_to_global_target(self):
        result = self.run_ps1("-Global")
        self.assertEqual(result.returncode, 0)
        target = self.home / ".config" / "opencode" / "skills" / "elicit-context" / "SKILL.md"
        self.assertTrue(target.exists())
        self.assertIn("restart OpenCode", (result.stdout + result.stderr))

    def test_project_flag_keeps_local_behavior(self):
        result = self.run_ps1("-Project")
        self.assertEqual(result.returncode, 0)
        self.assertTrue((self.repo / ".opencode" / "skills" / "map-connections" / "SKILL.md").exists())

    def test_global_mode_skips_registry_and_agents_generation(self):
        (self.repo / "AGENTS.md").unlink(missing_ok=True)
        before = (self.repo / ".atl" / "skill-registry.md").read_text(encoding="utf-8")
        result = self.run_ps1("-Global")
        self.assertEqual(result.returncode, 0)
        after = (self.repo / ".atl" / "skill-registry.md").read_text(encoding="utf-8")
        self.assertEqual(before, after)
        self.assertFalse((self.repo / "AGENTS.md").exists())

    def test_global_mode_preserves_unrelated_existing_global_skills(self):
        unrelated = self.home / ".config" / "opencode" / "skills" / "unrelated-skill"
        unrelated.mkdir(parents=True, exist_ok=True)
        marker = unrelated / "SKILL.md"
        marker.write_text("# keep me\n", encoding="utf-8")

        result = self.run_ps1("-Global")
        self.assertEqual(result.returncode, 0)

        self.assertTrue(marker.exists())
        self.assertEqual(marker.read_text(encoding="utf-8"), "# keep me\n")

    def test_script_contains_prompt_and_fallback_contracts(self):
        ps1 = (ROOT / "install-opencode.ps1").read_text(encoding="utf-8")
        sh = (ROOT / "install-opencode.sh").read_text(encoding="utf-8")
        self.assertIn("Install globally [G] or only for this project [P]?", ps1)
        self.assertIn("Install globally [G] or only for this project [P]?", sh)
        self.assertIn("Copy-Item -LiteralPath $source -Destination $destFile -Force", ps1)
        self.assertIn("cp \"$src\" \"$dest\"", sh)
        self.assertIn("$HOME/.config/opencode/skills", sh)

    def test_agent_deployed(self):
        cfg = seed_global_opencode(self.home)
        result = self.run_ps1("-Global", "-Agent")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        data = json.loads(cfg.read_text(encoding="utf-8-sig"))
        agent = data["agent"]["brain-ds-orchestrator"]
        self.assertEqual(agent["mode"], "primary")
        self.assertEqual(agent["model"], "opencode-go/deepseek-v4-flash")
        self.assertTrue(agent["tools"].get("engram"))

    def test_agent_has_description(self):
        cfg = seed_global_opencode(self.home)
        result = self.run_ps1("-Global", "-Agent")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        data = json.loads(cfg.read_text(encoding="utf-8-sig"))
        agent = data["agent"]["brain-ds-orchestrator"]
        self.assertTrue(agent.get("description"))

    def test_agent_has_file_prompt(self):
        cfg = seed_global_opencode(self.home)
        result = self.run_ps1("-Global", "-Agent")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        data = json.loads(cfg.read_text(encoding="utf-8-sig"))
        agent = data["agent"]["brain-ds-orchestrator"]
        prompt = agent.get("prompt", "")
        self.assertTrue(prompt.startswith("{file:"))
        self.assertTrue(prompt.endswith("}"))

    def test_agent_has_full_permissions(self):
        cfg = seed_global_opencode(self.home)
        result = self.run_ps1("-Global", "-Agent")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        data = json.loads(cfg.read_text(encoding="utf-8-sig"))
        permission = data["agent"]["brain-ds-orchestrator"].get("permission", {})
        self.assertEqual(permission.get("read"), "allow")
        self.assertEqual(permission.get("edit"), "allow")

    def test_commands_deployed(self):
        seed_global_opencode(self.home)
        result = self.run_ps1("-Global", "-Agent")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        commands_dir = self.home / ".config" / "opencode" / "commands"
        for name in (
            "brain-ds-pipeline.md",
            "brain-ds-map.md",
            "brain-ds-brd.md",
            "elicit-context.md",
            "map-connections.md",
            "generate-brd.md",
        ):
            cmd = commands_dir / name
            self.assertTrue(cmd.exists(), msg=f"Missing {name}")
            content = cmd.read_text(encoding="utf-8")
            self.assertIn("agent: brain-ds-orchestrator", content)

    def test_idempotent(self):
        cfg = seed_global_opencode(self.home)
        first = self.run_ps1("-Global", "-Agent")
        self.assertEqual(first.returncode, 0, msg=first.stdout + first.stderr)
        second = self.run_ps1("-Global", "-Agent")
        self.assertEqual(second.returncode, 0, msg=second.stdout + second.stderr)

        data = json.loads(cfg.read_text(encoding="utf-8-sig"))
        self.assertIn("brain-ds-orchestrator", data.get("agent", {}))

        commands_dir = self.home / ".config" / "opencode" / "commands"
        self.assertEqual(len(list(commands_dir.glob("brain-ds-*.md"))), 3)

    def test_gentle_ai_intact(self):
        cfg = seed_global_opencode(self.home)
        sdd_paths = seed_sdd_commands(self.home)
        result = self.run_ps1("-Global", "-Agent")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

        text = cfg.read_text(encoding="utf-8")
        self.assertIn('"gentle-orchestrator"', text)
        for p in sdd_paths:
            self.assertTrue(p.exists(), msg=f"Removed command: {p.name}")

        commands_dir = self.home / ".config" / "opencode" / "commands"
        self.assertTrue((commands_dir / "sdd-apply.md").exists())
        self.assertTrue((commands_dir / "sdd-verify.md").exists())

    def test_non_destructive_commands_dir(self):
        seed_global_opencode(self.home)
        commands_dir = self.home / ".config" / "opencode" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        marker = commands_dir / "unrelated-command.md"
        marker.write_text("# keep this\n", encoding="utf-8")

        result = self.run_ps1("-Global", "-Agent")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertTrue(marker.exists())
        self.assertEqual(marker.read_text(encoding="utf-8"), "# keep this\n")

    def test_wrapper_cross_platform_contracts(self):
        sh = (ROOT / "brain_ds.sh").read_text(encoding="utf-8")
        cmd = (ROOT / "brain_ds.cmd").read_text(encoding="utf-8")
        ps1 = (ROOT / "brain_ds.ps1").read_text(encoding="utf-8")

        self.assertIn("#!/usr/bin/env bash", sh)
        self.assertIn('uv run brain_ds "$@"', sh)
        self.assertIn("%~dp0", cmd)
        self.assertIn("uv run brain_ds %*", cmd)
        self.assertIn("$PSScriptRoot", ps1)
        self.assertIn("exit $LASTEXITCODE", ps1)

    def test_wrapper_passes_arguments(self):
        bash_path = usable_bash()
        if not bash_path:
            self.skipTest("bash not available in test environment")
        wrapper = ROOT / "brain_ds.sh"
        self.assertTrue(wrapper.exists())

        record = self.tmp / "args.txt"
        fake_uv = self.bin / "uv"
        fake_uv.write_text(
            "#!/usr/bin/env bash\nprintf '%s\n' \"$*\" > \"$BRAIN_DS_ARGS_RECORD\"\nexit 0\n",
            encoding="utf-8",
        )
        fake_uv.chmod(fake_uv.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{self.bin}{os.pathsep}{env.get('PATH', '')}"
        env["BRAIN_DS_ARGS_RECORD"] = str(record)
        subprocess.run(
            [bash_path, str(wrapper), "ui", "graph.json", "--open"],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

        self.assertEqual(record.read_text(encoding="utf-8").strip(), "run brain_ds ui graph.json --open")

    def test_wrapper_propagates_exit_code(self):
        bash_path = usable_bash()
        if not bash_path:
            self.skipTest("bash not available in test environment")
        wrapper = ROOT / "brain_ds.sh"
        self.assertTrue(wrapper.exists())

        fake_uv = self.bin / "uv"
        fake_uv.write_text("#!/usr/bin/env bash\nexit 42\n", encoding="utf-8")
        fake_uv.chmod(fake_uv.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{self.bin}{os.pathsep}{env.get('PATH', '')}"
        result = subprocess.run(
            [bash_path, str(wrapper), "ui"],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

        self.assertEqual(result.returncode, 42)

    def test_wrapper_uv_not_found_message(self):
        bash_path = usable_bash()
        if not bash_path:
            self.skipTest("bash not available in test environment")
        wrapper = ROOT / "brain_ds.sh"
        env = os.environ.copy()
        env["PATH"] = str(self.tmp / "missing-uv")

        result = subprocess.run(
            [bash_path, str(wrapper), "ui"],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("install uv", (result.stdout + result.stderr).lower())

    def test_wrapper_resolves_repo_root(self):
        wrapper = ROOT / "brain_ds.cmd"
        self.assertTrue(wrapper.exists())

        record = self.tmp / "cwd.txt"
        fake_uv = self.bin / "uv.cmd"
        fake_uv.write_text(
            "@echo off\r\n"
            "cd > \"%BRAIN_DS_CWD_RECORD%\"\r\n"
            "exit /b 0\r\n",
            encoding="utf-8",
        )

        env = os.environ.copy()
        env["PATH"] = f"{self.bin}{os.pathsep}{env.get('PATH', '')}"
        env["BRAIN_DS_CWD_RECORD"] = str(record)

        subprocess.run(
            ["cmd", "/c", str(wrapper), "ui"],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

        resolved = record.read_text(encoding="utf-8").strip().rstrip("\\")
        expected = str(ROOT).rstrip("\\")
        self.assertEqual(resolved.lower(), expected.lower())

    def test_register_path_copies_wrapper_ps1(self):
        result = self.run_ps1("-RegisterPath")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertTrue((self.home / ".config" / "opencode" / "bin" / "brain_ds.cmd").exists())

    @unittest.skipUnless(shutil.which("opencode"), "OpenCode CLI not installed")
    def test_register_path_copies_wrapper_sh(self):
        result = self.run_sh("--register-path")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertTrue((self.home / ".config" / "opencode" / "bin" / "brain_ds.sh").exists())

    def test_no_register_path_skips_copy(self):
        result = self.run_ps1("-Project")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertFalse((self.home / ".config" / "opencode" / "bin" / "brain_ds.cmd").exists())

    def test_register_path_idempotent(self):
        first = self.run_ps1("-RegisterPath")
        self.assertEqual(first.returncode, 0, msg=first.stdout + first.stderr)
        second = self.run_ps1("-RegisterPath")
        self.assertEqual(second.returncode, 0, msg=second.stdout + second.stderr)

    def test_register_path_creates_bin_dir(self):
        target = self.home / ".config" / "opencode" / "bin"
        shutil.rmtree(target, ignore_errors=True)
        result = self.run_ps1("-RegisterPath")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertTrue(target.exists())
        self.assertTrue((target / "brain_ds.cmd").exists())


if __name__ == "__main__":
    unittest.main()
