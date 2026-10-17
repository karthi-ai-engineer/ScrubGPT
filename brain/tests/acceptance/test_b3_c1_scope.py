"""B3/C1: #12 acceptance criteria 8 and 9, and the D-063 limits on `brain/` before the tag.

Expected behaviour, written from the spec before the code was opened:
- AC8: "When the FFmpeg CLI is missing, the FFmpeg tests `pytest.skip` with a reason. They don't
  fail." Checked by running Dev1's unit tests (brain/README.md: they "skip when FFmpeg isn't
  installed, as on the CI runner") and Tester 1's B3/C1 tests in a child pytest whose PATH has no
  `ffmpeg`/`ffprobe`: no failure or error, at least one skip, every skip with a reason.
- AC9: "`grep` finds no `scrubgpt_contracts` import under `brain/`. The branch diff against `main`
  touches only `knowledge/`, `brain/` and `uv.lock`. No media file is committed."
- D-063 / #12: "No reading or writing of `case.json`, `timeline.json`, `moments.json`,
  `questions.json` or `seed_records.json`": no Python code in `brain/` (outside Tester 1's own
  folder) names a case JSON file of plan §4.2.

The branch-diff check reads `git merge-base HEAD origin/main` and skips without git or that ref,
and once the fixture reference is on the branch (contracts-v1.0 tagged and merged: the pre-tag
rule no longer applies, as in test_a1_a4_scope.py).
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

IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+scrubgpt_contracts\b", re.MULTILINE)
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


def test_ac9_grep_finds_no_scrubgpt_contracts_import_under_brain(const):
    """#12 AC9 "`grep` finds no `scrubgpt_contracts` import under `brain/`" (D-063 "No `import
    scrubgpt_contracts` anywhere in `brain/`"). Every text file under brain/ (a line starting with
    `import scrubgpt_contracts` or `from scrubgpt_contracts`), every Python file's import
    statements and `importlib.import_module` / `__import__` calls, and the brain dependencies."""
    brain = const.repo_root / "brain"
    hits = []
    for path in brain.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyd"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(const.repo_root).as_posix()
        if IMPORT_RE.search(text):
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
            if any(n.split(".")[0] == "scrubgpt_contracts" for n in names):
                hits.append(f"{rel}:{node.lineno}: {names}")
    assert not hits, "scrubgpt_contracts imported under brain/:\n" + "\n".join(hits)
    project = tomllib.loads((brain / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = list(project.get("project", {}).get("dependencies") or [])
    for group in (project.get("project", {}).get("optional-dependencies") or {}).values():
        requirements += group
    for group in (project.get("dependency-groups") or {}).values():
        requirements += [r for r in group if isinstance(r, str)]
    sources = project.get("tool", {}).get("uv", {}).get("sources") or {}
    assert not [r for r in requirements if re.match(r"\s*scrubgpt[-_.]contracts", r, re.I)]
    assert not [s for s in sources if re.match(r"scrubgpt[-_.]contracts", s, re.I)]


def test_ac9_importing_the_brain_loads_no_contracts_module(const):
    """#12 AC9 at run time: importing the brain package, its CLI, B3, C1 and the media engine in a
    fresh interpreter leaves `scrubgpt_contracts` out of `sys.modules`."""
    code = (
        "import sys, scrubgpt_brain, scrubgpt_brain.cli, scrubgpt_brain.pipeline.normalize, "
        "scrubgpt_brain.pipeline.frames, scrubgpt_brain.engines.media; "
        "print(sorted(m for m in sys.modules if m.startswith('scrubgpt_contracts')))"
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
    assert result.stdout.strip() == "[]", f"contracts modules loaded: {result.stdout}"


@pytest.fixture(scope="module")
def branch_changes(const) -> list[tuple[str, str]]:
    """(status, path) of every file the branch changes since its merge base with origin/main."""
    if const.reference_fixture_path.is_file():
        pytest.skip(
            "the fixture reference is on the branch, so contracts-v1.0 is tagged and merged: the "
            "D-063 pre-tag scope rule no longer applies"
        )
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


def test_d063_brain_code_reads_and_writes_no_case_json(const, case_json_names):
    """D-063 "Still forbidden until the tag: … reading or writing case JSON files" (#12: "No
    reading or writing of `case.json`, `timeline.json`, `moments.json`, `questions.json` or
    `seed_records.json`"). No string in the Python code of brain/ (the package and Dev1's unit
    tests; docstrings and comments aside) names a case JSON file of plan §4.2. Tester 1's own
    folder is left out: it names them to check for them."""
    pattern = re.compile(
        r"(?:^|[/\\{\s\"'])(" + "|".join(re.escape(n) for n in case_json_names) + r")\b"
    )
    brain = const.repo_root / "brain"
    acceptance = Path(__file__).resolve().parent
    hits = []
    for path in brain.rglob("*.py"):
        if acceptance in path.parents or "__pycache__" in path.parts:
            continue
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
    assert not hits, "case JSON file names in brain/ code:\n" + "\n".join(hits)
