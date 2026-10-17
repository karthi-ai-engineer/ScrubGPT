"""C8 Ground-truth mode: #17 acceptance criteria 8-10 (Team Lead answer; D-070; plan §2.3 C8,
§4.2 `case.json` and `timeline.json`, §7 GC1; brain/CLAUDE.md rule 4; brain/README.md "C8
Ground-truth mode"; the `pipeline/ground_truth.py` docstring; the CLI docstring).

Expected behaviour, written from the spec before the code was opened:
8. From B1's dataset segments, `apply_ground_truth(case_dir, segments)` writes a `timeline.json`
   whose dataset step segments have `track: dataset`, `dataset_annotation` 📐 and `generated_by:
   null`; it validates against the contract and keeps the `ai` segments, events, instruments and
   utterances unchanged (README: the dataset track is replaced, numbered after the AI segments;
   without a timeline an empty one is started).
9. `case.json` gets `default_step_track: dataset`; a case with no dataset track is never switched
   (an error, nothing written); the written package passes `scrubgpt-validate case` (and
   `--drop`, D-064) on a synthetic package (a copy of `contracts/fixtures/cases/case-fixture-01`).
10. Re-running C8 is idempotent: the same input gives byte-identical files.

Also from the README: segments on the wrong track, with an AI trust label, a model, another case's
id or an overlap are refused with nothing written; `ground_truth_from_grasp` and the CLI
`ground-truth <case_dir> <file> <GRASP_CASE>` run B1 first.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from scrubgpt_brain.pipeline.grasp import import_grasp_steps
from scrubgpt_brain.pipeline.ground_truth import apply_ground_truth, ground_truth_from_grasp
from scrubgpt_contracts.models.case_package import Case, StepSegment, Timeline
from scrubgpt_contracts.validate import validate_case

CASE = "case-fixture-01"


@pytest.fixture
def case_dir(const, tmp_path) -> Path:
    """A copy of the synthetic fixture package, as a case's work folder (rule 4)."""
    target = tmp_path / "data" / "work" / CASE
    shutil.copytree(const.repo_root / "contracts" / "fixtures" / "cases" / CASE, target)
    return target


@pytest.fixture(scope="module")
def S(rulebook) -> list[str]:
    return [s["id"] for p in rulebook["phases"] for s in p.get("steps") or []]


