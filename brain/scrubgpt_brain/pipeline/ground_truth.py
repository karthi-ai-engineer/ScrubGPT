"""C8 Ground-truth mode (plan §2.3; D-070): a GraSP case shows GraSP's expert steps by default.

B1 (`grasp.import_grasp_steps`) turns GraSP's labels into dataset-track step segments. C8 puts
them into the case package, so the App plays the case with the experts' steps, and the AI's steps
alongside for comparison (the golden case GC1, plan §7):
- **`timeline.json`:** the dataset track is replaced by the given segments: track `dataset`, 📐
  `dataset_annotation`, `generated_by: null`. They are numbered after the AI segments
  (`<case>.sNNN`, as in the fixture case). The rest stays exactly as it was: the AI segments,
  events, instruments and utterances. Without a `timeline.json`, an empty one is started.
- **`case.json`:** `default_step_track: dataset`.

**A case without dataset segments is never switched:** that is an error, and nothing is written.
Every segment must belong to the case, be on the dataset track with the dataset trust label and
no model, and not overlap another. Both files are validated by the contract models and written
atomically, the timeline first. Re-running with the same segments gives byte-identical files. C8
works in the case's work folder; only finished packages go to `<DATA_DIR>/cases/` (rule 4).
"""

import json
import os
from collections.abc import Sequence
from pathlib import Path

from scrubgpt_contracts.models.case_package import Case, StepSegment, StepTrack, Timeline
from scrubgpt_contracts.models.common import CONTRACT_VERSION, TrustLabel, segment_id

from scrubgpt_brain.engines.rulebook import KNOWLEDGE_DIR
from scrubgpt_brain.pipeline.cases import CASE_FILE
from scrubgpt_brain.pipeline.grasp import ImportReport, import_grasp_steps

TIMELINE_FILE = "timeline.json"


def _read[M: (Case, Timeline)](path: Path, model: type[M]) -> M:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"can't read {path}: {exc}") from None


def _write(path: Path, model: Case | Timeline) -> None:
    part = path.with_name(path.name + ".part")
    text = json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    part.write_text(text, encoding="utf-8", newline="\n")
    os.replace(part, path)


def _check(case_id: str, dataset: Sequence[StepSegment]) -> None:
    if not dataset:
        raise ValueError(f"{case_id}: no dataset step segments; the case is not switched")
    problems = []
    for s in dataset:
        if s.track is not StepTrack.DATASET:
            problems.append(f"{s.id}: track {s.track.value}, not dataset")
        if s.provenance.trust_label is not TrustLabel.DATASET_ANNOTATION:
            problems.append(f"{s.id}: trust label {s.provenance.trust_label.value}")
        if s.provenance.generated_by is not None:
            problems.append(f"{s.id}: ground truth has no generated_by")
        if s.id.rsplit(".s", 1)[0] != case_id:
            problems.append(f"{s.id}: not a segment of {case_id}")
    reach: StepSegment | None = None
    for s in sorted(dataset, key=lambda s: (s.t_start, s.t_end)):
        if reach is not None and s.t_start < reach.t_end and s.t_end > s.t_start:
            problems.append(f"{reach.id} and {s.id} overlap")
        if reach is None or s.t_end > reach.t_end:
            reach = s
    if problems:
        raise ValueError("; ".join(problems))


def apply_ground_truth(case_dir: Path, dataset: Sequence[StepSegment]) -> tuple[Path, Path]:
    """Put the dataset step track into `case_dir`'s `timeline.json` and make it the case's default
    track in `case.json`. Returns both paths. Raises `ValueError` (nothing written) for a missing
    or invalid `case.json` or timeline, or segments that can't be ground truth."""
    case_path, timeline_path = case_dir / CASE_FILE, case_dir / TIMELINE_FILE
    case = _read(case_path, Case)
    _check(case.id, dataset)
    if timeline_path.exists():
        timeline = _read(timeline_path, Timeline)
        if timeline.case_id != case.id:
            raise ValueError(f"{timeline_path} is case {timeline.case_id}, not {case.id}")
    else:
        timeline = Timeline(
            contract_version=CONTRACT_VERSION,
            case_id=case.id,
            steps=[],
            events=[],
            instruments=[],
            utterances=[],
        )
    kept = [s for s in timeline.steps if s.track is not StepTrack.DATASET]
    last = max((int(s.id.rsplit(".s", 1)[1]) for s in kept), default=0)
    ordered = sorted(dataset, key=lambda s: (s.t_start, s.t_end, s.id))
    renumbered = [
        s.model_copy(update={"id": segment_id(case.id, last + i + 1)})
        for i, s in enumerate(ordered)
    ]
    # Validate the whole timeline again (unique ids, all in the case) before writing anything.
    updated = Timeline.model_validate(
        {**timeline.model_dump(), "steps": [s.model_dump() for s in [*kept, *renumbered]]}
    )
    switched = Case.model_validate({**case.model_dump(), "default_step_track": "dataset"})
    _write(timeline_path, updated)
    _write(case_path, switched)
    return case_path, timeline_path


def ground_truth_from_grasp(
    case_dir: Path,
    annotations: Path,
    grasp_case: str,
    *,
    video_fps: float | None = None,
    knowledge_dir: Path = KNOWLEDGE_DIR,
) -> tuple[Path, Path, ImportReport]:
    """B1 + C8: import one GraSP case's labels and apply them to its package in `case_dir`."""
    case = _read(case_dir / CASE_FILE, Case)
    segments, report = import_grasp_steps(
        annotations, grasp_case, case.id, video_fps=video_fps, knowledge_dir=knowledge_dir
    )
    case_path, timeline_path = apply_ground_truth(case_dir, segments)
    return case_path, timeline_path, report
