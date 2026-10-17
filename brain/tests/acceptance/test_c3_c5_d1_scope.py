"""The loader, C3, C5 pixel signals and D1: #14 acceptance criteria 14 and 15, and the D-067
limits on `brain/` before the tag.

Expected behaviour, written from the spec before the code was opened:
- AC14: "When the FFmpeg CLI is missing, the FFmpeg-based tests `pytest.skip` with a reason (as
  in #12 AC8)." Checked by running Dev1's unit tests and Tester 1's #14 tests in a child pytest
  whose PATH has no `ffmpeg`/`ffprobe`: nothing fails or errors, every skip has a reason, all of
  Tester 1's D1 tests and the C1-based C5 test skip, and the tests that need no FFmpeg (loader,
  C3, the Pillow-frame C5 tests) still run and pass.
- AC15: "`grep` under `brain/` finds no `scrubgpt_contracts` import, no `openai` import, and no
  reference to `timeline.json`, `moments.json`, `case.json`, `questions.json` or
  `seed_records.json`. The branch diff against `main` touches only `knowledge/`, `brain/` and
  `uv.lock`. No media file is committed." Tester 1's own folder is left out of the file-name grep
  (it names the files to look for them).
- D-067 / #14: "no B1, B2 or B4, no C2, D2 or later, and no OpenAI calls": none of the later
  modules of brain/CLAUDE.md's layout exists yet, and no prompt file (before the tag only).

Changed after `contracts-v1.0` (T1 brief at 5a89091; D-051; the D-067 limits applied only before
the tag): contract imports and case files are allowed in `brain/`. What still holds and is tested
here: no `openai` import anywhere in `brain/` (C2/D2 aren't built); the branch diff against
origin/main touches only `knowledge/`, `brain/` and `uv.lock` (CI's dev1/b* rule); no media is
committed; the loader, C3, C5 signals and D1 (with B3 and C1, test_b3_c1_scope.py) still write no
case-package JSON: only B4 writes `case.json`, and the reference export `reference/<id>.json`.

The branch checks use `git merge-base HEAD origin/main` and skip without git or that ref.
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

CHILD_GUARD = "SCRUBGPT_T1_14_AC14_CHILD"
FFMPEG_TOOLS = ("ffmpeg", "ffprobe")
ACCEPTANCE = Path(__file__).resolve().parent
NEW_FILES = (
    "test_loader_knowledge.py",
    "test_c3_decode.py",
    "test_c5_signals.py",
    "test_d1_audio.py",
)
FORBIDDEN_IMPORTS = ("openai",)  # after the tag; scrubgpt_contracts is allowed (T1 brief)
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+(openai)\b", re.MULTILINE)
# The #14 pieces (with B3/C1 in test_b3_c1_scope.py): they write no case-package JSON.
D067_MODULES = (
    "engines/rulebook.py",
    "engines/decode.py",
    "engines/signals.py",
    "pipeline/audio.py",
)
# Case-package JSON nobody may write yet: B4 writes only `case.json` (plan §4.2).
NOT_YET_WRITTEN = (
    "timeline.json",
    "moments.json",
    "questions.json",
    "seed_records.json",
    "metrics.json",
    "trainee.json",
)
CASE_JSON_14 = ("timeline.json", "moments.json", "case.json", "questions.json", "seed_records.json")
ALLOWED_PREFIXES = ("knowledge/", "brain/")
ALLOWED_FILES = {"uv.lock"}
MEDIA_SUFFIXES = {
    ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".mpg", ".mpeg", ".ts", ".wav", ".mp3",
    ".m4a", ".aac", ".flac", ".ogg", ".opus", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".tif", ".tiff",
}  # fmt: skip
# brain/CLAUDE.md "Layout": the stages and engines that come after D-067's list (B1/B2 ingest,
# C2 perception, E-H, the OpenAI gateway), which #14 keeps out until the tag.
LATER_MODULES = (
    "pipeline/ingest.py", "pipeline/perception.py", "pipeline/fuse.py", "pipeline/moments.py",
    "pipeline/questions.py", "pipeline/seed.py", "pipeline/package.py",
    "engines/openai_gateway.py", "engines/deviation.py", "engines/ranking.py",
    "engines/extraction.py", "engines/ask.py",
)  # fmt: skip


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
    if head[4:8] == b"ftyp":
        return "MP4/MOV"
    signatures = {
        b"\xff\xd8\xff": "JPEG", b"\x89PNG": "PNG", b"GIF8": "GIF", b"\x1aE\xdf\xa3": "Matroska",
        b"OggS": "Ogg", b"fLaC": "FLAC", b"ID3": "MP3", b"\x00\x00\x01\xba": "MPEG-PS",
    }  # fmt: skip
    for magic, kind in signatures.items():
        if head.startswith(magic):
            return kind
    if head.startswith(b"RIFF") and head[8:12] in (b"WAVE", b"AVI ", b"WEBP"):
        return head[8:12].decode().strip()
    return None


def _brain_files(const, *, skip_acceptance: bool):
    brain = const.repo_root / "brain"
    for path in sorted(brain.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyd"}:
            continue
        if skip_acceptance and ACCEPTANCE in path.parents:
            continue
        yield path


# ── AC14 ─────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def no_ffmpeg_run(const, tmp_path_factory):
    """Dev1's unit tests and Tester 1's #14 tests, run in a child pytest without FFmpeg on PATH;
    returns (testcases, output)."""
    if os.environ.get(CHILD_GUARD) or os.environ.get("SCRUBGPT_T1_AC8_CHILD"):
        pytest.skip("already inside an FFmpeg-less child run")
    folders = [f for f in os.environ.get("PATH", "").split(os.pathsep) if f]
    kept = [f for f in folders if not any(shutil.which(t, path=f) for t in FFMPEG_TOOLS)]
    path = os.pathsep.join(kept)
    assert not any(shutil.which(t, path=path) for t in FFMPEG_TOOLS), "FFmpeg still on PATH"
    report = tmp_path_factory.mktemp("ac14") / "junit.xml"
    targets = [const.repo_root / "brain" / "tests" / "unit", *(ACCEPTANCE / f for f in NEW_FILES)]
    child = subprocess.run(
        [sys.executable, "-m", "pytest", *map(str, targets), "-q", "-p", "no:cacheprovider",
         f"--junitxml={report}"],
        cwd=const.repo_root,
        capture_output=True,
        timeout=1200,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PATH": path, "PYTHONUTF8": "1", CHILD_GUARD: "1"},
    )  # fmt: skip
    output = f"exit {child.returncode}\n{child.stdout}\n{child.stderr}"
    assert report.is_file(), f"the child pytest wrote no report:\n{output}"
    return list(ET.parse(report).getroot().iter("testcase")), output


def _name(case) -> str:
    return f"{case.get('classname')}::{case.get('name')}"


def test_ac14_ffmpeg_tests_skip_with_a_reason_when_ffmpeg_is_missing(no_ffmpeg_run):
    """#14 AC14 "When the FFmpeg CLI is missing, the FFmpeg-based tests `pytest.skip` with a
    reason (as in #12 AC8)": no failure or error without FFmpeg, every skip has a reason, all of
    Tester 1's D1 tests and Dev1's FFmpeg unit tests skip."""
    cases, output = no_ffmpeg_run
    failed = [
        _name(c) for c in cases if c.find("failure") is not None or c.find("error") is not None
    ]
    assert not failed, f"failed or errored without FFmpeg: {failed}\n{output[-3000:]}"
    assert "exit 0" in output.splitlines()[0], output[-3000:]
    skipped = {_name(c): c.find("skipped") for c in cases if c.find("skipped") is not None}
    no_reason = [n for n, s in skipped.items() if not (s.get("message") or s.text or "").strip()]
    assert not no_reason, f"skipped without a reason: {no_reason}"
    d1 = [_name(c) for c in cases if "test_d1_audio" in (c.get("classname") or "")]
    assert d1 and all(n in skipped for n in d1), (
        f"D1 tests ran without FFmpeg: {set(d1) - set(skipped)}"
    )
    c1_based = [n for n in skipped if "test_c5_signals" in n and "c1_frames" in n]
    assert c1_based, "the C1-based C5 test did not skip without FFmpeg"
    unit = [n for n in skipped if "acceptance" not in n]
    assert any("test_audio" in n for n in unit), "no D1 unit test skipped without FFmpeg"


def test_ac14_tests_that_need_no_ffmpeg_still_run_without_it(no_ffmpeg_run):
    """#14 AC14, the other side: only the FFmpeg-based tests skip. Tester 1's loader and C3 tests
    and the C5 tests on Pillow frames run and pass without FFmpeg (so CI checks them)."""
    cases, _ = no_ffmpeg_run
    for file in ("test_loader_knowledge", "test_c3_decode", "test_c5_signals"):
        mine = [c for c in cases if file in (c.get("classname") or "")]
        assert mine, f"{file}: no test collected"
        skipped = [_name(c) for c in mine if c.find("skipped") is not None]
        if file == "test_c5_signals":
            assert all("c1_frames" in n for n in skipped), f"C5 Pillow tests skipped: {skipped}"
        else:
            assert not skipped, f"{file} skipped without FFmpeg: {skipped}"


# ── AC15 ─────────────────────────────────────────────────────────────────────


def test_ac15_grep_finds_no_openai_import_under_brain(const):
    """#14 AC15 "`grep` under `brain/` finds no … `openai` import", which still holds after the
    tag (T1 brief at 5a89091; the `scrubgpt_contracts` half is lifted by the tag): no line of any
    file under brain/ starts an `openai` import, no Python file imports it (statements,
    `importlib.import_module`, `__import__`), and brain/pyproject.toml doesn't depend on it."""
    hits = []
    for path in _brain_files(const, skip_acceptance=False):
        rel = path.relative_to(const.repo_root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        hits += [f"{rel}: import line {m.group(0).strip()!r}" for m in IMPORT_RE.finditer(text)]
        if path.suffix != ".py":
            continue
        for node in ast.walk(ast.parse(text, filename=rel)):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif (
                isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant)
            ):
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if called in {"import_module", "__import__"}:
                    names = [str(node.args[0].value)]
            hits += [
                f"{rel}:{node.lineno}: {n}" for n in names if n.split(".")[0] in FORBIDDEN_IMPORTS
            ]
    assert not hits, "openai imported under brain/:\n" + "\n".join(hits)
    project = tomllib.loads(
        (const.repo_root / "brain" / "pyproject.toml").read_text(encoding="utf-8")
    )
    deps = list(project.get("project", {}).get("dependencies") or [])
    assert not [d for d in deps if re.match(r"\s*openai\b", d, re.I)], deps


def test_ac15_the_14_pieces_name_no_case_json(const):
    """#14 AC15's case-JSON grep as changed after the tag (T1 brief at 5a89091: "the loader, C3,
    C5 signals, D1 … still don't write case-package JSON"): a plain text search of the loader,
    C3, C5 and D1 modules (code, docstrings and comments) finds none of `timeline.json`,
    `moments.json`, `case.json`, `questions.json` or `seed_records.json`, and they don't import the
    contracts' case-package module."""
    package = const.repo_root / "brain" / "scrubgpt_brain"
    hits = []
    for module in D067_MODULES:
        text = (package / module).read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            hits += [f"{module}:{number}: {name}" for name in CASE_JSON_14 if name in line]
            if "case_package" in line and "import" in line:
                hits.append(f"{module}:{number}: imports the case-package module")
    assert not hits, "case JSON in the #14 modules:\n" + "\n".join(hits)


def _code_strings(tree: ast.AST) -> list[tuple[int, str]]:
    """String constants of a module, its docstrings left out."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and id(node) not in docstrings
    ]  # fmt: skip


def test_post_tag_only_b4_names_case_json_and_nothing_writes_the_rest_yet(const):
    """T1 brief at 5a89091: "only B4 writes `case.json`, and the reference export writes
    `reference/<id>.json`". In the package's code (docstrings aside): `case.json` is named only by
    B4 (pipeline/cases.py) and the CLI's help for B4's `case` command; no module names the other
    case-package files (timeline, moments, questions, seed records, metrics, trainee) or uses the
    contracts' list of package files (`JSON_FILES`, `REQUIRED_FILES`)."""
    package = const.repo_root / "brain" / "scrubgpt_brain"
    hits = []
    for path in sorted(package.rglob("*.py")):
        rel = path.relative_to(package).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        for line, value in _code_strings(tree):
            hits += [f"{rel}:{line}: {name}" for name in NOT_YET_WRITTEN if name in value]
            if "case.json" in value and rel not in ("pipeline/cases.py", "cli.py"):
                hits.append(f"{rel}:{line}: case.json")
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Name):
                names = [node.id]
            elif isinstance(node, ast.ImportFrom):
                names = [alias.name for alias in node.names]
            hits += [f"{rel}: {n}" for n in names if n in {"JSON_FILES", "REQUIRED_FILES"}]
    assert not hits, "case-package JSON outside B4:\n" + "\n".join(hits)


