"""B1 GraSP importer, the label part (plan §2.2, C8): GraSP's ground truth → the dataset step track.

GraSP (Ayobi et al. 2024) labels every second of its RARP videos with one of 11 phases and one of
21 steps, made by experts. This module turns one GraSP case's labels into rule-book step segments
on the **dataset track** (📐 `dataset_annotation`). That powers two things:
- ground-truth mode for the GraSP demo case (C8);
- an honest accuracy score for our own AI steps (C7).

The labels come from `grasp_long-term_*.json`. Its keys `phases_categories` / `steps_categories`
must equal the A1 crosswalk in `knowledge/rulebooks/rarp.yaml` (ids, codes, names); otherwise the
import stops, so another annotation version can't be misread. `images[]` and `annotations[]` give
one keyframe per second with `frame_num` and the `phases` / `steps` ids.

**Time.** A keyframe's time is `frame_num / fps`, in float seconds from the start of the video. B3
normalises the video without cutting it, so these are also seconds of the normalised video. `fps`
is the source video's frame rate (`video_fps`, e.g. from `probe`); without it, it is estimated
from the keyframe spacing (the keyframes are 1 s apart). In the 1-fps annotation files that
spacing is 1 frame. Each keyframe stands for the second up to the next one; the last keyframe
stands for 1 s.

**Mapping to rule-book steps** (the crosswalk's `maps_to`, `by_phase` and `phase`):
- A GraSP step's targets (rule-book phases expand to their steps) apply, or its `by_phase`
  override for the GraSP phase it occurs in. A target `phase` means "whatever the GraSP phase
  maps to", for generic acts such as suction or cutting.
- With several candidate steps, the current one is kept if it is a candidate (continuity).
  Otherwise the first candidate not earlier in rule-book order is taken, else the first.
- `Idle` (and any label with no targets) gives **no** segment: a gap, not a guess.

Consecutive keyframes with the same rule-book step merge into one segment. A pause inside a step
(idle seconds with the same step before and after) is bridged: it is still that step, and GraSP
marks about a third of its time idle (instrument changes, camera cleaning). A gap remains only
where the step changes. The output is contract
`StepSegment`s (track `dataset`, confidence 1.0, provenance `dataset_annotation` / `dataset`);
E1 later merges them into `timeline.json`.
"""

import json
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from scrubgpt_contracts.models.case_package import StepSegment, StepTrack
from scrubgpt_contracts.models.common import Provenance, Role, TrustLabel, segment_id

from scrubgpt_brain.engines.rulebook import (
    KNOWLEDGE_DIR,
    GraspCrosswalk,
    GraspLabel,
    RuleBook,
    load_knowledge,
)

LAST_KEYFRAME_S = 1.0
"""How long the last keyframe stands for (the keyframes are 1 s apart)."""


class GraspError(ValueError):
    """The annotation file can't be read, doesn't match the crosswalk, or lacks the case."""


@dataclass(frozen=True)
class GraspLabels:
    """One GraSP case's keyframes: time (s) and the GraSP phase and step id of each."""

    case: str
    times: tuple[float, ...]
    phases: tuple[int, ...]
    steps: tuple[int, ...]
    fps: float


@dataclass(frozen=True)
class ImportReport:
    """What the import did, for the run log and for spotting crosswalk gaps."""

    seconds_by_step: dict[str, float]
    idle_seconds: float
    unmapped_seconds: dict[str, float] = field(default_factory=dict)
    """GraSP labels (code) that had no rule-book target, by seconds."""


def _check_categories(data: dict, crosswalk: GraspCrosswalk, path: Path) -> None:
    for key, labels in (
        ("phases_categories", crosswalk.phases),
        ("steps_categories", crosswalk.steps),
    ):
        given = {int(c["id"]): (c.get("name"), c.get("description")) for c in data.get(key) or []}
        expected = {label.grasp_id: (label.code, label.name) for label in labels}
        if given != expected:
            differ = sorted(
                i for i in set(given) | set(expected) if given.get(i) != expected.get(i)
            )
            raise GraspError(
                f"{path.name}: `{key}` doesn't match the A1 GraSP crosswalk (ids {differ}): "
                "another annotation version? Check it and update knowledge/rulebooks/rarp.yaml"
            )


