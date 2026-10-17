"""Dev1's unit tests for C8, ground-truth mode (pipeline/ground_truth.py; D-070). The package is a
copy of the contract's synthetic fixture case; annotation files are synthetic."""

import json
import shutil
from pathlib import Path

import pytest
from scrubgpt_brain import cli
from scrubgpt_brain.engines.rulebook import KNOWLEDGE_DIR, load_knowledge
from scrubgpt_brain.pipeline import ground_truth as gt
from scrubgpt_contracts.models.case_package import Case, StepSegment, StepTrack, Timeline
from scrubgpt_contracts.models.common import GeneratedBy, Provenance, Role, TrustLabel
from scrubgpt_contracts.validate import validate_case

FIXTURES = KNOWLEDGE_DIR.parent / "contracts" / "fixtures"
REFERENCE = FIXTURES / "reference" / "rarp.json"
CASE = "case-fixture-01"


@pytest.fixture
def package(tmp_path: Path) -> Path:
    """The fixture case without its dataset track, still on the AI track."""
    case_dir = tmp_path / "work" / CASE
    shutil.copytree(FIXTURES / "cases" / CASE, case_dir)
    path = case_dir / "timeline.json"
    timeline = Timeline.model_validate_json(path.read_text("utf-8"))
    timeline.steps = [s for s in timeline.steps if s.track is StepTrack.AI]
    path.write_text(timeline.model_dump_json(indent=2), encoding="utf-8")
    return case_dir


def truth(n: int, step: str, t_start: float, t_end: float, **changes) -> StepSegment:
    segment = StepSegment(
        id=f"{CASE}.s{n:03d}",
        t_start=t_start,
        t_end=t_end,
        confidence=1.0,
        provenance=Provenance(
            trust_label=TrustLabel.DATASET_ANNOTATION,
            attributed_to=Role.DATASET,
            generated_by=None,
            confirmed_by=None,
            confirmed_at=None,
        ),
        step_id=step,
        track=StepTrack.DATASET,
    )
    return segment.model_copy(update=changes)


DATASET = [
    truth(2, "rarp.p04.s01", 30.0, 60.0),
    truth(1, "rarp.p03.s01", 0.0, 30.0),
    truth(3, "rarp.p05.s01", 70.0, 120.0),
]


def test_the_dataset_track_becomes_the_default_and_the_rest_is_kept(package: Path):
    before = Timeline.model_validate_json((package / "timeline.json").read_text("utf-8"))
    case_path, timeline_path = gt.apply_ground_truth(package, DATASET)
    case = Case.model_validate_json(case_path.read_text("utf-8"))
    assert case.default_step_track is StepTrack.DATASET
    after = Timeline.model_validate_json(timeline_path.read_text("utf-8"))
    ai = [s for s in after.steps if s.track is StepTrack.AI]
    assert ai == before.steps  # the AI track, unchanged
    assert (after.events, after.instruments, after.utterances) == (
        before.events,
        before.instruments,
        before.utterances,
    )
    dataset = [s for s in after.steps if s.track is StepTrack.DATASET]
    # In time order, numbered after the 12 AI segments.
    assert [(s.id, s.step_id) for s in dataset] == [
        (f"{CASE}.s013", "rarp.p03.s01"),
        (f"{CASE}.s014", "rarp.p04.s01"),
        (f"{CASE}.s015", "rarp.p05.s01"),
    ]
    assert all(s.provenance.trust_label is TrustLabel.DATASET_ANNOTATION for s in dataset)
    assert all(s.provenance.generated_by is None for s in dataset)
    # The package as a whole still passes the contract validator.
    report = validate_case(package, REFERENCE)
    assert report.ok, report.render()


def test_re_running_is_byte_identical_and_replaces_the_dataset_track(package: Path):
    gt.apply_ground_truth(package, DATASET)
    first = [(package / name).read_bytes() for name in ("case.json", "timeline.json")]
    gt.apply_ground_truth(package, DATASET)
    assert [(package / name).read_bytes() for name in ("case.json", "timeline.json")] == first
    gt.apply_ground_truth(package, DATASET[:1])
    after = Timeline.model_validate_json((package / "timeline.json").read_text("utf-8"))
    assert [s.step_id for s in after.steps if s.track is StepTrack.DATASET] == ["rarp.p04.s01"]
    assert not list(package.glob("*.part"))


