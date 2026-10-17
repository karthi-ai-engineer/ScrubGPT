"""B3/C1: #12 acceptance criteria 8 and 9, and the D-063 limits on `brain/`.

Expected behaviour, written from the spec before the code was opened:
- AC8: "When the FFmpeg CLI is missing, the FFmpeg tests `pytest.skip` with a reason. They don't
  fail." Checked by running Dev1's unit tests (brain/README.md: they "skip when FFmpeg isn't
  installed, as on the CI runner") and Tester 1's B3/C1 tests in a child pytest whose PATH has no
  `ffmpeg`/`ffprobe`: no failure or error, at least one skip, every skip with a reason.
- AC9: "`grep` finds no `scrubgpt_contracts` import under `brain/`. The branch diff against `main`
  touches only `knowledge/`, `brain/` and `uv.lock`. No media file is committed."
- D-063 / #12: "No reading or writing of `case.json`, `timeline.json`, `moments.json`,
  `questions.json` or `seed_records.json`".

Changed after `contracts-v1.0` (T1 brief at 5a89091; D-051 "after the tag, merge `main` … before
any contract-using work"; the D-063/D-067 limits applied only before the tag): `brain/` may now
import the contracts (through the workspace dependency, brain/CLAUDE.md) and B4 writes
`case.json`. What still holds and is tested here: no `openai` import anywhere in `brain/`; the
branch diff against origin/main touches only `knowledge/`, `brain/` and `uv.lock` (CI's dev1/b*
rule); no media committed; B3 and C1 still name and write no case-package JSON.

The branch-diff check reads `git merge-base HEAD origin/main` and skips without git or that ref.
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

OPENAI_RE = re.compile(r"^\s*(?:from|import)\s+openai\b", re.MULTILINE)
ALLOWED_PREFIXES = ("knowledge/", "brain/")  # #12 AC9, D-063
ALLOWED_FILES = {"uv.lock"}
MEDIA_SUFFIXES = {
    ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".mpg", ".mpeg", ".ts", ".wav", ".mp3",
    ".m4a", ".aac", ".flac", ".ogg", ".opus", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".tif", ".tiff",
}  # fmt: skip
CHILD_GUARD = "SCRUBGPT_T1_AC8_CHILD"
FFMPEG_TOOLS = ("ffmpeg", "ffprobe")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        check=True,
        timeout=60,
        text=True,
        encoding="utf-8",
    ).stdout


def _media_magic(head: bytes) -> str | None:
    """A media container or image signature at the start of a file, if any."""
    if head[4:8] == b"ftyp":
        return "MP4/MOV"
    signatures = {
        b"\xff\xd8\xff": "JPEG",
        b"\x89PNG": "PNG",
        b"GIF8": "GIF",
        b"\x1aE\xdf\xa3": "Matroska/WebM",
        b"OggS": "Ogg",
        b"fLaC": "FLAC",
        b"ID3": "MP3",
        b"\x00\x00\x01\xba": "MPEG-PS",
    }
    for magic, kind in signatures.items():
        if head.startswith(magic):
            return kind
    if head.startswith(b"RIFF") and head[8:12] in (b"WAVE", b"AVI ", b"WEBP"):
        return head[8:12].decode().strip()
    return None


# ── AC8 ──────────────────────────────────────────────────────────────────────


def test_ac8_ffmpeg_tests_skip_with_a_reason_when_ffmpeg_is_missing(const, tmp_path):
    """#12 AC8 "When the FFmpeg CLI is missing, the FFmpeg tests `pytest.skip` with a reason.
    They don't fail." Runs brain/tests/unit and Tester 1's B3/C1 tests in a child pytest with
    every PATH folder holding ffmpeg or ffprobe removed; reads the result from JUnit XML."""
    if os.environ.get(CHILD_GUARD):
        pytest.skip("already inside the FFmpeg-less child run")
    folders = [f for f in os.environ.get("PATH", "").split(os.pathsep) if f]
    kept = [f for f in folders if not any(shutil.which(t, path=f) for t in FFMPEG_TOOLS)]
    path = os.pathsep.join(kept)
    assert not any(shutil.which(t, path=path) for t in FFMPEG_TOOLS), "FFmpeg still on PATH"
    acceptance = Path(__file__).resolve().parent
    targets = [
        const.repo_root / "brain" / "tests" / "unit",
        acceptance / "test_b3_normalizer.py",
        acceptance / "test_c1_frames.py",
    ]
    report = tmp_path / "junit.xml"
    child = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *map(str, targets),
            "-q",
            "-p",
            "no:cacheprovider",
            f"--junitxml={report}",
        ],  # fmt: skip
        cwd=const.repo_root,
        capture_output=True,
        timeout=600,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PATH": path, "PYTHONUTF8": "1", CHILD_GUARD: "1"},
    )
    output = f"{child.stdout}\n{child.stderr}"
    assert report.is_file(), (
        f"the child pytest wrote no report (exit {child.returncode}):\n{output}"
    )
    cases = list(ET.parse(report).getroot().iter("testcase"))
    failed = [
        f"{c.get('classname')}::{c.get('name')}"
        for c in cases
        if c.find("failure") is not None or c.find("error") is not None
    ]
    assert not failed, f"tests failed or errored without FFmpeg: {failed}\n{output[-3000:]}"
    assert child.returncode == 0, f"child pytest exited {child.returncode}:\n{output[-3000:]}"
    skipped = [(c, c.find("skipped")) for c in cases if c.find("skipped") is not None]
    unit = [c for c, _ in skipped if "unit" in (c.get("classname") or "")]
    ours = [c for c, _ in skipped if "acceptance" in (c.get("classname") or "")]
    assert unit, "no unit test skipped without FFmpeg (are the FFmpeg unit tests there?)"
    assert ours, "Tester 1's B3/C1 tests did not skip without FFmpeg"
    no_reason = [
        f"{c.get('classname')}::{c.get('name')}"
        for c, s in skipped
        if not (s.get("message") or s.text or "").strip()
    ]
    assert not no_reason, f"skipped without a reason: {no_reason}"


# ── AC9 ──────────────────────────────────────────────────────────────────────


def test_ac9_post_tag_no_openai_import_and_contracts_only_through_the_workspace(const):
    """#12 AC9 as changed after the tag (T1 brief at 5a89091): contract imports are now allowed,
    but "no `openai` import anywhere in `brain/`" still holds (no OpenAI calls yet: C2/D2 aren't
    built). Every text file under brain/ (a line starting an `openai` import) and every Python
    file's imports (statements, `importlib.import_module`, `__import__`). And since the package
    now imports `scrubgpt_contracts`, brain/pyproject.toml declares it and takes it from the
    workspace (brain/CLAUDE.md: "depends on `scrubgpt-contracts` through the workspace only after
    `contracts-v1.0`"), never `openai`."""
    brain = const.repo_root / "brain"
    hits, contract_importers = [], []
    for path in brain.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyd"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(const.repo_root).as_posix()
        if OPENAI_RE.search(text):
            hits.append(f"{rel}: import line")
        if path.suffix != ".py":
            continue
        for node in ast.walk(ast.parse(text, filename=rel)):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Call) and node.args:
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                first = node.args[0]
                if called in {"import_module", "__import__"} and isinstance(first, ast.Constant):
                    names = [str(first.value)]
            if any(n.split(".")[0] == "openai" for n in names):
                hits.append(f"{rel}:{node.lineno}: {names}")
            if any(n.split(".")[0] == "scrubgpt_contracts" for n in names):
                contract_importers.append(rel)
    assert not hits, "openai imported under brain/:\n" + "\n".join(hits)
    project = tomllib.loads((brain / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = list(project.get("project", {}).get("dependencies") or [])
    for group in (project.get("project", {}).get("optional-dependencies") or {}).values():
        requirements += group
    for group in (project.get("dependency-groups") or {}).values():
        requirements += [r for r in group if isinstance(r, str)]
    assert not [r for r in requirements if re.match(r"\s*openai\b", r, re.I)], requirements
    package_imports = [p for p in contract_importers if p.startswith("brain/scrubgpt_brain/")]
    if package_imports:
        declared = [r for r in requirements if re.match(r"\s*scrubgpt[-_.]contracts\b", r, re.I)]
        assert declared, f"{package_imports} import the contracts, which aren't a dependency"
        sources = project.get("tool", {}).get("uv", {}).get("sources") or {}
        assert sources.get("scrubgpt-contracts") == {"workspace": True}, sources


def test_ac9_importing_the_brain_loads_no_openai_module(const):
    """#12 AC9 at run time, as changed after the tag: importing the brain package, its CLI (and
    so every command's module), B3, C1 and the media engine in a fresh interpreter leaves `openai`
    out of `sys.modules`."""
    code = (
        "import sys, scrubgpt_brain, scrubgpt_brain.cli, scrubgpt_brain.pipeline.normalize, "
        "scrubgpt_brain.pipeline.frames, scrubgpt_brain.engines.media; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] == 'openai'))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=const.repo_root,
        capture_output=True,
        timeout=120,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", f"openai modules loaded: {result.stdout}"


@pytest.fixture(scope="module")
def branch_changes(const) -> list[tuple[str, str]]:
    """(status, path) of every file the branch changes since its merge base with origin/main. The
    rule holds after the tag too (CI's dev1/b* rule; T1 brief at 5a89091)."""
    try:
        base = _git(const.repo_root, "merge-base", "HEAD", "origin/main").strip()
        lines = _git(const.repo_root, "diff", "--name-status", "--no-renames", base, "HEAD")
    except (OSError, subprocess.SubprocessError) as error:
        pytest.skip(f"needs git with an origin/main ref (a full clone): {error}")
    return [tuple(line.split("\t", 1)) for line in lines.splitlines() if line]


def test_ac9_branch_diff_touches_only_knowledge_brain_and_uv_lock(branch_changes):
    """#12 AC9 "The branch diff against `main` touches only `knowledge/`, `brain/` and `uv.lock`"
    (D-063 "any change in `contracts/` or `docs/`" stays forbidden; #12 "No other root file
    changes")."""
    paths = [path for _status, path in branch_changes]
    outside = [p for p in paths if p not in ALLOWED_FILES and not p.startswith(ALLOWED_PREFIXES)]
    assert not outside, f"changed outside knowledge/, brain/ and uv.lock: {outside}"
    assert any(p.startswith("brain/scrubgpt_brain/") for p in paths), "no brain package at all"


def test_ac9_no_media_file_is_committed_by_the_branch(const, branch_changes):
    """#12 AC9 "No media file is committed": no file the branch adds or modifies has a media
    extension or starts with a media/image signature (MP4, Matroska, WAV, JPEG, PNG, …)."""
    found = []
    for status, path in branch_changes:
        if status.startswith("D"):
            continue
        file = const.repo_root / path
        if Path(path).suffix.lower() in MEDIA_SUFFIXES:
            found.append(f"{path}: media extension")
        elif file.is_file():
            with file.open("rb") as handle:
                kind = _media_magic(handle.read(16))
            if kind:
                found.append(f"{path}: {kind} data")
    assert not found, "media committed on the branch:\n" + "\n".join(found)


def test_ac9_no_media_file_is_tracked_under_brain_or_knowledge(const):
    """#12 AC9 "No media file is committed", without needing origin/main: `git ls-files` lists no
    media file under brain/ or knowledge/ (media is made in `tmp_path` only, D-036)."""
    try:
        tracked = _git(const.repo_root, "ls-files", "--", "brain", "knowledge").splitlines()
    except (OSError, subprocess.SubprocessError) as error:
        pytest.skip(f"needs git: {error}")
    found = [p for p in tracked if Path(p).suffix.lower() in MEDIA_SUFFIXES]
    for path in tracked:
        file = const.repo_root / path
        if file.is_file() and path not in found:
            with file.open("rb") as handle:
                kind = _media_magic(handle.read(16))
            if kind:
                found.append(f"{path}: {kind} data")
    assert not found, f"media tracked under brain/ or knowledge/: {found}"


# ── D-063: no case JSON ──────────────────────────────────────────────────────


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


# B3 and C1 modules (and the FFmpeg engine they share), which write only their media outputs.
B3_C1_MODULES = ("pipeline/normalize.py", "pipeline/frames.py", "engines/media.py")


def test_d063_b3_and_c1_code_names_no_case_json(const, case_json_names):
    """D-063 / #12 "No reading or writing of `case.json`, `timeline.json`, …", as changed after the
    tag (T1 brief at 5a89091: "B3, C1, … still don't write case-package JSON (only B4 writes
    `case.json`)"): no string in B3's, C1's or the media engine's code (docstrings aside) names a
    case JSON file of plan §4.2, and they don't import the contracts' case-package module (with
    its file list `JSON_FILES`). Their output folders are checked at run time in
    test_b3_normalizer.py and test_c1_frames.py."""
    pattern = re.compile(
        r"(?:^|[/\\{\s\"'])(" + "|".join(re.escape(n) for n in case_json_names) + r")\b"
    )
    package = const.repo_root / "brain" / "scrubgpt_brain"
    hits = []
    for module in B3_C1_MODULES:
        path = package / module
        rel = path.relative_to(const.repo_root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and (pattern.search(node.value) or node.value in case_json_names)
            ):
                hits.append(f"{rel}:{node.lineno}: {node.value!r}")
            if isinstance(node, ast.ImportFrom) and node.module and "case_package" in node.module:
                hits.append(f"{rel}:{node.lineno}: imports {node.module}")
            if isinstance(node, ast.Name) and node.id in {"JSON_FILES", "REQUIRED_FILES"}:
                hits.append(f"{rel}:{node.lineno}: the case-package file list")
    assert not hits, "case JSON in B3/C1 code:\n" + "\n".join(hits)
