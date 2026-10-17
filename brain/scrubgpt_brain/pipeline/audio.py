"""D1 Audio extraction and chunking (plan §2.4): the narration of a video → FLAC chunks small
enough for the transcription API's 25 MB file limit, each knowing where it starts in the video.

The surgeon's narration is transcribed later (D2), chunk by chunk, with word times relative to the
chunk. A word's time in the video is its chunk's `offset_s` plus its time in the chunk, so:
- **Chunks are cut at pauses**, so no sentence is split. A pause is a silence: every sample below
  `silence_db` (dBFS) for at least `min_silence_s`, found with FFmpeg's `silencedetect`. A chunk
  starting at `offset` aims to end at `offset + max_chunk_s` (the target). It is cut inside the
  latest pause that overlaps the last `search_window_s` before the target, at the middle of the
  pause, or as close to it as that window allows. Chunks cut at a pause don't overlap.
- **No pause in the window → a hard cut at the target.** The next chunk then starts
  `hard_cut_overlap_s` earlier, so a word (up to that long) cut by the hard cut is whole in the
  next chunk. D2 must drop the words it hears twice in that overlap.
- The chunks cover the audio from 0 to its end with no gap, and the last one ends at the end. No
  chunk is longer than `max_chunk_s`. A target less than `MIN_LAST_CHUNK_S` before the end moves
  back, so the last chunk is never a sliver.
- `offset_s` is float seconds from the start of the video, rounded down to the millisecond
  (16 samples at 16 kHz, so a cut lands exactly on a sample). An audio track that starts after the
  video is padded with silence at the start, and gaps in its timestamps are filled, so the time of
  a sample in the chunks is its time in the video.

How: one FFmpeg pass decodes the first audio track to a 16 kHz mono 16-bit FLAC in a work folder
while `silencedetect` lists the pauses. Each chunk is then cut from that FLAC with `-ss` and `-t`
before `-i` (FFmpeg seeks, decodes and trims to the sample) and checked: FLAC, 16 kHz, mono, the
planned duration ±0.1 s, and no more than `max_bytes`.

Writes into a folder the caller passes in: `chunk_000.flac`, `chunk_001.flac`, … (FLAC 16 kHz mono:
lossless, about half the size of WAV, and accepted by the transcription API) and `chunks.json`:
`{"source" (file name), "max_chunk_s", "chunks": [{"index", "file", "offset_s", "duration_s"}]}`.

- **A chunk above `max_bytes` raises `MediaError`; it isn't split further.** With the defaults it
  can't happen: 16-bit mono 16 kHz audio is 32 kB/s before compression, and FLAC never makes it
  more than a few bytes per frame larger, so a 600 s chunk is at most about 19.3 MB.
- **A source without an audio track raises `MediaError("… has no audio track")`** before anything
  is written. B3 gives such a source a `video.mp4` without audio; the caller should skip D1 then.
- Nothing half-written is left behind: everything is written into a work folder, then moved into
  place, `chunks.json` last. A failed run leaves earlier chunks as they were.
- A re-run replaces earlier `chunk_*.flac` files and `chunks.json`, and leaves other files alone.

Case JSON files are not this stage's job (D-063).
"""

import json
import math
import os
import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from scrubgpt_brain.engines.media import MediaError, probe, run, tool

