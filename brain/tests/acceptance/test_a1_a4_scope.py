"""D-051 scope of the early Block 1 work (criterion 13 of the A1-A4 brief; D-051 narrowed by #11).

Expected: "since its merge base with origin/main, dev1/b1 changes only knowledge/, plus exactly
brain/pyproject.toml (the PyYAML dependency only, still package = false, no other brain/ files)
and uv.lock (#11); nothing in contracts/ changes, and nothing imports scrubgpt_contracts".
`brain/tests/acceptance/` is Tester 1's own folder (D-044) and may also appear once Dev1
cherry-picks the T1 commit.

The rule only holds before `contracts-v1.0`: after the tag, main is merged into dev1/b1 and other
brain/ work is allowed (D-051), so these tests skip once the fixture reference is on the branch
(the same signal #11 uses). They need git and an `origin/main` ref, and skip without them (CI's
shallow checkouts). They read commits by sha; they never read `origin/p0/contracts` (#11).
"""

from __future__ import annotations

import re
import subprocess
import tomllib

import pytest

ALLOWED_FILES = {"brain/pyproject.toml", "uv.lock"}
ALLOWED_PREFIXES = ("knowledge/", "brain/tests/acceptance/")
PYYAML_REQUIREMENT = "pyyaml>=6.0.2,<7"  # #11 Team Lead decision, item 1
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+scrubgpt_contracts\b", re.MULTILINE)


def _git(root, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        check=True,
        timeout=60,
        text=True,
        encoding="utf-8",
    ).stdout


@pytest.fixture(scope="module")
def base(const) -> str:
    if const.reference_fixture_path.is_file():
        pytest.skip(
            "the fixture reference is on the branch, so contracts-v1.0 is tagged and merged: the "
            "D-051 pre-tag scope rule no longer applies"
        )
    try:
        return _git(const.repo_root, "merge-base", "HEAD", "origin/main").strip()
    except (OSError, subprocess.SubprocessError) as error:
        pytest.skip(f"needs git with an origin/main ref (a full clone): {error}")


@pytest.fixture(scope="module")
def changed(const, base) -> list[str]:
    return [
        line
        for line in _git(const.repo_root, "diff", "--name-only", base, "HEAD").splitlines()
        if line
    ]


def test_c13_branch_changes_only_knowledge_and_the_pyyaml_files(changed):
    """C13 "since its merge base with origin/main, dev1/b1 changes only knowledge/, plus exactly
    brain/pyproject.toml … and uv.lock (#11)" (D-051; #11 "dev1/b1 may change exactly two files
    outside knowledge/")."""
    outside = [
        path
        for path in changed
        if path not in ALLOWED_FILES and not path.startswith(ALLOWED_PREFIXES)
    ]
    assert not outside, f"changed outside the D-051/#11 scope: {outside}"
    assert any(path.startswith("knowledge/") for path in changed), "no knowledge/ change at all"


def test_c13_brain_pyproject_adds_only_pyyaml_and_stays_package_false(const, base):
    """C13 "brain/pyproject.toml (the PyYAML dependency only, still package = false, no other
    brain/ files)" (#11: `dependencies = ["pyyaml>=6.0.2,<7"]` only; "It stays package = false,
    with no code, no other dependencies")."""
    now = tomllib.loads((const.repo_root / "brain" / "pyproject.toml").read_text(encoding="utf-8"))
    before = tomllib.loads(_git(const.repo_root, "show", f"{base}:brain/pyproject.toml"))
    assert now.get("project", {}).get("dependencies") == [PYYAML_REQUIREMENT]
    assert now.get("tool", {}).get("uv", {}).get("package") is False
    now["project"].pop("dependencies", None)
    before.get("project", {}).pop("dependencies", None)
    assert now == before, "brain/pyproject.toml changed beyond its dependency list"


def test_c13_uv_lock_relocks_only_pyyaml(const, base):
    """C13 "… and uv.lock (#11)" (#11: "Root uv.lock: re-locked for that one package"): against the
    merge base, the lock adds only the `pyyaml` package and changes only scrubgpt-brain, whose new
    dependency is pyyaml; the manifest and Python requirement are unchanged."""
    now = tomllib.loads(_git(const.repo_root, "show", "HEAD:uv.lock"))
    before = tomllib.loads(_git(const.repo_root, "show", f"{base}:uv.lock"))
    now_pkgs = {p["name"]: p for p in now.get("package", [])}
    before_pkgs = {p["name"]: p for p in before.get("package", [])}
    assert set(now_pkgs) - set(before_pkgs) == {"pyyaml"}
    assert set(before_pkgs) - set(now_pkgs) == set()
    changed_pkgs = {
        name for name in before_pkgs if name in now_pkgs and now_pkgs[name] != before_pkgs[name]
    }
    assert changed_pkgs <= {"scrubgpt-brain"}, f"other locked packages changed: {changed_pkgs}"
    assert now_pkgs["scrubgpt-brain"].get("dependencies") == [{"name": "pyyaml"}]
    assert now.get("manifest") == before.get("manifest")
    assert now.get("requires-python") == before.get("requires-python")


def test_c13_nothing_in_contracts_changes_and_nothing_imports_the_contracts(const, changed):
    """C13 "nothing in contracts/ changes, and nothing imports scrubgpt_contracts" (D-051 "nothing
    in brain/, contracts/ or root files, nothing that imports scrubgpt_contracts"). Scans every
    Python file under knowledge/ and brain/, and the brain project's dependency list."""
    assert not [p for p in changed if p.startswith("contracts/")]
    importers = [
        path.relative_to(const.repo_root).as_posix()
        for folder in ("knowledge", "brain")
        for path in (const.repo_root / folder).rglob("*.py")
        if IMPORT_RE.search(path.read_text(encoding="utf-8", errors="replace"))
    ]
    assert not importers, f"files importing the contracts package: {importers}"
    brain = tomllib.loads(
        (const.repo_root / "brain" / "pyproject.toml").read_text(encoding="utf-8")
    )
    deps = brain.get("project", {}).get("dependencies") or []
    assert not [d for d in deps if "scrubgpt-contracts" in d or "scrubgpt_contracts" in d]
