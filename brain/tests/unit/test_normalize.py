"""Dev1's unit tests for B3, the normaliser (plan §2.2; D-063)."""

import json
from pathlib import Path

import pytest
from PIL import Image
from scrubgpt_brain import cli
from scrubgpt_brain.engines.media import MediaError
from scrubgpt_brain.pipeline import normalize as n


def test_normalize_writes_720p_faststart_video_poster_and_thumbs(media, tmp_path: Path):
    source = media.video(tmp_path / "src.mp4", size="640x360", duration=23)
    result = n.normalize(source, tmp_path / "case")
    streams = media.streams(result.video)
    video = [s for s in streams if s["codec_type"] == "video"]
    audio = [s for s in streams if s["codec_type"] == "audio"]
    assert video[0]["codec_name"] == "h264"
    assert (video[0]["width"], video[0]["height"]) == (1280, 720)  # 16:9 kept, even width
    assert len(audio) == 1 and audio[0]["codec_name"] == "aac"
    assert (int(audio[0]["sample_rate"]), audio[0]["channels"]) == (16_000, 1)
    data = result.video.read_bytes()
    assert data.index(b"moov") < data.index(b"mdat")  # faststart
    assert abs(result.duration_s - 23) <= 0.5
    with Image.open(result.poster) as poster:
        assert poster.format == "JPEG" and poster.size == (1280, 720)
    index = json.loads((tmp_path / "case" / "thumbs" / "index.json").read_text("utf-8"))
    assert index["strips"] == ["strip_000.jpg"]  # thumbs at 0, 10, 20 s: one strip of 10
    assert [p.name for p in result.thumbs] == index["strips"]
    with Image.open(result.thumbs[0]) as strip:
        assert strip.height == n.THUMB_HEIGHT
    assert sorted(p.name for p in (tmp_path / "case").iterdir()) == [
        "poster.jpg",
        "thumbs",
        "video.mp4",
    ]


def test_odd_aspect_ratio_gives_an_even_width(media, tmp_path: Path):
    result = n.normalize(media.video(tmp_path / "src.mp4", size="250x240"), tmp_path / "case")
    assert result.height == 720 and result.width % 2 == 0
    assert abs(result.width / result.height - 250 / 240) < 0.01


def test_a_source_without_audio_gives_a_video_without_audio(media, tmp_path: Path):
    result = n.normalize(media.video(tmp_path / "src.mp4", audio=False), tmp_path / "case")
    assert not result.has_audio
    assert [s["codec_type"] for s in media.streams(result.video)] == ["video"]


@pytest.mark.parametrize("name", ["missing.mp4", "notes.txt", "still.png"])
def test_bad_input_raises_and_leaves_no_partial_video(media, tmp_path: Path, name: str):
    source = tmp_path / name
    if name == "notes.txt":
        source.write_text("not a video", encoding="utf-8")
    elif name == "still.png":
        Image.new("RGB", (64, 48), "red").save(source)
    out = tmp_path / "case"
    with pytest.raises(MediaError):
        n.normalize(source, out)
    assert not (out / "video.mp4").exists()
    assert not any(out.glob("*.part")) if out.exists() else True
    lines: list[str] = []
    assert cli.main(["normalize", str(source), str(out)], out=lines.append) == 1
    assert lines[0].startswith("scrubgpt-brain: error:")


def test_a_failed_run_keeps_the_previous_outputs(media, tmp_path: Path, monkeypatch):
    out = tmp_path / "case"
    first = n.normalize(media.video(tmp_path / "src.mp4"), out)
    before = first.video.read_bytes()

    def broken(*args, **kwargs):
        raise MediaError("simulated failure while writing thumbs")

    monkeypatch.setattr(n, "_thumb_strips", broken)
    with pytest.raises(MediaError):
        n.normalize(media.video(tmp_path / "src2.mp4", duration=3), out)
    assert first.video.read_bytes() == before
    assert not any(p.name.endswith(".part") for p in out.iterdir())


def test_cli_normalize(media, tmp_path: Path):
    lines: list[str] = []
    source = media.video(tmp_path / "src.mp4", duration=3)
    assert cli.main(["normalize", str(source), str(tmp_path / "case")], out=lines.append) == 0
    assert "960x720" in lines[0]  # 4:3 source
    assert "mono 16 kHz audio" in lines[0]
