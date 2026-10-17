"""Pre-tag scope of the early Block 1 work (criterion 13 of the A1-A4 brief; D-051, widened by
D-062 (#11) and D-063 (#12)).

Expected (criterion 13 as changed by the B3/C1 brief, under D-063): "since its merge base with
origin/main, dev1/b1 changes only knowledge/, brain/ and uv.lock; nothing in contracts/ or docs/
changes, and nothing imports scrubgpt_contracts". `brain/pyproject.toml` is now the real
`scrubgpt-brain` project (console script, a build backend), and its dependencies are only ones
the code imports: today Pillow and PyYAML, within D-063's list (`pyyaml`, `numpy`, `pillow`);
`httpx` and `openai` are not allowed yet. `uv.lock` is re-locked for those dependencies only.

The rule only holds before `contracts-v1.0`: after the tag, main is merged into dev1/b1 and other
work is allowed (D-051, D-063), so these tests skip once the fixture reference is on the branch
(the same signal #11 uses). They need git and an `origin/main` ref, and skip without them (CI's
shallow checkouts). They read commits by sha; they never read `origin/p0/contracts` (#11).
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib

import pytest

ALLOWED_FILES = {"uv.lock"}  # D-063 / #12 "The root uv.lock is re-locked. No other root file"
ALLOWED_PREFIXES = ("knowledge/", "brain/")  # D-063 / #12 AC9
PYYAML_REQUIREMENT = "pyyaml>=6.0.2,<7"  # #11 Team Lead decision, item 1 (D-062)
# D-063: "only the dependencies the code imports: `pyyaml`, `numpy`, `pillow`; `httpx`/`openai`
# when code needs them". Distribution name -> the module the code imports.
D063_DEPENDENCIES = {"pyyaml": "yaml", "numpy": "numpy", "pillow": "PIL"}
NOT_YET = {"httpx", "openai", "scrubgpt-contracts"}  # D-063, D-051
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


def _dist(requirement: str) -> str:
    """The normalised distribution name of a PEP 508 requirement ("PyYAML>=6" -> "pyyaml")."""
    name = re.split(r"[\s<>=!~;\[(@]", requirement.strip(), maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", name).lower()


def _imported_modules(root) -> set[str]:
    """Top-level modules imported (absolute imports) by the Python files under `root`."""
    found: set[str] = set()
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
            if isinstance(node, ast.Import):
                found |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                found.add(node.module.split(".")[0])
    return found


def test_c13_branch_changes_only_knowledge_brain_and_uv_lock(changed):
    """C13 as changed by the B3/C1 brief: "since its merge base with origin/main, dev1/b1 changes
    only knowledge/, brain/ and uv.lock; nothing in contracts/ or docs/" (D-063 "Still forbidden
    until the tag: … any change in `contracts/` or `docs/`"; #12 "The root uv.lock is re-locked.
    No other root file changes"; #12 AC9)."""
    outside = [
        path
        for path in changed
        if path not in ALLOWED_FILES and not path.startswith(ALLOWED_PREFIXES)
    ]
    assert not outside, f"changed outside the D-063 scope: {outside}"
    assert not [p for p in changed if p.startswith(("contracts/", "docs/"))]
    assert any(path.startswith("knowledge/") for path in changed), "no knowledge/ change at all"


def test_c13_brain_pyproject_is_the_real_package_with_only_imported_dependencies(const, base):
    """C13 as changed by the B3/C1 brief: "brain/pyproject.toml is now the real `scrubgpt-brain`
    project. Its dependencies must be ones the code imports: today Pillow and PyYAML; `httpx` and
    `openai` are not allowed yet" (D-063 "the real `brain/` package (`scrubgpt-brain`, console
    scripts, only the dependencies the code imports: `pyyaml`, `numpy`, `pillow`)"; #12 item 1).
    "The code" is the Python under brain/: PyYAML is imported by Tester 1's A1-A4 tests (D-062),
    Pillow by the package. The PyYAML pin of D-062 stays, and every third-party module the package
    imports is declared (else it breaks in a clean install)."""
    brain = const.repo_root / "brain"
    now = tomllib.loads((brain / "pyproject.toml").read_text(encoding="utf-8"))
    before = tomllib.loads(_git(const.repo_root, "show", f"{base}:brain/pyproject.toml"))
    project = now.get("project", {})
    assert project.get("name") == "scrubgpt-brain"
    assert "scrubgpt-brain" in (project.get("scripts") or {}), "no `scrubgpt-brain` console script"
    assert now.get("tool", {}).get("uv", {}).get("package") is not False, "still package = false"
    assert now.get("build-system", {}).get("build-backend"), "no build backend: not a package"
    assert project.get("requires-python") == before.get("project", {}).get("requires-python")

    requirements = list(project.get("dependencies") or [])
    names = [_dist(r) for r in requirements]
    assert len(names) == len(set(names)), f"duplicate dependencies: {requirements}"
    assert not set(names) & NOT_YET, f"not allowed before the tag (D-063): {requirements}"
    assert set(names) <= set(D063_DEPENDENCIES), f"outside D-063's list: {requirements}"
    assert PYYAML_REQUIREMENT in requirements, f"the D-062 PyYAML pin changed: {requirements}"

    imported = _imported_modules(brain)
    unused = [n for n in names if D063_DEPENDENCIES[n] not in imported]
    assert not unused, f"declared but imported by no code under brain/: {unused}"
    package = _imported_modules(brain / "scrubgpt_brain")
    third_party = {m for m in package if m not in sys.stdlib_module_names and m != "scrubgpt_brain"}
    declared = {D063_DEPENDENCIES[n] for n in names}
    assert third_party <= declared, f"imported by scrubgpt_brain but not declared: {third_party}"


def test_c13_uv_lock_relocks_only_the_brain_dependencies(const, base):
    """C13 "… and uv.lock" (D-063 "`uv.lock` re-locked"; #12 "The root uv.lock is re-locked"):
    against the merge base, the lock adds exactly the brain project's declared dependencies (no
    others), removes nothing, and changes only scrubgpt-brain, which is now a real (editable)
    package depending on exactly those; the manifest and Python requirement are unchanged."""
    now = tomllib.loads(_git(const.repo_root, "show", "HEAD:uv.lock"))
    before = tomllib.loads(_git(const.repo_root, "show", f"{base}:uv.lock"))
    brain = tomllib.loads(_git(const.repo_root, "show", "HEAD:brain/pyproject.toml"))
    declared = {_dist(r) for r in brain.get("project", {}).get("dependencies") or []}
    now_pkgs = {p["name"]: p for p in now.get("package", [])}
    before_pkgs = {p["name"]: p for p in before.get("package", [])}
    assert set(now_pkgs) - set(before_pkgs) == declared, (
        f"added to the lock: {set(now_pkgs) - set(before_pkgs)}; declared: {declared}"
    )
    assert set(before_pkgs) - set(now_pkgs) == set()
    changed_pkgs = {
        name for name in before_pkgs if name in now_pkgs and now_pkgs[name] != before_pkgs[name]
    }
    assert changed_pkgs <= {"scrubgpt-brain"}, f"other locked packages changed: {changed_pkgs}"
    entry = now_pkgs["scrubgpt-brain"]
    assert {d["name"] for d in entry.get("dependencies") or []} == declared
    assert entry.get("source") == {"editable": "brain"}, f"not a real package: {entry['source']}"
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
