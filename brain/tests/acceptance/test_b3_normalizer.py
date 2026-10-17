"""B3 Normaliser: #12 acceptance criteria 1-4 (Team Lead answer; D-063; plan §2.2 B3, §4.2).

Expected behaviour, written from the spec before the code was opened:
- AC1: a synthetic `testsrc2` input with a tone, at a size other than 720p, becomes `video.mp4`
  with H.264 video 720 px high (aspect ratio kept, even width), exactly one AAC audio stream,
  mono, 16 kHz, `moov` before `mdat` (faststart), and a duration within 0.5 s of the input.
  Sources here: 426x240 (up-scaled, not 16:9), 1920x1080 (down-scaled), 500x380 MPEG-4 + PCM in
  Matroska (must be re-encoded; the exact width 947.4 isn't even) and 360x640 portrait (still
  720 px high). Every source carries a STEREO 44.1/48 kHz tone, so B3 must resample and down-mix.
- AC2: `poster.jpg` is a JPEG Pillow decodes; `thumbs/` holds at least one image.
- AC3: an input without audio doesn't crash, and the module README documents what happens.
  brain/README.md says: "A source without audio gives a `video.mp4` without an audio track".
- AC4: a missing or non-video input is rejected with a clear error and a non-zero exit code from
  the console script, and no partial `video.mp4` is left. brain/README.md adds: a still image is a
  non-video input, the exit code is 1 with `scrubgpt-brain: error: …`, no new or half-written
  output is left in `<out_dir>`, earlier outputs stay as they were, and `normalize()` raises
  `MediaError`.
- D-063 / #12: B3 writes no case JSON file into the folder it is given.

Entry points (brain/README.md): `scrubgpt-brain normalize <source> <out_dir>` and
`scrubgpt_brain.pipeline.normalize.normalize(source, out_dir)`. All media is synthetic, made in
`tmp_path` (D-036); every test here skips when FFmpeg is missing (#12 AC8).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

DURATION_S = 12.0
TARGET_HEIGHT = 720  # #12 AC1, plan §2.2 B3 "720p"
AUDIO_RATE = "16000"  # #12 AC1 "mono, 16 kHz"
DURATION_TOLERANCE_S = 0.5  # #12 AC1
WIDTH_TOLERANCE_PX = 2  # the even-width rounding of 720 * w / h
README = Path(__file__).resolve().parents[2] / "README.md"  # brain/README.md

# (id, width, height, container): every one is "a size other than 720p" (#12 AC1).
SOURCES = [
    ("426x240-h264", 426, 240, "mp4"),
    ("1920x1080-h264", 1920, 1080, "mp4"),
    ("500x380-mpeg4-pcm-mkv", 500, 380, "mkv"),
    ("360x640-portrait", 360, 640, "mp4"),
]


def _make_source(media, path: Path, width: int, height: int, *, audio: bool = True) -> Path:
    if path.suffix == ".mkv":
        return media.make_video(
            path, DURATION_S, size=f"{width}x{height}", audio=audio, vcodec="mpeg4",
            acodec="pcm_s16le",
        )  # fmt: skip
    return media.make_video(path, DURATION_S, size=f"{width}x{height}", audio=audio)


@pytest.fixture(scope="module", params=SOURCES, ids=[s[0] for s in SOURCES])
def normalized(request, media, tmp_path_factory) -> SimpleNamespace:
    """One `scrubgpt-brain normalize` run per source size (shared by the AC1 and AC2 tests)."""
    label, width, height, container = request.param
    root = tmp_path_factory.mktemp(f"b3-{label}")
    source = _make_source(media, root / f"source.{container}", width, height)
    out = root / "case"
    result = media.run_cli("normalize", str(source), str(out))
    video = out / "video.mp4"
    return SimpleNamespace(
        label=label,
        width=width,
        height=height,
        source=source,
        source_probe=media.ffprobe(source),
        out=out,
        video=video,
        result=result,
        probe=media.ffprobe(video) if video.is_file() else None,
    )


def _require_output(run: SimpleNamespace) -> dict:
    assert run.result.returncode == 0, (
        f"`scrubgpt-brain normalize` exited {run.result.returncode}\n"
        f"stdout: {run.result.stdout}\nstderr: {run.result.stderr}"
    )
    assert run.video.is_file(), f"no video.mp4 in {run.out}"
    return run.probe


def _square_pixels(stream: dict) -> bool:
    return stream.get("sample_aspect_ratio") in (None, "1:1", "0:1")  # 0:1 = unset (square)


def _assert_720p_h264(media, probe: dict, width: int, height: int) -> None:
    videos = media.streams(probe, "video")
    assert len(videos) == 1, f"expected one video stream, got {len(videos)}"
    video = videos[0]
    assert video["codec_name"] == "h264", video["codec_name"]
    assert video["height"] == TARGET_HEIGHT, f"height {video['height']}, expected 720"
    assert video["width"] % 2 == 0, f"odd width {video['width']}"
    exact = TARGET_HEIGHT * width / height
    assert abs(video["width"] - exact) <= WIDTH_TOLERANCE_PX, (
        f"width {video['width']} doesn't keep the {width}x{height} aspect ratio "
        f"(720 * {width} / {height} = {exact:.2f})"
    )
    assert _square_pixels(video), f"non-square pixels: SAR {video.get('sample_aspect_ratio')}"


# ── AC1 ──────────────────────────────────────────────────────────────────────


def test_ac1_b3_cli_writes_video_mp4(normalized):
    """#12 AC1 "B3 turns a synthetic FFmpeg `testsrc2` input with an audio tone, at a size other
    than 720p, into `video.mp4`" (plan §4.2: `video.mp4`, the normalised video, B3)."""
    _require_output(normalized)


