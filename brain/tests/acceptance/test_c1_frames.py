"""C1 Frame sampler: #12 acceptance criteria 5-7 (Team Lead answer; D-063; plan §2.3 C1).

Expected behaviour, written from the spec before the code was opened:
- AC5: at the default interval (5 s) a synthetic 30 s video gives frames at 0.0, 5.0, …, 25.0 s
  (±1 frame; nothing at 30.0, which is the end). Timestamps are floats, in seconds from the start
  of the video, and every frame decodes as an image. "At the timestamps" is also checked against
  the pixels: each frame matches the video frame at its time ±1 frame (`testsrc2` changes every
  frame: a moving band and a frame counter).
- AC6: a hard cut between two different test sources (`testsrc2` -> `smptebars`) at a known time
  (12.4 s, between interval frames) gives exactly one extra frame, within 1 s of the cut; a video
  with no cut (`testsrc2` alone, `smptebars` alone) gives no extra frame.
- AC7: a custom interval N gives frames at 0, N, 2N, … below the duration; the output is sorted by
  timestamp with no duplicate timestamps, also when a cut falls exactly on an interval frame (15.0
  s). A duplicate is two entries for the same video frame (timestamps less than one frame apart).
- D-063 / #12: C1 writes no case JSON file into the folder it is given.

Entry points (brain/README.md): `scrubgpt_brain.pipeline.frames.sample_frames(video, out_dir)`
returning `Frame(t, path, reason)`, and `scrubgpt-brain frames <video> <out_dir> [--interval N]`
writing JPEGs and `frames.json` (`{"t", "file", "reason": "interval" | "scene"}`, sorted by time).
All media is synthetic, made in `tmp_path` (D-036); every test here skips without FFmpeg (#12 AC8).
"""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import pytest

FPS = 25
ONE_FRAME_S = 1 / FPS
TOLERANCE_S = ONE_FRAME_S + 1e-6  # #12 AC5 "±1 frame"
SIZE = "320x240"
CUT_S = 12.4  # a frame boundary at 25 fps (frame 310), 2.4 s from the nearest interval frame
CUT_ON_INTERVAL_S = 15.0
SCENE_WINDOW_S = 1.0  # #12 AC6 "within 1 s of the cut"


def expected_interval_times(duration_s: float, interval_s: float) -> list[float]:
    """0, N, 2N, … strictly below the duration (the last video frame starts before it)."""
    return [k * interval_s for k in range(math.ceil(duration_s / interval_s)) if k * interval_s
            < duration_s - ONE_FRAME_S / 2]  # fmt: skip


def near(t: float, target: float) -> bool:
    return abs(t - target) <= TOLERANCE_S


@pytest.fixture(scope="module")
def videos(media, tmp_path_factory) -> SimpleNamespace:
    root = tmp_path_factory.mktemp("c1-videos")
    return SimpleNamespace(
        plain30=media.make_video(root / "plain30.mp4", 30, size=SIZE, rate=FPS),
        bars30=media.make_video(root / "bars30.mp4", 30, size=SIZE, rate=FPS, first="smptebars"),
        cut30=media.make_video(root / "cut30.mp4", 30, size=SIZE, rate=FPS, cut_at=CUT_S),
        cut15=media.make_video(
            root / "cut15.mp4", 30, size=SIZE, rate=FPS, cut_at=CUT_ON_INTERVAL_S
        ),
        plain20=media.make_video(root / "plain20.mp4", 20, size=SIZE, rate=FPS, audio=False),
    )


@pytest.fixture(scope="module")
def sample(videos, tmp_path_factory):
    """`sample_frames(video, out_dir, **kwargs)` once per (video, kwargs), memoised."""
    from scrubgpt_brain.pipeline.frames import sample_frames

    cache: dict[tuple, SimpleNamespace] = {}

    def run(name: str, **kwargs) -> SimpleNamespace:
        key = (name, tuple(sorted(kwargs.items())))
        if key not in cache:
            out = tmp_path_factory.mktemp(f"c1-{name}")
            frames = list(sample_frames(getattr(videos, name), out, **kwargs))
            cache[key] = SimpleNamespace(frames=frames, out=out, times=[f.t for f in frames])
        return cache[key]

    return run