def test_ac15_importing_the_brain_modules_loads_no_openai(const):
    """#14 AC15 at run time, as changed after the tag: importing the loader, C3, C5, D1, C1's
    reader, the post-tag modules (reference export, B4, B1, B2) and the CLI in a fresh interpreter
    leaves `openai` out of `sys.modules`."""
    code = (
        "import sys, scrubgpt_brain.cli, scrubgpt_brain.engines.rulebook, "
        "scrubgpt_brain.engines.decode, scrubgpt_brain.engines.signals, "
        "scrubgpt_brain.pipeline.audio, scrubgpt_brain.pipeline.frames, "
        "scrubgpt_brain.pipeline.reference, scrubgpt_brain.pipeline.cases, "
        "scrubgpt_brain.pipeline.grasp, scrubgpt_brain.pipeline.youtube; "
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
    assert result.stdout.strip() == "[]", f"loaded: {result.stdout}"


@pytest.fixture(scope="module")
def branch_changes(const) -> list[tuple[str, str]]:
    """The branch's changes since origin/main; the rule holds after the tag too (CI's dev1/b*
    rule, T1 brief at 5a89091)."""
    try:
        base = _git(const.repo_root, "merge-base", "HEAD", "origin/main").strip()
        lines = _git(const.repo_root, "diff", "--name-status", "--no-renames", base, "HEAD")
    except (OSError, subprocess.SubprocessError) as error:
        pytest.skip(f"needs git with an origin/main ref (a full clone): {error}")
    return [tuple(line.split("\t", 1)) for line in lines.splitlines() if line]


def test_ac15_branch_diff_touches_only_knowledge_brain_and_uv_lock(branch_changes):
    """#14 AC15 "The branch diff against `main` touches only `knowledge/`, `brain/` and
    `uv.lock`" (D-067 "Nothing changes in `contracts/` or `docs/`"; after the tag, CI's dev1/b*
    rule), and the four D-067 modules are in the tree."""
    paths = [path for _status, path in branch_changes]
    outside = [p for p in paths if p not in ALLOWED_FILES and not p.startswith(ALLOWED_PREFIXES)]
    assert not outside, f"changed outside knowledge/, brain/ and uv.lock: {outside}"
    assert not [p for p in paths if p.startswith(("contracts/", "docs/"))]
    package = Path(__file__).resolve().parents[2] / "scrubgpt_brain"
    for module in D067_MODULES:
        assert (package / module).is_file(), f"{module} is missing"


def test_ac15_no_media_file_is_committed(const, branch_changes):
    """#14 AC15 "No media file is committed": no file the branch adds or modifies, and no file
    tracked under brain/ or knowledge/, has a media extension (FLAC included: D1 writes FLAC) or
    starts with a media signature."""
    paths = {p for status, p in branch_changes if not status.startswith("D")}
    paths |= set(_git(const.repo_root, "ls-files", "--", "brain", "knowledge").splitlines())
    found = []
    for path in sorted(paths):
        file = const.repo_root / path
        if Path(path).suffix.lower() in MEDIA_SUFFIXES:
            found.append(f"{path}: media extension")
        elif file.is_file():
            with file.open("rb") as handle:
                kind = _media_magic(handle.read(16))
            if kind:
                found.append(f"{path}: {kind} data")
    assert not found, "media committed:\n" + "\n".join(found)


# ── D-067: nothing later than the four pieces ────────────────────────────────


def test_d067_no_later_pipeline_stage_or_prompt_yet(const):
    """D-067 / #14 "No reference export, no B1, B2 or B4, no C2, D2 or later, and no OpenAI
    calls": none of the later modules in brain/CLAUDE.md's layout (ingest, perception, fuse,
    moments, questions, seed, package; the OpenAI gateway, deviation, ranking, extraction, ask)
    exists, the API folder holds no code and there is no prompt file. A pre-tag rule: it skips
    once the fixture reference is on the branch (B1, B2, B4 and the export follow the tag)."""
    if const.reference_fixture_path.is_file():
        pytest.skip(
            "contracts-v1.0 is tagged and merged: the D-067 pre-tag limits no longer apply (the "
            "post-tag rules are the openai, case-JSON, branch-diff and media tests)"
        )
    package = const.repo_root / "brain" / "scrubgpt_brain"
    present = [m for m in LATER_MODULES if (package / m).exists()]
    assert not present, f"modules beyond D-067: {present}"
    api = [p.name for p in (package / "api").glob("*.py")] if (package / "api").is_dir() else []
    prompts = [p.name for p in (package / "prompts").glob("*") if p.name != ".gitkeep"] if (
        package / "prompts"
    ).is_dir() else []  # fmt: skip
    assert not api, f"Brain API code before the tag: {api}"
    assert not prompts, f"prompt files before C2/D2: {prompts}"