def test_ac1_b3_video_is_h264_720_high_aspect_kept_even_width(normalized, media):
    """#12 AC1 "ffprobe must show: H.264 video, 720 px high, with the aspect ratio kept and an
    even width" (plan §2.2 B3 "720p H.264")."""
    probe = _require_output(normalized)
    _assert_720p_h264(media, probe, normalized.width, normalized.height)


def test_ac1_b3_one_aac_audio_stream_mono_16khz(normalized, media):
    """#12 AC1 "one AAC audio stream, mono, 16 kHz" (plan §2.2 B3 "a 16 kHz mono audio track").
    The source track is stereo at 44.1 or 48 kHz (AAC or PCM), so it must be converted."""
    probe = _require_output(normalized)
    audios = media.streams(probe, "audio")
    assert len(audios) == 1, f"expected exactly one audio stream, got {len(audios)}"
    audio = audios[0]
    assert audio["codec_name"] == "aac", audio["codec_name"]
    assert audio["channels"] == 1, f"{audio['channels']} channels, expected mono"
    assert audio["sample_rate"] == AUDIO_RATE, f"{audio['sample_rate']} Hz, expected 16000"


def test_ac1_b3_audio_track_carries_the_source_tone(normalized, media):
    """#12 AC1 / plan §2.2 B3: the 16 kHz mono track is the source's audio, not a made-up silent
    track: the 440 Hz `sine` tone (about -18 dBFS peak) is still clearly audible."""
    _require_output(normalized)
    peak = media.max_volume_db(normalized.video)
    assert peak > -30.0, f"audio peak {peak} dB: the source tone is missing"


def test_ac1_b3_moov_before_mdat_faststart(normalized, media):
    """#12 AC1 "the `moov` atom before `mdat` (faststart)" (plan §2.2 B3 "faststart" MP4). Read
    from the file's top-level boxes."""
    _require_output(normalized)
    boxes = media.top_level_boxes(normalized.video)
    assert "moov" in boxes and "mdat" in boxes, f"top-level boxes: {boxes}"
    assert boxes.index("moov") < boxes.index("mdat"), f"moov after mdat (not faststart): {boxes}"


def test_ac1_b3_duration_within_half_a_second_of_the_input(normalized, media):
    """#12 AC1 "a duration within 0.5 s of the input" (container and video stream)."""
    probe = _require_output(normalized)
    source_s = float(normalized.source_probe["format"]["duration"])
    assert abs(source_s - DURATION_S) <= DURATION_TOLERANCE_S, "test source has the wrong length"
    output_s = float(probe["format"]["duration"])
    assert abs(output_s - source_s) <= DURATION_TOLERANCE_S, (
        f"video.mp4 lasts {output_s} s, the input {source_s} s"
    )
    video_s = media.streams(probe, "video")[0].get("duration")
    if video_s is not None:
        assert abs(float(video_s) - source_s) <= DURATION_TOLERANCE_S, (
            f"the video stream lasts {video_s} s, the input {source_s} s"
        )


def test_ac1_b3_python_api_writes_the_same_outputs(media, tmp_path):
    """#12 AC1/AC2 through the Python entry point `normalize(source, out_dir)` (brain/README.md):
    the same `video.mp4` (H.264, 720 px high, one AAC mono 16 kHz track, faststart), `poster.jpg`
    and `thumbs/` in the caller-given folder (D-063 "into a caller-given folder")."""
    from scrubgpt_brain.pipeline.normalize import normalize

    source = _make_source(media, tmp_path / "source.mp4", 640, 360)
    out = tmp_path / "given" / "folder"
    normalize(source, out)
    probe = media.ffprobe(out / "video.mp4")
    _assert_720p_h264(media, probe, 640, 360)
    audios = media.streams(probe, "audio")
    assert [(a["codec_name"], a["channels"], a["sample_rate"]) for a in audios] == [
        ("aac", 1, AUDIO_RATE)
    ]
    boxes = media.top_level_boxes(out / "video.mp4")
    assert boxes.index("moov") < boxes.index("mdat")
    assert media.decode_image(out / "poster.jpg")[0] == "JPEG"
    assert [p for p in (out / "thumbs").iterdir() if _is_image(p)], "no image in thumbs/"


