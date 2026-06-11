"""Suite-wide isolation: keep tests out of the user's real ~/.brain_ds registry."""

from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolated_brain_ds_home():
    with tempfile.TemporaryDirectory() as home:
        previous = os.environ.get("BRAIN_DS_HOME")
        os.environ["BRAIN_DS_HOME"] = home
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("BRAIN_DS_HOME", None)
            else:
                os.environ["BRAIN_DS_HOME"] = previous
