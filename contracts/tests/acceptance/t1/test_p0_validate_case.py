"""AC15: `scrubgpt-validate case <dir> [--reference <file>]` (plan §4.2, §4.5; D-038; #4
cross-file checks)."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

CASE_ID = "case-fixture-01"


def _assert_fails_naming(result, *names: str) -> None:
    assert result.code == 1, f"expected exit 1, got {result.code}\n{result.output}"
    for name in names:
        assert name in result.problems, f"{name!r} not named in an error:\n{result.output}"


def test_ac15_valid_package_exits_0(data_dir, run_validate):
    """AC15: "exit 0 on a valid package"."""
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 0, result.output


@pytest.mark.parametrize(
    "name",
    [
        "case.json",
        "video.mp4",
        "poster.jpg",
        "timeline.json",
        "moments.json",
        "questions.json",
        "clips",
        "seed_records.json",
    ],
)
def test_ac15_missing_required_file(data_dir, run_validate, name):
    """AC15: "exit 1, with an error naming the file, for ... a missing required file" (plan
    §4.2 Required column)."""
    target = data_dir.case_dir / name
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    _assert_fails_naming(run_validate("case", data_dir.case_dir), name)


def test_ac15_optional_files_may_be_absent(data_dir, run_validate):
    """§4.2: `thumbs/` and `metrics.json` (GraSP only) are optional. The fixture now ships a
    metrics.json (#9 AC12), so this copy deletes it."""
    (data_dir.case_dir / "metrics.json").unlink()
    assert not (data_dir.case_dir / "metrics.json").exists()
    assert not (data_dir.case_dir / "thumbs").exists()
    assert run_validate("case", data_dir.case_dir).code == 0


def test_ac15_invalid_file_named_and_others_still_checked(data_dir, run_validate):
    """AC15: "an invalid file (the other files are still checked, D-038)": two broken files in
    one package are both reported."""
    (data_dir.case_dir / "moments.json").write_text("{ not json", encoding="utf-8")
    questions = data_dir.load("questions.json")
    i = next(i for i, q in enumerate(questions["operating"]) if q["tap_options"])
    questions["operating"][i]["tap_options"][0]["id"] = "confirm"
    data_dir.save("questions.json", questions)
    timeline = data_dir.load("timeline.json")
    timeline["steps"][0]["t_start"] = -3.0
    data_dir.save("timeline.json", timeline)
    _assert_fails_naming(
        run_validate("case", data_dir.case_dir), "moments.json", "questions.json", "timeline.json"
    )


@pytest.mark.parametrize(
    "name",
    ["case.json", "timeline.json", "moments.json", "questions.json", "seed_records.json"],
)
def test_ac15_each_invalid_json_file_is_named(data_dir, run_validate, name):
    """AC15: "an invalid file" -> exit 1 with an error naming that file (every JSON file of
    §4.2)."""
    (data_dir.case_dir / name).write_text('{"contract_version": "1.0", "broken": ', "utf-8")
    _assert_fails_naming(run_validate("case", data_dir.case_dir), name)


def test_ac15_case_json_rule_violation_is_named(data_dir, run_validate):
    """AC15: an invalid case.json (a model rule, #4 point 9: `language: none` with
    `narrated: true`) is reported against case.json."""
    case = data_dir.load("case.json")
    case["language"] = "none"
    case["narrated"] = True
    data_dir.save("case.json", case)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "case.json")


def test_ac15_scores_not_descending_is_only_a_warning(data_dir, run_validate):
    """#4 point 6 (Team Lead): "Rank = list order; `validate.py` warns when `score` isn't
    descending" - a warning naming moments.json, not an error (exit 0)."""
    moments = data_dir.load("moments.json")
    first, last = moments["moments"][0], moments["moments"][-1]
    first["score"], last["score"] = last["score"], first["score"]
    data_dir.save("moments.json", moments)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 0, result.output
    assert "moments.json" in result.problems, result.output


def test_ac15_invalid_metrics_file_is_reported(data_dir, run_validate, metrics_doc):
    """AC15 + §4.2: an optional file that is present is validated too ("The loader validates
    every file that is present")."""
    metrics_doc["frame_accuracy"] = 1.7
    data_dir.save("metrics.json", metrics_doc)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "metrics.json")


def test_ac15_valid_metrics_file_passes(data_dir, run_validate, metrics_doc):
    """§4.2: a valid metrics.json does not break a valid package."""
    data_dir.save("metrics.json", metrics_doc)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 0, result.output


