"""C7 Accuracy evaluator (plan §2.3, §4.2 `metrics.json`; D-070): how well the AI's steps match
GraSP's ground truth for one case.

Inputs are contract `StepSegment`s of one case: the AI track (`track: ai`, from C2 + C3) and the
dataset track (`track: dataset`, from B1). The result is the contract `Metrics`, which E1 writes
into the GraSP case's package as `metrics.json` and the App shows as the honest accuracy figure.
These numbers are reported as they come out: the real ones are measured on GraSP's **test**
cases in Block 2, never on cases a prompt was tuned on (brain/CLAUDE.md rule 8).

**Frames.** Times `0, step, 2·step, …` (default `FRAME_STEP_S` = 1 s) at which a dataset segment
has a label: a segment covers `t_start <= t < t_end`, so a zero-length segment covers nothing.
These are the frames scored; `n_frames` counts them. Each frame's AI step is the AI segment that
covers it, and a frame no AI segment covers counts as wrong.
- `frame_accuracy`: the share of frames where the AI step equals the dataset step.
- `per_step`: for every step that appears in either track, frame-level `precision` (of the frames
  the AI gave this step, the share that are right; 0.0 if the AI gave it no frame) and `recall`
  (of this step's dataset frames, the share the AI got; 0.0 if the dataset has no frame of it).
  Sorted by step id.

**Segments.** An AI segment *matches* a dataset segment with the same `step_id` when their temporal
IoU (overlap / union) is at least `MATCH_IOU` (0.5). Matching is one-to-one: in time order, each
AI segment takes the unmatched dataset partner with the highest IoU. `segment_f1` = 2PR/(P+R),
with P = matches / AI segments and R = matches / dataset segments; 0.0 without a match. It
punishes over- and under-segmentation that frame accuracy hides.

`model_info` is the AI segments' `provenance.generated_by`, which must be present and the same on
all of them: a model name is never invented.

The evaluation is pure: the same segments always give byte-identical JSON. Errors (`ValueError`):
no AI or no dataset segment, a segment on the wrong track, segments of two cases, overlapping
segments within one track, no scored frame, or missing or differing `generated_by`.
"""

import json
import math
import os
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from scrubgpt_contracts.models.case_package import (
    Metrics,
    StepMetrics,
    StepSegment,
    StepTrack,
    Timeline,
)
from scrubgpt_contracts.models.common import CONTRACT_VERSION, GeneratedBy

FRAME_STEP_S = 1.0
MATCH_IOU = 0.5
METRICS_FILE = "metrics.json"


def _case_of(segment: StepSegment) -> str:
    return segment.id.rsplit(".s", 1)[0]


def _check_track(segments: Sequence[StepSegment], track: StepTrack) -> None:
    if not segments:
        raise ValueError(f"no {track.value} step segments to evaluate")
    wrong = [s.id for s in segments if s.track is not track]
    if wrong:
        raise ValueError(f"not on the {track.value} track: {', '.join(wrong)}")
    reach: StepSegment | None = None  # the segment reaching furthest so far
    for segment in sorted(segments, key=lambda s: (s.t_start, s.t_end)):
        overlaps = reach is not None and segment.t_start < reach.t_end
        if overlaps and segment.t_end > segment.t_start:  # a zero-length segment covers nothing
            assert reach is not None
            raise ValueError(f"{track.value} segments overlap: {reach.id} and {segment.id}")
        if reach is None or segment.t_end > reach.t_end:
            reach = segment


def _step_at(segments: Sequence[StepSegment], t: float) -> str | None:
    for segment in segments:
        if segment.t_start <= t < segment.t_end:
            return segment.step_id
    return None


def _iou(a: StepSegment, b: StepSegment) -> float:
    overlap = min(a.t_end, b.t_end) - max(a.t_start, b.t_start)
    union = max(a.t_end, b.t_end) - min(a.t_start, b.t_start)
    return max(overlap, 0.0) / union if union > 0 else 0.0


