"""A6 Visual step atlas: criteria A6-1 to A6-5 of the T1 brief, round 3 at 14de8b5 (plan §2.1 A6,
§7; brain/CLAUDE.md rule 8; knowledge/README.md `atlas/rarp.yaml`; brain/README.md "A6 Step
atlas"; the `pipeline/atlas.py` docstring; the CLI docstring).

Expected behaviour, written from the spec before the code was opened:
- A6-1: `scrubgpt-brain atlas pick <file> [--out]` writes an index: per step at most `--per-step`
  frames (default 3), each with `grasp_case`, `t`, `run`, `grasp_step`, `basis` (`exact` or
  `ambiguous`); `missing` lists exactly the rule-book steps without a frame; `review_status:
  draft_pending_urologist_review`; `procedure_id` is the rule book's; LF line ends, and a re-run
  is byte-identical. (The default `--out` is the repo's `knowledge/atlas/rarp.yaml`, so every
  test passes `--out` into `tmp_path`.)
- A6-2: GraSP's test cases (CASE041, 047, 050, 051, 053) are refused (exit 1, the reason on
  stderr), also in a file that mixes train and test cases; `--cases` limits the pick, and a case
  the file lacks is refused.
- A6-3: exact keyframes first; ambiguous runs only fill a step that has too few frames; generic
  acts are never chosen; a frame is the middle keyframe of a run at least `--min-run` s long, and
  idle or another step ends a run; different cases first, longest run first; a second frame from
  one case is at least 60 s from its first.
- A6-4: `scrubgpt-brain atlas frames <videos> [<data_dir>] [--index]` cuts each frame from
  `<videos>/<CASE>.<video suffix>` or `<videos>/<CASE>/video.mp4` at `t`, 720 px high, into
  `<data_dir>/atlas/rarp/<step_id>/<CASE>_<ms, 9 digits>.jpg`, writes `atlas.json`, and
  `load_atlas(data_dir)` returns the images per step; a re-run keeps frames already cut; a missing
  video or a frame past a video's end is reported for every case before anything is cut (exit 1);
  an invalid index lists every problem; `DATA_DIR` is the default data folder.
- A6-5: the committed `knowledge/atlas/rarp.yaml` loads cleanly, its ids resolve in the rule
  book, it has no test case, and the README's summary of it matches the file.

Label files are synthetic, 1 fps (`frame_num` = the second), built from the loaded crosswalk;
videos are FFmpeg `testsrc2` clips (D-036). Steps and labels are found by their kind in the
crosswalk, never hard-coded.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from PIL import Image
from scrubgpt_brain.pipeline import atlas

TEST_CASES = ("CASE041", "CASE047", "CASE050", "CASE051", "CASE053")  # README, A6-2
DRAFT = "draft_pending_urologist_review"
FRAME_KEYS = {"grasp_case", "t", "run", "grasp_step", "basis"}
CASE_NAME_RE = re.compile(r"^(CASE\d{3})_(\d{9})\.jpg$")


# ── the synthetic scenario ───────────────────────────────────────────────────


class Scenario:
    """Seven train cases whose expected atlas follows from the README's rules.

    X, Y: steps with exact labels. Z: a step with an exact label that is also a later candidate
    of an ambiguous label L (so L resolves to Z by continuity). A: the first candidate of an
    ambiguous label LA that no exact label names. G: a step only a generic act reaches here.
    """

    def __init__(self, grasp) -> None:
        cw = grasp.cw
        self.cw = cw
        exact = cw.exact_steps()
        self.L = self.Z = None
        for g, candidates in cw.ambiguous():
            later = [c for c in candidates[1:] if c in exact]
            if later:
                self.L, self.Z = g, later[0]
                break
        self.LA = self.A = None
        for g, candidates in cw.ambiguous():
            if candidates[0] not in exact and candidates[0] != self.Z:
                self.LA, self.A = g, candidates[0]
                break
        assert self.Z and self.A, "the crosswalk lacks the label kinds this scenario needs"
        others = [s for s in exact if s not in (self.Z, self.A)]
        self.X, self.Y = others[0], others[1]
        used = {self.X, self.Y, self.Z, self.A}
        self.generic_phase, self.G = next(
            (p, s) for p, s in cw.single_target_phases() if s not in used
        )
        self.generic_step = cw.generic()[0]
        ex, idle = grasp.exact, grasp.idle
        L_phase = cw.a_phase_for(self.Z)
        LA_phase = cw.a_phase_for(self.A)
        X, Y, Z = self.X, self.Y, self.Z
        self.cases = {
            "CASE001": ex(X, 40) + idle(5) + ex(Y, 30) + idle(5)
            + [(self.generic_phase, self.generic_step)] * 50 + idle(2),
            "CASE002": ex(X, 20) + idle(3) + ex(Y, 12),
            "CASE003": ex(X, 8) + idle(2) + ex(Z, 12) + idle(2),
            "CASE004": ex(X, 100) + idle(10) + ex(X, 25),
            "CASE005": ex(X, 30) + idle(2) + ex(X, 30),
            "CASE006": [(LA_phase, self.LA)] * 30 + idle(2) + ex(Z, 3) + idle(2)
            + [(L_phase, self.L)] * 50,
            "CASE007": ex(X, 15) + ex(Y, 15) + ex(X, 15),
        }  # fmt: skip


@pytest.fixture(scope="module")
def scenario(grasp) -> Scenario:
    return Scenario(grasp)


@pytest.fixture(scope="module")
def labels_file(grasp, scenario, tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("a6") / "grasp_long-term_train.json"
    return grasp.write(path, scenario.cases)


def pick(path: Path, out: Path, **kw) -> dict:
    """`atlas.pick_atlas` + `write_index` into `out`, read back as YAML."""
    index = atlas.pick_atlas(path, **kw)
    atlas.write_index(index, out)
    return yaml.safe_load(out.read_text(encoding="utf-8"))


def frames_of(index: dict, step: str) -> list[dict]:
    return list((index.get("steps") or {}).get(step) or [])


def run_len(frame: dict) -> float:
    return frame["run"][1] - frame["run"][0]


def assert_middle(frame: dict) -> None:
    """README "the middle second of a run": `t` is a keyframe second in the run, at its middle
    (either middle keyframe of an even run)."""
    start, end = frame["run"]
    n = round(end - start)
    assert start <= frame["t"] < end, frame
    assert frame["t"] in (start + (n - 1) // 2, start + n // 2), frame


# ── A6-1 ─────────────────────────────────────────────────────────────────────


def test_a6_1_the_cli_writes_an_index_with_the_documented_fields(cli, labels_file, rulebook,
                                                                  tmp_path):  # fmt: skip
    """A6-1 "`atlas pick <file> [--out]` writes an index: per step at most `--per-step` frames
    (default 3), each with `grasp_case`, `t`, `run`, `grasp_step` and `basis` (`exact`/
    `ambiguous`); … `review_status: draft_pending_urologist_review`; `procedure_id` is the rule
    book's": exit 0, a result on stdout, nothing on stderr."""
    out = tmp_path / "index.yaml"
    result = cli.run("atlas", "pick", str(labels_file), "--out", str(out))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() and not result.stderr.strip(), (result.stdout, result.stderr)
    index = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert index["procedure_id"] == rulebook["id"]
    assert index["review_status"] == DRAFT
    assert index["per_step"] == 3
    codes = {c["code"] for c in rulebook["grasp"]["steps"]}
    assert index["steps"], "no frame picked"
    for step, frames in index["steps"].items():
        assert 1 <= len(frames) <= 3, (step, frames)
        for frame in frames:
            assert set(frame) == FRAME_KEYS, frame
            assert frame["basis"] in ("exact", "ambiguous"), frame
            assert frame["grasp_step"] in codes, frame
            assert isinstance(frame["t"], (int, float)) and len(frame["run"]) == 2