# ── AC2 ──────────────────────────────────────────────────────────────────────


def _is_image(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with Image.open(path) as image:
            image.load()
    except Exception:  # noqa: BLE001 (any decode failure means "not an image")
        return False
    return True


def test_ac2_b3_poster_is_a_decodable_jpeg(normalized, media):
    """#12 AC2 "B3 writes `poster.jpg`, a decodable JPEG (Pillow opens it)" (plan §4.2
    `poster.jpg`, Required)."""
    _require_output(normalized)
    poster = normalized.out / "poster.jpg"
    assert poster.is_file(), f"no poster.jpg in {normalized.out}"
    image_format, (width, height) = media.decode_image(poster)
    assert image_format == "JPEG", f"poster.jpg is {image_format}, not a JPEG"
    assert width > 0 and height > 0


def test_ac2_b3_thumbs_holds_at_least_one_decodable_image(normalized):
    """#12 AC2 "… and at least one image in `thumbs/`" (plan §4.2 `thumbs/`, thumbnail strips).
    Every image file there must decode; other files (an index) are allowed."""
    _require_output(normalized)
    thumbs = normalized.out / "thumbs"
    assert thumbs.is_dir(), f"no thumbs/ folder in {normalized.out}"
    files = [p for p in thumbs.rglob("*") if p.is_file()]
    images = [p for p in files if _is_image(p)]
    assert images, f"no decodable image in thumbs/: {[p.name for p in files]}"
    broken = [
        p.name
        for p in files
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} and p not in images
    ]
    assert not broken, f"image files in thumbs/ that don't decode: {broken}"


# ── AC3 ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def silent_run(media, tmp_path_factory) -> SimpleNamespace:
    root = tmp_path_factory.mktemp("b3-no-audio")
    source = media.make_video(root / "silent.mp4", DURATION_S, size="426x240", audio=False)
    assert not media.streams(media.ffprobe(source), "audio"), "the test source has audio"
    out = root / "case"
    result = media.run_cli("normalize", str(source), str(out))
    return SimpleNamespace(source=source, out=out, result=result, video=out / "video.mp4")


def test_ac3_b3_input_without_audio_does_not_crash(silent_run, media):
    """#12 AC3 "B3 handles an input without audio without crashing": the console script exits 0
    and still writes a valid `video.mp4` (H.264, 720 px high, faststart, same duration),
    `poster.jpg` and `thumbs/`."""
    result = silent_run.result
    assert result.returncode == 0, (
        f"exit {result.returncode} on a source without audio\nstderr: {result.stderr}"
    )
    assert "Traceback" not in result.stderr, result.stderr
    probe = media.ffprobe(silent_run.video)
    _assert_720p_h264(media, probe, 426, 240)
    boxes = media.top_level_boxes(silent_run.video)
    assert boxes.index("moov") < boxes.index("mdat"), boxes
    assert abs(float(probe["format"]["duration"]) - DURATION_S) <= DURATION_TOLERANCE_S
    assert media.decode_image(silent_run.out / "poster.jpg")[0] == "JPEG"
    assert [p for p in (silent_run.out / "thumbs").iterdir() if _is_image(p)]


def test_ac3_b3_no_audio_behaviour_is_documented_in_the_readme(silent_run, media):
    """#12 AC3 "… and its behaviour is documented in the module README". brain/README.md must
    say what happens to a source without audio, and the behaviour must be what it says: "A source
    without audio gives a `video.mp4` without an audio track" (no silent track is made up)."""
    text = " ".join(README.read_text(encoding="utf-8").split())
    assert "without audio" in text or "no audio" in text, (
        "brain/README.md doesn't document an input without audio"
    )
    assert "without an audio track" in text, (
        "brain/README.md no longer says what a source without audio gives (the observed "
        "behaviour below follows the documented one)"
    )
    assert silent_run.result.returncode == 0, silent_run.result.stderr
    audios = media.streams(media.ffprobe(silent_run.video), "audio")
    assert audios == [], f"the README says no audio track; video.mp4 has {len(audios)}"


# ── AC4 ──────────────────────────────────────────────────────────────────────