def segment_f1(ai: Sequence[StepSegment], dataset: Sequence[StepSegment]) -> float:
    """F1 of one-to-one segment matches (same step, IoU >= `MATCH_IOU`)."""
    unmatched = list(dataset)
    matches = 0
    for segment in sorted(ai, key=lambda s: (s.t_start, s.t_end, s.id)):
        best: tuple[float, StepSegment] | None = None
        for partner in unmatched:
            if partner.step_id != segment.step_id:
                continue
            iou = _iou(segment, partner)
            if iou >= MATCH_IOU and (best is None or iou > best[0]):
                best = (iou, partner)
        if best is not None:
            unmatched.remove(best[1])
            matches += 1
    if matches == 0:
        return 0.0
    precision, recall = matches / len(ai), matches / len(dataset)
    return 2 * precision * recall / (precision + recall)


def _model_info(ai: Sequence[StepSegment]) -> GeneratedBy:
    missing = [s.id for s in ai if s.provenance.generated_by is None]
    if missing:
        raise ValueError(f"AI segments without provenance.generated_by: {', '.join(missing)}")
    models = {s.provenance.generated_by.model_dump_json() for s in ai if s.provenance.generated_by}
    if len(models) > 1:
        raise ValueError(f"the AI segments come from different models or prompts: {sorted(models)}")
    return GeneratedBy.model_validate_json(models.pop())


def evaluate(
    ai: Sequence[StepSegment],
    dataset: Sequence[StepSegment],
    *,
    frame_step_s: float = FRAME_STEP_S,
) -> Metrics:
    """Score one case's AI step segments against its dataset step segments."""
    if not (math.isfinite(frame_step_s) and frame_step_s > 0):
        raise ValueError(f"frame_step_s must be a positive number, not {frame_step_s}")
    _check_track(ai, StepTrack.AI)
    _check_track(dataset, StepTrack.DATASET)
    cases = sorted({_case_of(s) for s in [*ai, *dataset]})
    if len(cases) > 1:
        raise ValueError(f"segments of more than one case: {', '.join(cases)}")
    model_info = _model_info(ai)

    end = max(s.t_end for s in dataset)
    truth: list[str] = []
    guess: list[str | None] = []
    for k in range(math.ceil(end / frame_step_s) + 1):
        t = k * frame_step_s
        label = _step_at(dataset, t)
        if label is not None:
            truth.append(label)
            guess.append(_step_at(ai, t))
    if not truth:
        raise ValueError("no frame to score: the dataset segments cover no frame time")

    correct = sum(1 for g, d in zip(guess, truth, strict=True) if g == d)
    hits = Counter(d for g, d in zip(guess, truth, strict=True) if g == d)
    given = Counter(g for g in guess if g is not None)
    actual = Counter(truth)
    steps = sorted({s.step_id for s in ai} | {s.step_id for s in dataset})
    per_step = [
        StepMetrics(
            step_id=step,
            precision=hits[step] / given[step] if given[step] else 0.0,
            recall=hits[step] / actual[step] if actual[step] else 0.0,
        )
        for step in steps
    ]
    return Metrics(
        contract_version=CONTRACT_VERSION,
        case_id=cases[0],
        frame_accuracy=correct / len(truth),
        segment_f1=segment_f1(ai, dataset),
        per_step=per_step,
        n_frames=len(truth),
        model_info=model_info,
    )


def metrics_json(metrics: Metrics) -> str:
    """The `metrics.json` text (UTF-8, LF, 2-space indent)."""
    return json.dumps(metrics.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"


def write_metrics(metrics: Metrics, out_dir: Path) -> Path:
    """Write `metrics.json` into `out_dir` (the caller's choice: a work folder, rule 4)
    atomically, and return its path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / METRICS_FILE
    part = out_dir / f"{METRICS_FILE}.part"
    part.write_text(metrics_json(metrics), encoding="utf-8", newline="\n")
    os.replace(part, target)
    return target


def evaluate_timeline(timeline: Path, out_dir: Path, *, frame_step_s: float = FRAME_STEP_S) -> Path:
    """C7 on a `timeline.json` that carries both tracks (a GraSP case): write `metrics.json` into
    `out_dir`. Raises `ValueError` for an invalid timeline or anything `evaluate` refuses."""
    try:
        data = Timeline.model_validate_json(timeline.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"can't read {timeline}: {exc}") from None
    ai = [s for s in data.steps if s.track is StepTrack.AI]
    dataset = [s for s in data.steps if s.track is StepTrack.DATASET]
    return write_metrics(evaluate(ai, dataset, frame_step_s=frame_step_s), out_dir)