def test_ac15_metrics_step_not_in_reference(data_dir, run_validate, metrics_doc):
    """AC15: a step id that isn't in the reference (metrics `per_step[].step_id`)."""
    metrics_doc["per_step"][0]["step_id"] = "rarp.p03.s09"
    data_dir.save("metrics.json", metrics_doc)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "metrics.json")


# --- ids that are not in the reference -----------------------------------------------------


def test_ac15_timeline_step_not_in_reference(data_dir, run_validate):
    """AC15: "a step ... id that isn't in the reference" (timeline `step_id`, #4)."""
    tl = data_dir.load("timeline.json")
    tl["steps"][0]["step_id"] = "rarp.p03.s09"
    data_dir.save("timeline.json", tl)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "timeline.json")


def test_ac15_moment_step_not_in_reference(data_dir, run_validate):
    """AC15: a moment `step_id` that isn't in the reference."""
    moments = data_dir.load("moments.json")
    i = next(i for i, m in enumerate(moments["moments"]) if m["kind"] != "checkpoint")
    moments["moments"][i]["step_id"] = "rarp.p04.s09"
    data_dir.save("moments.json", moments)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "moments.json")


def test_ac15_moment_checkpoint_not_in_reference(data_dir, run_validate):
    """AC15: "a ... checkpoint ... id that isn't in the reference"."""
    moments = data_dir.load("moments.json")
    m = next(m for m in moments["moments"] if m["kind"] == "checkpoint")
    m["checkpoint_id"] = f"{m['step_id']}.c9"
    data_dir.save("moments.json", moments)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "moments.json")


def test_ac15_moment_obstacle_not_in_reference(data_dir, run_validate):
    """AC15: "an ... obstacle id that isn't in the reference" (`draft_obstacle`, #4)."""
    moments = data_dir.load("moments.json")
    m = next(m for m in moments["moments"] if m["draft_obstacle"])
    m["draft_obstacle"] = "bleeding.not_a_known_leaf"
    data_dir.save("moments.json", moments)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "moments.json")


def test_ac15_record_obstacle_not_in_reference(data_dir, run_validate):
    """AC15: a seed record `obstacle.type` that isn't in the reference taxonomy."""
    seeds = data_dir.load("seed_records.json")
    r = next(r for r in seeds["records"] if r["obstacle"] and r["obstacle"]["type"])
    r["obstacle"]["type"] = f"{r['obstacle']['family']}.not_a_known_leaf"
    data_dir.save("seed_records.json", seeds)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "seed_records.json")


def test_ac15_record_step_not_in_reference(data_dir, run_validate):
    """AC15: a seed record `step_id` that isn't in the reference."""
    seeds = data_dir.load("seed_records.json")
    seeds["records"][0]["step_id"] = "rarp.p04.s09"
    data_dir.save("seed_records.json", seeds)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "seed_records.json")


# --- times --------------------------------------------------------------------------------


def test_ac15_timeline_time_after_duration(data_dir, run_validate):
    """AC15: "a time after `duration_s`" (timeline item)."""
    tl = data_dir.load("timeline.json")
    tl["utterances"][-1]["t_end"] = 300.5
    data_dir.save("timeline.json", tl)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "timeline.json")


def test_ac15_moment_time_after_duration(data_dir, run_validate):
    """AC15: "a time after `duration_s`" (moment)."""
    moments = data_dir.load("moments.json")
    moments["moments"][0]["t_start"] = 310.0
    moments["moments"][0]["t_end"] = 330.0
    data_dir.save("moments.json", moments)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "moments.json")


def test_ac15_record_evidence_time_after_duration(data_dir, run_validate):
    """AC15: "a time after `duration_s`" (media evidence in a seed record)."""
    seeds = data_dir.load("seed_records.json")
    r = seeds["records"][0]
    ev = next(e for e in r["evidence"] if e["kind"] == "media")
    ev["t_start"], ev["t_end"], ev["uri"] = 380.0, 400.0, "video.mp4#t=380.0,400.0"
    data_dir.save("seed_records.json", seeds)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "seed_records.json")


def test_ac15_time_equal_to_duration_is_fine(data_dir, run_validate):
    """AC15: a time *at* `duration_s` is not "after" it."""
    tl = data_dir.load("timeline.json")
    tl["steps"][-1]["t_end"] = 300.0
    data_dir.save("timeline.json", tl)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 0, result.output


# --- clips and posters --------------------------------------------------------------------


@pytest.mark.parametrize("suffix", [".mp4", ".jpg"])
def test_ac15_missing_clip_or_poster(data_dir, run_validate, suffix):
    """AC15: "a missing clip or poster" (plan §4.2 `clips/`: `<moment_id>.mp4` and `.jpg`)."""
    name = f"{CASE_ID}.m03{suffix}"
    (data_dir.case_dir / "clips" / name).unlink()
    _assert_fails_naming(run_validate("case", data_dir.case_dir), name)