def test_a6_1_missing_lists_exactly_the_steps_without_a_frame(labels_file, rulebook, tmp_path):
    """A6-1 "`missing` lists exactly the rule-book steps with no frame"."""
    index = pick(labels_file, tmp_path / "i.yaml")
    steps = [s["id"] for p in rulebook["phases"] for s in p.get("steps") or []]
    picked = set(index["steps"])
    assert picked <= set(steps)
    assert len(index["missing"]) == len(set(index["missing"]))
    assert set(index["missing"]) == set(steps) - picked


@pytest.mark.parametrize("per_step", [1, 2])
def test_a6_1_per_step_caps_the_frames(cli, labels_file, tmp_path, per_step):
    """A6-1 "per step at most `--per-step` frames"."""
    out = tmp_path / "index.yaml"
    result = cli.run("atlas", "pick", str(labels_file), "--out", str(out), "--per-step",
                     str(per_step))  # fmt: skip
    assert result.returncode == 0, result.stderr
    index = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert index["per_step"] == per_step
    assert all(len(f) <= per_step for f in index["steps"].values())


def test_a6_1_lf_and_byte_identical_on_a_re_run(cli, labels_file, tmp_path):
    """A6-1 "LF line endings, byte-identical on a re-run" (README "The same labels always give
    the same index"): two runs into two files, and over the same file."""
    first, second = tmp_path / "a.yaml", tmp_path / "b.yaml"
    for out in (first, second, first):
        assert cli.run("atlas", "pick", str(labels_file), "--out", str(out)).returncode == 0
    data = first.read_bytes()
    assert data == second.read_bytes()
    assert b"\r" not in data and data.endswith(b"\n")