def dataset(spans, *, case=CASE, start=900, **overrides) -> list[StepSegment]:
    """Dataset-track segments as B1 makes them (📐, no model), numbered from `start`."""
    out = []
    for k, (step_id, t0, t1) in enumerate(spans):
        data = {
            "id": f"{case}.s{start + k:03d}", "step_id": step_id, "track": "dataset",
            "t_start": float(t0), "t_end": float(t1), "confidence": 1.0,
            "provenance": {"trust_label": "dataset_annotation", "attributed_to": "dataset",
                           "generated_by": None, "confirmed_by": None, "confirmed_at": None},
        }  # fmt: skip
        for key, value in overrides.items():
            if key in data["provenance"]:
                data["provenance"][key] = value
            else:
                data[key] = value
        out.append(StepSegment.model_validate(data))
    return out


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def files(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


def labels(S) -> list:
    return [(S[2], 0, 40), (S[3], 40, 90), (S[5], 95, 180), (S[6], 180, 290)]


# ── criterion 8 ──────────────────────────────────────────────────────────────


def test_c8_8_the_dataset_track_is_written_and_the_rest_kept(case_dir, S):
    """#17 C8 "writes a `timeline.json` whose dataset step segments have `track: dataset` and
    `provenance.trust_label: dataset_annotation` 📐 (`generated_by: null`). It validates against
    the contract and keeps any existing `ai` segments, events and other content unchanged."
    README: "the dataset track is replaced by the GraSP segments … numbered after the AI
    segments"."""
    before = read(case_dir / "timeline.json")
    case_path, timeline_path = apply_ground_truth(case_dir, dataset(labels(S)))
    assert (case_path, timeline_path) == (case_dir / "case.json", case_dir / "timeline.json")
    after = read(case_dir / "timeline.json")
    Timeline.model_validate(after)
    ai_before = [s for s in before["steps"] if s["track"] == "ai"]
    ai_after = [s for s in after["steps"] if s["track"] == "ai"]
    assert ai_after == ai_before
    for key in ("events", "instruments", "utterances", "case_id", "contract_version"):
        assert after[key] == before[key], key
    gt = [s for s in after["steps"] if s["track"] == "dataset"]
    assert [(s["step_id"], s["t_start"], s["t_end"]) for s in gt] == [
        (step, float(t0), float(t1)) for step, t0, t1 in labels(S)
    ]
    for seg in gt:
        assert seg["provenance"]["trust_label"] == "dataset_annotation"
        assert seg["provenance"]["attributed_to"] == "dataset"
        assert seg["provenance"]["generated_by"] is None
    last_ai = max(int(s["id"].rsplit(".s", 1)[1]) for s in ai_after)
    numbers = [int(s["id"].rsplit(".s", 1)[1]) for s in gt]
    assert numbers == list(range(last_ai + 1, last_ai + 1 + len(gt))), numbers


def test_c8_8_without_a_timeline_an_empty_one_is_started(case_dir, S):
    """README "Without a timeline, an empty one is started": the timeline then holds only the
    dataset track, and validates."""
    (case_dir / "timeline.json").unlink()
    apply_ground_truth(case_dir, dataset(labels(S)))
    after = Timeline.model_validate(read(case_dir / "timeline.json"))
    assert [s.track.value for s in after.steps] == ["dataset"] * len(labels(S))
    assert after.events == [] and after.instruments == [] and after.utterances == []


# ── criterion 9 ──────────────────────────────────────────────────────────────


def test_c8_9_case_json_switches_to_the_dataset_track(case_dir, S):
    """#17 C9 "The GraSP case's `case.json` gets `default_step_track: dataset`", every other
    field unchanged; the result is a contract `Case`."""
    before = read(case_dir / "case.json")
    assert before["default_step_track"] == "ai"
    apply_ground_truth(case_dir, dataset(labels(S)))
    after = read(case_dir / "case.json")
    Case.model_validate(after)
    assert after["default_step_track"] == "dataset"
    assert {k: v for k, v in after.items() if k != "default_step_track"} == {
        k: v for k, v in before.items() if k != "default_step_track"
    }


@pytest.mark.parametrize("drop", [False, True], ids=["case", "drop"])
def test_c8_9_the_written_package_passes_scrubgpt_validate(const, case_dir, S, drop):
    """#17 C9 "The written package passes `scrubgpt-validate case` (or `--drop`, D-064) on a
    synthetic package": `validate_case` on the copy, with the contract fixture's reference, has
    no error and nothing blocked."""
    reference = const.reference_fixture_path
    assert validate_case(case_dir, reference).ok, "the copy fails before C8 (test setup)"
    apply_ground_truth(case_dir, dataset(labels(S)))
    report = validate_case(case_dir, reference, drop=drop)
    assert report.ok, [f"{i.where}: {i.message}" for i in report.errors] + report.blocked


def test_c8_9_the_cli_validator_agrees(cli, const, case_dir, S):
    """#17 C9 with the CLI validator: `scrubgpt-validate case <dir> --reference <fixture>` exits
    0 after C8."""
    apply_ground_truth(case_dir, dataset(labels(S)))
    result = cli.validate("case", str(case_dir), "--reference", str(const.reference_fixture_path))
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_c8_9_a_case_without_a_dataset_track_is_never_switched(case_dir):
    """#17 C9 "A case with no dataset track is never switched (error)": no segments raises and
    nothing in the package changes."""
    before = files(case_dir)
    with pytest.raises(ValueError):
        apply_ground_truth(case_dir, [])
    assert files(case_dir) == before


def _bad(S, how):
    good = labels(S)
    if how == "ai-track":
        return dataset(good, track="ai")
    if how == "ai-trust-label":
        return dataset(good, trust_label="ai_detected", attributed_to="ai")
    if how == "has-a-model":
        gen = {"model_tier": "VISION_FAST", "model": "t1-model", "prompt_version": None}
        return dataset(good, generated_by=gen)
    if how == "other-case":
        return dataset(good, case="grasp-99")
    if how == "overlap":
        return dataset([(S[2], 0, 50), (S[3], 40, 90)])
    raise ValueError(how)


@pytest.mark.parametrize("how", ["ai-track", "ai-trust-label", "has-a-model", "other-case",
                                 "overlap"])  # fmt: skip
def test_c8_9_segments_that_cant_be_ground_truth_are_refused(case_dir, S, how):
    """README "Segments on the wrong track, with an AI trust label, a model, another case's id or
    an overlap are refused, and nothing is written"."""
    before = files(case_dir)
    with pytest.raises(ValueError):
        apply_ground_truth(case_dir, _bad(S, how))
    assert files(case_dir) == before


@pytest.mark.parametrize("broken", ["no-case-json", "invalid-case-json", "invalid-timeline"])
def test_c8_9_a_missing_or_invalid_package_file_is_refused(case_dir, S, broken):
    """CLI docstring "for `ground-truth` also a missing or invalid case.json/timeline.json":
    `ValueError`, and nothing else in the folder changes."""
    if broken == "no-case-json":
        (case_dir / "case.json").unlink()
    elif broken == "invalid-case-json":
        (case_dir / "case.json").write_text('{"id": "case-fixture-01"}', encoding="utf-8")
    else:
        (case_dir / "timeline.json").write_text("{not json", encoding="utf-8")
    before = files(case_dir)
    with pytest.raises(ValueError):
        apply_ground_truth(case_dir, dataset(labels(S)))
    assert files(case_dir) == before


# ── criterion 10 ─────────────────────────────────────────────────────────────


def test_c8_10_a_re_run_is_byte_identical(case_dir, S):
    """#17 C10 "Re-running C8 is idempotent: same input, byte-identical output": the second run
    changes no byte of the package; the files end with a newline and use LF."""
    apply_ground_truth(case_dir, dataset(labels(S)))
    first = files(case_dir)
    apply_ground_truth(case_dir, dataset(labels(S)))
    assert files(case_dir) == first
    for name in ("case.json", "timeline.json"):
        assert b"\r" not in first[name] and first[name].endswith(b"\n"), name


def test_c8_10_new_labels_replace_the_dataset_track(case_dir, S):
    """README "the dataset track is replaced": a second run with other labels leaves only the new
    dataset segments, with the same numbering start, and the AI track still unchanged."""
    apply_ground_truth(case_dir, dataset(labels(S)))
    ai_before = [s for s in read(case_dir / "timeline.json")["steps"] if s["track"] == "ai"]
    apply_ground_truth(case_dir, dataset([(S[1], 0, 100), (S[2], 100, 200)]))
    after = read(case_dir / "timeline.json")["steps"]
    assert [s for s in after if s["track"] == "ai"] == ai_before
    assert [(s["step_id"], s["t_start"]) for s in after if s["track"] == "dataset"] == [
        (S[1], 0.0), (S[2], 100.0)
    ]  # fmt: skip


# ── B1 + C8 and the CLI ──────────────────────────────────────────────────────


@pytest.fixture
def grasp_file(grasp, tmp_path) -> Path:
    cw = grasp.cw
    a, b = cw.exact_steps()[:2]
    labels_ = grasp.exact(a, 40) + grasp.idle(5) + grasp.exact(b, 60)
    return grasp.write(tmp_path / "grasp_long-term_t1.json", {"CASE042": labels_}, spacing=25)


def test_c8_ground_truth_from_grasp_applies_b1s_segments(case_dir, grasp_file):
    """README "`ground_truth_from_grasp(case_dir, annotations, "CASE041")`": B1's import of that
    case, applied to the package: the dataset track equals B1's segments (steps and times) for
    the package's case id, and the report comes back."""
    _, timeline, report = ground_truth_from_grasp(case_dir, grasp_file, "CASE042")
    segments, _ = import_grasp_steps(grasp_file, "CASE042", CASE)
    gt = [s for s in read(timeline)["steps"] if s["track"] == "dataset"]
    assert [(s["step_id"], s["t_start"], s["t_end"]) for s in gt] == [
        (s.step_id, s.t_start, s.t_end) for s in segments
    ]
    assert report.idle_seconds == pytest.approx(5.0)
    assert read(case_dir / "case.json")["default_step_track"] == "dataset"


def test_c8_the_cli_puts_the_ground_truth_into_the_package(cli, const, case_dir, grasp_file):
    """README `scrubgpt-brain ground-truth <case_dir> <grasp_long-term.json> <GRASP_CASE>`: exit
    0, a result on stdout, nothing on stderr; the package then passes the validator."""
    result = cli.run("ground-truth", str(case_dir), str(grasp_file), "CASE042")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() and not result.stderr.strip()
    assert read(case_dir / "case.json")["default_step_track"] == "dataset"
    assert validate_case(case_dir, const.reference_fixture_path).ok


@pytest.mark.parametrize("bad", ["missing-case", "crosswalk-mismatch", "no-labels"])
def test_c8_the_cli_refuses_bad_labels_on_stderr(cli, grasp, case_dir, grasp_file, tmp_path,
                                                  bad):  # fmt: skip
    """CLI docstring "for `ground-truth` also … labels that can't be ground truth": a GraSP case
    the file lacks, a file that doesn't match the crosswalk, or a case with only idle labels
    (no dataset segment, never switched) exits 1 with the error on stderr; the package is
    unchanged."""
    path, case = grasp_file, "CASE042"
    if bad == "missing-case":
        case = "CASE099"
    elif bad == "crosswalk-mismatch":
        data = read(grasp_file)
        data["steps_categories"][1]["description"] += " (v2)"
        path = tmp_path / "other.json"
        path.write_text(json.dumps(data), encoding="utf-8")
    else:
        path = grasp.write(tmp_path / "idle.json", {"CASE042": grasp.idle(30)})
    before = files(case_dir)
    result = cli.run("ground-truth", str(case_dir), str(path), case)
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert result.stderr.startswith("scrubgpt-brain: error:") and not result.stdout.strip()
    assert files(case_dir) == before