# --- references between files --------------------------------------------------------------


def test_ac15_question_points_to_missing_moment(data_dir, run_validate):
    """AC15: "a question ... that points to a missing moment"."""
    questions = data_dir.load("questions.json")
    questions["reviewer"][0]["id"] = f"{CASE_ID}.m09.r1"
    questions["reviewer"][0]["moment_id"] = f"{CASE_ID}.m09"
    data_dir.save("questions.json", questions)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "questions.json")


def test_ac15_question_quote_points_to_missing_utterance(data_dir, run_validate):
    """AC15: "a question ... that points to a missing ... utterance" (`quote.utterance_id`)."""
    questions = data_dir.load("questions.json")
    q = next(q for q in questions["operating"] if q["quote"])
    q["quote"]["utterance_id"] = f"{CASE_ID}.u0999"
    data_dir.save("questions.json", questions)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "questions.json")


def test_ac15_record_points_to_missing_moment(data_dir, run_validate):
    """AC15: "a ... record that points to a missing moment"."""
    seeds = data_dir.load("seed_records.json")
    seeds["records"][0]["moment_id"] = f"{CASE_ID}.m09"
    data_dir.save("seed_records.json", seeds)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "seed_records.json")


def test_ac15_record_points_to_missing_utterance(data_dir, run_validate):
    """AC15: "a ... record that points to a missing ... utterance" (transcript evidence)."""
    seeds = data_dir.load("seed_records.json")
    seeds["records"][0]["evidence"].append(
        {
            "kind": "transcript",
            "case_id": CASE_ID,
            "utterance_id": f"{CASE_ID}.u0999",
            "quote": "気腹圧を上げてください",
        }
    )
    data_dir.save("seed_records.json", seeds)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "seed_records.json")


def test_ac15_record_with_existing_utterance_passes(data_dir, run_validate):
    """AC15 control: transcript evidence pointing to an existing utterance is fine. Since #9
    AC16 (Team Lead reply on #9) the quote must be verbatim in the utterance's `original_lang`
    text, so this quotes u0001's `ja` text."""
    tl = data_dir.load("timeline.json")
    utterance = tl["utterances"][0]
    assert utterance["original_lang"] == "ja"
    seeds = data_dir.load("seed_records.json")
    seeds["records"][0]["evidence"].append(
        {
            "kind": "transcript",
            "case_id": CASE_ID,
            "utterance_id": utterance["id"],
            "quote": utterance["text"]["ja"],
        }
    )
    data_dir.save("seed_records.json", seeds)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 0, result.output


def test_ac15_ungrounded_filled_field_removed_grounding(data_dir, run_validate):
    """AC15: "an ungrounded filled field in a seed record" (G5; plan §4.3 grounding[])."""
    seeds = data_dir.load("seed_records.json")
    r = next(r for r in seeds["records"] if r["reason"] is not None)
    r["grounding"] = [g for g in r["grounding"] if not g["field"].startswith("reason")]
    data_dir.save("seed_records.json", seeds)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "seed_records.json")


def test_ac15_ungrounded_filled_field_new_value(data_dir, run_validate):
    """AC15: a field the surgeon did not state stays null; filling it without grounding is an
    ungrounded filled field (CLAUDE.md: never invent reasoning)."""
    seeds = data_dir.load("seed_records.json")
    r = next(r for r in seeds["records"] if r["anticipation"] is None)
    r["anticipation"] = {"ja": "出血を予想していた", "en": "Expected bleeding"}
    data_dir.save("seed_records.json", seeds)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "seed_records.json")


def test_ac15_case_json_id_not_folder_name(data_dir, run_validate):
    """AC15: "a `case.json` id that doesn't match the folder name"."""
    renamed = data_dir.case_dir.with_name("case-fixture-09")
    data_dir.case_dir.rename(renamed)
    _assert_fails_naming(run_validate("case", renamed), "case.json")


def test_ac15_file_case_id_not_case_json(data_dir, run_validate):
    """AC15: "a file whose `case_id` doesn't match `case.json`" (the file is consistent in
    itself, but belongs to another case)."""
    text = (data_dir.case_dir / "timeline.json").read_text(encoding="utf-8")
    (data_dir.case_dir / "timeline.json").write_text(
        text.replace(CASE_ID, "case-fixture-02"), encoding="utf-8"
    )
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "timeline.json")


