"""Dev1's unit tests for C5's pixel signals (plan §2.3): candidate spans on synthetic frames.

The frames are made here with numpy and Pillow: tissue-like frames that differ every time, and
runs of blood, drapes, a covered lens or one frame repeated. No video or real data is needed.
"""

import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from scrubgpt_brain.engines import signals as s
from scrubgpt_brain.pipeline import frames as c1
from scrubgpt_brain.pipeline.frames import frame_name

W, H = 320, 180
STEP = 5.0  # C1's default sampling interval
TISSUE = [(205, 115, 105), (215, 135, 95), (195, 120, 120), (225, 150, 110), (220, 185, 115)]
COOL = [(60, 140, 105), (55, 105, 165), (175, 180, 185)]  # green drape, blue drape, grey wall
BLOOD = (135, 14, 20)

_YY, _XX = np.mgrid[0:H, 0:W]


def _shading(rng: np.random.Generator, amount: float) -> np.ndarray:
    """Soft brightness changes (folds, curvature): a coarse random field, smoothly scaled up."""
    coarse = rng.normal(0, 1, (5, 8)).astype(np.float32)
    field = np.asarray(Image.fromarray(coarse).resize((W, H), Image.Resampling.BICUBIC))
    return (1 + amount * field)[..., None]


def _blob(rng: np.random.Generator, rx: float, ry: float) -> np.ndarray:
    """An ellipse mask at a random place near the middle."""
    cx, cy = rng.uniform(0.35, 0.65) * W, rng.uniform(0.35, 0.65) * H
    return ((_XX - cx) / rx) ** 2 + ((_YY - cy) / ry) ** 2 <= 1


def _image(pixels: np.ndarray, rng: np.random.Generator, noise: float = 10.0) -> Image.Image:
    pixels = pixels + rng.normal(0, noise, pixels.shape)
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))


def tissue_pixels(rng: np.random.Generator) -> np.ndarray:
    """Pink/orange tissue with shading, a grey instrument shaft, a thin vessel and a highlight."""
    pixels = np.array(TISSUE[rng.integers(len(TISSUE))], np.float32) * _shading(rng, 0.1)
    x = rng.integers(0, W - 40)
    pixels[:, x : x + 40] = (110, 112, 118)  # instrument: about 12 % of the view
    y = rng.integers(0, H - 3)
    pixels[y : y + 3] = (120, 25, 30)  # a vessel: a little real red, under 2 % of the view
    pixels[_blob(rng, 12, 8)] = (250, 248, 245)  # a specular highlight
    return pixels


def frame(kind: str, rng: np.random.Generator) -> Image.Image:
    """`n` normal tissue, `b` mostly blood, `o` outside (drapes, a wall, a light), `k` lens
    covered (near black); each call draws a new frame."""
    if kind == "n":
        return _image(tissue_pixels(rng), rng)
    if kind == "b":
        pixels = tissue_pixels(rng)
        pool = _blob(rng, 150, 90)  # about two thirds of the view
        pixels[pool] = (np.array(BLOOD, np.float32) * _shading(rng, 0.15))[pool]
        return _image(pixels, rng)
    if kind == "o":
        pixels = np.array(COOL[rng.integers(len(COOL))], np.float32) * _shading(rng, 0.2)
        pixels[_blob(rng, 40, 30)] = (252, 252, 248)  # a theatre light
        return _image(pixels, rng)
    if kind == "k":
        return _image(np.full((H, W, 3), 6, np.float32), rng, noise=3)
    raise ValueError(kind)


def series(pattern: str, seed: int = 0) -> list[tuple[float, Image.Image]]:
    """One frame per letter, STEP seconds apart (see `frame`); `=` repeats the frame before."""
    rng = np.random.default_rng(seed)
    images: list[Image.Image] = []
    for letter in pattern:
        images.append(images[-1].copy() if letter == "=" else frame(letter, rng))
    return [(i * STEP, image) for i, image in enumerate(images)]


def assert_span(candidate: s.Candidate, first: int, last: int) -> None:
    """The span is within one sampling interval of the true run (frames `first` … `last`)."""
    assert abs(candidate.t_start - first * STEP) <= STEP
    assert abs(candidate.t_end - last * STEP) <= STEP
    assert candidate.t_start < candidate.t_end


