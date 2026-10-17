"""Dev1's unit tests for D1, the audio chunker (plan §2.4).

The FFmpeg tests make tiny videos whose audio is AAC, mono, 16 kHz (as B3 writes it): a quiet
440 Hz tone stands for the narration, true silence for the pauses, and loud 1 kHz beeps mark known
times. The cut-rule tests need no FFmpeg, so they also run on the CI runner.
"""

import array
import itertools
import json
import random
import subprocess
from pathlib import Path

import pytest
from scrubgpt_brain import cli
from scrubgpt_brain.engines.media import MediaError
from scrubgpt_brain.pipeline import audio as a

RATE = 16_000
SPEECH = ((0.0, 25.0), (27.0, 55.0), (57.0, 80.0))
PAUSES = ((25.0, 27.0), (55.0, 57.0))
BEEP_S = 0.25
LOUD = 16_000
"""Half of full scale: only the beeps (0.8 + 0.1) reach it, never the tone (0.1)."""


def _voice(
    path: Path,
    *,
    duration: float,
    sound: tuple[tuple[float, float], ...],
    beeps: tuple[float, ...] = (),
    audio_delay_s: float = 0.0,
) -> Path:
    """A 64x48 video with a mono 16 kHz AAC track: the tone over `sound`, a `BEEP_S` long beep at
    each of `beeps`, silence elsewhere. `audio_delay_s` starts the audio track that much later."""
    tone = "+".join(f"gte(t,{start})*lt(t,{end})" for start, end in sound) or "0"
    beep = "+".join(f"gte(t,{t})*lt(t,{t + BEEP_S})" for t in beeps) or "0"
    expr = f"0.1*sin(2*PI*440*t)*({tone})+0.8*sin(2*PI*1000*t)*({beep})"
    delay = ["-itsoffset", str(audio_delay_s)] if audio_delay_s else []
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostdin", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c=black:s=64x48:r=5:d={duration}",
            *delay, "-f", "lavfi", "-i", f"aevalsrc='{expr}':s={RATE}:d={duration - audio_delay_s}",
            "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-ar", str(RATE), str(path),
        ],
        check=True,
    )  # fmt: skip
    return path


def _beeps(path: Path) -> list[tuple[float, float]]:
    """`(start, end)` of each loud beep in an audio file, in seconds from the start of the file
    (decoded to 16-bit PCM by FFmpeg, read with plain Python)."""
    pcm = ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(RATE)]
    raw = subprocess.run([*pcm, "-"], capture_output=True, check=True).stdout
    samples = array.array("h")
    samples.frombytes(raw)
    runs: list[list[int]] = []
    for i, value in enumerate(samples):
        if abs(value) > LOUD:
            if runs and i - runs[-1][1] <= RATE // 10:
                runs[-1][1] = i
            else:
                runs.append([i, i])
    return [(first / RATE, (last + 1) / RATE) for first, last in runs]


def _check_plan(
    plan: list[tuple[float, float]],
    duration_s: float,
    max_chunk_s: float,
    pauses: list[tuple[float, float]],
    overlap_s: float = a.HARD_CUT_OVERLAP_S,
) -> None:
    assert plan[0][0] == 0.0
    assert all(isinstance(x, float) for span in plan for x in span)
    assert all(0 < length <= max_chunk_s for _, length in plan)
    assert plan[-1][0] + plan[-1][1] == pytest.approx(duration_s, abs=1e-6)
    for (offset, length), (next_offset, _) in itertools.pairwise(plan):
        cut = offset + length
        assert offset < next_offset <= cut + 1e-9  # moves on, and leaves no gap
        if next_offset < cut - 1e-9:  # a hard cut: exactly the documented overlap
            assert cut - next_offset == pytest.approx(overlap_s, abs=0.002)
        else:  # a cut at a pause: inside one
            assert any(start - 0.001 <= cut <= end for start, end in pauses), cut


# ── The cut rule (no FFmpeg) ─────────────────────────────────────────────────


