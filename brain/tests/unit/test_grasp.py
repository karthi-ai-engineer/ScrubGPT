"""Dev1's unit tests for B1's GraSP label import (pipeline/grasp.py). The annotation files here
are synthetic, built from the A1 crosswalk itself (no GraSP data is committed)."""

import json
from pathlib import Path

import pytest
from scrubgpt_brain.engines.rulebook import load_knowledge
from scrubgpt_brain.pipeline import grasp as g
from scrubgpt_contracts.models.case_package import StepTrack
from scrubgpt_contracts.models.common import TrustLabel

BOOK = load_knowledge().rulebook
XWALK = BOOK.grasp
CODES = {label.code: label.grasp_id for label in XWALK.steps}
PHASES = {label.code: label.grasp_id for label in XWALK.phases}


def annotation_file(
    path: Path, keyframes: list[tuple[str, str]], *, case: str = "CASE001", fps: float = 45.0
) -> Path:
    """A long-term file with one keyframe per second: (GraSP phase code, GraSP step code)."""
    images, annotations = [], []
    for i, (phase, step) in enumerate(keyframes):
        frame = round(i * fps + 22)
        images.append({"id": i + 1, "video_name": case, "frame_num": frame})
        annotations.append(
            {"id": i + 1, "image_id": i + 1, "phases": PHASES[phase], "steps": CODES[step]}
        )
    categories = {
        "phases_categories": [
            {"id": label.grasp_id, "name": label.code, "description": label.name}
            for label in XWALK.phases
        ],
        "steps_categories": [
            {"id": label.grasp_id, "name": label.code, "description": label.name}
            for label in XWALK.steps
        ],
    }
    path.write_text(
        json.dumps({**categories, "images": images, "annotations": annotations}), encoding="utf-8"
    )
    return path


def first_target(code: str) -> str:
    label = XWALK.steps[CODES[code]]
    target = label.maps_to[0]
    return BOOK.phase(target).steps[0].id if target in {p.id for p in BOOK.phases} else target


def test_labels_become_dataset_step_segments(tmp_path: Path):
    frames = [("LPIL", "Id_Illiac_Vein_Artery")] * 4 + [
        ("Retzius_Space", "Prevessical_Dissection")
    ] * 3
    segments, report = g.import_grasp_steps(
        annotation_file(tmp_path / "a.json", frames), "CASE001", "grasp-01"
    )
    assert [s.step_id for s in segments] == [
        first_target("Id_Illiac_Vein_Artery"),
        first_target("Prevessical_Dissection"),
    ]
    expected = [(22 / 45, 4 + 22 / 45), (4 + 22 / 45, 7 + 22 / 45)]
    for segment, (t_start, t_end) in zip(segments, expected, strict=True):
        assert segment.t_start == pytest.approx(t_start, abs=1e-6)
        assert segment.t_end == pytest.approx(t_end, abs=1e-6)
    for s in segments:
        assert s.track is StepTrack.DATASET and s.confidence == 1.0
        assert s.provenance.trust_label is TrustLabel.DATASET_ANNOTATION
        assert s.id.startswith("grasp-01.s")
    assert sum(report.seconds_by_step.values()) == pytest.approx(7.0)


def test_idle_is_a_gap_and_a_pause_inside_a_step_is_bridged(tmp_path: Path):
    lnd, idle = ("LPIL", "Id_Illiac_Vein_Artery"), ("Idle", "Idle")
    retzius = ("Retzius_Space", "Prevessical_Dissection")
    frames = [idle] * 2 + [lnd] * 3 + [idle] * 4 + [lnd] * 2 + [idle] * 2 + [retzius] * 2
    segments, report = g.import_grasp_steps(
        annotation_file(tmp_path / "a.json", frames, fps=1), "CASE001", "c"
    )
    assert [(s.step_id, s.t_start, s.t_end) for s in segments] == [
        (first_target("Id_Illiac_Vein_Artery"), 22.0 + 2, 22.0 + 11),  # bridged over the pause
        (first_target("Prevessical_Dissection"), 22.0 + 13, 22.0 + 15),  # a gap at the change
    ]
    assert report.idle_seconds == 8.0


def test_generic_steps_follow_their_grasp_phase_and_by_phase_overrides(tmp_path: Path):
    # A generic step (`maps_to: phase`) and a by_phase override both resolve by the GraSP phase.
    generic = next(
        label for label in XWALK.steps if label.maps_to == "phase" and not label.by_phase
    )
    override = next(label for label in XWALK.steps if label.by_phase)
    phase_id, targets = next(iter(override.by_phase.items()))
    phase_code = XWALK.phases[phase_id].code
    frames = [(phase_code, override.code)] * 2 + [(phase_code, generic.code)] * 2
    segments, _ = g.import_grasp_steps(
        annotation_file(tmp_path / "a.json", frames, fps=1), "CASE001", "c"
    )
    expanded = [
        s.id
        for t in targets
        for s in (BOOK.phase(t).steps if t.count(".") == 1 else [BOOK.step(t)])
    ]
    assert segments[0].step_id == expanded[0]
    phase_targets = XWALK.phases[phase_id].maps_to
    phase_steps = {
        s.id
        for t in phase_targets
        for s in (BOOK.phase(t).steps if t.count(".") == 1 else [BOOK.step(t)])
    }
    assert segments[-1].step_id in phase_steps | {segments[0].step_id}


def test_the_file_must_match_the_crosswalk(tmp_path: Path):
    path = annotation_file(tmp_path / "a.json", [("LPIL", "Id_Illiac_Vein_Artery")] * 3)
    data = json.loads(path.read_text("utf-8"))
    data["steps_categories"][3]["description"] = "something else"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(g.GraspError, match="doesn't match the A1 GraSP crosswalk"):
        g.read_labels(path, "CASE001")


def test_missing_case_unreadable_file_and_fps(tmp_path: Path):
    path = annotation_file(tmp_path / "a.json", [("LPIL", "Id_Illiac_Vein_Artery")] * 3)
    with pytest.raises(g.GraspError, match="no keyframes for CASE999"):
        g.read_labels(path, "CASE999")
    with pytest.raises(g.GraspError, match="can't read"):
        g.read_labels(tmp_path / "missing.json", "CASE001")
    estimated = g.read_labels(path, "CASE001")  # 45 frames apart → 45 fps
    assert estimated.fps == 45.0 and estimated.times[1] - estimated.times[0] == pytest.approx(1.0)
    assert g.read_labels(path, "CASE001", video_fps=30.0).times[1] == pytest.approx(67 / 30)
