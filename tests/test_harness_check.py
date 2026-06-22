"""Tests for local harness parity helpers."""
from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from brain_ds.harness_check import (
    check_agent_files,
    check_deployed_skill_freshness,
    check_project_mcp_entries,
    check_skills_mirror,
    harness_check_main,
)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class HarnessCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="brain-ds-harness-check-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.project = self.tmp / "project"
        self.project.mkdir()

    def _by_name(self, results, name):
        return next(r for r in results if r.name == name)

    def test_mcp_entries_pass_when_both_clients_aligned(self) -> None:
        _write_json(
            self.project / ".mcp.json",
            {"mcpServers": {"brain_ds": {"args": ["mcp", "--project-root", "."]}}},
        )
        _write_json(
            self.project / ".opencode" / "opencode.json",
            {"mcp": {"brain_ds": {"command": ["exe", "mcp", "--project-root", "."]}}},
        )
        results = check_project_mcp_entries(self.project)
        self.assertEqual(self._by_name(results, "claude-mcp-entry").status, "PASS")
        self.assertEqual(self._by_name(results, "opencode-mcp-entry").status, "PASS")
        self.assertEqual(self._by_name(results, "mcp-roots-aligned").status, "PASS")

    def test_mcp_entries_fail_when_clients_drift(self) -> None:
        _write_json(
            self.project / ".mcp.json",
            {"mcpServers": {"brain_ds": {"args": ["mcp", "--project-root", "C:/a"]}}},
        )
        results = check_project_mcp_entries(self.project)
        self.assertEqual(self._by_name(results, "claude-mcp-entry").status, "PASS")
        self.assertEqual(self._by_name(results, "opencode-mcp-entry").status, "FAIL")
        self.assertEqual(self._by_name(results, "mcp-roots-aligned").status, "SKIP")

        _write_json(
            self.project / ".opencode" / "opencode.json",
            {"mcp": {"brain_ds": {"command": ["exe", "mcp", "--project-root", "C:/b"]}}},
        )
        results = check_project_mcp_entries(self.project)
        self.assertEqual(self._by_name(results, "mcp-roots-aligned").status, "FAIL")

    def test_skills_mirror_detects_drift(self) -> None:
        canonical = self.project / "skills" / "generate-brd"
        mirror = self.project / ".opencode" / "skills" / "generate-brd"
        canonical.mkdir(parents=True)
        mirror.mkdir(parents=True)
        (canonical / "SKILL.md").write_text("v2", encoding="utf-8")
        (mirror / "SKILL.md").write_text("v1", encoding="utf-8")
        results = check_skills_mirror(self.project)
        self.assertEqual(results[0].status, "FAIL")
        self.assertIn("generate-brd", results[0].detail)

    def test_deployed_skill_freshness_warns_when_deployed_copy_is_stale(self) -> None:
        canonical = self.project / "skills" / "elicit-context"
        deployed = self.tmp / "deployed-skills" / "elicit-context"
        canonical.mkdir(parents=True)
        deployed.mkdir(parents=True)
        (canonical / "SKILL.md").write_text("repo string: SOURCE_DOCUMENTATION_BUNDLE_CONTRACT", encoding="utf-8")
        (deployed / "SKILL.md").write_text("old deployed string", encoding="utf-8")

        results = check_deployed_skill_freshness(self.project, deployed_skills_root=deployed.parent)

        self.assertEqual(results[0].status, "WARNING")
        self.assertEqual(results[0].name, "deployed-skill-freshness")
        self.assertIn("elicit-context", results[0].detail)
        self.assertIn("SOURCE_DOCUMENTATION_BUNDLE_CONTRACT", results[0].detail)

    def test_harness_check_main_reports_warning_without_failing(self) -> None:
        _write_json(
            self.project / ".mcp.json",
            {"mcpServers": {"brain_ds": {"args": ["mcp", "--project-root", "."]}}},
        )
        _write_json(
            self.project / ".opencode" / "opencode.json",
            {"mcp": {"brain_ds": {"command": ["exe", "mcp", "--project-root", "."]}}},
        )
        self._write_passing_agent_files(self.project)
        canonical = self.project / "skills" / "map-connections"
        mirror = self.project / ".opencode" / "skills" / "map-connections"
        deployed = self.tmp / "deployed-skills" / "map-connections"
        canonical.mkdir(parents=True)
        mirror.mkdir(parents=True)
        deployed.mkdir(parents=True)
        (canonical / "SKILL.md").write_text("repo-only freshness marker", encoding="utf-8")
        (mirror / "SKILL.md").write_text("repo-only freshness marker", encoding="utf-8")
        (deployed / "SKILL.md").write_text("old marker", encoding="utf-8")

        stdout = io.StringIO()
        with patch.dict("os.environ", {"BRAIN_DS_OPENCODE_SKILLS_ROOT": str(deployed.parent)}):
            with redirect_stdout(stdout):
                exit_code = harness_check_main(self.project)

        self.assertEqual(exit_code, 0)
        self.assertIn("[WARNING] deployed-skill-freshness", stdout.getvalue())

    def _write_passing_agent_files(self, project_root: Path) -> None:
        """Write minimal passing agent .md files so check_agent_files returns PASS."""
        agent_dir = project_root / ".claude" / "agents"
        agent_dir.mkdir(parents=True, exist_ok=True)
        _agent_stubs = {
            "brainds-source-explorer": ["Write", "mcp__brain_ds__explore_source"],
            "brainds-graph-mapper": ["mcp__brain_ds__update_node", "mcp__brain_ds__add_edge"],
            "brainds-connection-mapper": ["Write"],
            "brainds-brd-writer": ["Write", "mcp__brain_ds__generate_brd"],
        }
        for slug, tools in _agent_stubs.items():
            tools_yaml = "\n".join(f"  - {t}" for t in tools)
            (agent_dir / f"{slug}.md").write_text(
                f"---\nname: {slug}\ntools:\n{tools_yaml}\n---\n\nStub.\n",
                encoding="utf-8",
            )

    def test_harness_check_main_returns_zero_when_checks_pass(self) -> None:
        _write_json(
            self.project / ".mcp.json",
            {"mcpServers": {"brain_ds": {"args": ["mcp", "--project-root", "."]}}},
        )
        _write_json(
            self.project / ".opencode" / "opencode.json",
            {"mcp": {"brain_ds": {"command": ["exe", "mcp", "--project-root", "."]}}},
        )
        self._write_passing_agent_files(self.project)

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = harness_check_main(self.project)

        self.assertEqual(exit_code, 0)
        self.assertIn("PASS", stdout.getvalue())

    def test_harness_check_main_returns_nonzero_when_any_check_fails(self) -> None:
        _write_json(
            self.project / ".mcp.json",
            {"mcpServers": {"brain_ds": {"args": ["mcp", "--project-root", "C:/a"]}}},
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = harness_check_main(self.project)

        self.assertEqual(exit_code, 1)
        self.assertIn("FAIL", stdout.getvalue())


class AgentFileCheckTests(unittest.TestCase):
    """R1: check_agent_files verifies agent .md presence, name, and tool grants."""

    REPO_ROOT = Path(__file__).resolve().parents[1]

    # Minimal valid frontmatter for each agent
    _VALID_AGENTS = {
        "brainds-source-explorer": {
            "name": "brainds-source-explorer",
            "tools": ["Write", "mcp__brain_ds__explore_source"],
        },
        "brainds-graph-mapper": {
            "name": "brainds-graph-mapper",
            "tools": ["mcp__brain_ds__update_node", "mcp__brain_ds__add_edge"],
        },
        "brainds-connection-mapper": {
            "name": "brainds-connection-mapper",
            "tools": ["Write"],
        },
        "brainds-brd-writer": {
            "name": "brainds-brd-writer",
            "tools": ["Write", "mcp__brain_ds__generate_brd"],
        },
    }

    def _make_agent_dir(self, tmp: Path) -> Path:
        agent_dir = tmp / ".claude" / "agents"
        agent_dir.mkdir(parents=True)
        return agent_dir

    def _write_agent(self, agent_dir: Path, slug: str, overrides: dict | None = None) -> None:
        data = dict(self._VALID_AGENTS[slug])
        if overrides:
            data.update(overrides)
        tools_lines = "\n".join(f"  - {t}" for t in data["tools"])
        content = f"---\nname: {data['name']}\ntools:\n{tools_lines}\n---\n\nBody.\n"
        (agent_dir / f"{slug}.md").write_text(content, encoding="utf-8")

    def _write_all_agents(self, agent_dir: Path) -> None:
        for slug in self._VALID_AGENTS:
            self._write_agent(agent_dir, slug)

    # A-1: all agents present with correct grants → all PASS
    def test_all_agents_pass_when_correct(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent_dir = self._make_agent_dir(root)
            self._write_all_agents(agent_dir)
            results = check_agent_files(root)
            fails = [r for r in results if r.status == "FAIL"]
            self.assertEqual(fails, [], f"Unexpected FAILs: {fails}")
            passes = [r for r in results if r.status == "PASS"]
            self.assertGreater(len(passes), 0)

    # A-2: connection-mapper missing Write → FAIL for agent-tools-brainds-connection-mapper
    def test_missing_required_grant_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent_dir = self._make_agent_dir(root)
            self._write_all_agents(agent_dir)
            # Overwrite connection-mapper without Write
            (agent_dir / "brainds-connection-mapper.md").write_text(
                "---\nname: brainds-connection-mapper\ntools:\n  - mcp__brain_ds__map_connections\n---\n",
                encoding="utf-8",
            )
            results = check_agent_files(root)
            target = next(
                (r for r in results if r.name == "agent-tools-brainds-connection-mapper"),
                None,
            )
            self.assertIsNotNone(target, "Expected result for agent-tools-brainds-connection-mapper")
            self.assertEqual(target.status, "FAIL")
            self.assertIn("Write", target.detail)

    # A-3: agent file absent → FAIL for agent-file-brainds-graph-mapper
    def test_missing_agent_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent_dir = self._make_agent_dir(root)
            self._write_all_agents(agent_dir)
            (agent_dir / "brainds-graph-mapper.md").unlink()
            results = check_agent_files(root)
            target = next(
                (r for r in results if r.name == "agent-file-brainds-graph-mapper"),
                None,
            )
            self.assertIsNotNone(target)
            self.assertEqual(target.status, "FAIL")

    # A-4: name: frontmatter mismatch → FAIL for agent-name-brainds-source-explorer
    def test_name_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent_dir = self._make_agent_dir(root)
            self._write_all_agents(agent_dir)
            self._write_agent(agent_dir, "brainds-source-explorer", {"name": "brainds-wrong"})
            results = check_agent_files(root)
            target = next(
                (r for r in results if r.name == "agent-name-brainds-source-explorer"),
                None,
            )
            self.assertIsNotNone(target)
            self.assertEqual(target.status, "FAIL")

    # A-5: query-consultant prompt mirror absent → SKIP never FAIL
    def test_query_consultant_mirror_absent_is_skip_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent_dir = self._make_agent_dir(root)
            self._write_all_agents(agent_dir)
            # no prompts/brainds-query-consultant.md
            results = check_agent_files(root)
            fails = [r for r in results if r.status == "FAIL"]
            self.assertEqual(fails, [], f"No FAIL expected for absent query-consultant mirror; got: {fails}")
            # May be SKIP for query-consultant mirror
            skips = [r for r in results if r.status == "SKIP"]
            self.assertGreater(len(skips), 0, "Expected at least one SKIP for query-consultant mirror")

    # A-6: CRLF/BOM frontmatter still parses as PASS
    def test_crlf_bom_frontmatter_parses_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent_dir = self._make_agent_dir(root)
            self._write_all_agents(agent_dir)
            # Overwrite brd-writer with CRLF + BOM encoding
            content = "---\r\nname: brainds-brd-writer\r\ntools:\r\n  - Write\r\n  - mcp__brain_ds__generate_brd\r\n---\r\n\r\nBody.\r\n"
            (agent_dir / "brainds-brd-writer.md").write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
            results = check_agent_files(root)
            target = next(
                (r for r in results if r.name == "agent-tools-brainds-brd-writer"),
                None,
            )
            self.assertIsNotNone(target)
            self.assertEqual(target.status, "PASS", f"BOM/CRLF must not cause FAIL; got: {target}")

    # A-7: check_agent_files registered — results include at least one agent- name
    def test_agent_check_registered_in_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Write minimal MCP configs so other checks PASS/SKIP cleanly
            (root / ".mcp.json").write_text(
                json.dumps({"mcpServers": {"brain_ds": {"args": ["mcp", "--project-root", "."]}}}),
                encoding="utf-8",
            )
            (root / ".opencode").mkdir()
            (root / ".opencode" / "opencode.json").write_text(
                json.dumps({"mcp": {"brain_ds": {"command": ["exe", "mcp", "--project-root", "."]}}}),
                encoding="utf-8",
            )
            agent_dir = self._make_agent_dir(root)
            self._write_all_agents(agent_dir)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                harness_check_main(root)
            output = stdout.getvalue()
            self.assertIn("agent-", output, "harness_check_main must print at least one agent- check result")


class InstallerWriteGrantTests(unittest.TestCase):
    """T1-16: regression guard — both installers grant write=True to all sub-agents."""

    REPO_ROOT = Path(__file__).resolve().parents[1]

    def test_install_opencode_sh_grants_write_to_all_subagents(self) -> None:
        sh_path = self.REPO_ROOT / "install-opencode.sh"
        if not sh_path.exists():
            self.skipTest("install-opencode.sh not found")
        content = sh_path.read_text(encoding="utf-8")
        self.assertIn(
            '"write": True',
            content,
            "install-opencode.sh must grant write: True to sub-agents",
        )

    def test_install_opencode_ps1_grants_write_to_all_subagents(self) -> None:
        ps1_path = self.REPO_ROOT / "install-opencode.ps1"
        if not ps1_path.exists():
            self.skipTest("install-opencode.ps1 not found")
        content = ps1_path.read_text(encoding="utf-8")
        self.assertIn(
            "write = $true",
            content,
            "install-opencode.ps1 must grant write = $true to sub-agents",
        )


if __name__ == "__main__":
    unittest.main()