# ── A6-2 ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("case", TEST_CASES)
def test_a6_2_a_test_case_is_refused(cli, grasp, scenario, tmp_path, case):
    """A6-2 "GraSP's test cases (CASE041, 047, 050, 051, 053) are refused, with exit 1 and the
    reason on stderr" (README: "they are kept for C7's accuracy score"); no index is written."""
    path = grasp.write(tmp_path / "test.json", {case: scenario.cases["CASE001"]})
    out = tmp_path / "index.yaml"
    result = cli.run("atlas", "pick", str(path), "--out", str(out))
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert result.stderr.startswith("scrubgpt-brain: error:") and case in result.stderr
    assert not out.exists()


def test_a6_2_a_file_mixing_train_and_test_cases_is_refused(cli, grasp, scenario, tmp_path):
    """A6-2 "… this includes a file mixing train and test cases"."""
    cases = {"CASE001": scenario.cases["CASE001"], "CASE047": scenario.cases["CASE002"]}
    path = grasp.write(tmp_path / "mixed.json", cases)
    out = tmp_path / "index.yaml"
    result = cli.run("atlas", "pick", str(path), "--out", str(out))
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert "CASE047" in result.stderr
    assert not out.exists()
    with pytest.raises(atlas.AtlasError):
        atlas.pick_atlas(path)


def test_a6_2_cases_limits_the_pick(cli, labels_file, tmp_path):
    """A6-2 "`--cases` limits the pick": only those cases are listed and used."""
    out = tmp_path / "index.yaml"
    result = cli.run("atlas", "pick", str(labels_file), "--out", str(out), "--cases", "CASE002",
                     "CASE007")  # fmt: skip
    assert result.returncode == 0, result.stderr
    index = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert sorted(index["cases"]) == ["CASE002", "CASE007"]
    used = {f["grasp_case"] for frames in index["steps"].values() for f in frames}
    assert used and used <= {"CASE002", "CASE007"}, used


@pytest.mark.parametrize("cases", [["CASE009"], ["CASE001", "CASE009"], ["CASE050"]])
def test_a6_2_an_unknown_or_test_case_in_cases_is_refused(cli, labels_file, tmp_path, cases):
    """A6-2 "… and an unknown case is refused" (README "a case missing from the file"), as is a
    test case named in `--cases`: exit 1, the case on stderr, no index."""
    out = tmp_path / "index.yaml"
    result = cli.run("atlas", "pick", str(labels_file), "--out", str(out), "--cases", *cases)
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert cases[-1] in result.stderr
    assert not out.exists()