def _assert_interval_frames(times: list[float], expected: list[float]) -> None:
    for target in expected:
        hits = [t for t in times if near(t, target)]
        assert len(hits) == 1, f"expected one frame at {target} s (±1 frame), got {hits}: {times}"


def _assert_sorted_unique(times: list[float], label: str) -> None:
    assert times == sorted(times), f"{label}: not sorted by timestamp: {times}"
    assert len(times) == len(set(times)), f"{label}: duplicate timestamps: {times}"
    gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
    assert all(g > ONE_FRAME_S / 2 for g in gaps), (
        f"{label}: two entries for the same video frame: {times}"
    )


def _extras(times: list[float], interval_s: float = 5.0) -> list[float]:
    """Timestamps that are not an interval frame (0, N, 2N, … ±1 frame)."""
    return [t for t in times if not near(t, round(t / interval_s) * interval_s)]


# ── AC5 ──────────────────────────────────────────────────────────────────────


def test_ac5_c1_default_interval_gives_frames_at_0_5_to_25_s(sample):
    """#12 AC5 "C1 at the default interval (5 s) on a synthetic 30 s video returns frames at the
    timestamps 0.0, 5.0, …, 25.0 (±1 frame)" (plan §2.3 C1 "One frame every N seconds (default
    5)"). Nothing at or past 30.0 s, and the interval frames are marked `interval` (README)."""
    run = sample("plain30")
    expected = expected_interval_times(30, 5)
    assert expected == [0, 5, 10, 15, 20, 25]
    _assert_interval_frames(run.times, expected)
    assert all(0 <= t < 30 - ONE_FRAME_S / 2 for t in run.times), f"out of range: {run.times}"
    interval = [f.t for f in run.frames if f.reason == "interval"]
    assert len(interval) == 6 and all(
        near(t, e) for t, e in zip(interval, expected, strict=True)
    ), f"`interval` frames: {interval}"


def test_ac5_c1_timestamps_are_float_seconds_from_the_start(sample):
    """#12 AC5 "Timestamps are floats in seconds from the start of the video": a `float` each,
    the first at 0.0 (the start), all within the 30 s duration."""
    run = sample("plain30")
    assert run.frames, "no frames"
    assert all(type(t) is float for t in run.times), [type(t).__name__ for t in run.times]
    assert near(run.times[0], 0.0), f"first frame at {run.times[0]} s, not at the start"
    assert all(0.0 <= t < 30.0 for t in run.times), run.times


def test_ac5_c1_each_frame_decodes_as_an_image(sample, media):
    """#12 AC5 "Each frame decodes as an image" (Pillow fully decodes every file); the files are
    in the caller-given folder (D-063) and are distinct."""
    run = sample("plain30")
    paths = [Path(f.path) for f in run.frames]
    assert len(set(paths)) == len(paths), f"two frames share a file: {paths}"
    for path in paths:
        assert path.is_file(), f"missing frame file {path}"
        assert path.resolve().is_relative_to(run.out.resolve()), f"{path} is outside {run.out}"
        media.decode_image(path)


def test_ac5_c1_frames_show_the_video_at_their_timestamps(sample, videos, media, tmp_path):
    """#12 AC5 "returns frames at the timestamps 0.0, 5.0, …, 25.0 (±1 frame)", checked on the
    pixels: each frame is closest to the video frame at its expected time ±1 frame, among the
    frames ±2 around it (FFmpeg decodes the references independently)."""
    run = sample("plain30")
    wrong = []
    for target in expected_interval_times(30, 5):
        frame = next(f for f in run.frames if near(f.t, target))
        k = round(target * FPS)
        candidates = [n for n in range(k - 2, k + 3) if n >= 0]
        refs = media.reference_frames(videos.plain30, candidates, tmp_path / f"ref_{k}")
        distances = {n: media.image_distance(Path(frame.path), p) for n, p in refs.items()}
        best = min(distances, key=distances.get)
        if abs(best - k) > 1:
            wrong.append(f"t={frame.t}: shows frame {best}, expected {k}±1 ({distances})")
    assert not wrong, "\n".join(wrong)


