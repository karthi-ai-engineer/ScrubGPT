"""D1 Audio extraction and chunking: #14 acceptance criteria 11-13 (Team Lead answer; D-067;
plan §2.4 D1; brain/README.md "D1 Audio chunker").

Expected behaviour, written from the spec before the code was opened:
- `chunk_audio(source, out_dir)` (CLI `scrubgpt-brain audio <video> <out_dir> [--max-chunk N]`)
  cuts a video's audio track into `chunk_000.flac`, … (FLAC, 16 kHz, mono) plus `chunks.json`
  `{"source", "max_chunk_s", "chunks": [{"index", "file", "offset_s", "duration_s"}]}` and returns
  `AudioChunk(index, path, offset_s, duration_s)`.
- AC11: the chunks cover the audio from 0 s to its end with no gap; overlap only at hard cuts and
  at most the documented 1 s. `offset_s` is a float in video time (README: an audio track that
  starts after the picture is padded, offsets rounded down to the millisecond), and the chunk's
  audio at local t equals the source at offset_s + t (±0.1 s).
- AC12: every chunk is at most `max_chunk_s` (default 600 s) and every file at most 24,000,000
  bytes (< the API's 25 MB, plan D1). A chunk aims to end `max_chunk_s` after it starts and is cut
  in the latest pause (>= 0.5 s below -30 dBFS) that overlaps the last 60 s before that target, at
  the pause's middle, with no overlap; with no pause there, it is cut hard at the target and the
  next chunk starts 1 s earlier.
- AC13: chunk files are 16 kHz mono FLAC (the format the README names). A video without an audio
  track raises `MediaError` ("… has no audio track") and writes nothing; a missing or non-video
  input exits 1 with `scrubgpt-brain: error: …`; earlier outputs stay as they were on any error; a
  re-run replaces `chunk_*.flac` and `chunks.json` and leaves other files alone.

Sources are synthetic (D-036): a `testsrc2` picture muxed with audio generated here, "tones"
(a sine plus seeded noise, so no two moments sound alike) separated by digital silence at known
times. Lossless sources (PCM in Matroska) give an exact ground truth; one AAC/MP4 source is
compared with FFmpeg's own decode. Everything is made in `tmp_path`; the `media` fixture skips
these tests when the FFmpeg CLI is missing (#14 AC14).
"""

from __future__ import annotations

import json
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest

RATE = 16_000
MAX_BYTES = 24_000_000  # README "every file is checked against 24,000,000 bytes"
API_LIMIT = 25 * 1024 * 1024  # plan D1 "the API's 25 MB file limit"
OVERLAP_S = 1.0  # README: hard cuts overlap by 1 s
TOLERANCE_S = 0.1  # #14 AC11 "(±0.1 s)"
EPS = 0.002  # millisecond rounding of offsets and durations


# ── synthetic sources ────────────────────────────────────────────────────────


def synth(segments, *, seed: int = 0) -> np.ndarray:
    """16 kHz mono float samples: "tone" = a sine (its own frequency per segment) plus seeded
    uniform noise, about -15 dBFS RMS; "loud" = full-scale noise (doesn't compress); "silence" =
    digital zero."""
    rng = np.random.default_rng(seed)
    parts = []
    for k, (kind, seconds) in enumerate(segments):
        n = round(seconds * RATE)
        if kind == "silence":
            parts.append(np.zeros(n))
        elif kind == "tone":
            t = np.arange(n) / RATE
            parts.append(0.2 * np.sin(2 * np.pi * (300 + 37 * k) * t) + rng.uniform(-0.2, 0.2, n))
        elif kind == "loud":
            parts.append(rng.uniform(-0.9, 0.9, n))
        else:
            raise ValueError(kind)
    return np.concatenate(parts)


def _ffmpeg(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-y", "-v", "error", *args],
        capture_output=True,
        check=True,
        timeout=900,
    )


