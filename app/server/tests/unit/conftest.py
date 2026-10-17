"""Shared fixtures for Dev2's app-server unit tests (synthetic fixtures only, D-036)."""

import shutil
from pathlib import Path

import pytest
from scrubgpt_app.settings import REPO_ROOT

FIXTURES = REPO_ROOT / "contracts" / "fixtures"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A writable copy of the fixture DATA_DIR (one case + the reference)."""
    target = tmp_path / "data"
    shutil.copytree(FIXTURES / "cases" / "case-fixture-01", target / "cases" / "case-fixture-01")
    shutil.copytree(FIXTURES / "reference", target / "reference")
    return target