def test_plan_cuts_in_the_latest_pause_of_the_window():
    plan = a.plan_chunks(80.0, PAUSES, max_chunk_s=30, search_window_s=10)
    assert plan == [(0.0, 26.0), (26.0, 30.0), (56.0, 24.0)]
    _check_plan(plan, 80.0, 30, list(PAUSES))
    # Two pauses in the window: the later one, cut at its middle.
    assert a.plan_chunks(50.0, [(26, 27), (22, 23)], max_chunk_s=30, search_window_s=10)[0] == (
        0.0,
        26.5,
    )
    # A pause that starts before the window, or runs past the target: cut where the window meets
    # it, as close to its middle as the window allows.
    assert a.plan_chunks(40.0, [(15, 22)], max_chunk_s=30, search_window_s=10)[0] == (0.0, 20.0)
    assert a.plan_chunks(50.0, [(28, 35)], max_chunk_s=30, search_window_s=10)[0] == (0.0, 30.0)
    assert a.chunk_name(0) == "chunk_000.flac" and a.chunk_name(12) == "chunk_012.flac"


def test_plan_without_a_pause_in_the_window_hard_cuts_with_the_overlap():
    no_pause = a.plan_chunks(70.0, [], max_chunk_s=30, search_window_s=10, hard_cut_overlap_s=1)
    assert no_pause == [(0.0, 30.0), (29.0, 30.0), (58.0, 12.0)]
    _check_plan(no_pause, 70.0, 30, [])
    # A pause before the window doesn't count.
    assert a.plan_chunks(50.0, [(5, 8)], max_chunk_s=30, search_window_s=10) == [
        (0.0, 30.0),
        (29.0, 21.0),
    ]
    assert a.plan_chunks(12.5, []) == [(0.0, 12.5)]
    # A hard cut stays at the maximum near the end: the 1 s overlap already keeps the last chunk
    # at least 1 s long (#14 AC12). Only with a smaller overlap does the cut move back.
    assert a.plan_chunks(30.4, [], max_chunk_s=30) == [(0.0, 30.0), (29.0, 1.4)]
    assert a.plan_chunks(30.4, [], max_chunk_s=30, hard_cut_overlap_s=0.0) == [
        (0.0, 29.4),
        (29.4, 1.0),
    ]


def test_plan_on_a_long_track_with_random_pauses():
    rng = random.Random(7)
    pauses, t = [], 0.0
    while t < 3600:
        t += rng.uniform(5, 150)
        length = rng.uniform(0.5, 4)
        pauses.append((round(t, 6), round(t + length, 6)))
        t += length
    for max_chunk_s in (30.0, 120.0, 600.0):
        _check_plan(
            a.plan_chunks(3600.0, pauses, max_chunk_s=max_chunk_s), 3600.0, max_chunk_s, pauses
        )


def test_parse_silences():
    log = (
        "  title           : silence_start: 9\n"  # a tag, not silencedetect: ignored
        "[silencedetect @ 0x55] silence_start: -2e-05\n"
        "[silencedetect @ 0x55] silence_end: 0.75 | silence_duration: 0.75\n"
        "[Parsed_silencedetect_2 @ 00000286d359de80] silence_start: 4.999937\n"
        "[Parsed_silencedetect_2 @ 00000286d359de80] silence_end: 7.000125 | silence_duration: 2\n"
        "[Parsed_silencedetect_2 @ 00000286d359de80] silence_start: 14.999937\n"
    )
    assert a.parse_silences(log, 20.0) == [(0.0, 0.75), (4.999937, 7.000125), (14.999937, 20.0)]


@pytest.mark.parametrize(
    "bad",
    [
        {"max_chunk_s": 5},
        {"search_window_s": -1},
        {"max_chunk_s": 30, "hard_cut_overlap_s": 20},
        {"hard_cut_overlap_s": -0.5},
        {"max_bytes": 0},
        {"silence_db": 3},
        {"min_silence_s": 0},
    ],
)
def test_bad_settings_raise_value_error(tmp_path: Path, bad: dict):
    with pytest.raises(ValueError):
        a.chunk_audio(tmp_path / "v.mp4", tmp_path / "audio", **bad)
    assert not (tmp_path / "audio").exists()


# ── Chunking with FFmpeg ─────────────────────────────────────────────────────


