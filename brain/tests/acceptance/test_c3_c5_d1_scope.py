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
  modules of brain/CLAUDE.md's layout exists yet, and no prompt file.

The branch checks use `git merge-base HEAD origin/main`; they skip without git or that ref, and
once the fixture reference is on the branch (contracts-v1.0 tagged and merged).
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
FORBIDDEN_IMPORTS = ("scrubgpt_contracts", "openai")
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+(scrubgpt_contracts|openai)\b", re.MULTILINE)
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


def test_ac15_grep_finds_no_contracts_or_openai_import_under_brain(const):
    """#14 AC15 "`grep` under `brain/` finds no `scrubgpt_contracts` import, no `openai`
    import": no line of any file under brain/ starts an import of either, no Python file imports
    either (statements, `importlib.import_module`, `__import__`), and brain/pyproject.toml
    depends on neither."""
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
    assert not hits, "forbidden imports under brain/:\n" + "\n".join(hits)
    project = tomllib.loads(
        (const.repo_root / "brain" / "pyproject.toml").read_text(encoding="utf-8")
    )
    deps = list(project.get("project", {}).get("dependencies") or [])
    assert not [d for d in deps if re.match(r"\s*(openai|scrubgpt[-_.]contracts)\b", d, re.I)], deps


def test_ac15_grep_finds_no_case_json_file_name_under_brain(const):
    """#14 AC15 "`grep` under `brain/` finds no … reference to `timeline.json`, `moments.json`,
    `case.json`, `questions.json` or `seed_records.json`": a plain text search of every file under
    brain/ (code, docstrings, comments, README, Dev1's unit tests), Tester 1's own folder aside."""
    hits = []
    for path in _brain_files(const, skip_acceptance=True):
        rel = path.relative_to(const.repo_root).as_posix()
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            hits += [f"{rel}:{number}: {name}" for name in CASE_JSON_14 if name in line]
    assert not hits, "case JSON file names under brain/:\n" + "\n".join(hits)


def test_ac15_importing_the_new_modules_loads_no_contracts_or_openai(const):
    """#14 AC15 at run time: importing the loader, C3, C5, D1, C1's reader and the CLI in a fresh
    interpreter leaves `scrubgpt_contracts` and `openai` out of `sys.modules`."""
    code = (
        "import sys, scrubgpt_brain.cli, scrubgpt_brain.engines.rulebook, "
        "scrubgpt_brain.engines.decode, scrubgpt_brain.engines.signals, "
        "scrubgpt_brain.pipeline.audio, scrubgpt_brain.pipeline.frames; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] in "
        "('scrubgpt_contracts', 'openai')))"
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
    if const.reference_fixture_path.is_file():
        pytest.skip(
            "the fixture reference is on the branch, so contracts-v1.0 is tagged and merged: the "
            "D-067 pre-tag scope rule no longer applies"
        )
    try:
        base = _git(const.repo_root, "merge-base", "HEAD", "origin/main").strip()
        lines = _git(const.repo_root, "diff", "--name-status", "--no-renames", base, "HEAD")
    except (OSError, subprocess.SubprocessError) as error:
        pytest.skip(f"needs git with an origin/main ref (a full clone): {error}")
    return [tuple(line.split("\t", 1)) for line in lines.splitlines() if line]


def test_ac15_branch_diff_touches_only_knowledge_brain_and_uv_lock(branch_changes):
    """#14 AC15 "The branch diff against `main` touches only `knowledge/`, `brain/` and
    `uv.lock`" (D-067 "Nothing changes in `contracts/` or `docs/`"), and it holds the four
    D-067 modules."""
    paths = [path for _status, path in branch_changes]
    outside = [p for p in paths if p not in ALLOWED_FILES and not p.startswith(ALLOWED_PREFIXES)]
    assert not outside, f"changed outside knowledge/, brain/ and uv.lock: {outside}"
    for module in (
        "engines/rulebook.py",
        "engines/decode.py",
        "engines/signals.py",
        "pipeline/audio.py",
    ):
        assert f"brain/scrubgpt_brain/{module}" in paths, f"{module} is not on the branch"


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
    exists, the API folder holds no code and there is no prompt file."""
    package = const.repo_root / "brain" / "scrubgpt_brain"
    present = [m for m in LATER_MODULES if (package / m).exists()]
    assert not present, f"modules beyond D-067: {present}"
    api = [p.name for p in (package / "api").glob("*.py")] if (package / "api").is_dir() else []
    prompts = [p.name for p in (package / "prompts").glob("*") if p.name != ".gitkeep"] if (
        package / "prompts"
    ).is_dir() else []  # fmt: skip
    assert not api, f"Brain API code before the tag: {api}"
    assert not prompts, f"prompt files before C2/D2: {prompts}"
