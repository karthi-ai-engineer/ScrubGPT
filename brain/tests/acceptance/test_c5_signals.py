"""C5 pixel signals (C5 stays open until its GPT check, D-067): #14 acceptance criteria 8-10
(Team Lead answer; plan §2.3 C5; brain/README.md "C5 pixel signals").

Expected behaviour, written from the spec before the code was opened:
- Input: a time-sorted series of `(t, image path)` frames (C1's, read with `load_frames`), each
  with a float timestamp. `detect_candidates(frames, **thresholds)` returns
  `Candidate(kind, t_start, t_end, score, status)`; `measure_frames` + `find_candidates` give the
  same result in two steps.
- The README's heuristics and default thresholds, which the synthetic frames are built from:
  - `bleeding`: >= 25 % blood pixels (`min_blood_ratio=0.25`); blood = red in 40..220 and at least
    2.5 x green and 2.5 x blue. Score = the blood fraction.
  - `out_of_body`: <= 25 % lit warm-tissue pixels (`min_out_of_body=0.75`); warm = brightest
    channel >= 40, saturation >= 0.2, hue 320°..70°. Score = 1 - warm fraction.
  - `idle`: consecutive frames with mean absolute difference <= 3 (`max_idle_change=3.0`); the run
    takes in the frame before its first still frame. Score = 1 - change / 3.
  - Spans: runs with at most one missed frame merged (`max_gap_frames=1`); t_start = first frame's
    t, t_end = min(last t + interval, next frame's t); spans shorter than `min_span_s=10` dropped.
- AC8: a run of mostly red / out-of-body / identical frames inside a varied normal series gives
  exactly one span of that kind, t_start and t_end within one sampling interval of the true run
  (the run's frames cover [t_first, t_last + interval)).
- AC9: a varied normal series gives no candidate; every threshold and the minimum span length can
  be passed as keywords and change the result as documented.
- AC10: each candidate carries its kind and a score (0..1, higher = stronger) and is clearly a
  candidate: `status == "candidate"` and no field claims confirmation.

Frames are made with Pillow from coarse random blocks (20 px) of documented colours, saved as PNG
in `tmp_path` (D-036). One test runs C1 on a synthetic FFmpeg video first (skips without FFmpeg).
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from scrubgpt_brain.engines.signals import detect_candidates, find_candidates, measure_frames

SIZE = (320, 180)
BLOCK = 20
GRID = (SIZE[0] // BLOCK, SIZE[1] // BLOCK)
N_BLOCKS = GRID[0] * GRID[1]
DT = 5.0  # C1's default spacing
T0 = 2.25  # non-integer float timestamps
KINDS = {"bleeding", "out_of_body", "idle"}


# ── synthetic frames from the README's colour rules ──────────────────────────


def _tissue(rng):
    """Lit pink/orange tissue: warm (hue ~330°..30°, saturation >= 0.3, bright), never blood
    (red < 2.5 x green)."""
    return rng.integers(190, 231), rng.integers(95, 131), rng.integers(85, 126)


def _blood(rng):
    """Dark saturated red: red 110..170, green and blue <= 35 (red >= 3 x each)."""
    return rng.integers(110, 171), rng.integers(5, 36), rng.integers(5, 36)


def _outside(rng):
    """Operating room: blue or green drapes, grey/white lights, dark: none of it warm or blood."""
    pick = rng.integers(0, 4)
    if pick == 0:
        return rng.integers(40, 71), rng.integers(80, 111), rng.integers(140, 181)
    if pick == 1:
        return rng.integers(50, 81), rng.integers(120, 151), rng.integers(90, 121)
    if pick == 2:
        v = int(rng.integers(200, 251))
        return v, v - int(rng.integers(0, 4)), v - int(rng.integers(0, 4))
    return rng.integers(0, 31), rng.integers(0, 31), rng.integers(0, 31)


def blocks(seed: int, base, special=None, fraction: float = 0.0, extra=()) -> Image.Image:
    """A frame of 20 px blocks: `fraction` of them from `special`, each `(maker, fraction)` of
    `extra` likewise, the rest from `base`."""
    rng = np.random.default_rng(seed)
    makers = [(special, fraction), *extra] if special else list(extra)
    order = rng.permutation(N_BLOCKS).tolist()
    assigned: dict[int, object] = {}
    for maker, share in makers:
        for k in order[len(assigned) : len(assigned) + round(share * N_BLOCKS)]:
            assigned[k] = maker
    grid = np.zeros((GRID[1], GRID[0], 3), np.uint8)
    for k in range(N_BLOCKS):
        grid[k // GRID[0], k % GRID[0]] = assigned.get(k, base)(rng)
    return Image.fromarray(grid, "RGB").resize(SIZE, Image.Resampling.NEAREST)


def tissue(seed):
    return blocks(seed, _tissue)


def bloody(seed, fraction=0.7):
    return blocks(seed, _tissue, _blood, fraction)


def outside(seed):
    return blocks(seed, _outside)


def partly_warm(seed, warm_fraction):
    return blocks(seed, _outside, _tissue, warm_fraction)


def shifted(image: Image.Image, k: int) -> Image.Image:
    return Image.fromarray(np.clip(np.asarray(image, np.int16) + k, 0, 255).astype(np.uint8))


def series(folder: Path, images: list[Image.Image], t0: float = T0, dt: float = DT):
    """Save the frames and return C1-style `(t, path)` pairs with float times."""
    folder.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, image in enumerate(images):
        path = folder / f"{i:03d}.png"
        image.save(path)
        frames.append((t0 + i * dt, path))
    return frames


def normal(n: int, seed: int = 1000) -> list[Image.Image]:
    return [tissue(seed + i) for i in range(n)]


def with_run(n, first, last, make, seed=1000):
    """A normal series of `n` frames with frames `first..last` replaced by `make(i)`."""
    images = normal(n, seed)
    for i in range(first, last + 1):
        images[i] = make(i)
    return images


def assert_span(candidate, frames, first, last, dt=DT):
    """#14 AC8 "Each span's `t_start` and `t_end` are within one sampling interval of the true
    run": the run's frames cover [t_first, t_last + interval)."""
    t_first, t_last = frames[first][0], frames[last][0]
    assert isinstance(candidate.t_start, float) and isinstance(candidate.t_end, float)
    assert candidate.t_start < candidate.t_end
    assert abs(candidate.t_start - t_first) <= dt, (candidate, t_first)
    assert abs(candidate.t_end - (t_last + dt)) <= dt, (candidate, t_last + dt)


