"""Dev1's unit tests for C7, the accuracy evaluator (pipeline/evaluate.py; D-070). Synthetic
segments; every expected number is worked out by hand in the comments."""

import json
from pathlib import Path

import pytest
from scrubgpt_brain import cli
from scrubgpt_brain.pipeline import evaluate as ev
from scrubgpt_contracts.models.case_package import Metrics, StepSegment, StepTrack, Timeline
from scrubgpt_contracts.models.common import (
    CONTRACT_VERSION,
    GeneratedBy,
    Provenance,
    Role,
    TrustLabel,
)

A, B, C = "rarp.p02.s01", "rarp.p03.s01", "rarp.p04.s01"
MODEL = GeneratedBy(model_tier="VISION_FAST", model="model-x", prompt_version="step_window.v1")


def seg(
    n: int,
    step: str,
    t_start: float,
    t_end: float,
    track: str = "dataset",
    *,
    case: str = "grasp-01",
    model: GeneratedBy | None = MODEL,
) -> StepSegment:
    ai = track == "ai"
    return StepSegment(
        id=f"{case}.s{n:03d}",
        t_start=t_start,
        t_end=t_end,
        confidence=0.8 if ai else 1.0,
        provenance=Provenance(
            trust_label=TrustLabel.AI_DETECTED if ai else TrustLabel.DATASET_ANNOTATION,
            attributed_to=Role.AI if ai else Role.DATASET,
            generated_by=model if ai else None,
            confirmed_by=None,
            confirmed_at=None,
        ),
        step_id=step,
        track=StepTrack(track),
    )


def ai(n: int, step: str, t_start: float, t_end: float, **kw) -> StepSegment:
    return seg(n, step, t_start, t_end, "ai", **kw)


def test_a_mixed_case_by_hand():
    # Truth: A at 0-9, B at 10-19 (20 frames). AI: A at 0-5, B at 6-19 → 16 right.
    metrics = ev.evaluate(
        [ai(101, A, 0, 6), ai(102, B, 6, 20)], [seg(1, A, 0, 10), seg(2, B, 10, 20)]
    )
    assert isinstance(metrics, Metrics) and metrics.contract_version == CONTRACT_VERSION
    assert metrics.case_id == "grasp-01" and metrics.n_frames == 20
    assert metrics.frame_accuracy == pytest.approx(16 / 20, abs=1e-9)
    per_step = {m.step_id: (m.precision, m.recall) for m in metrics.per_step}
    assert per_step[A] == pytest.approx((6 / 6, 6 / 10), abs=1e-9)
    assert per_step[B] == pytest.approx((10 / 14, 10 / 10), abs=1e-9)
    # IoU A: 6/10, B: 10/14, both >= 0.5 → 2 matches of 2 and 2.
    assert metrics.segment_f1 == pytest.approx(1.0, abs=1e-9)
    assert metrics.model_info == MODEL


def test_identical_and_disjoint_tracks():
    truth = [seg(1, A, 0, 10), seg(2, B, 10, 20)]
    same = ev.evaluate([ai(3, A, 0, 10), ai(4, B, 10, 20)], truth)
    assert (same.frame_accuracy, same.segment_f1) == (1.0, 1.0)
    assert all((m.precision, m.recall) == (1.0, 1.0) for m in same.per_step)
    wrong = ev.evaluate([ai(3, C, 0, 20)], truth)
    assert (wrong.frame_accuracy, wrong.segment_f1) == (0.0, 0.0)
    assert [m.step_id for m in wrong.per_step] == [A, B, C]  # every step of either track, sorted
    assert all((m.precision, m.recall) == (0.0, 0.0) for m in wrong.per_step)


def test_frames_without_an_ai_step_are_wrong_and_steps_without_frames_score_zero():
    # Truth A at 0-9; AI A at 0-4 only, plus C outside every scored frame.
    metrics = ev.evaluate([ai(2, A, 0, 5), ai(3, C, 30, 40)], [seg(1, A, 0, 10)])
    assert metrics.n_frames == 10 and metrics.frame_accuracy == 0.5
    per_step = {m.step_id: (m.precision, m.recall) for m in metrics.per_step}
    assert per_step == {A: (1.0, 0.5), C: (0.0, 0.0)}


@pytest.mark.parametrize(
    ("ai_segments", "truth", "f1"),
    [
        # Over-segmented: AI splits A in two; only one part matches (IoU 12/20). P 1/2, R 1/1.
        ([ai(5, A, 0, 12), ai(6, A, 12, 20)], [seg(1, A, 0, 20)], 2 / 3),
        # Under-segmented: AI misses the short B. A (IoU 10/12) and C match. P 2/2, R 2/3.
        (
            [ai(5, A, 0, 12), ai(6, C, 12, 30)],
            [seg(1, A, 0, 10), seg(2, B, 10, 12), seg(3, C, 12, 30)],
            0.8,
        ),
        # Three thirds of one long step: IoU 1/3 each, below 0.5 → no match.
        ([ai(5, A, 0, 10), ai(6, A, 10, 20), ai(7, A, 20, 30)], [seg(1, A, 0, 30)], 0.0),
    ],
)
def test_segment_f1_by_hand(ai_segments, truth, f1):
    assert ev.evaluate(ai_segments, truth).segment_f1 == pytest.approx(f1, abs=1e-9)