# ── A6-3 ─────────────────────────────────────────────────────────────────────


def test_a6_3_exact_frames_first_ambiguous_runs_only_fill_up(labels_file, scenario, tmp_path):
    """A6-3 "exact keyframes first; ambiguous runs only fill a step that has too few frames"
    (README "A label naming several steps (`ambiguous` …) only fills up a step with too few
    frames"). Z has one exact run (CASE003, 12 s) and a longer ambiguous run (CASE006, 50 s): with
    `per_step` 1 only the exact frame; with 3, the ambiguous run fills up (`basis: ambiguous`). A,
    reached only by an ambiguous label, gets an ambiguous frame."""
    one = pick(labels_file, tmp_path / "one.yaml", per_step=1)
    assert [(f["grasp_case"], f["basis"]) for f in frames_of(one, scenario.Z)] == [
        ("CASE003", "exact")
    ]
    three = pick(labels_file, tmp_path / "three.yaml")
    assert sorted((f["grasp_case"], f["basis"]) for f in frames_of(three, scenario.Z)) == [
        ("CASE003", "exact"),
        ("CASE006", "ambiguous"),
    ]
    assert [(f["grasp_case"], f["basis"]) for f in frames_of(three, scenario.A)] == [
        ("CASE006", "ambiguous")
    ]
    assert all(f["basis"] == "exact" for f in frames_of(three, scenario.X))


def test_a6_3_generic_acts_are_never_chosen(labels_file, scenario, tmp_path):
    """A6-3 "generic acts (suction, cutting) are never chosen": the step G, reached here only by
    a 50 s generic-act run (which B1 maps to G), has no frame and is listed as missing; no frame
    anywhere carries a generic act's code."""
    index = pick(labels_file, tmp_path / "i.yaml", per_step=10)
    assert frames_of(index, scenario.G) == []
    assert scenario.G in index["missing"]
    generic_codes = {scenario.cw.steps[g].code for g in scenario.cw.generic()}
    used = {f["grasp_step"] for frames in index["steps"].values() for f in frames}
    assert not used & generic_codes, used & generic_codes


def test_a6_3_each_frame_is_the_middle_of_a_long_enough_run(labels_file, scenario, tmp_path):
    """A6-3 "each frame is the middle keyframe of a run at least `--min-run` s long": every frame
    sits in the middle of its run, and the run is at least 10 s (the default); CASE003's 8 s run
    of X is never used."""
    index = pick(labels_file, tmp_path / "i.yaml", per_step=10)
    for frames in index["steps"].values():
        for frame in frames:
            assert_middle(frame)
            assert run_len(frame) >= 10, frame
    assert "CASE003" not in {f["grasp_case"] for f in frames_of(index, scenario.X)}


@pytest.mark.parametrize(("min_run", "expected"), [(25, 4), (41, 1)])
def test_a6_3_min_run_changes_which_runs_qualify(labels_file, scenario, tmp_path, min_run,
                                                 expected):  # fmt: skip
    """A6-3 with `--min-run`: X's runs are 100 and 25 s (CASE004), 40 (CASE001), 30 + 30
    (CASE005), 20 (CASE002), 15 + 15 (CASE007) and 8 (CASE003). At 25 s: CASE004, CASE001,
    CASE005, then CASE004's second run (more than 60 s away) = 4. At 41 s: only CASE004's 100 s
    run."""
    index = pick(labels_file, tmp_path / "i.yaml", per_step=10, min_run_s=min_run)
    frames = frames_of(index, scenario.X)
    assert len(frames) == expected, frames
    assert all(run_len(f) >= min_run for f in frames)