def kinds(candidates):
    return [c.kind for c in candidates]


# ── AC8 ──────────────────────────────────────────────────────────────────────


def test_ac8_a_run_of_mostly_red_frames_gives_one_bleeding_span(tmp_path):
    """#14 AC8 "a run of mostly red frames gives one bleeding candidate span" (README: a frame
    with at least 25 % dark, saturated red pixels). 30 varied tissue frames, frames 10-17 70 %
    blood-red."""
    frames = series(tmp_path, with_run(30, 10, 17, lambda i: bloody(i)))
    candidates = detect_candidates(frames)
    assert kinds(candidates) == ["bleeding"], candidates
    assert_span(candidates[0], frames, 10, 17)


def test_ac8_a_run_of_out_of_body_frames_gives_one_out_of_body_span(tmp_path):
    """#14 AC8 "a run of out-of-body frames gives one out-of-body span" (README: at most 25 %
    lit warm-tissue pixels; drapes, lights, walls and a dark lens aren't warm). Frames 12-19 show
    the operating room."""
    frames = series(tmp_path, with_run(30, 12, 19, lambda i: outside(500 + i)))
    candidates = detect_candidates(frames)
    assert kinds(candidates) == ["out_of_body"], candidates
    assert_span(candidates[0], frames, 12, 19)


def test_ac8_a_run_of_identical_frames_gives_one_idle_span(tmp_path):
    """#14 AC8 "a run of identical frames gives one idle span" (README: consecutive frames
    differing by at most 3; the run takes in the frame before its first still frame). Frames 8-15
    are one tissue image."""
    still = tissue(77)
    frames = series(tmp_path, with_run(30, 8, 15, lambda i: still))
    candidates = detect_candidates(frames)
    assert kinds(candidates) == ["idle"], candidates
    assert_span(candidates[0], frames, 8, 15)


