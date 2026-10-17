"""C5 Event detection, pixel-signal part (plan §2.3): cheap per-frame measures that point at the
spans worth a GPT check.

C5 looks for bleeding, the camera out of the body, and idle pauses. Asking GPT about every frame of
a long video is slow and costly, so this module first scores each C1 frame with plain pixel maths
(numpy, no model) and returns *candidate* spans: places where something might be happening. A
later GPT check confirms or rejects each one; nothing here claims that an event happened.

Each frame is downscaled to `ANALYSIS_WIDTH` px wide, then measured (`FrameSignals`):
- **blood ratio** (0–1): the fraction of "blood" pixels, a dark, saturated red (`BLOOD_*`);
- **out-of-body score** (0–1): inside the patient the view is mostly lit, warm tissue (red, pink,
  orange, yellow). The score is the fraction of pixels that are *not*: dark pixels (a covered
  lens) plus lit pixels of a cool or neutral colour (drapes, theatre lights, walls);
- **change** (0–255): the mean absolute pixel difference to the previous frame; a pause barely
  changes the view.

Frames that meet a threshold form a run, and runs become spans as `find_candidates` describes.

The thresholds are placeholders, tuned on synthetic frames only. The real tuning happens on GraSP
data in Block 2, never on the test videos we report (brain/CLAUDE.md rule 8).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image

# Frames are downscaled to this width (px) before measuring: enough for colour fractions, and fast.
FALLBACK_INTERVAL_S = 5.0  # C1's default spacing, for a series of a single frame
ANALYSIS_WIDTH = 160

# Bleeding. A pixel is "blood" when its red channel is between BLOOD_MIN_RED and BLOOD_MAX_RED
# and at least BLOOD_RED_FACTOR times both its green and its blue channel (all 0–255).
BLOOD_RED_FACTOR = 2.5  # pink or orange tissue has red only ~1.3–2 times green and blue
BLOOD_MIN_RED = 40  # darker than this is black, not blood we can see
BLOOD_MAX_RED = 220  # a brighter red is lit tissue or a highlight, not blood
MIN_BLOOD_RATIO = 0.25  # a bleeding frame has at least 25 % blood pixels

# Out of body. A pixel is "warm tissue" when it is lit, coloured and of a warm hue.
DARK_MAX_VALUE = 40  # a pixel whose brightest channel is below this (0–255) is dark, never warm
WARM_MIN_SATURATION = 0.2  # greyer pixels (white walls, lights, smoke) are not warm
WARM_HUE_FROM_DEG = 320.0  # warm hues run from pink (320°) through red (0°) ...
WARM_HUE_TO_DEG = 70.0  # ... and orange to yellow (70°)
MIN_OUT_OF_BODY_SCORE = 0.75  # an out-of-body frame has at most 25 % lit warm-tissue pixels

# Idle. A frame is still when its change to the previous frame is at most MAX_IDLE_CHANGE.
MAX_IDLE_CHANGE = 3.0  # mean absolute difference per pixel and channel, 0–255

# Spans.
MIN_SPAN_S = 10.0  # shorter spans are dropped: with C1's 5 s frames, a span needs 2 frames
MAX_GAP_FRAMES = 1  # runs of one kind with at most 1 frame between them that misses are merged

CandidateKind = Literal["bleeding", "out_of_body", "idle"]
ImageSource = Image.Image | Path
"""A frame: a Pillow image, or the path of an image file (C1 writes JPEGs)."""
_KINDS: tuple[CandidateKind, ...] = ("bleeding", "out_of_body", "idle")


@dataclass(frozen=True)
class FrameSignals:
    """The pixel measures of one frame."""

    t: float
    """Seconds from the start of the video."""
    blood_ratio: float
    """Fraction of the pixels that are blood (0–1)."""
    warm_ratio: float
    """Fraction of the pixels that are lit, warm tissue (0–1)."""
    dark_ratio: float
    """Fraction of the pixels that are dark (0–1); a dark pixel is never warm tissue."""
    change: float | None
    """Mean absolute pixel difference to the previous frame (0–255); `None` for the first."""

    @property
    def out_of_body_score(self) -> float:
        """`1 - warm_ratio`: the dark pixels plus the lit ones that aren't warm (0–1)."""
        return 1.0 - self.warm_ratio