def test_a6_3_idle_or_another_step_ends_a_run(labels_file, scenario, tmp_path):
    """A6-3 "idle or another step ends a run": CASE005 is X 30 s, idle 2 s, X 30 s and CASE007 is
    X 15 s, Y 15 s, X 15 s; their X frames come from 30 s and 15 s runs, never one run across the
    idle or across Y."""
    index = pick(labels_file, tmp_path / "i.yaml", per_step=10)
    for frame in frames_of(index, scenario.X):
        if frame["grasp_case"] == "CASE005":
            assert run_len(frame) == 30, frame
        if frame["grasp_case"] == "CASE007":
            assert run_len(frame) == 15, frame


def test_a6_3_different_cases_first_longest_run_first(labels_file, scenario, tmp_path):
    """A6-3 "different cases first, the longest run first": with 3 frames, X takes the longest
    run of each of the three cases with the longest runs (CASE004 100 s, CASE001 40 s, CASE005 30
    s), not a second run of CASE004 (25 s, longer than CASE002's 20 s)."""
    index = pick(labels_file, tmp_path / "i.yaml")
    frames = frames_of(index, scenario.X)
    assert sorted(f["grasp_case"] for f in frames) == ["CASE001", "CASE004", "CASE005"]
    by_case = {f["grasp_case"]: f for f in frames}
    assert run_len(by_case["CASE004"]) == 100 and run_len(by_case["CASE001"]) == 40


def test_a6_3_a_second_frame_from_one_case_is_60_s_away(labels_file, scenario, tmp_path):
    """A6-3 "a second frame from one case is at least 60 s from its first" (README "a second
    frame from one case must be at least 60 s from its first"): with room for 10, X takes one
    frame from each of its 5 cases with a long enough run, plus CASE004's second run (72 s away);
    CASE005's and CASE007's second runs (32 s and 30 s away) are not used."""
    index = pick(labels_file, tmp_path / "i.yaml", per_step=10)
    frames = frames_of(index, scenario.X)
    per_case: dict[str, list[float]] = {}
    for frame in frames:
        per_case.setdefault(frame["grasp_case"], []).append(frame["t"])
    assert {c: len(t) for c, t in per_case.items()} == {
        "CASE004": 2, "CASE001": 1, "CASE005": 1, "CASE002": 1, "CASE007": 1,
    }  # fmt: skip
    first, second = sorted(per_case["CASE004"])
    assert second - first >= 60


# ── A6-4 (FFmpeg) ────────────────────────────────────────────────────────────

VIDEO_S = 25.0
RATE = 2


@pytest.fixture(scope="module")
def videos(media, tmp_path_factory) -> Path:
    """Three 25 s `testsrc2` clips in the three documented layouts: `<CASE>.mp4`, another suffix
    (`<CASE>.mkv`) and a B3 folder (`<CASE>/video.mp4`)."""
    folder = tmp_path_factory.mktemp("videos")
    kw = {"size": "320x180", "rate": RATE, "audio": False}
    media.make_video(folder / "CASE001.mp4", VIDEO_S, **kw)
    media.make_video(folder / "CASE002.mkv", VIDEO_S, **kw)
    media.make_video(folder / "CASE003" / "video.mp4", VIDEO_S, **kw)
    return folder


def write_index(path: Path, rulebook: dict, steps: dict, *, procedure_id=None, cases=None):
    """An atlas index in the committed file's format, with `missing` = every other step."""
    all_steps = [s["id"] for p in rulebook["phases"] for s in p.get("steps") or []]
    data = {
        "procedure_id": procedure_id or rulebook["id"],
        "source": "t1_synthetic.json",
        "cases": cases or sorted({f["grasp_case"] for fr in steps.values() for f in fr}),
        "per_step": 3, "min_run_s": 10.0, "min_gap_s": 60.0, "review_status": DRAFT,
        "steps": steps,
        "missing": [s for s in all_steps if s not in steps],
    }  # fmt: skip
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def frame(case, t, run, code, basis="exact"):
    return {"grasp_case": case, "t": t, "run": list(run), "grasp_step": code, "basis": basis}