BAD_INPUTS = ["missing", "text-file", "text-named-mp4", "empty-mp4", "still-image", "audio-only"]
MISSING_WORDS = ("not found", "no such", "does not exist", "doesn't exist", "missing", "not exist")
NON_VIDEO_WORDS = ("video", "stream", "invalid", "not a ", "unsupported", "no frames", "decode")


def _bad_input(media, kind: str, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    if kind == "missing":
        return folder / "no_such_video.mp4"
    if kind == "text-file":
        path = folder / "notes.txt"
        path.write_text("this is not a video\n", encoding="utf-8")
        return path
    if kind == "text-named-mp4":
        path = folder / "fake_video.mp4"
        path.write_text("this is not a video either\n" * 50, encoding="utf-8")
        return path
    if kind == "empty-mp4":
        path = folder / "empty.mp4"
        path.write_bytes(b"")
        return path
    if kind == "still-image":
        path = folder / "still.jpg"
        Image.new("RGB", (640, 360), (40, 120, 200)).save(path, "JPEG")
        return path
    if kind == "audio-only":
        return media.make_audio(folder / "tone.m4a", 5.0)
    raise AssertionError(kind)


def _earlier_outputs(out: Path) -> None:
    out.mkdir(parents=True)
    (out / "video.mp4").write_bytes(b"an earlier video.mp4")
    (out / "poster.jpg").write_bytes(b"an earlier poster.jpg")
    (out / "keep.txt").write_text("not B3's\n", encoding="utf-8")


@pytest.mark.parametrize("out_state", ["fresh-out-dir", "earlier-outputs"])
@pytest.mark.parametrize("kind", BAD_INPUTS)
def test_ac4_b3_cli_rejects_missing_or_non_video_input(media, tmp_path, kind, out_state):
    """#12 AC4 "B3 rejects a missing or non-video input with a clear error, a non-zero exit code
    from the console script, and no partial `video.mp4` left behind". A text file, a text or empty
    file named `.mp4`, a still image (brain/README.md: "a non-video input (a text file or a still
    image)") and an audio-only file are all non-video. "Clear": an error line (README:
    `scrubgpt-brain: error: …`) naming the file or the problem, not a traceback. README: "no new or
    half-written output is left in `<out_dir>`, and earlier outputs stay as they were"."""
    source = _bad_input(media, kind, tmp_path / "inputs")
    out = tmp_path / "case"
    if out_state == "earlier-outputs":
        _earlier_outputs(out)
    before = media.files_under(out)

    result = media.run_cli("normalize", str(source), str(out))

    message = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0, f"exit 0 for a {kind} input\n{message}"
    assert "Traceback" not in message, f"a traceback, not a clear error:\n{message}"
    assert "error" in message.casefold(), f"no error message:\n{message}"
    words = MISSING_WORDS if kind == "missing" else NON_VIDEO_WORDS
    assert source.name in message or any(w in message.casefold() for w in words), (
        f"the error names neither the file nor the problem:\n{message}"
    )
    after = media.files_under(out)
    if out_state == "fresh-out-dir":
        assert not (out / "video.mp4").exists(), "a partial video.mp4 was left behind"
        assert after == {}, f"output left behind after the failure: {sorted(after)}"
    else:
        assert after == before, (
            f"the failed run changed {out}: before {sorted(before)}, after {sorted(after)}; "
            f"video.mp4 intact: {after.get('video.mp4') == before['video.mp4']}"
        )


@pytest.mark.parametrize("kind", ["missing", "text-named-mp4", "audio-only"])
def test_ac4_b3_python_api_raises_media_error(media, tmp_path, kind):
    """#12 AC4 through the Python entry point: brain/README.md "`normalize(source, out_dir)`
    returns a `NormalizedMedia`, or raises `MediaError`"; the message is clear (not empty) and no
    `video.mp4` is left in the folder."""
    from scrubgpt_brain.engines.media import MediaError
    from scrubgpt_brain.pipeline.normalize import normalize

    source = _bad_input(media, kind, tmp_path / "inputs")
    out = tmp_path / "case"
    with pytest.raises(MediaError) as raised:
        normalize(source, out)
    assert str(raised.value).strip(), "MediaError without a message"
    assert not (out / "video.mp4").exists(), "a partial video.mp4 was left behind"
    assert media.files_under(out) == {}, "output left behind after the failure"


# ── D-063 ────────────────────────────────────────────────────────────────────


def test_d063_b3_writes_no_case_json(normalized, case_json_names):
    """D-063 / #12 "No reading or writing of `case.json`, `timeline.json`, `moments.json`,
    `questions.json` or `seed_records.json`" before the tag: B3's output folder holds none of the
    case JSON files of plan §4.2."""
    _require_output(normalized)
    written = {p.name for p in normalized.out.rglob("*.json")}
    assert not written & set(case_json_names), f"case JSON written: {written}"