MODEL = GeneratedBy(model_tier="VISION_FAST", model="m", prompt_version=None)


@pytest.mark.parametrize(
    ("segments", "message"),
    [
        ([], "no dataset step segments; the case is not switched"),
        ([truth(1, "rarp.p03.s01", 0, 10, track=StepTrack.AI)], "track ai, not dataset"),
        (
            [
                truth(
                    1,
                    "rarp.p03.s01",
                    0,
                    10,
                    provenance=Provenance(
                        trust_label=TrustLabel.AI_DETECTED,
                        attributed_to=Role.AI,
                        generated_by=MODEL,
                        confirmed_by=None,
                        confirmed_at=None,
                    ),
                )
            ],
            "trust label ai_detected",
        ),
        ([truth(1, "rarp.p03.s01", 0, 10, id="grasp-02.s001")], "not a segment of case-fixture"),
        ([truth(1, "rarp.p03.s01", 0, 10), truth(2, "rarp.p04.s01", 5, 15)], "overlap"),
    ],
)
def test_bad_segments_switch_nothing(package: Path, segments, message):
    before = [(package / name).read_bytes() for name in ("case.json", "timeline.json")]
    with pytest.raises(ValueError, match=message):
        gt.apply_ground_truth(package, segments)
    assert [(package / name).read_bytes() for name in ("case.json", "timeline.json")] == before


def test_a_case_without_a_timeline_gets_one(package: Path):
    (package / "timeline.json").unlink()
    _, timeline_path = gt.apply_ground_truth(package, DATASET)
    timeline = Timeline.model_validate_json(timeline_path.read_text("utf-8"))
    assert [s.id for s in timeline.steps] == [f"{CASE}.s00{n}" for n in (1, 2, 3)]
    assert timeline.events == [] and timeline.utterances == []


def test_a_missing_case_json_is_an_error(tmp_path: Path):
    with pytest.raises(ValueError, match="can't read"):
        gt.apply_ground_truth(tmp_path, DATASET)


def annotations(path: Path) -> Path:
    """A 1 fps GraSP file for CASE001: 20 s of iliac dissection, then 15 s of Retzius."""
    crosswalk = load_knowledge().rulebook.grasp
    phase = {x.code: x.grasp_id for x in crosswalk.phases}
    step = {x.code: x.grasp_id for x in crosswalk.steps}
    blocks = [("LPIL", "Id_Illiac_Vein_Artery")] * 20 + [
        ("Retzius_Space", "Prevessical_Dissection")
    ] * 15
    data = {
        "phases_categories": [
            {"id": x.grasp_id, "name": x.code, "description": x.name} for x in crosswalk.phases
        ],
        "steps_categories": [
            {"id": x.grasp_id, "name": x.code, "description": x.name} for x in crosswalk.steps
        ],
        "images": [
            {"id": i + 1, "video_name": "CASE001", "frame_num": i} for i in range(len(blocks))
        ],
        "annotations": [
            {"id": i + 1, "image_id": i + 1, "phases": phase[p], "steps": step[s]}
            for i, (p, s) in enumerate(blocks)
        ],
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_from_grasp_and_the_cli(package: Path, tmp_path: Path):
    path = annotations(tmp_path / "train.json")
    _, timeline_path, report = gt.ground_truth_from_grasp(package, path, "CASE001")
    timeline = Timeline.model_validate_json(timeline_path.read_text("utf-8"))
    dataset = [s for s in timeline.steps if s.track is StepTrack.DATASET]
    assert [(s.t_start, s.t_end) for s in dataset] == [(0.0, 20.0), (20.0, 35.0)]
    assert sum(report.seconds_by_step.values()) == 35.0
    out: list[str] = []
    args = ["ground-truth", str(package), str(path), "CASE001"]
    assert cli.main(args, out=out.append) == 0
    assert out[0].startswith("ground truth: 2 dataset step segment(s), 35.0 s labelled")
    err: list[str] = []
    assert cli.main([*args[:3], "CASE999"], err=err.append) == 1
    assert err[0].startswith("scrubgpt-brain: error: train.json has no keyframes for CASE999")
