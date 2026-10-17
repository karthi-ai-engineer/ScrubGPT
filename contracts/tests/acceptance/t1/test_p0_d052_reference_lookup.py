"""#7 AC1, AC2, AC7: how `scrubgpt-validate case` finds the Procedure Reference, and mixed
step-id prefixes (Team Lead answer on issue #7, logged as D-052).

D-052: "Reference lookup: `--reference <file>`, else `<case_dir>/../../reference/<prefix>.json`;
the `DATA_DIR` environment variable is never read (results must not depend on `.env`)."
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

CASE_ID = "case-fixture-01"
FOREIGN_STEP = "lap.p01.s01"  # a well-formed step id of another procedure


def _norm(text: str) -> str:
    return text.replace("\\", "/").lower()


def _names_path(output: str, path: Path) -> bool:
    """True when `output` names `path` (raw, normalised or resolved; any separator)."""
    out = _norm(output)
    forms = {str(path), os.path.normpath(path), str(path.resolve()), path.as_posix()}
    return any(_norm(f) in out for f in forms)


@pytest.fixture
def orphan_case(tmp_path, paths) -> Path:
    """The fixture case in a folder with no `reference/` two levels up."""
    case_dir = tmp_path / "drop" / "2026-10-16" / CASE_ID
    shutil.copytree(paths["case"], case_dir)
    assert not (case_dir / ".." / ".." / "reference").exists()
    return case_dir


@pytest.fixture
def other_data_root(tmp_path, paths) -> Path:
    """A complete DATA_DIR-like folder elsewhere, with a valid `reference/rarp.json`."""
    root = tmp_path / "other-data"
    (root / "reference").mkdir(parents=True)
    shutil.copy2(paths["reference"], root / "reference" / "rarp.json")
    shutil.copytree(paths["case"], root / "cases" / CASE_ID)
    return root


# --- AC1 ------------------------------------------------------------------------------------


def test_7ac1_no_reference_two_levels_up_exits_2(orphan_case, run_validate, monkeypatch):
    """#7 AC1: "A case dir with no `reference/` two levels up and no `--reference` -> exit 2"."""
    monkeypatch.delenv("DATA_DIR", raising=False)
    result = run_validate("case", orphan_case)
    assert result.code == 2, result.output


def test_7ac1_message_names_tried_path_and_reference_option(orphan_case, run_validate, monkeypatch):
    """#7 AC1: "The message names the tried path and `--reference`" (#7 point 1: "a message that
    names the path it tried and suggests `--reference`")."""
    monkeypatch.delenv("DATA_DIR", raising=False)
    result = run_validate("case", orphan_case)
    tried = orphan_case / ".." / ".." / "reference" / "rarp.json"
    assert _names_path(result.output, tried), result.output
    assert "--reference" in result.output, result.output


def test_7ac1_data_dir_env_with_a_reference_changes_nothing(
    orphan_case, other_data_root, run_validate, monkeypatch
):
    """#7 AC1: "Setting the `DATA_DIR` env var changes nothing": a DATA_DIR that holds a valid
    `reference/rarp.json` must not be used (D-052: "the `DATA_DIR` environment variable is never
    read")."""
    monkeypatch.setenv("DATA_DIR", str(other_data_root))
    result = run_validate("case", orphan_case)
    assert result.code == 2, result.output
    tried = orphan_case / ".." / ".." / "reference" / "rarp.json"
    assert _names_path(result.output, tried), result.output
    assert not _names_path(result.output, other_data_root / "reference" / "rarp.json"), (
        result.output
    )


@pytest.mark.parametrize("how", ["broken-reference", "missing-folder", "unset"])
def test_7ac1_data_dir_env_does_not_override_the_layout(
    data_dir, tmp_path, run_validate, monkeypatch, how
):
    """#7 AC1 / D-052: with a valid `reference/rarp.json` two levels up, whatever DATA_DIR says
    (a broken reference, a folder that doesn't exist, unset) the verdict stays exit 0."""
    if how == "broken-reference":
        bad = tmp_path / "bad-data"
        (bad / "reference").mkdir(parents=True)
        (bad / "reference" / "rarp.json").write_text("{ not json", encoding="utf-8")
        monkeypatch.setenv("DATA_DIR", str(bad))
    elif how == "missing-folder":
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "no-such-data-dir"))
    else:
        monkeypatch.delenv("DATA_DIR", raising=False)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 0, result.output


