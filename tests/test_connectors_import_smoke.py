"""Import smoke tests for the connectors package."""
from __future__ import annotations

import subprocess
import sys


def test_import_brain_ds_connectors_in_fresh_process():
    result = subprocess.run(
        [sys.executable, "-c", "import brain_ds.connectors; print('ok')"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
