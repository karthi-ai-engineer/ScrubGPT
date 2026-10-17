"""Dev1's unit tests for A6, the step atlas (pipeline/atlas.py). Annotation files are synthetic,
built from the A1 crosswalk (no GraSP data is committed); videos are FFmpeg test sources."""

import json
from pathlib import Path

import pytest
from PIL import Image
from scrubgpt_brain import cli
from scrubgpt_brain.engines.rulebook import load_knowledge
from scrubgpt_brain.pipeline import atlas as a

BOOK = load_knowledge().rulebook
XWALK = BOOK.grasp
STEP_IDS = {label.code: label.grasp_id for label in XWALK.steps}
PHASE_IDS = {label.code: label.grasp_id for label in XWALK.phases}

IDLE = ("Idle", "Idle")
LND = ("LPIL", "Id_Illiac_Vein_Artery")  # exact: rarp.p02.s01
SUCTION = ("LPIL", "Suction")  # a generic act
RETZIUS = ("Retzius_Space", "Prevessical_Dissection")  # exact: rarp.p03.s01
CUT_BLADDER = ("Id_Bladder_Neck", "Cut_Bladder")  # ambiguous: rarp.p05.s01 or rarp.p06.s01
CUT_PROSTATE = ("Severing_Prostate_Urethra", "Cut_Prostate")  # exact: rarp.p10.s02
HOLD_PROSTATE = ("Severing_Prostate_Urethra", "Hold_Prostate")  # ambiguous: rarp.p10.*