@dataclass(frozen=True)
class Candidate:
    """A span where a pixel signal suggests an event: a *candidate* for the GPT check, never a
    confirmed event.

    `score` is higher for a stronger signal, averaged over the frames of the span that met the
    threshold:
    - `bleeding`: their blood ratio (0–1, at least `min_blood_ratio`);
    - `out_of_body`: their out-of-body score (0–1, at least `min_out_of_body`);
    - `idle`: how still the view was, `1 - change / max_idle_change` (0–1; 1 = identical frames).
    """

    kind: CandidateKind
    t_start: float
    """Seconds: the time of the span's first frame."""
    t_end: float
    """Seconds: the last frame's time plus one sampling interval, but never past the next frame."""
    score: float
    status: Literal["candidate"] = "candidate"
    """Always `"candidate"`: only the GPT check that follows can confirm an event."""


def _check_times(times: Sequence[float]) -> None:
    if any(later <= earlier for earlier, later in pairwise(times)):
        raise ValueError("frame times must be strictly increasing (sorted, no duplicates)")


def _downscale(source: ImageSource, width: int, size: tuple[int, int] | None) -> Image.Image:
    """`source` in RGB at `size`, or `width` px wide with its own aspect ratio if `size` is None."""
    if isinstance(source, Image.Image):
        image = source.convert("RGB")
    else:
        with Image.open(source) as opened:
            # JPEG only: decode at 1/2, 1/4 or 1/8 scale (still at least `width` wide); much faster.
            opened.draft("RGB", size or (width, max(1, width * opened.height // opened.width)))
            image = opened.convert("RGB")
    if size is None:
        size = (width, max(1, round(width * image.height / image.width)))
    return image.resize(size, Image.Resampling.BILINEAR)


def _ratios(image: Image.Image) -> tuple[float, float, float]:
    """The blood, warm-tissue and dark fractions of an RGB image."""
    rgb = np.asarray(image, dtype=np.float32)
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    blood = (
        (red >= BLOOD_MIN_RED)
        & (red <= BLOOD_MAX_RED)
        & (red >= BLOOD_RED_FACTOR * np.maximum(green, blue))
    )
    # Pillow's HSV: hue, saturation and value all on 0–255 (a hue of 255 is 360°).
    hsv = np.asarray(image.convert("HSV"), dtype=np.float32)
    hue_deg, saturation, value = hsv[..., 0] * (360 / 255), hsv[..., 1] / 255, hsv[..., 2]
    dark = value < DARK_MAX_VALUE
    warm_hue = (hue_deg >= WARM_HUE_FROM_DEG) | (hue_deg <= WARM_HUE_TO_DEG)  # wraps through 0°
    warm = ~dark & (saturation >= WARM_MIN_SATURATION) & warm_hue
    return float(blood.mean()), float(warm.mean()), float(dark.mean())


def measure_frames(
    frames: Sequence[tuple[float, ImageSource]], *, width: int = ANALYSIS_WIDTH
) -> list[FrameSignals]:
    """Measure a time-sorted series of `(t, image)` frames, each downscaled to `width` px wide.

    Every frame is resized to the size of the first one, so the changes compare like with like.
    Raises `ValueError` if the times aren't strictly increasing; a missing or undecodable image
    file raises Pillow's error."""
    if width < 1:
        raise ValueError(f"width must be at least 1, not {width}")
    _check_times([t for t, _ in frames])
    signals: list[FrameSignals] = []
    size: tuple[int, int] | None = None
    previous: np.ndarray | None = None
    for t, source in frames:
        image = _downscale(source, width, size)
        size = image.size
        pixels = np.asarray(image, dtype=np.int16)
        change = None if previous is None else float(np.abs(pixels - previous).mean())
        previous = pixels
        blood, warm, dark = _ratios(image)
        signals.append(FrameSignals(float(t), blood, warm, dark, change))
    return signals


def _runs(flags: Sequence[bool], max_gap: int) -> list[tuple[int, int]]:
    """`(first, last)` indices of the runs of `True`, joining runs at most `max_gap` apart."""
    runs: list[tuple[int, int]] = []
    for i, flag in enumerate(flags):
        if not flag:
            continue
        if runs and i - runs[-1][1] - 1 <= max_gap:
            runs[-1] = (runs[-1][0], i)
        else:
            runs.append((i, i))
    return runs


def _check_options(
    max_idle_change: float, min_span_s: float, max_gap_frames: int, interval_s: float | None
) -> None:
    if max_idle_change < 0:
        raise ValueError(f"max_idle_change can't be negative, not {max_idle_change}")
    if min_span_s < 0:
        raise ValueError(f"min_span_s can't be negative, not {min_span_s}")
    if max_gap_frames < 0:
        raise ValueError(f"max_gap_frames can't be negative, not {max_gap_frames}")
    if interval_s is not None and interval_s <= 0:
        raise ValueError(f"interval_s must be positive, not {interval_s}")


def find_candidates(
    signals: Sequence[FrameSignals],
    *,
    min_blood_ratio: float = MIN_BLOOD_RATIO,
    min_out_of_body: float = MIN_OUT_OF_BODY_SCORE,
    max_idle_change: float = MAX_IDLE_CHANGE,
    min_span_s: float = MIN_SPAN_S,
    max_gap_frames: int = MAX_GAP_FRAMES,
    interval_s: float | None = None,
) -> list[Candidate]:
    """Candidate spans from measured frames, sorted by `t_start` (the options are
    `detect_candidates`'). Measuring once and calling this many times lets a tuning run try
    many thresholds.

    A bleeding (or out-of-body) frame meets its threshold; a still frame changed at most
    `max_idle_change` from the frame before, and an idle run is a run of still frames plus the
    frame before the first (so `n` identical frames make one idle run of `n` frames). Runs of one
    kind with at most `max_gap_frames` frames between them that miss the threshold are merged.
    A run of the frames at `t_a … t_b` becomes the span `t_start = t_a`,
    `t_end = min(t_b + interval, the next frame's time)`, where `interval` is `interval_s` or else
    the median spacing of the frames. Spans shorter than `min_span_s` are dropped.
    """
    _check_options(max_idle_change, min_span_s, max_gap_frames, interval_s)
    times = [s.t for s in signals]
    _check_times(times)
    if not signals:
        return []
    if interval_s is None:
        interval_s = float(np.median(np.diff(times))) if len(times) > 1 else FALLBACK_INTERVAL_S
    # One value per frame; for idle, value i is the change from frame i to frame i + 1.
    blood = [s.blood_ratio for s in signals]
    out_of_body = [s.out_of_body_score for s in signals]
    change = [s.change if s.change is not None else np.inf for s in signals[1:]]
    tests = {
        "bleeding": (blood, [v >= min_blood_ratio for v in blood]),
        "out_of_body": (out_of_body, [v >= min_out_of_body for v in out_of_body]),
        "idle": (change, [v <= max_idle_change for v in change]),
    }
    found: list[Candidate] = []
    for kind in _KINDS:
        values, flags = tests[kind]
        for first, last in _runs(flags, max_gap_frames):
            hits = [values[i] for i in range(first, last + 1) if flags[i]]
            mean = float(np.mean(hits))
            if kind == "idle":
                score = 1.0 - mean / max_idle_change if max_idle_change > 0 else 1.0
                last += 1  # the run of changes first … last spans frames first … last + 1
            else:
                score = mean
            t_end = times[last] + interval_s
            if last + 1 < len(times):
                t_end = min(t_end, times[last + 1])
            if t_end - times[first] < min_span_s - 1e-9:
                continue
            found.append(
                Candidate(
                    kind=kind,
                    t_start=round(times[first], 6),
                    t_end=round(t_end, 6),
                    score=round(min(max(score, 0.0), 1.0), 4),
                )
            )
    return sorted(found, key=lambda c: (c.t_start, _KINDS.index(c.kind)))


def detect_candidates(
    frames: Sequence[tuple[float, ImageSource]],
    *,
    min_blood_ratio: float = MIN_BLOOD_RATIO,
    min_out_of_body: float = MIN_OUT_OF_BODY_SCORE,
    max_idle_change: float = MAX_IDLE_CHANGE,
    min_span_s: float = MIN_SPAN_S,
    max_gap_frames: int = MAX_GAP_FRAMES,
    interval_s: float | None = None,
    width: int = ANALYSIS_WIDTH,
) -> list[Candidate]:
    """Candidate spans of bleeding, camera out of body and idle in a time-sorted series of
    `(t, image)` frames (e.g. C1's `frames.load_frames(folder)`), sorted by `t_start`.

    - `min_blood_ratio`: a bleeding frame has at least this fraction of blood pixels;
    - `min_out_of_body`: an out-of-body frame has at least this out-of-body score;
    - `max_idle_change`: a still frame differs from the one before by at most this (0–255);
    - `min_span_s`: shorter spans are dropped;
    - `max_gap_frames`: runs of one kind this many frames apart or fewer are merged (0: never);
    - `interval_s`: the sampling interval added to a span's last frame; `None` takes the median
      spacing of the frames (C1's default 5 s for a single frame);
    - `width`: frames are downscaled to this width before measuring.

    How runs become spans: `find_candidates`. Raises `ValueError` on bad options or unsorted
    times, before decoding any frame.
    """
    _check_options(max_idle_change, min_span_s, max_gap_frames, interval_s)
    return find_candidates(
        measure_frames(frames, width=width),
        min_blood_ratio=min_blood_ratio,
        min_out_of_body=min_out_of_body,
        max_idle_change=max_idle_change,
        min_span_s=min_span_s,
        max_gap_frames=max_gap_frames,
        interval_s=interval_s,
    )