SAMPLE_RATE = 16_000
"""16 kHz mono 16-bit, as B3 writes it: what speech recognition uses; more adds bytes, not words."""
MAX_CHUNK_S = 600.0
"""10 min: under 20 MB as FLAC even for audio that doesn't compress, and a retried request repeats
at most 10 min of audio."""
MAX_BYTES = 24_000_000
"""Below the API's 25 MB upload limit, with room for the rest of the request."""
SILENCE_DB = -30.0
"""A pause has every sample below -30 dBFS: speech peaks far above it, quiet room noise stays
below it."""
MIN_SILENCE_S = 0.5
"""A pause between sentences; the gaps between words are shorter (about 0.1–0.3 s)."""
SEARCH_WINDOW_S = 60.0
"""Look for a pause in the last minute before the target, so with the defaults every chunk but the
last is about 9 min long or more. Capped at half of `max_chunk_s`."""
HARD_CUT_OVERLAP_S = 1.0
"""Longer than most spoken words, so a word cut by a hard cut is whole in the next chunk."""
MIN_CHUNK_S = 10.0
"""The smallest `max_chunk_s` allowed: shorter chunks give the transcription too little context."""
MIN_LAST_CHUNK_S = 1.0
"""The last chunk is at least this long (when the audio is): the API refuses audio under 0.1 s."""
DURATION_TOLERANCE_S = 0.1
INDEX_NAME = "chunks.json"
WORK_DIR = "chunks.part"
FFMPEG_TIMEOUT_S = 6 * 3600
_FULL_NAME = "full.flac"
_CHUNK_FILE = re.compile(r"^chunk_\d{3,}\.flac$")
_SILENCE = re.compile(
    r"\[(?:Parsed_)?silencedetect[^\]]*\]\s*silence_(start|end):\s*(-?\d+(?:\.\d+)?(?:e[-+]?\d+)?)"
)


@dataclass(frozen=True)
class AudioChunk:
    """One chunk of the audio track."""

    index: int
    path: Path
    offset_s: float
    """Where the chunk starts in the source: seconds from the start of the video."""
    duration_s: float


@dataclass(frozen=True)
class _Audio:
    codec: str
    rate: int
    channels: int
    duration_s: float


def chunk_name(index: int) -> str:
    """`chunk_name(3)` → `"chunk_003.flac"`."""
    return f"chunk_{index:03d}.flac"


def _ms(t: float) -> float:
    """`t` rounded down to the millisecond (the 1e-6 absorbs float error such as 25.9999999)."""
    return math.floor(t * 1000 + 1e-6) / 1000


def _window(max_chunk_s: float, search_window_s: float, hard_cut_overlap_s: float) -> float:
    """Checks the cut settings; returns the search window, capped at half of `max_chunk_s`."""
    if not max_chunk_s >= MIN_CHUNK_S:
        raise ValueError(f"max_chunk_s must be at least {MIN_CHUNK_S:g} s, not {max_chunk_s}")
    if not search_window_s >= 0:
        raise ValueError(f"search_window_s must be 0 or more, not {search_window_s}")
    if not 0 <= hard_cut_overlap_s <= max_chunk_s / 2:
        raise ValueError(
            "hard_cut_overlap_s must be between 0 and half of max_chunk_s, "
            f"not {hard_cut_overlap_s}"
        )
    return min(search_window_s, max_chunk_s / 2)


def plan_chunks(
    duration_s: float,
    silences: Sequence[tuple[float, float]],
    *,
    max_chunk_s: float = MAX_CHUNK_S,
    search_window_s: float = SEARCH_WINDOW_S,
    hard_cut_overlap_s: float = HARD_CUT_OVERLAP_S,
) -> list[tuple[float, float]]:
    """`(offset_s, duration_s)` of each chunk of a `duration_s` long track whose pauses are
    `silences` (`(start, end)` in seconds), by the cut rule in the module docstring. No FFmpeg.

    The window is capped at half of `max_chunk_s`, so a chunk that isn't the last is never much
    shorter than half of `max_chunk_s`; a chunk ending at a hard cut is exactly `max_chunk_s` long
    (unless its target moved back from the end of the track).
    """
    window = _window(max_chunk_s, search_window_s, hard_cut_overlap_s)
    pauses = sorted(silences)
    spans: list[tuple[float, float]] = []
    offset = 0.0
    while duration_s - offset > max_chunk_s:
        target = min(offset + max_chunk_s, duration_s - MIN_LAST_CHUNK_S)
        low = target - window
        cut = None
        for start, end in pauses:
            inside_start, inside_end = max(start, low), min(end, target)
            if inside_end > inside_start:  # the pause overlaps the window; a later one wins
                cut = min(max((start + end) / 2, inside_start), inside_end)
        if cut is None:
            end_s = _ms(target)
            next_offset = _ms(end_s - hard_cut_overlap_s)
        else:
            end_s = next_offset = _ms(cut)
        spans.append((offset, round(end_s - offset, 6)))
        offset = next_offset
    spans.append((offset, round(duration_s - offset, 6)))
    return spans