@pytest.fixture
def index_file(rulebook, scenario, tmp_path) -> Path:
    cw = scenario.cw
    code_x = cw.steps[cw.label_for(scenario.X)].code
    code_y = cw.steps[cw.label_for(scenario.Y)].code
    steps = {
        scenario.X: [frame("CASE001", 12.0, (5.0, 20.0), code_x),
                     frame("CASE002", 7.0, (2.0, 14.0), code_x)],
        scenario.Y: [frame("CASE003", 15.0, (10.0, 21.0), code_y)],
    }  # fmt: skip
    return write_index(tmp_path / "index.yaml", rulebook, steps)


def expected_files(scenario) -> dict[str, list[str]]:
    return {
        scenario.X: ["CASE001_000012000.jpg", "CASE002_000007000.jpg"],
        scenario.Y: ["CASE003_000015000.jpg"],
    }


def test_a6_4_frames_are_cut_into_the_data_folder(media, videos, index_file, scenario,
                                                  rulebook, tmp_path):  # fmt: skip
    """A6-4 "cuts each frame from `<videos>/<CASE>.mp4` (or another video suffix) or
    `<videos>/<CASE>/video.mp4`, at `t`, scaled to 720 px high, into
    `<data_dir>/atlas/rarp/<step_id>/<CASE>_<ms 9 digits>.jpg`; writes `atlas.json`, and
    `load_atlas(data_dir)` returns the images per step" (CLI: exit 0, result on stdout)."""
    data = tmp_path / "data"
    result = media.run_cli("atlas", "frames", str(videos), str(data), "--index", str(index_file))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() and not result.stderr.strip()
    folder = data / "atlas" / rulebook["id"]
    assert (folder / "atlas.json").is_file()
    images = atlas.load_atlas(data)
    want = expected_files(scenario)
    assert {s: sorted(p.name for p in paths) for s, paths in images.items()} == want
    for step, names in want.items():
        for name in names:
            path = folder / step / name
            assert path.is_file()
            with Image.open(path) as image:
                assert image.format == "JPEG" and image.size[1] == 720, (name, image.size)
    jpgs = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*.jpg"))
    assert jpgs == sorted(f"{s}/{n}" for s, names in want.items() for n in names)


def test_a6_4_each_image_is_the_video_frame_at_t(media, videos, index_file, scenario, tmp_path):
    """A6-4 "… at `t`": each image looks like the video's frame at `t` (decoded by FFmpeg),
    more than like the frame 6 s away (`testsrc2` changes over time)."""
    data = tmp_path / "data"
    atlas.extract_atlas(videos, data, index=index_file)
    images = {p.name: p for paths in atlas.load_atlas(data).values() for p in paths}
    sources = {"CASE001": videos / "CASE001.mp4", "CASE002": videos / "CASE002.mkv",
               "CASE003": videos / "CASE003" / "video.mp4"}  # fmt: skip
    for name, path in images.items():
        case, ms = CASE_NAME_RE.match(name).groups()
        t = int(ms) / 1000
        other = t + 6 if t + 6 < VIDEO_S else t - 6
        refs = media.reference_frames(
            sources[case], [round(t * RATE), round(other * RATE)], tmp_path / f"ref_{case}"
        )
        near = media.image_distance(path, refs[round(t * RATE)])
        far = media.image_distance(path, refs[round(other * RATE)])
        assert near < far, (name, near, far)


def test_a6_4_a_re_run_keeps_frames_already_cut(media, videos, index_file, scenario, tmp_path):
    """A6-4 "a re-run keeps frames already cut" (README "a re-run only cuts what is missing"):
    after one image is deleted, a re-run cuts it again and leaves the others untouched."""
    data = tmp_path / "data"
    atlas.extract_atlas(videos, data, index=index_file)
    paths = [p for ps in atlas.load_atlas(data).values() for p in ps]
    before = {p: p.stat().st_mtime_ns for p in paths}
    paths[0].unlink()
    atlas.extract_atlas(videos, data, index=index_file)
    assert paths[0].is_file()
    for path in paths[1:]:
        assert path.stat().st_mtime_ns == before[path], path