def test_7ac1_two_levels_up_is_used_not_data_dir(
    data_dir, other_data_root, run_validate, monkeypatch
):
    """D-052: the reference two levels up is the one used; DATA_DIR pointing at another valid
    reference does not rescue a two-levels-up reference that lacks a used step."""
    tl = data_dir.load("timeline.json")
    ref = json.loads(data_dir.reference.read_text(encoding="utf-8"))
    used = tl["steps"][0]["step_id"]
    for phase in ref["phases"]:
        phase["steps"] = [s for s in phase["steps"] if s["id"] != used]
        for order, step in enumerate(phase["steps"], start=1):
            step["order"] = order
    data_dir.reference.write_text(json.dumps(ref, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(other_data_root))
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert "timeline.json" in result.problems, result.output


def test_7ac1_reference_option_wins_over_two_levels_up(data_dir, tmp_path, run_validate):
    """#7 point 1: "the order is (a) `--reference <file>`, then (b)
    `<case_dir>/../../reference/<prefix>.json`": a `--reference` lacking a used step makes the
    case fail even though the reference two levels up is valid."""
    tl = data_dir.load("timeline.json")
    ref = json.loads(data_dir.reference.read_text(encoding="utf-8"))
    used = tl["steps"][0]["step_id"]
    for phase in ref["phases"]:
        phase["steps"] = [s for s in phase["steps"] if s["id"] != used]
        for order, step in enumerate(phase["steps"], start=1):
            step["order"] = order
    custom = tmp_path / "custom" / "rarp.json"
    custom.parent.mkdir()
    custom.write_text(json.dumps(ref, ensure_ascii=False), encoding="utf-8")
    assert run_validate("case", data_dir.case_dir).code == 0
    result = run_validate("case", data_dir.case_dir, "--reference", custom)
    assert result.code == 1, result.output


def test_7ac1_reference_file_name_follows_the_step_id_prefix(
    tmp_path, paths, run_validate, monkeypatch
):
    """D-052: the file tried is `<case_dir>/../../reference/<prefix>.json` (the prefix of the step
    ids). A case whose steps all start with `lap.` uses `reference/lap.json`: exit 2 naming
    `lap.json` while only `rarp.json` exists, exit 0 once `lap.json` is there."""
    monkeypatch.delenv("DATA_DIR", raising=False)
    root = tmp_path / "data"
    case_dir = root / "cases" / CASE_ID
    shutil.copytree(paths["case"], case_dir)
    for f in case_dir.glob("*.json"):
        f.write_text(f.read_text(encoding="utf-8").replace('"rarp.', '"lap.'), encoding="utf-8")
    (root / "reference").mkdir()
    shutil.copy2(paths["reference"], root / "reference" / "rarp.json")
    result = run_validate("case", case_dir)
    assert result.code == 2, result.output
    assert "lap.json" in result.output, result.output

    ref = paths["reference"].read_text(encoding="utf-8").replace('"rarp.', '"lap.')
    ref_doc = json.loads(ref)
    ref_doc["id"] = "lap"
    (root / "reference" / "lap.json").write_text(
        json.dumps(ref_doc, ensure_ascii=False), encoding="utf-8"
    )
    assert run_validate("reference", root / "reference" / "lap.json").code == 0
    result = run_validate("case", case_dir)
    assert result.code == 0, result.output


# --- AC2 ------------------------------------------------------------------------------------


def test_7ac2_same_case_with_reference_option_exits_0(
    orphan_case, paths, run_validate, monkeypatch
):
    """#7 AC2: "The same case with `--reference contracts/fixtures/reference/rarp.json` -> exit 0
    (fixture case)" (relative path, run from the repo root)."""
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.chdir(paths["repo"])
    result = run_validate(
        "case", orphan_case, "--reference", "contracts/fixtures/reference/rarp.json"
    )
    assert result.code == 0, result.output


def test_7ac2_console_script_with_reference_option(orphan_case, paths, tmp_path):
    """#7 AC2 through the installed console script, with a DATA_DIR that points nowhere."""
    exe = shutil.which("scrubgpt-validate")
    assert exe
    env = dict(os.environ, DATA_DIR=str(tmp_path / "nowhere"))
    common = dict(cwd=paths["repo"], env=env, capture_output=True, text=True, timeout=120)
    proc = subprocess.run(
        [exe, "case", str(orphan_case), "--reference", "contracts/fixtures/reference/rarp.json"],
        encoding="utf-8",
        errors="replace",
        **common,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    proc = subprocess.run(
        [exe, "case", str(orphan_case)], encoding="utf-8", errors="replace", **common
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr


def test_7ac2_fixture_case_in_place_exits_0(paths, run_validate, monkeypatch):
    """#7 AC2 / plan §4.5 (`contracts/fixtures/` is laid out like DATA_DIR): the fixture case
    itself finds `contracts/fixtures/reference/rarp.json` two levels up -> exit 0 (read only)."""
    monkeypatch.delenv("DATA_DIR", raising=False)
    result = run_validate("case", paths["case"])
    assert result.code == 0, result.output


# --- AC7 ------------------------------------------------------------------------------------


def _mixed_prefix_named(problems: str) -> bool:
    """A mixed-prefix error: a problem line that says "prefix", or names both prefixes (not just
    the reference file `rarp.json` next to the unknown step id `lap.p01.s01`)."""
    for line in problems.splitlines():
        low = line.lower()
        if "prefix" in low:
            return True
        rest = low.replace("rarp.json", "").replace(FOREIGN_STEP, "")
        if "lap" in rest and "rarp" in rest:
            return True
    return False


def _introduce_foreign_step(case_dir: Path, where: str, metrics: dict | None) -> str:
    """Give one step id in `where` the `lap.` prefix; returns the file name changed."""

    def load(name):
        return json.loads((case_dir / name).read_text(encoding="utf-8"))

    def save(name, doc):
        (case_dir / name).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    if where == "timeline":
        doc = load("timeline.json")
        doc["steps"][0]["step_id"] = FOREIGN_STEP
        save("timeline.json", doc)
        return "timeline.json"
    if where == "moments":
        doc = load("moments.json")
        m = next(m for m in doc["moments"] if m["kind"] != "checkpoint")
        m["step_id"] = FOREIGN_STEP
        save("moments.json", doc)
        return "moments.json"
    if where == "seed_records":
        doc = load("seed_records.json")
        doc["records"][0]["step_id"] = FOREIGN_STEP
        save("seed_records.json", doc)
        return "seed_records.json"
    assert metrics is not None
    metrics["per_step"][0]["step_id"] = FOREIGN_STEP
    save("metrics.json", metrics)
    return "metrics.json"


WHERE = ["timeline", "moments", "seed_records", "metrics"]


@pytest.mark.parametrize("where", WHERE)
def test_7ac7_mixed_prefixes_exit_1_without_reference_option(
    data_dir, run_validate, metrics_doc, where
):
    """#7 AC7: "Two step-id prefixes in one case -> exit 1 with a mixed-prefix error" (#7 point 5:
    "Without `--reference`, skip the checks that need the reference and report the mixed-prefix
    error"). The case has `reference/rarp.json` two levels up but no `lap.json`."""
    if where != "metrics":
        data_dir.save("metrics.json", metrics_doc)
    _introduce_foreign_step(data_dir.case_dir, where, metrics_doc)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert _mixed_prefix_named(result.problems), result.output


@pytest.mark.parametrize("where", WHERE)
def test_7ac7_mixed_prefixes_with_reference_option(
    data_dir, run_validate, metrics_doc, paths, where
):
    """#7 AC7 + point 5: "With `--reference`, steps whose prefix doesn't match are also reported
    as unknown steps": exit 1, the mixed-prefix error, and the file with the `lap.` step id is
    named."""
    if where != "metrics":
        data_dir.save("metrics.json", metrics_doc)
    name = _introduce_foreign_step(data_dir.case_dir, where, metrics_doc)
    result = run_validate("case", data_dir.case_dir, "--reference", paths["reference"])
    assert result.code == 1, result.output
    assert _mixed_prefix_named(result.problems), result.output
    assert any(name in ln and FOREIGN_STEP in ln for ln in result.problems.splitlines()), (
        result.output
    )


def test_7ac7_mixed_prefixes_without_any_reference_folder(orphan_case, run_validate, monkeypatch):
    """#7 AC7 ("Two step-id prefixes in one case -> exit 1") with point 5 ("Without
    `--reference`, skip the checks that need the reference and report the mixed-prefix error"):
    no reference is looked up, so there is no "reference not found" exit 2."""
    monkeypatch.delenv("DATA_DIR", raising=False)
    _introduce_foreign_step(orphan_case, "timeline", None)
    result = run_validate("case", orphan_case)
    assert result.code == 1, result.output
    assert _mixed_prefix_named(result.problems), result.output


def test_7ac7_single_prefix_is_not_a_mixed_prefix_error(data_dir, run_validate):
    """#7 AC7 control: the unchanged fixture (one prefix, `rarp`) has no mixed-prefix error."""
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 0, result.output
    assert not _mixed_prefix_named(result.problems), result.output