def test_chunks_are_cut_inside_the_pauses_and_cover_the_track(media, tmp_path: Path):
    source = _voice(tmp_path / "v.mp4", duration=80, sound=SPEECH)
    out = tmp_path / "audio"
    chunks = a.chunk_audio(source, out, max_chunk_s=30, search_window_s=10)
    assert [c.index for c in chunks] == [0, 1, 2]
    assert [c.path for c in chunks] == [out / f"chunk_00{i}.flac" for i in range(3)]
    assert chunks[0].offset_s == 0.0
    assert all(isinstance(c.offset_s, float) and isinstance(c.duration_s, float) for c in chunks)
    for before, after in itertools.pairwise(chunks):
        cut = before.offset_s + before.duration_s
        assert after.offset_s == pytest.approx(cut, abs=1e-6)  # no gap, no overlap
        assert any(start < cut < end for start, end in PAUSES), cut
    assert chunks[-1].offset_s + chunks[-1].duration_s == pytest.approx(80.0, abs=0.1)
    for chunk in chunks:
        assert 0 < chunk.duration_s <= 30
        assert chunk.path.stat().st_size <= a.MAX_BYTES
        (stream,) = media.streams(chunk.path)  # one audio stream, nothing else
        assert stream["codec_name"] == "flac"
        assert (int(stream["sample_rate"]), stream["channels"]) == (16_000, 1)
        assert float(stream["duration"]) == pytest.approx(chunk.duration_s, abs=0.1)
    index = json.loads((out / "chunks.json").read_text("utf-8"))
    assert index["source"] == source.name and index["max_chunk_s"] == 30
    assert index["chunks"] == [
        {"index": c.index, "file": c.path.name, "offset_s": c.offset_s, "duration_s": c.duration_s}
        for c in chunks
    ]
    assert sorted(p.name for p in out.iterdir()) == [
        "chunk_000.flac",
        "chunk_001.flac",
        "chunk_002.flac",
        "chunks.json",
    ]


def test_offsets_put_each_marker_at_its_true_time(media, tmp_path: Path):
    beeps = (10.0, 40.0, 70.0)  # one in each chunk: 0–26, 26–56 and 56–80 s
    source = _voice(tmp_path / "v.mp4", duration=80, sound=SPEECH, beeps=beeps)
    chunks = a.chunk_audio(source, tmp_path / "audio", max_chunk_s=30, search_window_s=10)
    assert len(chunks) == 3
    for chunk, beep in zip(chunks, beeps, strict=True):
        ((start, end),) = _beeps(chunk.path)
        assert start == pytest.approx(beep - chunk.offset_s, abs=0.1)
        assert end - start == pytest.approx(BEEP_S, abs=0.05)


def test_an_audio_track_that_starts_late_keeps_video_time(media, tmp_path: Path):
    # The track starts 0.5 s into the video; its beep at 10 s of audio is at 10.5 s of video.
    source = _voice(tmp_path / "v.mp4", duration=20, sound=(), beeps=(10.0,), audio_delay_s=0.5)
    (chunk,) = a.chunk_audio(source, tmp_path / "audio")
    ((start, _),) = _beeps(chunk.path)
    assert chunk.offset_s + start == pytest.approx(10.5, abs=0.1)
    assert chunk.duration_s == pytest.approx(20.0, abs=0.1)


def test_no_pause_gives_hard_cuts_with_the_overlap(media, tmp_path: Path):
    # A beep across the hard cut at 30 s (29.9–30.15 s), and one in the middle of the 2nd chunk.
    source = _voice(tmp_path / "v.mp4", duration=70, sound=((0.0, 70.0),), beeps=(29.9, 45.0))
    chunks = a.chunk_audio(source, tmp_path / "audio", max_chunk_s=30, search_window_s=10)
    assert [c.offset_s for c in chunks] == [0.0, 29.0, 58.0]
    assert [c.duration_s for c in chunks[:2]] == [30.0, 30.0]
    assert chunks[2].duration_s == pytest.approx(12.0, abs=0.1)
    for before, after in itertools.pairwise(chunks):
        overlap = before.offset_s + before.duration_s - after.offset_s
        assert overlap == pytest.approx(a.HARD_CUT_OVERLAP_S, abs=1e-6)
    ((start, end),) = _beeps(chunks[0].path)  # cut short by the hard cut…
    assert start == pytest.approx(29.9, abs=0.1) and end == pytest.approx(30.0, abs=0.02)
    whole, middle = _beeps(chunks[1].path)  # …and whole in the next chunk, thanks to the overlap
    assert whole[0] == pytest.approx(29.9 - 29.0, abs=0.1)
    assert whole[1] - whole[0] == pytest.approx(BEEP_S, abs=0.05)
    assert middle[0] == pytest.approx(45.0 - 29.0, abs=0.1)
    assert _beeps(chunks[2].path) == []


