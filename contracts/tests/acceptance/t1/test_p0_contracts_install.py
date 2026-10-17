"""AC1: the `scrubgpt-contracts` package and its console scripts (plan §4.5, D-031, #3 point 10)."""

from __future__ import annotations

import importlib
import importlib.metadata as metadata
import re
import shutil
import subprocess


def _console_scripts() -> dict[str, str]:
    dist = metadata.distribution("scrubgpt-contracts")
    return {ep.name: ep.value for ep in dist.entry_points if ep.group == "console_scripts"}


def test_ac1_package_installed_and_importable():
    """AC1: "`uv sync --all-packages` installs the package `scrubgpt-contracts`, importable as
    `scrubgpt_contracts`." (plan §4.5, D-031)"""
    dist = metadata.distribution("scrubgpt-contracts")
    assert dist.metadata["Name"] == "scrubgpt-contracts"
    for module in (
        "scrubgpt_contracts",
        "scrubgpt_contracts.models.common",
        "scrubgpt_contracts.models.case_package",
        "scrubgpt_contracts.models.decision_record",
        "scrubgpt_contracts.models.reference",
        "scrubgpt_contracts.validate",
    ):
        importlib.import_module(module)


def test_ac1_console_scripts_declared():
    """AC1: "The console scripts `scrubgpt-validate`, `scrubgpt-mock-brain` and
    `scrubgpt-codegen` are declared." (plan §4.5 table, D-031; targets per #3 point 10)"""
    scripts = _console_scripts()
    assert {"scrubgpt-validate", "scrubgpt-mock-brain", "scrubgpt-codegen"} <= set(scripts)
    assert scripts["scrubgpt-validate"] == "scrubgpt_contracts.validate:main"
    assert scripts["scrubgpt-mock-brain"].startswith("scrubgpt_contracts.mock_brain")
    assert scripts["scrubgpt-codegen"].startswith("scrubgpt_contracts.codegen")


def test_ac1_validate_script_runs():
    """AC1: the declared `scrubgpt-validate` script is installed and runs (`--help` exits 0)."""
    exe = shutil.which("scrubgpt-validate")
    assert exe, "scrubgpt-validate is not on PATH inside the uv environment"
    proc = subprocess.run([exe, "--help"], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    for sub in ("case", "reference", "response", "live"):
        assert sub in proc.stdout


def test_ac1_dependencies_per_team_lead_3_10():
    """#3 point 10 (Team Lead): dependencies include pydantic (floor >= 2.13, where `UUID7`
    exists), uuid6, `python-multipart` and `httpx`."""
    requires = metadata.distribution("scrubgpt-contracts").requires or []
    names = {re.split(r"[ <>=!~;\[]", r, maxsplit=1)[0].lower(): r for r in requires}
    for needed in ("pydantic", "uuid6", "httpx", "python-multipart"):
        assert needed in names, f"{needed} missing from {requires}"
    floor = re.search(r">=\s*(\d+)\.(\d+)", names["pydantic"])
    assert floor, f"pydantic has no version floor: {names['pydantic']}"
    assert (int(floor.group(1)), int(floor.group(2))) >= (2, 13)
