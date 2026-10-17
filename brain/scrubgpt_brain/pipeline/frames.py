"""C1 Frame sampler (plan §2.3): one frame every N seconds (default 5), plus extra frames where the
scene changes.

Timestamps are floats in seconds from the start of the (normalised) video, as everywhere in the
system. Interval frames sit at 0, N, 2N, … below the duration. Scene frames come from FFmpeg's
`scene` score (0–1, how much a frame differs from the one before): a frame scoring above
`scene_threshold` is a cut (camera out of the body, a hard edit, a change of view). Scene frames
closer than `min_scene_gap_s` to the previous one are dropped, so a flicker gives one frame, and a
scene frame on the same video frame as an interval frame isn't added twice.

Files are named by time in milliseconds (`000025000.jpg` = 25.0 s), next to a `frames.json` index:
`{"interval_s", "scene_threshold", "frames": [{"t", "file", "reason"}]}`, sorted by `t`.
Case JSON files are not this stage's job (D-063).
"""

import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from scrubgpt_brain.engines.media import MediaError, check_image, probe, run, tool

DEFAULT_INTERVAL_S = 5.0
SCENE_THRESHOLD = 0.3
MIN_SCENE_GAP_S = 1.0
INDEX_NAME = "frames.json"
_FRAME_FILE = re.compile(r"^\d{9}\.jpg$")
_PTS_TIME = re.compile(r"pts_time:\s*([0-9]+(?:\.[0-9]+)?)")
_SEEK_PAST_S = 0.001
"""Seek a hair past a scene frame's printed time, so rounding can't land on the frame before."""

Reason = Literal["interval", "scene"]


@dataclass(frozen=True)
class Frame:
    """One sampled frame."""

    t: float
    """Seconds from the start of the video."""
    path: Path
    reason: Reason


def load_frames(folder: Path) -> list[tuple[float, Path]]:
    """The `(t, path)` pairs of a frame folder this module wrote (its `frames.json`), by time.

    Raises `FileNotFoundError` if the index is missing, `ValueError` if it isn't a C1 index."""
    index = folder / INDEX_NAME
    text = index.read_text(encoding="utf-8")
    try:
        frames = [(float(item["t"]), folder / item["file"]) for item in json.loads(text)["frames"]]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"not a C1 frames index: {index} ({exc})") from None
    return sorted(frames, key=lambda frame: frame[0])


def frame_name(t: float) -> str:
    """`frame_name(25.0)` → `"000025000.jpg"` (milliseconds, so files sort by time)."""
    return f"{round(t * 1000):09d}.jpg"


def interval_times(duration_s: float, interval_s: float) -> list[float]:
    """0, N, 2N, … strictly below the duration."""
    count = math.ceil(duration_s / interval_s - 1e-9)
    return [float(round(i * interval_s, 6)) for i in range(count) if i * interval_s < duration_s]


def scene_times(video: Path, threshold: float = SCENE_THRESHOLD) -> list[float]:
    """Times of the frames whose scene score is above `threshold` (one decoding pass)."""
    # A small copy of each frame is enough to score it, and much faster.
    vf = f"scale=160:-2,select='gt(scene\\,{threshold})',showinfo"
    args = [tool("ffmpeg"), "-hide_banner", "-nostdin", "-v", "info", "-i", str(video)]
    args += ["-an", "-sn", "-vf", vf, "-f", "null", "-"]
    result = run(args, timeout=6 * 3600)
    times = [float(m.group(1)) for m in _PTS_TIME.finditer(result.stderr)]
    return sorted(t for t in times if t > 0)


def _extract(video: Path, t: float, target: Path) -> None:
    args = [tool("ffmpeg"), "-hide_banner", "-nostdin", "-y", "-v", "error"]
    args += ["-ss", f"{t:.6f}", "-i", str(video), "-frames:v", "1", "-q:v", "2"]
    args += ["-c:v", "mjpeg", "-update", "1", "-f", "image2", str(target)]
    run(args, timeout=600)
    if not target.is_file():
        raise MediaError(f"ffmpeg wrote no frame at {t} s of {video}")
    check_image(target)


def sample_frames(
    video: Path,
    out_dir: Path,
    *,
    interval_s: float = DEFAULT_INTERVAL_S,
    scene_threshold: float | None = SCENE_THRESHOLD,
    min_scene_gap_s: float = MIN_SCENE_GAP_S,
    workers: int | None = None,
) -> list[Frame]:
    """Sample frames from `video` into `out_dir`; returns them sorted by time.

    `scene_threshold=None` skips the scene frames. Raises `MediaError` if the video is missing or
    isn't a video, or if FFmpeg fails. Earlier frames in `out_dir` (files named like `frame_name()`
    and `frames.json`) are replaced; other files are left alone.
    """
    if interval_s <= 0:
        raise ValueError(f"interval_s must be positive, not {interval_s}")
    if scene_threshold is not None and not 0 < scene_threshold < 1:
        raise ValueError(f"scene_threshold must be between 0 and 1, not {scene_threshold}")
    info = probe(video)
    frame_s = 1 / info.fps if info.fps else 0.04

    wanted: list[tuple[float, Reason]] = [
        (t, "interval") for t in interval_times(info.duration_s, interval_s)
    ]
    if scene_threshold is not None:
        last_scene = -math.inf
        for t in scene_times(video, scene_threshold):
            if t - last_scene < min_scene_gap_s or t >= info.duration_s:
                continue
            last_scene = t
            if all(abs(t - other) >= frame_s / 2 for other, _ in wanted):
                wanted.append((t, "scene"))
    wanted.sort()

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.iterdir():
        if _FRAME_FILE.match(old.name) or old.name == INDEX_NAME:
            old.unlink()
    frames = [Frame(t=t, path=out_dir / frame_name(t), reason=reason) for t, reason in wanted]

    def extract(frame: Frame) -> None:
        seek = frame.t + _SEEK_PAST_S if frame.reason == "scene" else frame.t
        _extract(video, seek, frame.path)

    with ThreadPoolExecutor(max_workers=workers or min(4, os.cpu_count() or 1)) as pool:
        list(pool.map(extract, frames))

    index = {
        "interval_s": interval_s,
        "scene_threshold": scene_threshold,
        "frames": [{"t": f.t, "file": f.path.name, "reason": f.reason} for f in frames],
    }
    (out_dir / INDEX_NAME).write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return frames