def parse_silences(log: str, end_s: float) -> list[tuple[float, float]]:
    """The pauses FFmpeg's `silencedetect` printed in `log`, as `(start, end)` seconds within
    `0…end_s`. A pause still open at the end of the log ends at `end_s`."""
    pauses: list[tuple[float, float]] = []
    start: float | None = None
    for kind, value in _SILENCE.findall(log):
        if kind == "start":
            start = float(value)
        elif start is not None:
            pauses.append((start, float(value)))
            start = None
    if start is not None:
        pauses.append((start, end_s))
    clipped = [(max(0.0, a), min(b, end_s)) for a, b in pauses]
    return [(a, b) for a, b in clipped if b > a]


def _audio_info(path: Path) -> _Audio:
    """What ffprobe says about the first audio stream of `path`."""
    args = [tool("ffprobe"), "-v", "error", "-select_streams", "a:0", "-print_format", "json"]
    args += ["-show_entries", "stream=codec_name,sample_rate,channels,duration:format=duration"]
    result = run([*args, str(path)], timeout=120)
    try:
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        return _Audio(
            codec=str(stream["codec_name"]),
            rate=int(stream["sample_rate"]),
            channels=int(stream["channels"]),
            duration_s=float(stream.get("duration") or data["format"]["duration"]),
        )
    except (ValueError, KeyError, IndexError, TypeError):
        raise MediaError(f"ffprobe found no readable audio stream in {path}") from None


def _decode(source: Path, target: Path, *, silence_db: float, min_silence_s: float) -> str:
    """Decode the first audio track of `source` to 16 kHz mono 16-bit FLAC; returns FFmpeg's log,
    which lists the pauses."""
    # first_pts=0 pads a track that starts after the video with silence, and async=1 fills gaps in
    # its timestamps, so a sample's place in the FLAC is its time in the video.
    af = f"aresample=async=1:first_pts=0,aformat=sample_fmts=s16:sample_rates={SAMPLE_RATE}"
    af += f":channel_layouts=mono,silencedetect=noise={silence_db}dB:duration={min_silence_s}"
    args = [tool("ffmpeg"), "-hide_banner", "-nostdin", "-nostats", "-y", "-v", "info"]
    args += ["-i", str(source), "-map", "0:a:0", "-vn", "-sn", "-dn", "-af", af]
    args += ["-c:a", "flac", "-f", "flac", str(target)]
    return run(args, timeout=FFMPEG_TIMEOUT_S).stderr