def test_ac15_seed_records_case_id_not_case_json(data_dir, run_validate):
    """AC15: "a file whose `case_id` doesn't match `case.json`" (seed_records.json)."""
    seeds = data_dir.load("seed_records.json")
    seeds["case_id"] = "case-fixture-02"
    data_dir.save("seed_records.json", seeds)
    _assert_fails_naming(run_validate("case", data_dir.case_dir), "seed_records.json")


# --- finding the reference ------------------------------------------------------------------


def _remove_step(reference_doc: dict, step_id: str) -> dict:
    for phase in reference_doc["phases"]:
        phase["steps"] = [s for s in phase["steps"] if s["id"] != step_id]
        for order, step in enumerate(phase["steps"], start=1):
            step["order"] = order
    return reference_doc


def test_ac15_reference_under_data_dir_is_the_one_used(data_dir, run_validate):
    """AC15: "the reference is found from the step-id prefix as
    `<DATA_DIR>/reference/<prefix>.json` (#4)" - editing that file changes the verdict."""
    assert run_validate("case", data_dir.case_dir).code == 0
    tl = data_dir.load("timeline.json")
    used_step = tl["steps"][0]["step_id"]
    ref = json.loads(data_dir.reference.read_text(encoding="utf-8"))
    data_dir.reference.write_text(
        json.dumps(_remove_step(ref, used_step), ensure_ascii=False), encoding="utf-8"
    )
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output


def test_ac15_reference_given_with_option(tmp_path, paths, run_validate, monkeypatch):
    """AC15: the reference can be "given with `--reference`"."""
    empty = tmp_path / "empty-data"
    empty.mkdir()
    monkeypatch.setenv("DATA_DIR", str(empty))
    case_dir = tmp_path / "elsewhere" / CASE_ID
    shutil.copytree(paths["case"], case_dir)
    result = run_validate("case", case_dir, "--reference", paths["reference"])
    assert result.code == 0, result.output


def test_ac15_reference_option_is_the_one_used(tmp_path, paths, run_validate, monkeypatch):
    """AC15: with `--reference`, a reference missing a used step makes the package fail."""
    monkeypatch.setenv("DATA_DIR", str(paths["fixtures"]))
    case_dir = tmp_path / "cases" / CASE_ID
    shutil.copytree(paths["case"], case_dir)
    ref = json.loads(paths["reference"].read_text(encoding="utf-8"))
    tl = json.loads((case_dir / "timeline.json").read_text(encoding="utf-8"))
    custom = tmp_path / "rarp.json"
    custom.write_text(
        json.dumps(_remove_step(ref, tl["steps"][0]["step_id"]), ensure_ascii=False),
        encoding="utf-8",
    )
    result = run_validate("case", case_dir, "--reference", custom)
    assert result.code == 1, result.output


# --- exit 2 -------------------------------------------------------------------------------


def test_ac15_exit_2_when_case_dir_missing(tmp_path, run_validate):
    """AC15: "exit 2 when the check can't run" (no such folder)."""
    result = run_validate("case", tmp_path / "data" / "cases" / "no-such-case")
    assert result.code == 2, result.output


def test_ac15_exit_2_when_case_dir_is_a_file(tmp_path, run_validate):
    """AC15: exit 2 when the check can't run (the path is a file, not a folder)."""
    f = tmp_path / "case.json"
    f.write_text("{}", encoding="utf-8")
    result = run_validate("case", f)
    assert result.code == 2, result.output


def test_ac15_exit_2_when_no_reference_can_be_found(tmp_path, paths, run_validate, monkeypatch):
    """AC15: exit 2 when the check can't run: no `<DATA_DIR>/reference/rarp.json` and no
    `--reference`."""
    root = tmp_path / "data"
    case_dir = root / "cases" / CASE_ID
    shutil.copytree(paths["case"], case_dir)
    monkeypatch.setenv("DATA_DIR", str(root))
    result = run_validate("case", case_dir)
    assert result.code == 2, result.output


def test_ac15_exit_2_when_reference_option_missing(data_dir, run_validate, tmp_path):
    """AC15: exit 2 when the check can't run (`--reference` names no file)."""
    result = run_validate("case", data_dir.case_dir, "--reference", tmp_path / "nope.json")
    assert result.code == 2, result.output


def test_ac15_cli_exit_code_and_file_name(data_dir, paths):
    """AC15 through the installed console script: exit 1 and the file is named."""
    (data_dir.case_dir / "questions.json").unlink()
    exe = shutil.which("scrubgpt-validate")
    assert exe
    proc = subprocess.run(
        [exe, "case", str(data_dir.case_dir)],
        cwd=paths["repo"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    errors = [ln for ln in proc.stdout.splitlines() if "questions.json" in ln]
    assert errors and not any(ln.strip().startswith("checked") for ln in errors), proc.stdout
