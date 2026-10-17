"""#7 AC6: exit codes of `scrubgpt-validate` (Team Lead answer on issue #7, logged as D-052).

D-052: "Exit codes, every subcommand: 0 = every check ran and passed; 1 = every check ran, at
least one failed; 2 = the run could not complete (usage, missing/unreadable input, unknown
endpoint, reference not found). 2 wins over 1; the checks that could run are still printed."

`response` uses Dev2's real `ENDPOINTS` registry here (`models/brain_api.py`). `live` exit codes
are in test_p0_live_fake_brain.py.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

CASE_ID = "case-fixture-01"
VALID_TRANSLATE = {"contract_version": "1.0", "items": [{"ja": "出血", "en": "Bleeding"}]}


def _write(path: Path, body) -> Path:
    path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def response_file(tmp_path) -> Path:
    return _write(tmp_path / "translate.response.json", VALID_TRANSLATE)


@pytest.fixture
def orphan_case(tmp_path, paths, monkeypatch) -> Path:
    """The fixture case with no `reference/` two levels up (and no DATA_DIR)."""
    monkeypatch.delenv("DATA_DIR", raising=False)
    case_dir = tmp_path / "drop" / "2026-10-16" / CASE_ID
    shutil.copytree(paths["case"], case_dir)
    return case_dir


# --- 0: valid --------------------------------------------------------------------------------


def test_7ac6_valid_case_exits_0(data_dir, run_validate):
    """#7 AC6: "valid -> 0" (`case`)."""
    assert run_validate("case", data_dir.case_dir).code == 0


def test_7ac6_valid_reference_exits_0(paths, tmp_path, run_validate):
    """#7 AC6: "valid -> 0" (`reference`)."""
    target = tmp_path / "rarp.json"
    shutil.copy2(paths["reference"], target)
    assert run_validate("reference", target).code == 0


def test_7ac6_valid_response_exits_0_with_the_real_registry(response_file, run_validate):
    """#7 AC6: "valid -> 0" (`response translate <file>`, real ENDPOINTS registry)."""
    result = run_validate("response", "translate", response_file)
    assert result.code == 0, result.output


# --- 1: invalid ------------------------------------------------------------------------------


def test_7ac6_invalid_case_exits_1(data_dir, run_validate):
    """#7 AC6: "Invalid -> 1" (`case`: a tap option with the built-in id `confirm`)."""
    questions = data_dir.load("questions.json")
    q = next(q for q in questions["operating"] if q["tap_options"])
    q["tap_options"][0]["id"] = "confirm"
    data_dir.save("questions.json", questions)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output


def test_7ac6_invalid_reference_exits_1(paths, tmp_path, run_validate):
    """#7 AC6: "Invalid -> 1" (`reference`: one of the 8 families missing)."""
    doc = json.loads(paths["reference"].read_text(encoding="utf-8"))
    doc["obstacle_taxonomy"] = doc["obstacle_taxonomy"][1:]
    result = run_validate("reference", _write(tmp_path / "rarp.json", doc))
    assert result.code == 1, result.output


@pytest.mark.parametrize(
    "body",
    [
        {"items": [{"ja": "出血", "en": "Bleeding"}]},
        {"contract_version": "1.0", "items": [{"ja": "出血", "en": ""}]},
        {"contract_version": "1.0", "items": "Bleeding"},
    ],
    ids=["no-version", "half-bilingual", "wrong-shape"],
)
def test_7ac6_invalid_response_exits_1_with_the_real_registry(tmp_path, run_validate, body):
    """#7 AC6: "Invalid -> 1" (`response translate <file>`, real ENDPOINTS registry)."""
    result = run_validate("response", "translate", _write(tmp_path / "r.json", body))
    assert result.code == 1, result.output


# --- 2: the run could not complete -----------------------------------------------------------


def test_7ac6_missing_case_dir_exits_2(tmp_path, run_validate):
    """#7 AC6: "Missing file ... -> 2" (`case <dir that doesn't exist>`)."""
    assert run_validate("case", tmp_path / "cases" / CASE_ID).code == 2


def test_7ac6_missing_reference_file_exits_2(tmp_path, run_validate):
    """#7 AC6: "Missing file ... -> 2" (`reference <file that doesn't exist>`; stricter than
    AC16, which allowed 1 or 2 before #7)."""
    result = run_validate("reference", tmp_path / "rarp.json")
    assert result.code == 2, result.output


def test_7ac6_missing_response_file_exits_2(tmp_path, run_validate):
    """#7 AC6: "Missing file ... -> 2" (`response translate <file that doesn't exist>`)."""
    result = run_validate("response", "translate", tmp_path / "nope.json")
    assert result.code == 2, result.output


@pytest.mark.parametrize("command", ["reference", "response"])
def test_7ac6_unreadable_input_exits_2(tmp_path, run_validate, command):
    """D-052: "2 = ... missing/unreadable input": a folder given where a file is expected."""
    folder = tmp_path / "rarp.json"
    folder.mkdir()
    argv = ("reference", folder) if command == "reference" else ("response", "translate", folder)
    result = run_validate(*argv)
    assert result.code == 2, result.output