def test_a6_4_missing_videos_and_frames_past_the_end_are_reported_first(
    media, videos, rulebook, scenario, tmp_path
):
    """A6-4 "a missing video, or a frame past a video's end, is reported for every case
    **before anything is cut** (exit 1)": CASE001 is fine, CASE009 has no video and CASE003's
    frame is at 40 s of a 25 s video; both problems are named and no image or manifest is
    written."""
    code = scenario.cw.steps[scenario.cw.label_for(scenario.X)].code
    steps = {scenario.X: [frame("CASE001", 12.0, (5.0, 20.0), code),
                          frame("CASE009", 12.0, (5.0, 20.0), code),
                          frame("CASE003", 40.0, (35.0, 46.0), code)]}  # fmt: skip
    index = write_index(tmp_path / "index.yaml", rulebook, steps)
    data = tmp_path / "data"
    result = media.run_cli("atlas", "frames", str(videos), str(data), "--index", str(index))
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert result.stderr.startswith("scrubgpt-brain: error:")
    assert "CASE009" in result.stderr and "CASE003" in result.stderr, result.stderr
    assert not list(data.rglob("*.jpg")) and not list(data.rglob("atlas.json"))
    with pytest.raises(atlas.AtlasError) as caught:
        atlas.extract_atlas(videos, data, index=index)
    assert len(caught.value.problems) >= 2, caught.value.problems


def test_a6_4_an_invalid_index_lists_every_problem(rulebook, scenario, tmp_path):
    """A6-4 "an invalid index (an unknown step, a test case, `t` outside its run, a wrong
    `procedure_id`) lists every problem": one `AtlasError` names all four."""
    code = scenario.cw.steps[scenario.cw.label_for(scenario.X)].code
    unknown = f"{rulebook['id']}.p{len(rulebook['phases']) + 1:02d}.s01"
    steps = {
        scenario.X: [frame("CASE001", 30.0, (5.0, 20.0), code),  # t outside its run
                     frame("CASE041", 12.0, (5.0, 20.0), code)],  # a test case
        unknown: [frame("CASE002", 12.0, (5.0, 20.0), code)],  # an unknown step
    }  # fmt: skip
    path = write_index(tmp_path / "bad.yaml", rulebook, steps, procedure_id="t1proc",
                       cases=["CASE001", "CASE002", "CASE041"])  # fmt: skip
    with pytest.raises(atlas.AtlasError) as caught:
        atlas.load_index(path)
    text = "\n".join(caught.value.problems)
    for needle in ("CASE041", unknown, "t1proc", "30"):
        assert needle in text, (needle, caught.value.problems)
    assert len(caught.value.problems) >= 4, caught.value.problems


def test_a6_4_an_invalid_index_is_exit_1_on_stderr(cli, rulebook, scenario, tmp_path):
    """A6-4 / CLI docstring "for `atlas` also … an invalid index": `atlas frames` with an index
    holding a test case exits 1 with the problem on stderr, before looking for videos."""
    code = scenario.cw.steps[scenario.cw.label_for(scenario.X)].code
    path = write_index(tmp_path / "bad.yaml", rulebook,
                       {scenario.X: [frame("CASE053", 12.0, (5.0, 20.0), code)]})  # fmt: skip
    result = cli.run("atlas", "frames", str(tmp_path / "no-videos"), str(tmp_path / "d"),
                     "--index", str(path))  # fmt: skip
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert result.stderr.startswith("scrubgpt-brain: error:") and "CASE053" in result.stderr


def test_a6_4_data_dir_is_the_default_data_folder(media, cli, videos, index_file, scenario,
                                                  tmp_path):  # fmt: skip
    """A6-4 "`DATA_DIR` is the default data folder, as for `reference`": without `<data_dir>`
    the images go under `$DATA_DIR/atlas/rarp/`, and nothing into the working folder."""
    data = tmp_path / "env-data"
    work = tmp_path / "work"
    work.mkdir()
    result = cli.run("atlas", "frames", str(videos), "--index", str(index_file),
                     env={"DATA_DIR": str(data)}, cwd=work)  # fmt: skip
    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in (data / "atlas").rglob("*.jpg")) == sorted(
        n for names in expected_files(scenario).values() for n in names
    )
    assert not list(work.rglob("*"))