NORMAL = "n" * 8


def test_a_bleeding_run_gives_one_candidate():
    found = s.detect_candidates(series(NORMAL + "bbbbbb" + NORMAL))
    assert [c.kind for c in found] == ["bleeding"]
    assert_span(found[0], 8, 13)
    assert (found[0].t_start, found[0].t_end) == (40.0, 70.0)  # the documented span rule
    assert s.MIN_BLOOD_RATIO <= found[0].score <= 1


def test_a_run_outside_the_body_gives_one_candidate():
    found = s.detect_candidates(series(NORMAL + "oooooo" + NORMAL))
    assert [c.kind for c in found] == ["out_of_body"]
    assert_span(found[0], 8, 13)
    assert s.MIN_OUT_OF_BODY_SCORE <= found[0].score <= 1


def test_a_covered_lens_counts_as_out_of_body():
    found = s.detect_candidates(series(NORMAL + "kkkkk" + NORMAL))
    outside = [c for c in found if c.kind == "out_of_body"]
    assert len(outside) == 1 and outside[0].score > 0.95
    assert_span(outside[0], 8, 12)
    # A still black view also looks idle; that is fine for a candidate. Nothing looks like blood.
    assert {c.kind for c in found} <= {"out_of_body", "idle"}


def test_a_run_of_identical_frames_gives_one_idle_candidate():
    found = s.detect_candidates(series(NORMAL + "n=====" + NORMAL))
    assert [c.kind for c in found] == ["idle"]
    assert_span(found[0], 8, 13)
    assert found[0].score == 1.0  # identical frames: as still as it gets


def test_slight_sensor_noise_still_counts_as_idle():
    rng = np.random.default_rng(3)
    still = tissue_pixels(rng)
    frames = series(NORMAL)
    frames += [(t * STEP, _image(still, rng, noise=1.5)) for t in range(8, 14)]
    frames += [(t * STEP, frame("n", rng)) for t in range(14, 22)]
    found = s.detect_candidates(frames)
    assert [c.kind for c in found] == ["idle"]
    assert_span(found[0], 8, 13)
    assert 0 < found[0].score < 1


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_a_normal_series_gives_no_candidates(seed: int):
    frames = series("n" * 40, seed)
    assert s.detect_candidates(frames) == []
    # With margin, not just under the thresholds.
    measured = s.measure_frames(frames)
    assert max(m.blood_ratio for m in measured) < s.MIN_BLOOD_RATIO / 2
    assert max(m.out_of_body_score for m in measured) < s.MIN_OUT_OF_BODY_SCORE - 0.25
    assert min(m.change for m in measured[1:] if m.change is not None) > 2 * s.MAX_IDLE_CHANGE


def test_thresholds_and_the_minimum_span_are_parameters():
    short = series(NORMAL + "b" + NORMAL)
    assert s.detect_candidates(short) == []  # one frame (5 s) is under the default 10 s
    found = s.detect_candidates(short, min_span_s=5)
    assert [(c.kind, c.t_start, c.t_end) for c in found] == [("bleeding", 40.0, 45.0)]

    bleeding = series(NORMAL + "bbbbbb" + NORMAL)
    assert s.detect_candidates(bleeding, min_blood_ratio=0.99) == []
    assert s.detect_candidates(bleeding, min_span_s=60) == []
    assert s.detect_candidates(series(NORMAL + "oooooo" + NORMAL), min_out_of_body=1.01) == []
    idle = series(NORMAL + "n=====" + NORMAL)
    assert [c.kind for c in s.detect_candidates(idle, max_idle_change=0)] == ["idle"]
    found = s.detect_candidates(series("n" * 20), max_idle_change=200)
    assert [(c.kind, c.t_start, c.t_end) for c in found] == [("idle", 0.0, 100.0)]


def test_runs_one_frame_apart_are_merged_unless_asked_not_to():
    frames = series(NORMAL + "bbb" + "n" + "bbb" + NORMAL)
    found = s.detect_candidates(frames)
    assert [(c.kind, c.t_start, c.t_end) for c in found] == [("bleeding", 40.0, 75.0)]
    found = s.detect_candidates(frames, max_gap_frames=0)
    assert [(c.kind, c.t_start, c.t_end) for c in found] == [
        ("bleeding", 40.0, 55.0),
        ("bleeding", 60.0, 75.0),
    ]
    # Two frames apart: two candidates.
    found = s.detect_candidates(series(NORMAL + "bbb" + "nn" + "bbb" + NORMAL))
    assert [c.t_start for c in found] == [40.0, 65.0]