def test_ac8_three_runs_in_one_series_give_one_span_each(tmp_path):
    """#14 AC8, all three signals in one 50-frame series: bleeding 5-11, out of body 20-27, idle
    35-42; one span of each kind, sorted by time, each within one interval of its run."""
    still = tissue(78)
    images = normal(50)
    for i in range(5, 12):
        images[i] = bloody(i)
    for i in range(20, 28):
        images[i] = outside(600 + i)
    for i in range(35, 43):
        images[i] = still
    frames = series(tmp_path, images)
    candidates = detect_candidates(frames)
    assert kinds(candidates) == ["bleeding", "out_of_body", "idle"], candidates
    for candidate, (first, last) in zip(candidates, [(5, 11), (20, 27), (35, 42)], strict=True):
        assert_span(candidate, frames, first, last)


def test_ac8_one_missed_frame_inside_a_run_keeps_one_span(tmp_path):
    """README "Runs of one kind with at most one missed frame between them are merged
    (`max_gap_frames=1`)": a red run 10-19 with one normal frame at 14 is still one span."""
    images = with_run(30, 10, 19, lambda i: bloody(i))
    images[14] = tissue(4242)
    frames = series(tmp_path, images)
    candidates = detect_candidates(frames)
    assert kinds(candidates) == ["bleeding"], candidates
    assert_span(candidates[0], frames, 10, 19)


def test_ac8_a_non_default_sampling_interval(tmp_path):
    """#14 AC8 "within one sampling interval of the true run" with 2 s frames (README: `interval`
    is `interval_s` or else the median frame spacing): a bleeding run of frames 10-19 at 2 s."""
    frames = series(tmp_path, with_run(40, 10, 19, lambda i: bloody(i)), t0=0.4, dt=2.0)
    for interval in (None, 2.0):
        candidates = detect_candidates(frames, interval_s=interval)
        assert kinds(candidates) == ["bleeding"], candidates
        assert_span(candidates[0], frames, 10, 19, dt=2.0)


def _ffmpeg(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-y", "-v", "error", *args],
        capture_output=True,
        check=True,
        timeout=600,
    )


def test_ac8_bleeding_on_c1_frames_of_a_synthetic_video(media, tmp_path):
    """#14 AC8 end to end, on C1's own frames (README: `frames = load_frames(frames_dir)`, C1's
    `(t, path)` pairs from frames.json, sorted): a video of `testsrc2` for 30 s, a dark-red
    `color` source for 20 s and `testsrc2` again for 30 s. `load_frames` returns frames.json's
    frames in time order with float times, and exactly one bleeding candidate lies within one
    interval (5 s) of the red 30-50 s."""
    from scrubgpt_brain.pipeline.frames import load_frames, sample_frames

    video = tmp_path / "red.mp4"
    size, rate = "320x180", 5
    _ffmpeg(
        "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration=30",
        "-f", "lavfi", "-i", f"color=c=0x962010:size={size}:rate={rate}:duration=20",
        "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration=30",
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(video),
    )  # fmt: skip
    out = tmp_path / "frames"
    sample_frames(video, out)
    frames = load_frames(out)
    index = json.loads((out / "frames.json").read_text(encoding="utf-8"))
    entries = index["frames"] if isinstance(index, dict) else index
    assert [t for t, _ in frames] == sorted(float(e["t"]) for e in entries)
    assert all(isinstance(t, float) and Path(p).is_file() for t, p in frames)
    candidates = [c for c in detect_candidates(frames) if c.kind == "bleeding"]
    assert len(candidates) == 1, candidates
    assert abs(candidates[0].t_start - 30.0) <= DT and abs(candidates[0].t_end - 50.0) <= DT


# ── AC9 ──────────────────────────────────────────────────────────────────────