def read_labels(
    path: Path,
    grasp_case: str,
    *,
    video_fps: float | None = None,
    crosswalk: GraspCrosswalk | None = None,
) -> GraspLabels:
    """The keyframe labels of one GraSP case (e.g. `CASE001`) from a long-term annotation file,
    checked against `crosswalk` (default: the repo rule book's).

    Raises `GraspError` if the file can't be read, doesn't match the crosswalk or lacks the case.
    """
    crosswalk = crosswalk or load_knowledge().rulebook.grasp
    if crosswalk is None:
        raise GraspError("the rule book has no GraSP crosswalk")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise GraspError(f"can't read {path}: {exc}") from None
    _check_categories(data, crosswalk, path)
    frames = {
        int(image["id"]): int(image["frame_num"])
        for image in data.get("images") or []
        if image.get("video_name") == grasp_case
    }
    if not frames:
        raise GraspError(f"{path.name} has no keyframes for {grasp_case}")
    keyframes = sorted(
        (frames[a["image_id"]], int(a["phases"]), int(a["steps"]))
        for a in data.get("annotations") or []
        if a.get("image_id") in frames
    )
    if len(keyframes) != len(frames):
        raise GraspError(f"{path.name}: {grasp_case} has keyframes without exactly one label")
    if video_fps is None:
        spacing = [b[0] - a[0] for a, b in zip(keyframes, keyframes[1:], strict=False)]
        video_fps = float(statistics.median(spacing)) if spacing else 1.0
    if video_fps <= 0:
        raise GraspError(f"video_fps must be positive, not {video_fps}")
    return GraspLabels(
        case=grasp_case,
        times=tuple(frame / video_fps for frame, _, _ in keyframes),
        phases=tuple(phase for _, phase, _ in keyframes),
        steps=tuple(step for _, _, step in keyframes),
        fps=video_fps,
    )


class _Mapper:
    """Resolves (GraSP phase, GraSP step) → one rule-book step id, or `None` for a gap."""

    def __init__(self, rulebook: RuleBook) -> None:
        crosswalk = rulebook.grasp
        assert crosswalk is not None
        self.order = [step.id for step in rulebook.steps()]
        self.phase_steps = {p.id: [s.id for s in p.steps] for p in rulebook.phases}
        self.phases = {label.grasp_id: label for label in crosswalk.phases}
        self.steps = {label.grasp_id: label for label in crosswalk.steps}

    def _expand(self, ids: tuple[str, ...]) -> list[str]:
        expanded: list[str] = []
        for item in ids:
            for step in self.phase_steps.get(item, [item]):
                if step not in expanded:
                    expanded.append(step)
        return sorted(expanded, key=self.order.index)

    def _targets(self, label: GraspLabel, grasp_phase: int) -> tuple[str, ...]:
        if grasp_phase in label.by_phase:
            return label.by_phase[grasp_phase]
        if label.maps_to == "phase":
            phase = self.phases.get(grasp_phase)
            return () if phase is None or phase.maps_to == "phase" else phase.maps_to
        return label.maps_to

    def step(self, grasp_phase: int, grasp_step: int, current: str | None) -> str | None:
        label = self.steps.get(grasp_step)
        if label is None:
            return None
        candidates = self._expand(self._targets(label, grasp_phase))
        if not candidates:
            return None
        if current in candidates:
            return current
        if current is not None:
            later = [c for c in candidates if self.order.index(c) >= self.order.index(current)]
            if later:
                return later[0]
        return candidates[0]

    def code(self, grasp_step: int) -> str:
        label = self.steps.get(grasp_step)
        return (label.code or label.name) if label else str(grasp_step)


def dataset_steps(
    labels: GraspLabels, case_id: str, rulebook: RuleBook
) -> tuple[list[StepSegment], ImportReport]:
    """The dataset-track step segments for one case's labels, and a report of the import."""
    mapper = _Mapper(rulebook)
    ends = [*labels.times[1:], labels.times[-1] + LAST_KEYFRAME_S]
    provenance = Provenance(
        trust_label=TrustLabel.DATASET_ANNOTATION,
        attributed_to=Role.DATASET,
        generated_by=None,
        confirmed_by=None,
        confirmed_at=None,
    )
    seconds: Counter[str] = Counter()
    unmapped: Counter[str] = Counter()
    idle = 0.0
    runs: list[tuple[str, float, float]] = []
    current: str | None = None
    for t, end, phase, step in zip(labels.times, ends, labels.phases, labels.steps, strict=True):
        mapped = mapper.step(phase, step, current)
        if mapped is None:
            if step == 0:
                idle += end - t
            else:
                unmapped[mapper.code(step)] += end - t
            continue
        seconds[mapped] += end - t
        if runs and runs[-1][0] == mapped:  # contiguous, or the same step after a pause
            runs[-1] = (mapped, runs[-1][1], end)
        else:
            runs.append((mapped, t, end))
        current = mapped
    segments = [
        StepSegment(
            id=segment_id(case_id, i + 1),
            t_start=round(start, 6),
            t_end=round(end, 6),
            confidence=1.0,
            provenance=provenance,
            step_id=step_id,
            track=StepTrack.DATASET,
        )
        for i, (step_id, start, end) in enumerate(runs)
    ]
    report = ImportReport(
        seconds_by_step=dict(seconds), idle_seconds=idle, unmapped_seconds=dict(unmapped)
    )
    return segments, report


def import_grasp_steps(
    path: Path,
    grasp_case: str,
    case_id: str,
    *,
    video_fps: float | None = None,
    knowledge_dir: Path = KNOWLEDGE_DIR,
) -> tuple[list[StepSegment], ImportReport]:
    """Read one GraSP case's labels and turn them into dataset-track step segments."""
    rulebook = load_knowledge(knowledge_dir).rulebook
    labels = read_labels(path, grasp_case, video_fps=video_fps, crosswalk=rulebook.grasp)
    return dataset_steps(labels, case_id, rulebook)