def annotations(path: Path, cases: dict[str, list[tuple[tuple[str, str], int]]]) -> Path:
    """A 1 fps long-term file: per case, (label, seconds) blocks; frame_num = the second."""
    images, labels = [], []
    for case, blocks in cases.items():
        second = 0
        for (phase, step), length in blocks:
            for _ in range(length):
                image_id = len(images) + 1
                images.append({"id": image_id, "video_name": case, "frame_num": second})
                labels.append(
                    {
                        "id": image_id,
                        "image_id": image_id,
                        "phases": PHASE_IDS[phase],
                        "steps": STEP_IDS[step],
                    }
                )
                second += 1
    data = {
        "phases_categories": [
            {"id": x.grasp_id, "name": x.code, "description": x.name} for x in XWALK.phases
        ],
        "steps_categories": [
            {"id": x.grasp_id, "name": x.code, "description": x.name} for x in XWALK.steps
        ],
        "images": images,
        "annotations": labels,
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


CASES = {
    "CASE001": [(IDLE, 2), (LND, 30), (SUCTION, 5), (LND, 12), (RETZIUS, 8), (CUT_BLADDER, 20)],
    "CASE002": [(LND, 20), (RETZIUS, 15), (IDLE, 3)],
    "CASE004": [(LND, 50)],
}


def frames_of(index: a.AtlasIndex, step_id: str) -> list[tuple[str, float, str, str]]:
    return [(f.grasp_case, f.t, f.grasp_step, f.basis) for f in index.steps.get(step_id, ())]


def test_pick_prefers_other_cases_long_runs_and_run_middles(tmp_path: Path):
    index = a.pick_atlas(annotations(tmp_path / "train.json", CASES))
    # One frame per case first; each in the middle of that case's longest run of the step.
    assert frames_of(index, "rarp.p02.s01") == [
        ("CASE001", 16.0, "Id_Illiac_Vein_Artery", "exact"),  # run 2-32 (suction ends it)
        ("CASE002", 9.0, "Id_Illiac_Vein_Artery", "exact"),
        ("CASE004", 24.0, "Id_Illiac_Vein_Artery", "exact"),
    ]
    assert index.steps["rarp.p02.s01"][0].run == (2.0, 32.0)
    # CASE001's 8 s Retzius run is shorter than min_run_s: only CASE002's counts.
    assert frames_of(index, "rarp.p03.s01") == [
        ("CASE002", 27.0, "Prevessical_Dissection", "exact")
    ]
    # A label naming several steps fills an otherwise empty step, marked ambiguous.
    assert frames_of(index, "rarp.p05.s01") == [("CASE001", 66.0, "Cut_Bladder", "ambiguous")]
    assert set(index.missing) == {s.id for s in BOOK.steps()} - set(index.steps)
    assert "rarp.p06.s01" in index.missing
    # Generic acts are never atlas frames.
    assert all(f.grasp_step != "Suction" for fs in index.steps.values() for f in fs)
    assert index.cases == ("CASE001", "CASE002", "CASE004")
    assert index.review_status == "draft_pending_urologist_review"


def test_a_second_frame_of_a_case_needs_min_gap(tmp_path: Path):
    path = annotations(tmp_path / "train.json", CASES)
    four = a.pick_atlas(path, per_step=4)
    assert len(four.steps["rarp.p02.s01"]) == 3  # CASE001's 12 s run is 26 s from its frame
    close = a.pick_atlas(path, per_step=4, min_gap_s=10)
    assert ("CASE001", 42.0, "Id_Illiac_Vein_Artery", "exact") in frames_of(close, "rarp.p02.s01")
    assert len(a.pick_atlas(path, per_step=1).steps["rarp.p02.s01"]) == 1
    only = a.pick_atlas(path, cases=["CASE002"])
    assert only.cases == ("CASE002",)
    assert {f.grasp_case for fs in only.steps.values() for f in fs} == {"CASE002"}


def test_exact_runs_come_before_ambiguous_ones(tmp_path: Path):
    cases = {"CASE003": [(CUT_PROSTATE, 15), (HOLD_PROSTATE, 40)]}
    path = annotations(tmp_path / "train.json", cases)
    exact_only = a.pick_atlas(path)
    assert frames_of(exact_only, "rarp.p10.s02") == [("CASE003", 7.0, "Cut_Prostate", "exact")]
    # With no gap needed, the longer run that includes the ambiguous Hold_Prostate seconds fills
    # up the step, after the exact frame.
    filled = a.pick_atlas(path, min_gap_s=0)
    assert [f.basis for f in filled.steps["rarp.p10.s02"]] == ["exact", "ambiguous"]


def test_pick_is_deterministic_and_round_trips(tmp_path: Path):
    path = annotations(tmp_path / "train.json", CASES)
    first = a.write_index(a.pick_atlas(path), tmp_path / "out" / "rarp.yaml")
    text = first.read_bytes()
    a.write_index(a.pick_atlas(path), first)
    assert first.read_bytes() == text and b"\r\n" not in text
    assert not (first.parent / "rarp.yaml.part").exists()
    assert a.load_index(first) == a.pick_atlas(path)


def test_test_cases_and_unknown_cases_are_refused(tmp_path: Path):
    path = annotations(tmp_path / "a.json", {"CASE041": [(LND, 20)], "CASE001": [(LND, 20)]})
    with pytest.raises(a.AtlasError) as info:
        a.pick_atlas(path)
    assert info.value.problems == ["CASE041: a GraSP test case (kept for C7)"]
    with pytest.raises(a.AtlasError, match="CASE009: not in a.json"):
        a.pick_atlas(path, cases=["CASE001", "CASE009"])
    with pytest.raises(a.AtlasError, match="per_step"):
        a.pick_atlas(path, cases=["CASE001"], per_step=0)


def test_load_index_lists_every_problem(tmp_path: Path):
    path = a.write_index(
        a.pick_atlas(annotations(tmp_path / "t.json", CASES)), tmp_path / "rarp.yaml"
    )
    text = path.read_text("utf-8")
    text = text.replace("procedure_id: rarp", "procedure_id: other")
    text = text.replace("rarp.p03.s01:", "rarp.p99.s01:")
    text = text.replace("grasp_case: CASE004", "grasp_case: CASE050")
    text = text.replace("t: 9.0", "t: 500.0")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(a.AtlasError) as info:
        a.load_index(path)
    problems = "\n".join(info.value.problems)
    assert "procedure_id 'other'" in problems
    assert "rarp.p99.s01: not a rule-book step" in problems
    assert "CASE050 is a GraSP test case" in problems
    assert "t 500.0 must lie in its run" in problems


def write_small_index(tmp_path: Path) -> Path:
    index = a.AtlasIndex(
        procedure_id="rarp",
        source="test",
        cases=("CASE001", "CASE002"),
        per_step=3,
        min_run_s=1.0,
        min_gap_s=0.0,
        review_status=a.DRAFT,
        steps={
            "rarp.p02.s01": (
                a.AtlasFrame("CASE001", 1.5, (0.0, 3.0), "Id_Illiac_Vein_Artery", "exact"),
                a.AtlasFrame("CASE002", 2.0, (1.0, 3.0), "Id_Illiac_Vein_Artery", "exact"),
            ),
            "rarp.p03.s01": (
                a.AtlasFrame("CASE001", 3.5, (3.0, 4.0), "Prevessical_Dissection", "exact"),
            ),
        },
        missing=(),
    )
    return a.write_index(index, tmp_path / "index.yaml")


def test_extract_cuts_720p_frames_and_writes_the_manifest(media, tmp_path: Path):
    videos = tmp_path / "videos"
    (videos / "CASE002").mkdir(parents=True)
    media.video(videos / "CASE001.mp4", duration=5, audio=False)
    media.video(videos / "CASE002" / "video.mp4", duration=4, audio=False)  # a B3 folder
    data = tmp_path / "data"
    manifest = a.extract_atlas(videos, data, index=write_small_index(tmp_path))
    assert manifest == data / "atlas" / "rarp" / "atlas.json"
    images = a.load_atlas(data)
    assert [p.name for p in images["rarp.p02.s01"]] == [
        "CASE001_000001500.jpg",
        "CASE002_000002000.jpg",
    ]
    with Image.open(images["rarp.p03.s01"][0]) as image:
        assert image.size == (960, 720)  # 320x240, scaled to 720 px high
    body = json.loads(manifest.read_text("utf-8"))
    assert body["review_status"] == a.DRAFT and body["height"] == 720
    assert not list((data / "atlas").rglob("*.part*"))
    # A re-run keeps the frames already cut.
    before = images["rarp.p02.s01"][0].stat().st_mtime_ns
    a.extract_atlas(videos, data, index=tmp_path / "index.yaml")
    assert images["rarp.p02.s01"][0].stat().st_mtime_ns == before


def test_extract_checks_every_video_before_cutting(media, tmp_path: Path):
    videos = tmp_path / "videos"
    videos.mkdir()
    media.video(videos / "CASE001.mp4", duration=3, audio=False)  # too short for t = 3.5
    with pytest.raises(a.AtlasError) as info:
        a.extract_atlas(videos, tmp_path / "data", index=write_small_index(tmp_path))
    problems = "\n".join(info.value.problems)
    assert "CASE002: no video" in problems and "CASE001: a frame at 3.5 s" in problems
    assert not (tmp_path / "data").exists()


def test_cli_atlas(media, tmp_path: Path, monkeypatch):
    out: list[str] = []
    path = annotations(tmp_path / "train.json", CASES)
    index = tmp_path / "rarp.yaml"
    assert cli.main(["atlas", "pick", str(path), "--out", str(index)], out=out.append) == 0
    assert index.is_file() and "picked 5 frame(s) for 3 step(s) from 3 GraSP case(s)" in out[0]
    assert any(line.startswith("  no GraSP frames") for line in out)
    err: list[str] = []
    bad = annotations(tmp_path / "test.json", {"CASE047": [(LND, 20)]})
    assert cli.main(["atlas", "pick", str(bad), "--out", str(index)], err=err.append) == 1
    assert err == ["scrubgpt-brain: error: CASE047: a GraSP test case (kept for C7)"]
    videos = tmp_path / "videos"
    videos.mkdir()
    media.video(videos / "CASE001.mp4", duration=5, audio=False)
    media.video(videos / "CASE002.mp4", duration=4, audio=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    args = ["atlas", "frames", str(videos), "--index", str(write_small_index(tmp_path))]
    assert cli.main(args, out=out.append) == 0
    assert out[-1].startswith("cut 3 atlas image(s) for 2 step(s)")
