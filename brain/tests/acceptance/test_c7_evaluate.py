"""C7 Accuracy evaluator: #17 acceptance criteria 1-7 (Team Lead answer; D-070; plan §2.3 C7,
§4.2 `metrics.json`; brain/CLAUDE.md rules 4 and 8; brain/README.md "C7 Accuracy evaluator"; the
`pipeline/evaluate.py` docstring; the CLI docstring).

Expected behaviour, written from the spec before the code was opened:
1. Input: AI `StepSegment`s (`track: ai`) and dataset ones (`track: dataset`) of one case; output a
   `Metrics` that validates against `scrubgpt_contracts`, written as `metrics.json` only into a
   caller-given folder (never `<DATA_DIR>/cases/` directly, rule 4).
2. Frames every `frame_step_s` (default 1.0 s; times 0, step, 2·step, … per the docstring) where
   the dataset track has a label (`t_start <= t < t_end`); `n_frames` counts them (0 → error, no
   file); a frame without an AI segment is wrong.
3. `frame_accuracy` = right frames / `n_frames`: identical tracks 1.0, disjoint 0.0, a
   hand-computed mixed case to 1e-9.
4. `segment_f1`: same `step_id` and temporal IoU ≥ 0.5, one-to-one, each AI segment takes its
   highest-IoU unmatched partner; F1 = 2PR/(P+R), 0.0 without a match; over- and
   under-segmented examples give the hand-computed values.
5. `per_step`: one entry per step in either track, each once, frame precision and recall in
   [0, 1]; a step without AI frames has precision 0.0, one without dataset frames recall 0.0.
6. `model_info` = the AI segments' `provenance.generated_by`; a missing or differing one is an
   error; a model name is never invented.
7. Segments of two `case_id`s are an error; the function is pure (same input → byte-identical
   JSON).

All segments are synthetic; step ids come from the loaded rule book.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scrubgpt_brain.engines.rulebook import load_knowledge
from scrubgpt_brain.pipeline.evaluate import (
    evaluate,
    evaluate_timeline,
    metrics_json,
    segment_f1,
    write_metrics,
)
from scrubgpt_contracts.models.case_package import Metrics, StepSegment

CASE = "grasp-07"
GEN = {
    "model_tier": "VISION_FAST",
    "model": "t1-synthetic-model",
    "prompt_version": "step_window.v1",
}


@pytest.fixture(scope="module")
def S() -> list[str]:
    """Rule-book step ids, in order (A = S[0], B = S[1], …)."""
    return [s.id for p in load_knowledge().rulebook.phases for s in p.steps]


class Track:
    """Builds the step segments of one track, numbered `<case>.sNNN`."""

    counter = 0

    def __init__(self, track: str, case: str = CASE, generated_by=GEN) -> None:
        self.track, self.case, self.generated_by = track, case, generated_by

    def __call__(self, *spans, generated_by="same") -> list[StepSegment]:
        out = []
        for step_id, t_start, t_end in spans:
            Track.counter += 1
            ai = self.track == "ai"
            gen = self.generated_by if generated_by == "same" else generated_by
            out.append(StepSegment.model_validate({
                "id": f"{self.case}.s{Track.counter:03d}", "step_id": step_id,
                "track": self.track, "t_start": float(t_start), "t_end": float(t_end),
                "confidence": 0.8 if ai else 1.0,
                "provenance": {
                    "trust_label": "ai_detected" if ai else "dataset_annotation",
                    "attributed_to": "ai" if ai else "dataset",
                    "generated_by": gen if ai else None,
                    "confirmed_by": None, "confirmed_at": None,
                },
            }))  # fmt: skip
        return out


ai, gt = Track("ai"), Track("dataset")


def per_step(metrics: Metrics) -> dict[str, tuple[float, float]]:
    return {e.step_id: (e.precision, e.recall) for e in metrics.per_step}


# ── criterion 1 ──────────────────────────────────────────────────────────────


def test_c7_1_the_result_is_a_contract_metrics(S):
    """#17 C1 "Input: AI `StepSegment`s (`track: ai`) and dataset `StepSegment`s (`track:
    dataset`) for one case. Output: a `Metrics` object that validates against
    `scrubgpt_contracts`" (plan §4.2: contract_version, case_id, frame_accuracy, segment_f1,
    per_step, n_frames, model_info)."""
    metrics = evaluate(ai((S[0], 0, 10), (S[1], 10, 20)), gt((S[0], 0, 12), (S[1], 12, 20)))
    assert isinstance(metrics, Metrics)
    data = json.loads(metrics_json(metrics))
    assert set(data) == {"contract_version", "case_id", "frame_accuracy", "segment_f1",
                         "per_step", "n_frames", "model_info"}  # fmt: skip
    Metrics.model_validate(data)
    assert data["contract_version"] == "1.0" and data["case_id"] == CASE


def test_c7_1_metrics_json_goes_only_into_the_callers_folder(S, tmp_path):
    """#17 C1 "… written as `metrics.json` only to a caller-given folder (never
    `<DATA_DIR>/cases/` directly, rule 4)": `write_metrics(m, out)` writes exactly
    `out/metrics.json` (no temporary file left), and nothing else anywhere under the data
    folder."""
    data = tmp_path / "data"
    (data / "cases" / CASE).mkdir(parents=True)
    out = data / "work" / CASE
    metrics = evaluate(ai((S[0], 0, 10)), gt((S[0], 0, 10)))
    path = write_metrics(metrics, out)
    assert path == out / "metrics.json"
    files = sorted(p.relative_to(data).as_posix() for p in data.rglob("*") if p.is_file())
    assert files == [f"work/{CASE}/metrics.json"]
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(metrics_json(metrics))


def _timeline(path: Path, steps: list[StepSegment], case: str = CASE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "contract_version": "1.0", "case_id": case,
        "steps": [s.model_dump(mode="json") for s in steps],
        "events": [], "instruments": [], "utterances": [],
    }), encoding="utf-8")  # fmt: skip
    return path


def test_c7_1_the_cli_writes_metrics_json_into_out_dir(cli, S, tmp_path):
    """#17 C1 through `scrubgpt-brain metrics <timeline.json> <out_dir>` (README): exit 0, a
    result on stdout, `metrics.json` in `<out_dir>` equal to `evaluate`'s, and the folder of the
    timeline (a case folder) untouched."""
    a, d = ai((S[0], 0, 10), (S[1], 10, 20)), gt((S[0], 0, 11), (S[1], 11, 20))
    timeline = _timeline(tmp_path / "data" / "cases" / CASE / "timeline.json", [*a, *d])
    before = sorted(p.name for p in timeline.parent.iterdir())
    out = tmp_path / "data" / "work" / CASE
    result = cli.run("metrics", str(timeline), str(out))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() and not result.stderr.strip()
    assert sorted(p.name for p in out.iterdir()) == ["metrics.json"]
    assert (out / "metrics.json").read_text(encoding="utf-8") == metrics_json(evaluate(a, d))
    assert sorted(p.name for p in timeline.parent.iterdir()) == before
    assert evaluate_timeline(timeline, tmp_path / "py") == tmp_path / "py" / "metrics.json"


# ── criterion 2 ──────────────────────────────────────────────────────────────


def test_c7_2_frames_are_on_the_grid_where_the_dataset_has_a_label(S):
    """#17 C2 "frames are sampled at a configurable step (default 1.0 s), at times where the
    dataset track has a label. `n_frames` is the number of those frames": a dataset labelled over
    0-10 s and 20-30 s (a gap between) gives 20 frames at 1 s, and 8 at 2.5 s (0, 2.5, 5, 7.5,
    20, 22.5, 25, 27.5)."""
    d = gt((S[0], 0, 10), (S[1], 20, 30))
    a = ai((S[0], 0, 30))
    assert evaluate(a, d).n_frames == 20
    assert evaluate(a, d, frame_step_s=2.5).n_frames == 8


def test_c7_2_a_frame_without_an_ai_segment_counts_as_wrong(S):
    """#17 C2 "A frame with no AI segment counts as wrong": the AI covers only 0-6 s of a 0-10 s
    dataset step: 6 of 10 frames right."""
    metrics = evaluate(ai((S[0], 0, 6)), gt((S[0], 0, 10)))
    assert metrics.n_frames == 10
    assert metrics.frame_accuracy == pytest.approx(0.6, abs=1e-9)


@pytest.mark.parametrize("dataset", [[(0.2, 0.7)], [(5.0, 5.0)]], ids=["between-frames", "empty"])
def test_c7_2_no_frame_is_an_error_and_writes_nothing(cli, S, tmp_path, dataset):
    """#17 C2 "when it is 0, raise an error and write no file": a dataset label that covers no
    grid time (0.2-0.7 s, or a zero-length segment) is an error; the CLI exits 1 with the error
    on stderr and writes no `metrics.json`."""
    a = ai((S[0], 0, 10))
    d = gt(*[(S[0], t0, t1) for t0, t1 in dataset])
    with pytest.raises(ValueError):
        evaluate(a, d)
    timeline = _timeline(tmp_path / "timeline.json", [*a, *d])
    out = tmp_path / "out"
    result = cli.run("metrics", str(timeline), str(out))
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert result.stderr.startswith("scrubgpt-brain: error:")
    assert not (out / "metrics.json").exists()


@pytest.mark.parametrize("step", [0, -1.0, float("nan")])
def test_c7_2_the_frame_step_must_be_positive(S, step):
    """#17 C2 "a configurable step": a step that isn't a positive number is refused."""
    with pytest.raises(ValueError):
        evaluate(ai((S[0], 0, 10)), gt((S[0], 0, 10)), frame_step_s=step)


# ── criterion 3 ──────────────────────────────────────────────────────────────


def test_c7_3_identical_tracks_give_1(S):
    """#17 C3 "Identical tracks give 1.0" (and a segment F1 of 1.0)."""
    spans = [(S[0], 0, 30), (S[1], 30, 75), (S[2], 75, 100)]
    metrics = evaluate(ai(*spans), gt(*spans))
    assert metrics.frame_accuracy == 1.0 and metrics.segment_f1 == 1.0
    assert all(p == 1.0 and r == 1.0 for p, r in per_step(metrics).values())


def test_c7_3_disjoint_step_labels_give_0(S):
    """#17 C3 "Fully disjoint step labels give 0.0"."""
    metrics = evaluate(ai((S[2], 0, 30), (S[3], 30, 60)), gt((S[0], 0, 30), (S[1], 30, 60)))
    assert metrics.frame_accuracy == 0.0 and metrics.segment_f1 == 0.0


def test_c7_3_a_hand_computed_mixed_case(S):
    """#17 C3 "A hand-computed mixed case matches to 1e-9": dataset A 0-10, B 10-20, D 20-25; AI
    A 0-8, C 8-12, B 12-20, E 25-30. Frames 0..24 (25): right are A 0-7 (8) and B 12-19 (8), so
    16/25 = 0.64."""
    a = ai((S[0], 0, 8), (S[2], 8, 12), (S[1], 12, 20), (S[4], 25, 30))
    d = gt((S[0], 0, 10), (S[1], 10, 20), (S[3], 20, 25))
    metrics = evaluate(a, d)
    assert metrics.n_frames == 25
    assert metrics.frame_accuracy == pytest.approx(16 / 25, abs=1e-9)


def test_c7_3_a_finer_frame_step(S):
    """#17 C3 with `frame_step_s=0.5`: dataset A 0-10; AI A 0-7.5 → frames 0, 0.5, …, 9.5 (20),
    right 0..7.0 (15): 0.75."""
    metrics = evaluate(ai((S[0], 0, 7.5)), gt((S[0], 0, 10)), frame_step_s=0.5)
    assert metrics.n_frames == 20
    assert metrics.frame_accuracy == pytest.approx(0.75, abs=1e-9)


# ── criterion 4 ──────────────────────────────────────────────────────────────


def test_c7_4_over_segmentation(S):
    """#17 C4 over-segmented: dataset A 0-20; AI A 0-12, A 12-20. IoUs 0.6 (match) and 0.4 (no):
    P = 1/2, R = 1/1, F1 = 2/3."""
    a, d = ai((S[0], 0, 12), (S[0], 12, 20)), gt((S[0], 0, 20))
    assert segment_f1(a, d) == pytest.approx(2 / 3, abs=1e-9)
    assert evaluate(a, d).segment_f1 == pytest.approx(2 / 3, abs=1e-9)


def test_c7_4_under_segmentation(S):
    """#17 C4 under-segmented: dataset A 0-10, B 10-20; AI A 0-20 (B merged into A). IoU with A
    is 0.5 (a match, ≥ 0.5), B has no partner: P = 1/1, R = 1/2, F1 = 2/3."""
    a, d = ai((S[0], 0, 20)), gt((S[0], 0, 10), (S[1], 10, 20))
    assert segment_f1(a, d) == pytest.approx(2 / 3, abs=1e-9)


def test_c7_4_matching_is_one_to_one_by_best_iou(S):
    """#17 C4 "Matching is one-to-one, and each AI segment takes its highest-IoU unmatched
    partner": dataset A 0-10 and A 10-20; AI A 2-11 (IoU 8/11 with the first, 1/18 with the
    second) and A 11-20 (IoU 0.9 with the second): 2 matches, F1 1.0. A third AI segment of A,
    0-1, finds no partner left: P = 2/3, R = 1, F1 = 0.8."""
    d = gt((S[0], 0, 10), (S[0], 10, 20))
    assert segment_f1(ai((S[0], 2, 11), (S[0], 11, 20)), d) == pytest.approx(1.0)
    three = ai((S[0], 0, 1), (S[0], 2, 11), (S[0], 11, 20))
    assert segment_f1(three, d) == pytest.approx(0.8, abs=1e-9)


def test_c7_4_the_same_step_is_required_and_no_match_gives_0(S):
    """#17 C4 "an AI segment matches a dataset segment with the same `step_id`" and "0.0 when
    there are no matches": perfectly aligned segments of other steps give 0.0; an IoU just under
    0.5 doesn't match (A 0-10 vs A 0-21: 10/21)."""
    assert segment_f1(ai((S[1], 0, 10)), gt((S[0], 0, 10))) == 0.0
    assert segment_f1(ai((S[0], 0, 10)), gt((S[0], 0, 21))) == 0.0


def test_c7_4_a_mixed_example(S):
    """#17 C4 hand-computed: the C3 mixed case (dataset A 0-10, B 10-20, D 20-25; AI A 0-8 (IoU
    0.8, match), C 8-12, B 12-20 (IoU 0.8, match), E 25-30): P = 2/4, R = 2/3, F1 = 4/7."""
    a = ai((S[0], 0, 8), (S[2], 8, 12), (S[1], 12, 20), (S[4], 25, 30))
    d = gt((S[0], 0, 10), (S[1], 10, 20), (S[3], 20, 25))
    assert evaluate(a, d).segment_f1 == pytest.approx(4 / 7, abs=1e-9)


# ── criterion 5 ──────────────────────────────────────────────────────────────


def test_c7_5_per_step_has_every_step_once_with_the_hand_computed_values(S):
    """#17 C5 "`per_step`: one entry per step that appears in either track, each `step_id`
    once, frame-level precision and recall in [0, 1]. A step with no AI frames has precision
    0.0. A step with no dataset frames has recall 0.0." The C3 mixed case: A (8/8, 8/10), B (8/8,
    8/10), C (AI frames 8-11 all wrong: 0/4, no dataset frames: 0.0), D (no AI frame: 0.0, 0/5),
    E (AI only outside the labelled frames: 0.0, 0.0). README: sorted by step id."""
    a = ai((S[0], 0, 8), (S[2], 8, 12), (S[1], 12, 20), (S[4], 25, 30))
    d = gt((S[0], 0, 10), (S[1], 10, 20), (S[3], 20, 25))
    metrics = evaluate(a, d)
    ids = [e.step_id for e in metrics.per_step]
    assert ids == sorted(ids) and len(ids) == len(set(ids))
    assert set(ids) == {S[0], S[1], S[2], S[3], S[4]}
    got = per_step(metrics)
    want = {S[0]: (1.0, 0.8), S[1]: (1.0, 0.8), S[2]: (0.0, 0.0), S[3]: (0.0, 0.0),
            S[4]: (0.0, 0.0)}  # fmt: skip
    for step, (p, r) in want.items():
        assert got[step] == pytest.approx((p, r), abs=1e-9), step
    assert all(0.0 <= v <= 1.0 for pr in got.values() for v in pr)


def test_c7_5_precision_counts_wrong_ai_frames(S):
    """#17 C5 frame-level precision: dataset A 0-10, B 10-20; AI A 0-15, B 15-20. A: AI gave 15
    frames, 10 right → precision 2/3, recall 1.0; B: 5 of 5 right → precision 1.0, recall 0.5."""
    got = per_step(evaluate(ai((S[0], 0, 15), (S[1], 15, 20)), gt((S[0], 0, 10), (S[1], 10, 20))))
    assert got[S[0]] == pytest.approx((2 / 3, 1.0), abs=1e-9)
    assert got[S[1]] == pytest.approx((1.0, 0.5), abs=1e-9)


# ── criterion 6 ──────────────────────────────────────────────────────────────


def test_c7_6_model_info_comes_from_the_ai_segments(S):
    """#17 C6 "`model_info` comes from the AI segments' `provenance.generated_by`"."""
    metrics = evaluate(ai((S[0], 0, 10), (S[1], 10, 20)), gt((S[0], 0, 20)))
    assert metrics.model_info.model_dump() == GEN


def test_c7_6_a_missing_generated_by_is_an_error(S):
    """#17 C6 "If any AI segment has no `generated_by` … raise an error. Never invent a model
    name"."""
    a = ai((S[0], 0, 10)) + ai((S[1], 10, 20), generated_by=None)
    with pytest.raises(ValueError):
        evaluate(a, gt((S[0], 0, 20)))


def test_c7_6_differing_generated_by_is_an_error(S):
    """#17 C6 "… or the segments disagree, raise an error": another model, or another prompt
    version, on one AI segment."""
    for other in ({**GEN, "model": "t1-other-model"}, {**GEN, "prompt_version": "step_window.v2"}):
        a = ai((S[0], 0, 10)) + ai((S[1], 10, 20), generated_by=other)
        with pytest.raises(ValueError):
            evaluate(a, gt((S[0], 0, 20)))


# ── criterion 7 ──────────────────────────────────────────────────────────────


def test_c7_7_segments_of_two_cases_are_an_error(S):
    """#17 C7 "Input segments from two different `case_id`s raise an error": an AI segment of
    another case, and a dataset segment of another case."""
    other_ai, other_gt = Track("ai", case="grasp-08"), Track("dataset", case="grasp-08")
    with pytest.raises(ValueError):
        evaluate(ai((S[0], 0, 10)) + other_ai((S[1], 10, 20)), gt((S[0], 0, 20)))
    with pytest.raises(ValueError):
        evaluate(ai((S[0], 0, 20)), gt((S[0], 0, 10)) + other_gt((S[1], 10, 20)))


def test_c7_7_the_same_input_gives_byte_identical_json(S, tmp_path):
    """#17 C7 "The function is pure: the same input gives byte-identical JSON": twice in-process,
    and the written file twice."""
    a = ai((S[0], 0, 8), (S[2], 8, 12), (S[1], 12, 20))
    d = gt((S[0], 0, 10), (S[1], 10, 20))
    first, second = metrics_json(evaluate(a, d)), metrics_json(evaluate(list(a), list(d)))
    assert first == second
    one = write_metrics(evaluate(a, d), tmp_path / "one").read_bytes()
    two = write_metrics(evaluate(a, d), tmp_path / "two").read_bytes()
    assert one == two and b"\r" not in one


def test_c7_7_errors_write_no_file_through_the_cli(cli, S, tmp_path):
    """README "Errors exit 1 …, and no file is written": a timeline with segments of two cases
    (invalid: ids outside the case) and one without an AI track."""
    d = gt((S[0], 0, 10))
    for name, steps in {"no-ai": d, "mixed-generated-by": ai((S[0], 0, 5)) + ai(
            (S[1], 5, 10), generated_by=None) + d}.items():  # fmt: skip
        timeline = _timeline(tmp_path / name / "timeline.json", steps)
        out = tmp_path / name / "out"
        result = cli.run("metrics", str(timeline), str(out))
        assert result.returncode == 1, (name, result.returncode, result.stderr)
        assert result.stderr.startswith("scrubgpt-brain: error:"), result.stderr
        assert not out.exists() or not any(out.iterdir()), name