def test_ac9_a_varied_normal_series_gives_no_candidates(tmp_path):
    """#14 AC9 "A varied "normal" series gives no candidates": 40 tissue frames, and 40 frames
    with a little blood (10 %) and a little drape or light (15 %) in view."""
    plain = series(tmp_path / "plain", normal(40))
    assert detect_candidates(plain) == []
    mixed = [blocks(2000 + i, _tissue, _blood, 0.10, extra=[(_outside, 0.15)]) for i in range(40)]
    assert detect_candidates(series(tmp_path / "mixed", mixed)) == []


# label -> (frame maker for the run, keyword, value, kind, hits by default, hits with the value)
THRESHOLD_CASES = {
    "blood-35%-higher-ratio": (lambda i: bloody(i, 0.35), "min_blood_ratio", 0.5, "bleeding", 1, 0),
    "blood-15%-lower-ratio": (lambda i: bloody(i, 0.15), "min_blood_ratio", 0.1, "bleeding", 0, 1),
    "warm-40%-lower-score": (
        lambda i: partly_warm(i, 0.4), "min_out_of_body", 0.5, "out_of_body", 0, 1,
    ),
    "warm-5%-higher-score": (
        lambda i: partly_warm(i, 0.05), "min_out_of_body", 0.99, "out_of_body", 1, 0,
    ),
}  # fmt: skip


@pytest.mark.parametrize("label", list(THRESHOLD_CASES))
def test_ac9_signal_thresholds_can_be_passed(tmp_path, label):
    """#14 AC9 "Thresholds … can be passed as parameters" (README "every threshold is a
    keyword"): a run of 8 frames that the default threshold does (or doesn't) flag is not (or
    is) flagged with the threshold passed."""
    make, keyword, value, kind, default_hits, changed_hits = THRESHOLD_CASES[label]
    frames = series(tmp_path, with_run(30, 10, 17, make))
    default = [c for c in detect_candidates(frames) if c.kind == kind]
    changed = [c for c in detect_candidates(frames, **{keyword: value}) if c.kind == kind]
    assert len(default) == default_hits, default
    assert len(changed) == changed_hits, changed
    for candidate in default + changed:
        assert_span(candidate, frames, 10, 17)


@pytest.mark.parametrize(
    ("step", "value", "default_hits", "changed_hits"), [(6, 8.0, 0, 1), (2, 1.0, 1, 0)]
)
def test_ac9_idle_threshold_can_be_passed(tmp_path, step, value, default_hits, changed_hits):
    """#14 AC9 "Thresholds … can be passed" for idle (README `max_idle_change=3.0`, the mean
    absolute pixel difference on 0-255): frames 10-17 alternate one image and the same image
    `step` levels brighter."""
    base = tissue(91)
    frames = series(tmp_path, with_run(30, 10, 17, lambda i: shifted(base, step * (i % 2))))
    default = [c for c in detect_candidates(frames) if c.kind == "idle"]
    changed = [c for c in detect_candidates(frames, max_idle_change=value) if c.kind == "idle"]
    assert (len(default), len(changed)) == (default_hits, changed_hits), (default, changed)
    for candidate in default + changed:
        assert_span(candidate, frames, 10, 17)


def test_ac9_the_minimum_span_length_can_be_passed(tmp_path):
    """#14 AC9 "… and the minimum span length can be passed as parameters" (README "Spans shorter
    than `min_span_s=10` s (two C1 frames) are dropped"): one red frame (a 5 s span) is dropped by
    default and kept with `min_span_s=5`; a 3-frame run (15 s) is kept by default and dropped with
    `min_span_s=20`."""
    one = series(tmp_path / "one", with_run(20, 9, 9, lambda i: bloody(i)))
    assert detect_candidates(one) == []
    kept = detect_candidates(one, min_span_s=5)
    assert kinds(kept) == ["bleeding"] and abs(kept[0].t_start - one[9][0]) <= DT
    three = series(tmp_path / "three", with_run(20, 9, 11, lambda i: bloody(i)))
    assert kinds(detect_candidates(three)) == ["bleeding"]
    assert detect_candidates(three, min_span_s=20) == []