def test_ac5_c1_cli_default_interval_writes_the_frames(media, videos, tmp_path):
    """#12 AC5 through the console script `scrubgpt-brain frames <video> <out_dir>`: exit 0, and
    `frames.json` (brain/README.md) lists frames at 0.0 … 25.0 s (±1 frame), sorted, with float
    seconds, each file decoding as an image."""
    out = tmp_path / "frames"
    result = media.run_cli("frames", str(videos.plain30), str(out))
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stdout}\n{result.stderr}"
    entries = media.frames_index(out)
    times = [e["t"] for e in entries]
    assert all(isinstance(t, (int, float)) and not isinstance(t, bool) for t in times), times
    _assert_interval_frames(times, expected_interval_times(30, 5))
    assert len(times) == 6, f"expected only the 6 interval frames on a video without cuts: {times}"
    _assert_sorted_unique(times, "frames.json")
    for entry in entries:
        path = Path(entry["file"])
        media.decode_image(path if path.is_absolute() else out / path)


def test_ac5_c1_on_the_normalised_video(media, videos, tmp_path):
    """#12 AC5 on B3's output, as the pipeline runs it (brain/README.md "Run it on the normalised
    `video.mp4`"): frames at 0.0 … 25.0 s (±1 frame of the normalised video), float seconds from
    its start, each decoding."""
    from scrubgpt_brain.pipeline.frames import sample_frames

    case = tmp_path / "case"
    result = media.run_cli("normalize", str(videos.plain30), str(case))
    assert result.returncode == 0, result.stderr
    video = media.streams(media.ffprobe(case / "video.mp4"), "video")[0]
    num, den = (int(x) for x in video["avg_frame_rate"].split("/"))
    one_frame = den / num + 1e-6
    frames = sample_frames(case / "video.mp4", tmp_path / "frames")
    times = [f.t for f in frames]
    for target in expected_interval_times(30, 5):
        hits = [t for t in times if abs(t - target) <= one_frame]
        assert len(hits) == 1, f"expected one frame at {target} s, got {hits}: {times}"
    assert all(type(t) is float for t in times)
    for frame in frames:
        media.decode_image(Path(frame.path))


# ── AC6 ──────────────────────────────────────────────────────────────────────


def test_ac6_c1_hard_cut_gives_one_extra_frame_within_1_s(sample):
    """#12 AC6 "C1 adds extra frames at scene changes. A synthetic video with a hard cut between
    two different test sources at a known time gives one extra frame within 1 s of the cut"
    (plan §2.3 C1 "plus extra frames where the scene changes"; D-063 "a C1 without scene-change
    frames isn't done"). Cut: `testsrc2` -> `smptebars` at 12.4 s."""
    run = sample("cut30")
    _assert_interval_frames(run.times, expected_interval_times(30, 5))
    extras = _extras(run.times)
    assert len(extras) == 1, f"expected one extra frame, got {extras}: {run.times}"
    assert abs(extras[0] - CUT_S) <= SCENE_WINDOW_S, (
        f"extra frame at {extras[0]} s, the cut is at {CUT_S} s"
    )
    assert len(run.times) == 7, run.times
    scene = [f.t for f in run.frames if f.reason == "scene"]
    assert scene == extras, f"frames marked `scene` (README): {scene}, extra frames: {extras}"


@pytest.mark.parametrize("name", ["plain30", "bars30"], ids=["testsrc2", "smptebars"])
def test_ac6_c1_video_without_a_cut_gives_no_extra_frames(sample, name):
    """#12 AC6 "A video with no cut gives no extra frames": only the 6 interval frames, none
    marked `scene` (README)."""
    run = sample(name)
    assert _extras(run.times) == [], f"extra frames without a cut: {run.times}"
    assert len(run.times) == 6, run.times
    assert [f.reason for f in run.frames] == ["interval"] * 6, [f.reason for f in run.frames]


