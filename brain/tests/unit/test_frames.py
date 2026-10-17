"""Dev1's unit tests for C1, the frame sampler (plan §2.3; D-063)."""

import json
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat
from scrubgpt_brain import cli
from scrubgpt_brain.engines.media import MediaError
from scrubgpt_brain.pipeline import frames as f


def test_interval_times_and_names():
    assert f.interval_times(30.0, 5.0) == [0.0, 5.0, 10.0, 15.0, 20.0, 25.0]
    assert f.interval_times(30.1, 5.0)[-1] == 30.0
    assert f.interval_times(4.0, 5.0) == [0.0]
    assert all(isinstance(t, float) for t in f.interval_times(21, 7))
    assert f.frame_name(25.0) == "000025000.jpg" and f.frame_name(12.3456) == "000012346.jpg"


def test_default_interval_on_a_30_s_video(media, tmp_path: Path):
    frames = f.sample_frames(media.video(tmp_path / "v.mp4", duration=30), tmp_path / "frames")
    assert [(fr.t, fr.reason) for fr in frames] == [
        (t, "interval") for t in (0.0, 5.0, 10.0, 15.0, 20.0, 25.0)
    ]
    for frame in frames:
        with Image.open(frame.path) as image:
            assert image.size == (320, 240)
    index = json.loads((tmp_path / "frames" / "frames.json").read_text("utf-8"))
    assert [item["t"] for item in index["frames"]] == [fr.t for fr in frames]


def _difference(a: Path, b: Path) -> float:
    with Image.open(a) as x, Image.open(b) as y:
        stat = ImageStat.Stat(ImageChops.difference(x.convert("RGB"), y.convert("RGB")))
        return sum(stat.mean) / 3


def test_a_hard_cut_adds_one_scene_frame(media, tmp_path: Path):
    frames = f.sample_frames(media.cut_video(tmp_path / "cut.mp4", cut_at=12), tmp_path / "frames")
    scene = [fr for fr in frames if fr.reason == "scene"]
    assert len(scene) == 1 and abs(scene[0].t - 12.0) <= 1.0
    by_time = {fr.t: fr.path for fr in frames}
    # The scene frame shows the new scene: like the frame after the cut, unlike the one before.
    assert _difference(scene[0].path, by_time[15.0]) < 5
    assert _difference(scene[0].path, by_time[10.0]) > 30


def test_no_cut_no_scene_frames_and_custom_interval(media, tmp_path: Path):
    video = media.video(tmp_path / "v.mp4", duration=30)
    frames = f.sample_frames(video, tmp_path / "frames", interval_s=7)
    assert [fr.t for fr in frames] == [0.0, 7.0, 14.0, 21.0, 28.0]
    assert {fr.reason for fr in frames} == {"interval"}
    times = [fr.t for fr in frames]
    assert times == sorted(times) and len(set(times)) == len(times)


def test_rerun_replaces_old_frames_only(media, tmp_path: Path):
    out = tmp_path / "frames"
    out.mkdir()
    (out / "keep.txt").write_text("mine", encoding="utf-8")
    video = media.video(tmp_path / "v.mp4", duration=12)
    f.sample_frames(video, out, interval_s=2)
    f.sample_frames(video, out, interval_s=5, scene_threshold=None)
    assert sorted(p.name for p in out.iterdir()) == [
        "000000000.jpg",
        "000005000.jpg",
        "000010000.jpg",
        "frames.json",
        "keep.txt",
    ]


def test_bad_input_and_cli(media, tmp_path: Path):
    with pytest.raises(MediaError):
        f.sample_frames(tmp_path / "missing.mp4", tmp_path / "frames")
    with pytest.raises(ValueError):
        f.sample_frames(media.video(tmp_path / "v.mp4"), tmp_path / "frames", interval_s=0)
    lines: list[str] = []
    assert (
        cli.main(["frames", str(tmp_path / "missing.mp4"), str(tmp_path / "o")], out=lines.append)
        == 1
    )
    lines.clear()
    video = media.video(tmp_path / "v.mp4", duration=10)
    assert (
        cli.main(["frames", str(video), str(tmp_path / "o"), "--no-scenes"], out=lines.append) == 0
    )
    assert "2 frame(s)" in lines[0] and "0 scene change" in lines[0]