def test_candidates_are_sorted_have_kind_and_score_and_claim_nothing():
    pattern = NORMAL + "bbbb" + NORMAL + "oooo" + NORMAL + "n===" + NORMAL
    found = s.detect_candidates(series(pattern))
    assert [c.kind for c in found] == ["bleeding", "out_of_body", "idle"]
    assert [c.t_start for c in found] == sorted(c.t_start for c in found)
    for candidate in found:
        assert candidate.status == "candidate"
        assert isinstance(candidate.score, float) and 0 < candidate.score <= 1
    assert [f.name for f in dataclasses.fields(s.Candidate)] == [
        "kind",
        "t_start",
        "t_end",
        "score",
        "status",
    ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        found[0].score = 1.0  # type: ignore[misc]


def _signals(times: list[float], bleeding: set[float]) -> list[s.FrameSignals]:
    return [
        s.FrameSignals(t, 0.6 if t in bleeding else 0.0, 0.9, 0.0, None if i == 0 else 50.0)
        for i, t in enumerate(times)
    ]


def test_the_span_rule_with_irregular_frames():
    # A C1 scene frame at 12.3 s: a run ends at the next frame, not a whole interval later.
    times = [0.0, 5.0, 10.0, 12.3, 15.0, 20.0, 25.0]
    found = s.find_candidates(_signals(times, {10.0, 12.3}), min_span_s=0)
    assert [(c.t_start, c.t_end) for c in found] == [(10.0, 15.0)]
    # A run on the last frame ends one interval (the median spacing, 5 s here) after it.
    found = s.find_candidates(_signals(times, {25.0}), min_span_s=0)
    assert [(c.t_start, c.t_end) for c in found] == [(25.0, 30.0)]
    found = s.find_candidates(_signals(times, {25.0}), min_span_s=0, interval_s=2)
    assert [(c.t_start, c.t_end) for c in found] == [(25.0, 27.0)]
    found = s.find_candidates(_signals([7.0], {7.0}), min_span_s=0)
    assert [(c.t_start, c.t_end) for c in found] == [(7.0, 12.0)]  # one frame: C1's 5 s


def test_c1_load_frames_reads_the_index(tmp_path: Path):
    frames = series(NORMAL + "bbbb" + NORMAL)
    for t, image in frames:
        image.save(tmp_path / frame_name(t), quality=90)
    entries = [{"t": t, "file": frame_name(t), "reason": "interval"} for t, _ in frames]
    index = {"interval_s": STEP, "scene_threshold": 0.3, "frames": entries[::-1]}
    (tmp_path / "frames.json").write_text(json.dumps(index), encoding="utf-8")

    loaded = c1.load_frames(tmp_path)
    assert loaded == [(t, tmp_path / frame_name(t)) for t, _ in frames]  # sorted by time
    found = s.detect_candidates(loaded)
    assert [c.kind for c in found] == ["bleeding"]
    assert_span(found[0], 8, 11)


def test_bad_input(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        c1.load_frames(tmp_path)
    (tmp_path / "frames.json").write_text('{"frames": [{"t": 0}]}', encoding="utf-8")
    with pytest.raises(ValueError, match="not a C1 frames index"):
        c1.load_frames(tmp_path)
    (tmp_path / "frames.json").write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not a C1 frames index"):
        c1.load_frames(tmp_path)

    assert s.detect_candidates([]) == []
    frames = series("nnn")
    with pytest.raises(ValueError, match="strictly increasing"):
        s.detect_candidates(frames[::-1])
    with pytest.raises(ValueError, match="strictly increasing"):
        s.detect_candidates([frames[0], frames[0]])
    for options in ({"min_span_s": -1}, {"max_gap_frames": -1}, {"interval_s": 0}):
        with pytest.raises(ValueError):
            s.detect_candidates(frames, **options)
    with pytest.raises(FileNotFoundError):
        s.detect_candidates([(0.0, tmp_path / "missing.jpg")])
