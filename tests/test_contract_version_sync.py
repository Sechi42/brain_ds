import re
import unittest
from pathlib import Path

from brain_ds.ui.render_context import CONTRACT_VERSION


class TestContractVersionSync(unittest.TestCase):
    def test_contract_version_ts_matches_python_constant(self):
        ts_path = Path(__file__).resolve().parent.parent / "brain_ds" / "ui" / "src" / "contract_version.ts"
        ts_text = ts_path.read_text(encoding="utf-8")

        match = re.search(r'CONTRACT_VERSION\s*=\s*"([^"]+)"', ts_text)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), CONTRACT_VERSION)

    def test_pr4_semantic_layout_contract_version_bumped(self):
        self.assertGreaterEqual(
            tuple(int(part) for part in CONTRACT_VERSION.split(".")),
            (1, 1, 0),
            "PR4 adds semantic_clusters/semantic_layout payload fields, so the UI contract version must be bumped.",
        )