def _cut(full: Path, offset_s: float, duration_s: float, target: Path) -> None:
    # -ss and -t before -i: FFmpeg seeks, then decodes and trims to the exact sample.
    args = [tool("ffmpeg"), "-hide_banner", "-nostdin", "-y", "-v", "error"]
    args += ["-ss", f"{offset_s:.6f}", "-t", f"{duration_s:.6f}", "-i", str(full)]
    args += ["-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "flac"]
    args += ["-f", "flac", str(target)]
    run(args, timeout=600)


def _check_chunk(path: Path, duration_s: float, max_bytes: int) -> None:
    audio = _audio_info(path)
    if (audio.codec, audio.rate, audio.channels) != ("flac", SAMPLE_RATE, 1):
        raise MediaError(
            f"{path.name} is {audio.codec}, {audio.rate} Hz, {audio.channels} channel(s), "
            f"not FLAC, {SAMPLE_RATE} Hz, mono"
        )
    if abs(audio.duration_s - duration_s) > DURATION_TOLERANCE_S:
        raise MediaError(f"{path.name} is {audio.duration_s:.3f} s long, not {duration_s:.3f} s")
    size = path.stat().st_size
    if size > max_bytes:
        raise MediaError(
            f"{path.name} is {size:,} bytes, above the {max_bytes:,}-byte limit: "
            "use a smaller max_chunk_s"
        )


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def chunk_audio(
    source: Path,
    out_dir: Path,
    *,
    max_chunk_s: float = MAX_CHUNK_S,
    max_bytes: int = MAX_BYTES,
    silence_db: float = SILENCE_DB,
    min_silence_s: float = MIN_SILENCE_S,
    search_window_s: float = SEARCH_WINDOW_S,
    hard_cut_overlap_s: float = HARD_CUT_OVERLAP_S,
) -> list[AudioChunk]:
    """Cut the audio track of `source` (a video, normally B3's `video.mp4`) into FLAC chunks in
    `out_dir`; returns them in order.

    Raises `ValueError` for a bad setting, and `MediaError` if the source is missing, isn't a video
    or has no audio track, if FFmpeg fails, or if a chunk is above `max_bytes`. Then no new chunk is
    left in `out_dir`, and earlier ones are not touched.
    """
    _window(max_chunk_s, search_window_s, hard_cut_overlap_s)
    if max_bytes <= 0:
        raise ValueError(f"max_bytes must be positive, not {max_bytes}")
    if not silence_db < 0:
        raise ValueError(f"silence_db must be below 0 dBFS, not {silence_db}")
    if not min_silence_s > 0:
        raise ValueError(f"min_silence_s must be positive, not {min_silence_s}")
    if not probe(source).has_audio:
        raise MediaError(f"{source} has no audio track")

    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / WORK_DIR
    _remove(work)
    work.mkdir()
    try:
        full = work / _FULL_NAME
        log = _decode(source, full, silence_db=silence_db, min_silence_s=min_silence_s)
        total_s = _audio_info(full).duration_s
        if total_s <= 0:
            raise MediaError(f"no audio could be decoded from {source}")
        spans = plan_chunks(
            total_s,
            parse_silences(log, total_s),
            max_chunk_s=max_chunk_s,
            search_window_s=search_window_s,
            hard_cut_overlap_s=hard_cut_overlap_s,
        )
        chunks: list[AudioChunk] = []
        for index, (offset_s, duration_s) in enumerate(spans):
            part = work / chunk_name(index)
            _cut(full, offset_s, duration_s, part)
            _check_chunk(part, duration_s, max_bytes)
            chunks.append(
                AudioChunk(
                    index=index, path=out_dir / part.name, offset_s=offset_s, duration_s=duration_s
                )
            )
        full.unlink()
        index_doc = {
            "source": source.name,  # the file name only: no machine-specific path in the index
            "max_chunk_s": max_chunk_s,
            "chunks": [
                {
                    "index": c.index,
                    "file": c.path.name,
                    "offset_s": c.offset_s,
                    "duration_s": c.duration_s,
                }
                for c in chunks
            ],
        }
        (work / INDEX_NAME).write_text(json.dumps(index_doc, indent=2) + "\n", encoding="utf-8")
    except BaseException:
        _remove(work)
        raise

    try:
        (out_dir / INDEX_NAME).unlink(missing_ok=True)
        for old in out_dir.iterdir():
            if _CHUNK_FILE.match(old.name):
                old.unlink()
        for chunk in chunks:
            os.replace(work / chunk.path.name, chunk.path)
        os.replace(work / INDEX_NAME, out_dir / INDEX_NAME)
    finally:
        _remove(work)
    return chunks
