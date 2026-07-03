from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OptionalDependencyContractTests(unittest.TestCase):
    def test_gsheets_extra_includes_direct_google_sheets_api_client(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        gsheets = pyproject["project"]["optional-dependencies"]["gsheets"]

        self.assertIn("google-api-python-client>=2", gsheets)


if __name__ == "__main__":
    unittest.main()