def test_a_video_without_audio_raises_and_writes_nothing(media, tmp_path: Path):
    source = media.video(tmp_path / "v.mp4", audio=False)
    out = tmp_path / "audio"
    out.mkdir()
    (out / "keep.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(MediaError, match="has no audio track"):
        a.chunk_audio(source, out)
    assert [p.name for p in out.iterdir()] == ["keep.txt"]


@pytest.mark.parametrize("name", ["missing.mp4", "notes.txt"])
def test_a_missing_or_non_media_input_raises(media, tmp_path: Path, name: str):
    source = tmp_path / name
    if name == "notes.txt":
        source.write_text("not a video", encoding="utf-8")
    with pytest.raises(MediaError):
        a.chunk_audio(source, tmp_path / "audio")
    assert not (tmp_path / "audio").exists()


def test_a_chunk_above_max_bytes_raises_and_keeps_the_earlier_chunks(media, tmp_path: Path):
    source = _voice(tmp_path / "v.mp4", duration=20, sound=((0.0, 20.0),))
    out = tmp_path / "audio"
    (first,) = a.chunk_audio(source, out)
    before = first.path.read_bytes(), (out / "chunks.json").read_bytes()
    with pytest.raises(MediaError, match="above the 1,000-byte limit"):
        a.chunk_audio(source, out, max_bytes=1000)
    assert (first.path.read_bytes(), (out / "chunks.json").read_bytes()) == before
    assert sorted(p.name for p in out.iterdir()) == ["chunk_000.flac", "chunks.json"]


def test_a_rerun_replaces_only_its_own_files(media, tmp_path: Path):
    source = _voice(tmp_path / "v.mp4", duration=80, sound=SPEECH)
    out = tmp_path / "audio"
    out.mkdir()
    (out / "keep.txt").write_text("mine", encoding="utf-8")
    (out / "chunk_notes.flac.txt").write_text("mine too", encoding="utf-8")
    assert len(a.chunk_audio(source, out, max_chunk_s=30, search_window_s=10)) == 3
    assert len(a.chunk_audio(source, out, max_chunk_s=50, search_window_s=10)) == 2
    assert sorted(p.name for p in out.iterdir()) == [
        "chunk_000.flac",
        "chunk_001.flac",
        "chunk_notes.flac.txt",
        "chunks.json",
        "keep.txt",
    ]
    index = json.loads((out / "chunks.json").read_text("utf-8"))
    assert index["max_chunk_s"] == 50 and [c["file"] for c in index["chunks"]] == [
        "chunk_000.flac",
        "chunk_001.flac",
    ]


def test_cli(media, tmp_path: Path):
    lines: list[str] = []
    missing = tmp_path / "missing.mp4"
    assert (
        cli.main(["audio", str(missing), str(tmp_path / "o")], out=lines.append, err=lines.append)
        == 1
    )
    assert lines[0].startswith("scrubgpt-brain: error:")
    lines.clear()
    source = _voice(tmp_path / "v.mp4", duration=80, sound=SPEECH)
    args = ["audio", str(source), str(tmp_path / "o"), "--max-chunk", "30"]
    assert cli.main(args, out=lines.append) == 0
    assert len(lines) == 1
    assert "3 FLAC chunk(s)" in lines[0] and "2 cut(s) at pauses, 0 hard cut(s)" in lines[0]
    lines.clear()
    assert cli.main([*args[:3], "--max-chunk", "5"], out=lines.append, err=lines.append) == 1
    assert lines[0].startswith("scrubgpt-brain: error: max_chunk_s")