def test_7ac6_unknown_endpoint_exits_2(response_file, run_validate):
    """#7 AC6: "unknown endpoint -> 2" (real ENDPOINTS registry)."""
    result = run_validate("response", "no_such_endpoint", response_file)
    assert result.code == 2, result.output


def test_7ac6_missing_reference_exits_2(orphan_case, run_validate):
    """#7 AC6: "missing reference -> 2"."""
    result = run_validate("case", orphan_case)
    assert result.code == 2, result.output


def test_7ac6_missing_reference_option_file_exits_2(data_dir, tmp_path, run_validate):
    """#7 AC6: "missing reference -> 2" (`--reference` names a file that doesn't exist, even
    though a reference exists two levels up)."""
    result = run_validate("case", data_dir.case_dir, "--reference", tmp_path / "nope.json")
    assert result.code == 2, result.output


def test_7ac6_invalid_reference_option_exits_2(data_dir, tmp_path, run_validate):
    """D-052, settled by D-055 (#7, Team Lead's newest ruling): a `--reference` that is not a
    valid Procedure Reference is an invalid input -> exit 2 (tightened from "never exit 0")."""
    bad = tmp_path / "rarp.json"
    bad.write_text("{ not json", encoding="utf-8")
    result = run_validate("case", data_dir.case_dir, "--reference", bad)
    assert result.code == 2, result.output


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["no-such-command"],
        ["case"],
        ["reference"],
        ["response", "translate"],
        ["live"],
        ["case", "{case}", "--no-such-option"],
    ],
    ids=repr,
)
def test_7ac6_usage_error_exits_2(data_dir, run_validate, argv):
    """D-052: "2 = the run could not complete (usage, ...)"."""
    args = [a.replace("{case}", str(data_dir.case_dir)) for a in argv]
    assert run_validate(*args).code == 2


# --- 2 wins over 1 ----------------------------------------------------------------------------


def _break_reference_free_checks(case_dir: Path) -> list[str]:
    """Errors that need no Procedure Reference, in files checked early and late. Returns the
    names that must appear in the report."""

    def load(name):
        return json.loads((case_dir / name).read_text(encoding="utf-8"))

    def save(name, doc):
        (case_dir / name).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    case = load("case.json")
    case["language"], case["narrated"] = "none", True
    save("case.json", case)
    questions = load("questions.json")
    q = next(q for q in questions["operating"] if q["tap_options"])
    q["tap_options"][0]["id"] = "reject"
    save("questions.json", questions)
    clip = f"{CASE_ID}.m03.jpg"
    (case_dir / "clips" / clip).unlink()
    seeds = load("seed_records.json")
    r = next(r for r in seeds["records"] if r["reason"] is not None)
    r["grounding"] = [g for g in r["grounding"] if g["field"] != "reason"]
    save("seed_records.json", seeds)
    return ["case.json", "questions.json", clip, "seed_records.json"]


def test_7ac6_missing_reference_with_other_errors_exits_2_and_prints_them(
    orphan_case, run_validate
):
    """#7 AC6: "A missing reference together with other errors -> 2, and those errors are still
    printed" (#7 point 4: "Exit 2 wins over 1 ... the exit code no longer depends on the order of
    the checks")."""
    names = _break_reference_free_checks(orphan_case)
    result = run_validate("case", orphan_case)
    assert result.code == 2, result.output
    for name in names:
        assert name in result.problems, f"{name!r} not reported:\n{result.output}"
    assert "--reference" in result.output, result.output


def test_7ac6_missing_reference_option_file_with_other_errors_exits_2(
    data_dir, tmp_path, run_validate
):
    """#7 AC6: the same with `--reference` naming a missing file."""
    names = _break_reference_free_checks(data_dir.case_dir)
    result = run_validate("case", data_dir.case_dir, "--reference", tmp_path / "nope.json")
    assert result.code == 2, result.output
    for name in names:
        assert name in result.problems, f"{name!r} not reported:\n{result.output}"


def test_7ac6_same_errors_with_a_reference_exit_1(data_dir, run_validate):
    """#7 point 4 control: "Exit 1 must mean complete report" - with the reference found, the
    same errors give exit 1."""
    names = _break_reference_free_checks(data_dir.case_dir)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    for name in names:
        assert name in result.problems, f"{name!r} not reported:\n{result.output}"


def test_7ac6_console_script_exit_2_and_errors_on_output(orphan_case, paths, tmp_path):
    """#7 AC6 through the installed console script (DATA_DIR pointing at a valid reference
    changes nothing, D-052)."""
    names = _break_reference_free_checks(orphan_case)
    exe = shutil.which("scrubgpt-validate")
    assert exe
    env = dict(os.environ, DATA_DIR=str(paths["fixtures"]))
    proc = subprocess.run(
        [exe, "case", str(orphan_case)],
        cwd=paths["repo"],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    for name in names:
        assert name in proc.stdout + proc.stderr, proc.stdout + proc.stderr