# ── AC7 ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "duration", "interval"),
    [("plain20", 20, 3), ("plain30", 30, 10), ("plain30", 30, 4)],
    ids=["N=3-on-20s", "N=10-on-30s", "N=4-on-30s"],
)
def test_ac7_c1_custom_interval_n(sample, name, duration, interval):
    """#12 AC7 "C1 takes a custom interval N": frames at 0, N, 2N, … below the duration (±1
    frame), nothing else on a video without cuts; sorted, no duplicate timestamps."""
    run = sample(name, interval_s=interval)
    expected = expected_interval_times(duration, interval)
    _assert_interval_frames(run.times, expected)
    assert len(run.times) == len(expected), f"expected {expected}, got {run.times}"
    _assert_sorted_unique(run.times, f"N={interval}")


def test_ac7_c1_cli_custom_interval(media, videos, tmp_path):
    """#12 AC7 through the console script: `scrubgpt-brain frames <video> <out_dir> --interval 7`
    (brain/README.md) on 30 s gives 0, 7, 14, 21, 28 s in `frames.json`, sorted, no duplicates."""
    out = tmp_path / "frames"
    result = media.run_cli("frames", str(videos.plain30), str(out), "--interval", "7")
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stdout}\n{result.stderr}"
    times = [e["t"] for e in media.frames_index(out)]
    expected = expected_interval_times(30, 7)
    assert expected == [0, 7, 14, 21, 28]
    _assert_interval_frames(times, expected)
    assert len(times) == len(expected), times
    _assert_sorted_unique(times, "frames.json --interval 7")


@pytest.mark.parametrize(
    ("name", "kwargs"),
    [
        ("plain30", {}),
        ("cut30", {}),
        ("cut15", {}),
        ("plain20", {"interval_s": 3}),
        ("cut30", {"interval_s": 2}),
    ],
    ids=["plain30", "cut-at-12.4", "cut-on-interval-15.0", "N=3", "cut-N=2"],
)
def test_ac7_c1_output_sorted_by_timestamp_without_duplicates(sample, name, kwargs):
    """#12 AC7 "… its output is sorted by timestamp with no duplicate timestamps", including a cut
    exactly on an interval frame (15.0 s; brain/README.md "A scene frame on the same video frame
    as an interval frame isn't added twice") and a cut between frames of a short interval."""
    run = sample(name, **kwargs)
    _assert_sorted_unique(run.times, name)
    paths = [Path(f.path).name for f in run.frames]
    assert len(paths) == len(set(paths)), f"duplicate frame files: {paths}"


def test_ac7_c1_cli_cut_on_an_interval_frame_has_no_duplicates(media, videos, tmp_path):
    """#12 AC7 for `frames.json` when the cut falls on the 15.0 s interval frame: sorted, no
    duplicate timestamps, every listed file present."""
    out = tmp_path / "frames"
    result = media.run_cli("frames", str(videos.cut15), str(out))
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    entries = media.frames_index(out)
    times = [e["t"] for e in entries]
    _assert_sorted_unique(times, "frames.json cut on 15.0 s")
    _assert_interval_frames(times, expected_interval_times(30, 5))
    for entry in entries:
        path = Path(entry["file"])
        assert (path if path.is_absolute() else out / path).is_file(), entry


# ── D-063 ────────────────────────────────────────────────────────────────────


def test_d063_c1_writes_no_case_json(sample, case_json_names):
    """D-063 / #12 "No reading or writing of `case.json`, `timeline.json`, …": C1's output folder
    holds none of the case JSON files of plan §4.2."""
    run = sample("cut30")
    written = {p.name for p in run.out.rglob("*.json")}
    assert not written & set(case_json_names), f"case JSON written: {written}"