def test_ac9_the_merge_gap_can_be_passed(tmp_path):
    """README "Runs of one kind with at most one missed frame between them are merged
    (`max_gap_frames=1`)" as a keyword: with `max_gap_frames=0` a red run 10-19 broken at 14 gives
    two spans."""
    images = with_run(30, 10, 19, lambda i: bloody(i))
    images[14] = tissue(4243)
    frames = series(tmp_path, images)
    split = detect_candidates(frames, max_gap_frames=0)
    assert kinds(split) == ["bleeding", "bleeding"], split
    assert_span(split[0], frames, 10, 13)
    assert_span(split[1], frames, 15, 19)


def test_ac9_measuring_once_and_finding_many_times_agree(tmp_path):
    """README "`measure_frames(frames)` returns the per-frame measures, and
    `find_candidates(signals, …)` turns them into spans": the two steps give what
    `detect_candidates` gives, for the defaults and for changed thresholds."""
    still = tissue(79)
    images = normal(40)
    for i in range(5, 12):
        images[i] = bloody(i, 0.35)
    for i in range(20, 27):
        images[i] = outside(700 + i)
    for i in range(30, 36):
        images[i] = still
    frames = series(tmp_path, images)
    signals = measure_frames(frames)
    for options in ({}, {"min_blood_ratio": 0.5}, {"min_span_s": 40}, {"max_idle_change": 0.5}):
        assert find_candidates(signals, **options) == detect_candidates(frames, **options), options


# ── AC10 ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def three_kinds(tmp_path):
    still = tissue(80)
    images = normal(50)
    for i in range(5, 12):
        images[i] = bloody(i, 0.7)
    for i in range(20, 28):
        images[i] = outside(800 + i)
    for i in range(35, 43):
        images[i] = still
    return detect_candidates(series(tmp_path, images))


def test_ac10_each_candidate_has_a_kind_a_score_and_candidate_status(three_kinds):
    """#14 AC10 "Each candidate carries its signal kind and a score. It is clearly a *candidate*,
    not a confirmed event: no field claims confirmation." (README: `status="candidate"`, never a
    confirmed event; scores from 0 to 1.)"""
    assert {c.kind for c in three_kinds} == KINDS
    for candidate in three_kinds:
        assert candidate.kind in KINDS
        assert isinstance(candidate.score, float) and 0.0 <= candidate.score <= 1.0, candidate
        assert candidate.status == "candidate", candidate
        names = [f.name for f in dataclasses.fields(candidate)]
        claims = [
            n for n in names if any(w in n.lower() for w in ("confirm", "verif", "valid", "approv"))
        ]
        assert not claims, f"fields that claim confirmation: {claims}"
        flags = [n for n in names if getattr(candidate, n) is True]
        assert not flags, f"boolean fields set on a candidate: {flags}"


def test_ac10_scores_follow_the_documented_meaning(tmp_path, three_kinds):
    """README "Each score runs from 0 to 1 (higher = stronger)": bleeding = the blood fraction (a
    70 % red run scores about 0.7 and more than a 35 % one), out of body = 1 - warm fraction
    (about 1 for an operating-room view), idle = 1 - change / 3 (1 for identical frames)."""
    by_kind = {c.kind: c for c in three_kinds}
    assert 0.6 <= by_kind["bleeding"].score <= 0.9, by_kind["bleeding"]
    assert by_kind["out_of_body"].score >= 0.9, by_kind["out_of_body"]
    assert by_kind["idle"].score >= 0.99, by_kind["idle"]
    weaker = detect_candidates(
        series(tmp_path / "weaker", with_run(30, 10, 17, lambda i: bloody(i, 0.35)))
    )
    assert kinds(weaker) == ["bleeding"]
    assert weaker[0].score < by_kind["bleeding"].score


def test_ac10_candidates_are_internal_objects_not_files(tmp_path):
    """D-067 / #14 "The output is internal candidate spans" (README: a list of `Candidate`):
    detecting writes nothing into the frame folder."""
    folder = tmp_path / "frames"
    frames = series(folder, with_run(20, 5, 10, lambda i: bloody(i)))
    before = sorted(p.name for p in folder.iterdir())
    result = detect_candidates(frames)
    assert isinstance(result, list) and result
    assert sorted(p.name for p in folder.iterdir()) == before