def test_matching_is_one_to_one_and_takes_the_best_partner():
    # AI A at 5-25 overlaps A at 0-10 (IoU 5/25) and A at 10-30 (IoU 15/25): it takes the second.
    truth = [seg(1, A, 0, 10), seg(2, A, 10, 30)]
    assert ev.segment_f1([ai(3, A, 5, 25)], truth) == pytest.approx(2 * 1 * 0.5 / 1.5)
    # Both halves have IoU 0.5 with A at 0-10, but only one can match it: P 1/2, R 1/1.
    halves = [ai(3, A, 0, 5), ai(4, A, 5, 10)]
    assert ev.segment_f1(halves, [seg(1, A, 0, 10)]) == pytest.approx(2 / 3)


def test_the_frame_step_sets_the_grid():
    metrics = ev.evaluate([ai(2, A, 0, 10)], [seg(1, A, 0, 10)], frame_step_s=0.5)
    assert metrics.n_frames == 20
    with pytest.raises(ValueError, match="frame_step_s"):
        ev.evaluate([ai(2, A, 0, 10)], [seg(1, A, 0, 10)], frame_step_s=0)


@pytest.mark.parametrize(
    ("ai_segments", "truth", "message"),
    [
        ([], [seg(1, A, 0, 10)], "no ai step segments"),
        ([ai(2, A, 0, 10)], [], "no dataset step segments"),
        ([seg(2, A, 0, 10)], [seg(1, A, 0, 10)], "not on the ai track: grasp-01.s002"),
        ([ai(2, A, 0, 10, case="grasp-02")], [seg(1, A, 0, 10)], "more than one case"),
        ([ai(2, A, 0, 10), ai(3, B, 9, 12)], [seg(1, A, 0, 10)], "ai segments overlap"),
        ([ai(2, A, 0, 10)], [seg(1, A, 0, 20), seg(3, B, 2, 3)], "dataset segments overlap"),
        ([ai(2, A, 0, 10)], [seg(1, A, 3, 3)], "no frame to score"),
        ([ai(2, A, 0, 10, model=None)], [seg(1, A, 0, 10)], "without provenance.generated_by"),
        (
            [ai(2, A, 0, 5), ai(3, A, 5, 10, model=MODEL.model_copy(update={"model": "y"}))],
            [seg(1, A, 0, 10)],
            "different models or prompts",
        ),
    ],
)
def test_refused_inputs(ai_segments, truth, message):
    with pytest.raises(ValueError, match=message):
        ev.evaluate(ai_segments, truth)


def test_an_overlap_behind_a_zero_length_segment_is_found():
    truth = [seg(1, A, 0, 10), seg(2, B, 5, 5), seg(3, B, 6, 7)]
    with pytest.raises(ValueError, match="grasp-01.s001 and grasp-01.s003"):
        ev.evaluate([ai(4, A, 0, 10)], truth)


def test_metrics_json_is_byte_identical_and_written_atomically(tmp_path: Path):
    def make() -> Metrics:
        return ev.evaluate([ai(3, A, 0, 6), ai(4, B, 6, 20)], [seg(1, A, 0, 10), seg(2, B, 10, 20)])

    assert ev.metrics_json(make()) == ev.metrics_json(make())
    path = ev.write_metrics(make(), tmp_path / "work" / "grasp-01")
    assert path.name == "metrics.json" and not (path.parent / "metrics.json.part").exists()
    text = path.read_text("utf-8")
    assert text.endswith("\n") and Metrics.model_validate_json(text) == make()


def write_timeline(path: Path, steps: list[StepSegment]) -> Path:
    timeline = Timeline(
        contract_version=CONTRACT_VERSION,
        case_id="grasp-01",
        steps=steps,
        events=[],
        instruments=[],
        utterances=[],
    )
    path.write_text(timeline.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_evaluate_timeline_and_the_cli(tmp_path: Path):
    timeline = write_timeline(
        tmp_path / "timeline.json",
        [seg(1, A, 0, 10), seg(2, B, 10, 20), ai(3, A, 0, 6), ai(4, B, 6, 20)],
    )
    path = ev.evaluate_timeline(timeline, tmp_path / "out")
    assert json.loads(path.read_text("utf-8"))["frame_accuracy"] == 0.8
    out: list[str] = []
    assert cli.main(["metrics", str(timeline), str(tmp_path / "cli")], out=out.append) == 0
    assert out[0].startswith("frame accuracy 0.800, segment F1 1.000 over 20 frame(s)")
    only_truth = write_timeline(tmp_path / "t2.json", [seg(1, A, 0, 10)])
    err: list[str] = []
    assert cli.main(["metrics", str(only_truth), str(tmp_path / "x")], err=err.append) == 1
    assert err == ["scrubgpt-brain: error: no ai step segments to evaluate"]
    assert not (tmp_path / "x").exists()