def test_a6_4_no_data_folder_is_exit_1(cli, index_file, tmp_path):
    """A6-4 "as for `reference`": no `<data_dir>` and no `DATA_DIR` exits 1 naming `DATA_DIR`."""
    result = cli.run("atlas", "frames", str(tmp_path / "v"), "--index", str(index_file),
                     drop_env=("DATA_DIR",), cwd=tmp_path)  # fmt: skip
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert "DATA_DIR" in result.stderr


# ── A6-5 ─────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def committed(const) -> dict:
    return yaml.safe_load((const.knowledge / "atlas" / "rarp.yaml").read_text(encoding="utf-8"))


def test_a6_5_the_committed_index_loads_cleanly(const, committed, rulebook):
    """A6-5 "The committed `knowledge/atlas/rarp.yaml` loads cleanly. Its ids resolve in the rule
    book, it has no test case": `load_index` accepts it; every step id (picked or missing) is a
    rule-book step, each step once; no case or frame is a GraSP test case; draft status."""
    index = atlas.load_index(const.knowledge / "atlas" / "rarp.yaml")
    assert index.procedure_id == rulebook["id"] == committed["procedure_id"]
    steps = [s["id"] for p in rulebook["phases"] for s in p.get("steps") or []]
    picked, missing = list(committed["steps"]), list(committed["missing"])
    assert set(picked) <= set(steps) and set(missing) <= set(steps)
    assert not set(picked) & set(missing)
    assert sorted(picked + missing) == sorted(steps)
    cases = set(committed["cases"]) | {f["grasp_case"] for fr in committed["steps"].values()
                                      for f in fr}  # fmt: skip
    assert not cases & set(TEST_CASES), cases & set(TEST_CASES)
    assert committed["review_status"] == DRAFT
    codes = {c["code"] for c in rulebook["grasp"]["steps"]}
    for frames in committed["steps"].values():
        assert len(frames) <= committed["per_step"]
        for f in frames:
            assert set(f) == FRAME_KEYS and f["grasp_step"] in codes and f["basis"] in (
                "exact", "ambiguous")  # fmt: skip
            assert_middle(f)
            assert run_len(f) >= committed["min_run_s"], f


def test_a6_5_the_readme_summary_matches_the_file(const, committed):
    """A6-5 "the README's summary of it (36 frames, 13 steps, 32 exact, p09.s02 with one frame,
    the 7 missing steps) matches the file", read from brain/README.md's "Picked from GraSP's real
    train labels" paragraph."""
    readme = (const.repo_root / "brain" / "README.md").read_text(encoding="utf-8")
    para = next(line for line in readme.splitlines() if "Picked from GraSP's real train" in line)
    numbers = re.search(r"(\d+) frames for (\d+) of the (\d+) steps, (\d+) of them exact", para)
    frames_n, steps_n, total_n, exact_n = map(int, numbers.groups())
    one = re.search(r"(p\d{2}\.s\d{2}) has one frame", para).group(1)
    missing = re.findall(r"p\d{2}\.s\d{2}", para.split("Missing:", 1)[1].split("**", 1)[0])
    all_frames = [f for fr in committed["steps"].values() for f in fr]
    assert len(all_frames) == frames_n
    assert len(committed["steps"]) == steps_n
    assert len(committed["steps"]) + len(committed["missing"]) == total_n
    assert sum(f["basis"] == "exact" for f in all_frames) == exact_n
    assert len(committed["steps"][f"rarp.{one}"]) == 1
    assert sorted(committed["missing"]) == sorted(f"rarp.{m}" for m in missing)
    assert len(committed["cases"]) == int(re.search(r"\((\d+) cases\)", para).group(1))