def make_source(
    folder: Path,
    name: str,
    samples: np.ndarray,
    *,
    ext: str = "mkv",
    acodec: str = "pcm_s16le",
    rate: int = RATE,
    channels: int = 1,
    audio_delay: float = 0.0,
) -> tuple[Path, np.ndarray]:
    """A video (`testsrc2`, 64x36 at 2 fps) with `samples` as its audio track. Returns the video
    and the int16 16 kHz mono ground truth in video time (zeros before a delayed audio start)."""
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    work = folder / "_wav"
    work.mkdir(parents=True, exist_ok=True)
    wav = work / f"{name}.wav"
    with wave.open(str(wav), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(pcm.tobytes())
    video = folder / f"{name}.{ext}"
    duration = len(pcm) / RATE + audio_delay
    args = ["-f", "lavfi", "-i", f"testsrc2=size=64x36:rate=2:duration={duration:.3f}"]
    if audio_delay:
        args += ["-itsoffset", f"{audio_delay:.3f}"]
    args += ["-i", str(wav), "-map", "0:v:0", "-map", "1:a:0"]
    args += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    args += ["-c:a", acodec, "-ar", str(rate), "-ac", str(channels)]
    if acodec == "aac":
        args += ["-b:a", "128k"]
    _ffmpeg(*args, str(video))
    wav.unlink()
    truth = np.concatenate([np.zeros(round(audio_delay * RATE), "<i2"), pcm])
    return video, truth


def decode_pcm(path: Path) -> np.ndarray:
    """The first audio stream of `path`, decoded by FFmpeg to 16 kHz mono int16."""
    out = _ffmpeg(
        "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"
    )
    return np.frombuffer(out.stdout, "<i2")


def lag_at(chunk_pcm, truth, offset_s, local_s, *, probe_s=0.5, search_s=0.25):
    """Where the chunk's audio at `local_s` best matches the source near `offset_s + local_s`:
    (lag in seconds, normalised correlation), or None for a silent probe."""
    n, s = round(probe_s * RATE), round(search_s * RATE)
    a = round(local_s * RATE)
    probe = chunk_pcm[a : a + n].astype(float)
    if len(probe) < n or np.sqrt(np.mean(probe**2)) < 300:
        return None
    lo = round((offset_s + local_s) * RATE) - s
    ref = truth[max(lo, 0) : lo + 2 * s + n].astype(float)
    if lo < 0:
        ref = np.concatenate([np.zeros(-lo), ref])
    ref = np.concatenate([ref, np.zeros(max(0, 2 * s + n - len(ref)))])
    corr = np.correlate(ref, probe, "valid")
    energy = np.sqrt(np.convolve(ref**2, np.ones(n), "valid") * np.sum(probe**2))
    ncc = corr / np.maximum(energy, 1e-9)
    k = int(np.argmax(ncc))
    return (k - s) / RATE, float(ncc[k])


@dataclass
class Run:
    source: Path
    truth: np.ndarray | None
    end_s: float  # where the audio ends, in video time
    max_chunk_s: float
    out: Path
    chunks: list = field(default_factory=list)
    pauses: list[tuple[float, float]] = field(default_factory=list)


def _run(media, root: Path, name: str, segments, *, max_chunk_s=None, **source_kw) -> Run:
    from scrubgpt_brain.pipeline.audio import chunk_audio

    folder = root / name
    folder.mkdir(parents=True)
    samples = synth(segments, seed=len(name))
    source, truth = make_source(folder / "src", name, samples, **source_kw)
    out = folder / "chunks"
    kwargs = {} if max_chunk_s is None else {"max_chunk_s": max_chunk_s}
    chunks = chunk_audio(source, out, **kwargs)
    delay = source_kw.get("audio_delay", 0.0)
    t, pauses = delay, []
    for kind, seconds in segments:
        if kind == "silence":
            pauses.append((t, t + seconds))
        t += seconds
    return Run(source, truth, t, max_chunk_s or 600.0, out, list(chunks), pauses)


# Scenario P: pauses at known times, max 120 s (window = the last 60 s before each target).
#   chunk 0 targets 120 s: pauses 30-31 (outside the window), 70-71 and 95-96 (the latest) -> 95.5
#   chunk 1 targets 215.5 s: no pause in 155.5-215.5 -> hard cut at 215.5, next starts at 214.5
#   chunk 2 targets 334.5 s: pause 300-300.8 -> cut at 300.4; chunk 3 runs to the end (360 s)
PAUSED = [
    ("tone", 30), ("silence", 1), ("tone", 39), ("silence", 1), ("tone", 24), ("silence", 1),
    ("tone", 204), ("silence", 0.8), ("tone", 59.2),
]  # fmt: skip


@pytest.fixture(scope="module")
def d1_root(media, tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("d1")


@pytest.fixture(scope="module")
def paused(media, d1_root) -> Run:
    return _run(media, d1_root, "paused", PAUSED, max_chunk_s=120)


@pytest.fixture(scope="module")
def unbroken(media, d1_root) -> Run:
    """Scenario H: 300 s with no pause, max 120 s -> hard cuts: 0-120, 119-239, 238-300."""
    return _run(media, d1_root, "unbroken", [("tone", 300)], max_chunk_s=120)


@pytest.fixture(scope="module")
def delayed(media, d1_root) -> Run:
    """The audio starts 2 s after the picture (README: padded, offsets in video time); 148 s of
    tone with one pause, max 120 s."""
    run = _run(
        media, d1_root, "delayed", [("tone", 80), ("silence", 1), ("tone", 67)], max_chunk_s=120,
        audio_delay=2.0,
    )  # fmt: skip
    audio = media.streams(media.ffprobe(run.source), "audio")[0]
    assert abs(float(audio["start_time"]) - 2.0) < 0.05, f"test setup: audio starts at {audio}"
    return run


@pytest.fixture(scope="module")
def stereo_aac(media, d1_root) -> Run:
    """An MP4 with 44.1 kHz stereo AAC (D1 must resample and down-mix), 50 s with a pause,
    default settings; ground truth = FFmpeg's own decode of the source."""
    run = _run(
        media, d1_root, "stereo", [("tone", 20), ("silence", 1), ("tone", 29)], ext="mp4",
        acodec="aac", rate=44_100, channels=2,
    )  # fmt: skip
    run.truth = decode_pcm(run.source)
    return run


@pytest.fixture(scope="module")
def b3_like(media, d1_root) -> Run:
    """Like B3's `video.mp4`: AAC mono 16 kHz in MP4, 45 s (shorter than a chunk), defaults."""
    run = _run(media, d1_root, "b3like", [("tone", 45)], ext="mp4", acodec="aac")
    run.truth = decode_pcm(run.source)
    return run


@pytest.fixture(scope="module")
def all_runs(paused, unbroken, delayed, stereo_aac, b3_like) -> dict[str, Run]:
    return {
        "paused": paused,
        "unbroken": unbroken,
        "delayed": delayed,
        "stereo-aac": stereo_aac,
        "b3-like": b3_like,
    }


RUNS = ["paused", "unbroken", "delayed", "stereo-aac", "b3-like"]


def _ends(chunks):
    return [c.offset_s + c.duration_s for c in chunks]


# ── AC11 ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", RUNS)
def test_ac11_chunks_cover_the_whole_duration_without_gap(all_runs, name):
    """#14 AC11 "Together they cover the whole duration with no gap, and any overlap is within
    the documented size. Each chunk has a float `offset_s`" (README: "The chunks cover the audio
    from 0 s to its end with no gap"; hard cuts overlap by 1 s; "Offsets are rounded down to the
    millisecond")."""
    run = all_runs[name]
    chunks = run.chunks
    assert chunks, "no chunk"
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert chunks[0].offset_s == 0.0
    for c in chunks:
        assert isinstance(c.offset_s, float) and isinstance(c.duration_s, float), c
        assert c.duration_s > 0, c
        assert abs(c.offset_s * 1000 - round(c.offset_s * 1000)) < 1e-6, f"not whole ms: {c}"
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        end = prev.offset_s + prev.duration_s
        assert nxt.offset_s <= end + EPS, f"gap between {prev} and {nxt}"
        assert end - nxt.offset_s <= OVERLAP_S + EPS, f"overlap above 1 s: {prev} / {nxt}"
        assert nxt.offset_s > prev.offset_s
    assert abs(_ends(chunks)[-1] - run.end_s) <= TOLERANCE_S, (chunks[-1], run.end_s)


@pytest.mark.parametrize("name", RUNS)
def test_ac11_each_file_lasts_its_duration(media, all_runs, name):
    """#14 AC11 "Each chunk has a float `offset_s`" with its `duration_s`: every chunk file's
    decoded length is its `duration_s` (±0.05 s), so offsets + durations describe the files."""
    for chunk in all_runs[name].chunks:
        samples = decode_pcm(chunk.path)
        assert abs(len(samples) / RATE - chunk.duration_s) <= 0.05, (chunk, len(samples) / RATE)


@pytest.mark.parametrize("name", RUNS)
def test_ac11_chunk_audio_equals_the_source_at_its_offset(all_runs, name):
    """#14 AC11 "its audio at local time *t* equals the source at `offset_s + t` (±0.1 s)": probes
    of 0.5 s at the start, quarters and end of each chunk are matched against the source (video
    time) by cross-correlation; the best match is within 0.1 s and the audio is the same
    (normalised correlation >= 0.95)."""
    run = all_runs[name]
    for chunk in run.chunks:
        pcm = decode_pcm(chunk.path)
        d = chunk.duration_s
        found = []
        for local in (0.05, d * 0.25, d * 0.5, d * 0.75, d - 0.6):
            result = lag_at(pcm, run.truth, chunk.offset_s, local)
            if result is not None:
                found.append((round(local, 2), *result))
        assert len(found) >= 2, f"chunk {chunk.index}: too few non-silent probes"
        for local, lag, ncc in found:
            assert abs(lag) <= TOLERANCE_S, f"chunk {chunk.index} at {local} s: off by {lag:+.3f} s"
            assert ncc >= 0.95, f"chunk {chunk.index} at {local} s: not the source ({ncc:.3f})"


def test_ac11_offsets_are_in_video_time_when_the_audio_starts_late(delayed):
    """README "An audio track that starts after the video's picture is padded at the start, so
    offsets are in video time" (#14 AC11 "the source at `offset_s + t`"): the first chunk starts
    at 0 with the 2 s of padding silent, and the chunks reach the end of the picture."""
    first = delayed.chunks[0]
    pcm = decode_pcm(first.path)
    assert first.offset_s == 0.0
    assert np.sqrt(np.mean(pcm[: round(1.8 * RATE)].astype(float) ** 2)) < 50, "padding not silent"
    assert np.sqrt(np.mean(pcm[round(2.2 * RATE) : round(3 * RATE)].astype(float) ** 2)) > 1000
    assert abs(_ends(delayed.chunks)[-1] - delayed.end_s) <= TOLERANCE_S


# ── AC12 ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", RUNS)
def test_ac12_chunks_respect_the_maximum_length_and_file_size(all_runs, name):
    """#14 AC12 "Chunks respect the maximum length and the per-file size limit, which defaults
    below 25 MB (plan D1)" (README: "A chunk is at most 600 s", "every file is checked against
    24,000,000 bytes")."""
    run = all_runs[name]
    for chunk in run.chunks:
        assert chunk.duration_s <= run.max_chunk_s + EPS, chunk
        size = Path(chunk.path).stat().st_size
        assert size <= MAX_BYTES < API_LIMIT, (chunk, size)


def test_ac12_default_limits_hold_for_audio_that_doesnt_compress(media, d1_root):
    """#14 AC12 "… the per-file size limit, which defaults below 25 MB" with the defaults: 650 s
    of full-scale noise (README: "a chunk is at most 600 s (≈ 19.3 MB even for audio that doesn't
    compress)"). The first chunk is cut hard at 600 s, every file stays at most 24,000,000 bytes,
    and chunks.json records `max_chunk_s` 600."""
    run = _run(media, d1_root, "loud", [("loud", 650)])
    chunks = run.chunks
    assert [round(c.offset_s, 3) for c in chunks] == [0.0, 599.0], chunks
    assert chunks[0].duration_s == pytest.approx(600.0, abs=EPS)
    assert _ends(chunks)[-1] == pytest.approx(650.0, abs=0.05)
    for chunk in chunks:
        size = Path(chunk.path).stat().st_size
        assert chunk.duration_s <= 600.0 + EPS and size <= MAX_BYTES, (chunk, size)
    assert Path(chunks[0].path).stat().st_size > 15_000_000, (
        "the noise compressed: not a worst case"
    )
    index = json.loads((run.out / "chunks.json").read_text(encoding="utf-8"))
    assert index["max_chunk_s"] == 600


def test_ac12_cuts_land_inside_the_latest_silence_of_the_window(paused):
    """#14 AC12 "Cuts land inside a silence whenever a silence exists within the allowed window"
    (README: "the latest pause that overlaps the last 60 s before that target, at the pause's
    middle"; "Chunks cut at a pause don't overlap"). Chunk 0 (target 120 s) ends in the 95-96 s
    pause (not 30-31 or 70-71); chunk 2 (target 334.5 s) ends in the 300-300.8 s pause; the next
    chunk starts exactly there."""
    c = paused.chunks
    assert len(c) == 4, c
    ends = _ends(c)
    for index, (start, end) in ((0, (95.0, 96.0)), (2, (300.0, 300.8))):
        assert start <= ends[index] <= end, (
            f"chunk {index} ends at {ends[index]}, not in {start}-{end}"
        )
        assert abs(ends[index] - (start + end) / 2) <= TOLERANCE_S, f"not mid-pause: {ends[index]}"
        assert c[index + 1].offset_s == pytest.approx(ends[index], abs=EPS), "a pause cut overlaps"


def test_ac12_without_a_silence_the_cut_is_hard_at_the_maximum(paused, unbroken):
    """#14 AC12 "If there is no silence, the cut is a hard cut at the maximum length" (README:
    "the next one starts 1 s earlier"): in a 300 s track with no pause the chunks are 0-120,
    119-239 and 238-300; in the paused track, chunk 1 (no pause in its window) is exactly 120 s
    and chunk 2 starts 1 s before its end."""
    u = unbroken.chunks
    assert [round(c.offset_s, 3) for c in u] == [0.0, 119.0, 238.0], u
    assert [round(c.duration_s, 3) for c in u] == [120.0, 120.0, 62.0], u
    p = paused.chunks
    assert p[1].duration_s == pytest.approx(120.0, abs=EPS), p[1]
    assert p[2].offset_s == pytest.approx(_ends(p)[1] - OVERLAP_S, abs=EPS), p[2]


def test_ac12_a_hard_cut_near_the_end_is_still_at_the_maximum(media, d1_root):
    """#14 AC12 "If there is no silence, the cut is a hard cut at the maximum length" (README:
    "With no pause in the window, the chunk is cut hard at the target, and the next one starts 1 s
    earlier"; "The last chunk is at least 1 s long"): 120.5 s of tone with no pause and max 120 s
    give 0-120 s and 119-120.5 s; the last chunk (1.5 s) is already at least 1 s long."""
    run = _run(media, d1_root, "nearend", [("tone", 120.5)], max_chunk_s=120)
    got = [(round(c.offset_s, 3), round(c.duration_s, 3)) for c in run.chunks]
    assert got == [(0.0, 120.0), (119.0, 1.5)], got


def test_ac12_the_last_chunk_is_at_least_1_s(media, d1_root):
    """README "The last chunk is at least 1 s long", with #14 AC12 "Cuts land inside a silence
    whenever a silence exists within the allowed window": 120.95 s whose only pause (119.9-120.9 s)
    ends 0.05 s before the audio does, max 120 s. The cut lies in that pause, within 120 s, and the
    last chunk lasts at least 1 s."""
    run = _run(
        media, d1_root, "tail", [("tone", 119.9), ("silence", 1.0), ("tone", 0.05)],
        max_chunk_s=120,
    )  # fmt: skip
    c = run.chunks
    assert len(c) == 2, c
    assert 119.9 <= _ends(c)[0] <= 120.0 + EPS, c
    assert c[1].offset_s == pytest.approx(_ends(c)[0], abs=EPS)
    assert c[1].duration_s >= 1.0 - EPS, c
    assert _ends(c)[1] == pytest.approx(120.95, abs=0.05)


def test_ac12_an_oversized_chunk_is_an_error_that_keeps_earlier_chunks(media, unbroken, tmp_path):
    """#14 AC12 "the per-file size limit" is enforced (README "every file is checked against
    24,000,000 bytes"; "an oversized chunk exits 1 …, and earlier chunks stay as they were"): with
    a 100 kB limit, chunking into a folder that holds an earlier run raises `MediaError` and leaves
    that folder byte for byte as it was."""
    from scrubgpt_brain.engines.media import MediaError
    from scrubgpt_brain.pipeline.audio import chunk_audio

    out = tmp_path / "chunks"
    chunk_audio(unbroken.source, out, max_chunk_s=120)
    (out / "notes.txt").write_text("not D1's", encoding="utf-8")
    before = media.files_under(out)
    with pytest.raises(MediaError):
        chunk_audio(unbroken.source, out, max_chunk_s=120, max_bytes=100_000)
    assert media.files_under(out) == before


# ── AC13 ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", RUNS)
def test_ac13_chunk_files_are_16_khz_mono_flac(media, all_runs, name):
    """#14 AC13 "The chunk files are 16 kHz mono, in a format the README names" (README:
    "`chunk_000.flac`, `chunk_001.flac`, …: FLAC, 16 kHz, mono"), whatever the source's rate
    and channels."""
    for chunk in all_runs[name].chunks:
        path = Path(chunk.path)
        assert path.parent == all_runs[name].out
        assert path.name == f"chunk_{chunk.index:03d}.flac"
        assert path.read_bytes()[:4] == b"fLaC"
        streams = media.streams(media.ffprobe(path), "audio")
        assert len(streams) == 1
        assert streams[0]["codec_name"] == "flac"
        assert int(streams[0]["sample_rate"]) == RATE
        assert int(streams[0]["channels"]) == 1


@pytest.mark.parametrize("name", RUNS)
def test_ac13_chunks_json_describes_the_chunks(all_runs, name):
    """README "`chunks.json`: `{"source" (file name), "max_chunk_s", "chunks": [{"index",
    "file", "offset_s", "duration_s"}]}`", equal to what `chunk_audio` returns."""
    run = all_runs[name]
    index = json.loads((run.out / "chunks.json").read_text(encoding="utf-8"))
    assert index["source"] == run.source.name
    assert index["max_chunk_s"] == pytest.approx(run.max_chunk_s)
    assert index["chunks"] == [
        {
            "index": c.index,
            "file": Path(c.path).name,
            "offset_s": c.offset_s,
            "duration_s": c.duration_s,
        }
        for c in run.chunks
    ]


@pytest.mark.parametrize("name", RUNS)
def test_ac13_only_the_chunks_and_index_are_written(media, all_runs, name):
    """README "writes them into `<out_dir>`: `chunk_000.flac`, … and `chunks.json`" (D-067:
    "files in a folder the caller passes in"): after a run the folder holds exactly those (no
    temporary decode left behind), and nothing is written next to the source."""
    run = all_runs[name]
    names = set(media.files_under(run.out))
    assert names == {Path(c.path).name for c in run.chunks} | {"chunks.json"}, names
    assert set(media.files_under(run.source.parent)) == {run.source.name}


def _no_audio_video(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    video = folder / "silent.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=64x36:rate=2:duration=20",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(video),
    )  # fmt: skip
    return video


def test_ac13_a_video_without_audio_raises_and_writes_nothing(media, unbroken, tmp_path):
    """#14 AC13 "An input without audio gives the documented behaviour (an empty result or a
    clear error) with no partial files left behind." README: "A video without an audio track
    raises `MediaError` ("… has no audio track") and writes nothing": a new folder stays absent
    or empty, and a folder with an earlier run stays as it was."""
    from scrubgpt_brain.engines.media import MediaError
    from scrubgpt_brain.pipeline.audio import chunk_audio

    video = _no_audio_video(tmp_path / "src")
    fresh = tmp_path / "fresh"
    with pytest.raises(MediaError) as caught:
        chunk_audio(video, fresh)
    assert "no audio track" in str(caught.value), caught.value
    assert not fresh.exists() or not any(fresh.iterdir()), list(fresh.iterdir())
    earlier = tmp_path / "earlier"
    chunk_audio(unbroken.source, earlier, max_chunk_s=120)
    before = media.files_under(earlier)
    with pytest.raises(MediaError):
        chunk_audio(video, earlier)
    assert media.files_under(earlier) == before


def test_ac13_cli_video_without_audio_fails_and_writes_nothing(media, tmp_path):
    """#14 AC13 through `scrubgpt-brain audio`: a video without audio fails with a clear message
    ("… has no audio track", README) and leaves no file behind. The README doesn't say whether
    the message goes to stdout or stderr, so both are read."""
    video = _no_audio_video(tmp_path / "src")
    out = tmp_path / "out"
    result = media.run_cli("audio", str(video), str(out))
    message = f"{result.stdout}\n{result.stderr}"  # the README names no stream
    assert result.returncode != 0, message
    assert "no audio track" in message, message
    assert not out.exists() or not any(out.iterdir())


@pytest.mark.parametrize("bad", ["missing", "text-file"])
def test_ac13_cli_missing_or_non_video_input_exits_1(media, tmp_path, bad):
    """README "A missing or non-video input … exits 1 with `scrubgpt-brain: error: …`", with no
    output written."""
    source = tmp_path / "input.mp4"
    if bad == "text-file":
        source.write_text("this is not a video\n", encoding="utf-8")
    out = tmp_path / "out"
    result = media.run_cli("audio", str(source), str(out))
    message = f"{result.stdout}\n{result.stderr}"  # the README names no stream
    assert result.returncode == 1, (result.returncode, message)
    assert "scrubgpt-brain: error:" in message, message
    assert "Traceback" not in message, message
    assert not out.exists() or not any(out.iterdir())


def test_ac13_cli_writes_the_same_chunks_as_python(media, paused, tmp_path):
    """README "`uv run scrubgpt-brain audio <video> <out_dir> [--max-chunk 600]`": the CLI with
    `--max-chunk 120` exits 0 and writes the same chunks.json and the same audio as `chunk_audio`
    with `max_chunk_s=120`."""
    out = tmp_path / "cli"
    result = media.run_cli("audio", str(paused.source), str(out), "--max-chunk", "120")
    assert result.returncode == 0, result.stderr
    cli_index = json.loads((out / "chunks.json").read_text(encoding="utf-8"))
    py_index = json.loads((paused.out / "chunks.json").read_text(encoding="utf-8"))
    assert cli_index == py_index
    for entry in cli_index["chunks"]:
        assert np.array_equal(
            decode_pcm(out / entry["file"]), decode_pcm(paused.out / entry["file"])
        )


def test_ac13_a_rerun_replaces_the_chunks_and_leaves_other_files(media, unbroken, tmp_path):
    """README "A re-run replaces `chunk_*.flac` and `chunks.json` and leaves other files alone":
    3 chunks (max 120 s), then a re-run with the default max (one chunk) leaves exactly
    `chunk_000.flac`, the new chunks.json and an unrelated file."""
    from scrubgpt_brain.pipeline.audio import chunk_audio

    out = tmp_path / "chunks"
    assert len(chunk_audio(unbroken.source, out, max_chunk_s=120)) == 3
    (out / "notes.txt").write_text("keep me", encoding="utf-8")
    again = chunk_audio(unbroken.source, out)
    assert len(again) == 1 and again[0].duration_s == pytest.approx(300.0, abs=0.05)
    assert set(media.files_under(out)) == {"chunk_000.flac", "chunks.json", "notes.txt"}
    assert (out / "notes.txt").read_text(encoding="utf-8") == "keep me"
    index = json.loads((out / "chunks.json").read_text(encoding="utf-8"))
    assert [c["file"] for c in index["chunks"]] == ["chunk_000.flac"]
