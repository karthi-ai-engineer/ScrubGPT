"""B3 Normaliser (plan §2.2): one source video → the normalised media of a case.

Writes into a folder the caller passes in (D-063):
- `video.mp4`: H.264, 720 px high (aspect ratio kept, even width, square pixels), a keyframe every
  2 s (so clips cut with `-c copy` and frame seeks stay close), "faststart" (`moov` before `mdat`),
  and one AAC audio track, mono, 16 kHz. **A source without audio gives a `video.mp4` without an
  audio track** (`has_audio` is false), never a silent made-up one: later audio stages skip it.
- `poster.jpg`: one frame at 10 % of the video, so it isn't the black first frame.
- `thumbs/`: thumbnail strips for the player's seek bar: `strip_000.jpg`, … each holding
  `STRIP_TILES` thumbnails side by side, one every `thumb_interval_s` seconds from 0, plus
  `index.json` (`interval_s`, `tile`, `thumb_height`, `strips`).

Nothing half-written is left behind: each output is written under a temporary name and moved into
place only when it is complete. Case JSON files are not this stage's job (D-063).
"""

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from scrubgpt_brain.engines.media import MediaError, check_image, probe, run, tool

VIDEO_NAME = "video.mp4"
POSTER_NAME = "poster.jpg"
THUMBS_DIR = "thumbs"
TARGET_HEIGHT = 720
AUDIO_RATE = 16_000
KEYFRAME_INTERVAL_S = 2
POSTER_AT = 0.10
THUMB_INTERVAL_S = 10.0
THUMB_HEIGHT = 90
STRIP_TILES = 10
FFMPEG_TIMEOUT_S = 6 * 3600


@dataclass(frozen=True)
class NormalizedMedia:
    """What `normalize()` wrote."""

    video: Path
    poster: Path
    thumbs: tuple[Path, ...]
    duration_s: float
    width: int
    height: int
    has_audio: bool


def _encode(source: Path, target: Path, *, height: int, has_audio: bool) -> None:
    # Width from the display aspect ratio (handles non-square source pixels), rounded to even.
    scale = f"scale=trunc({height}*dar/2)*2:{height}:flags=bicubic,setsar=1,format=yuv420p"
    args = [tool("ffmpeg"), "-hide_banner", "-nostdin", "-y", "-v", "error", "-i", str(source)]
    args += ["-map", "0:v:0", "-vf", scale, "-c:v", "libx264", "-preset", "veryfast"]
    args += ["-crf", "23", "-force_key_frames", f"expr:gte(t,n_forced*{KEYFRAME_INTERVAL_S})"]
    if has_audio:
        args += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-ar", str(AUDIO_RATE)]
    else:
        args += ["-an"]
    args += ["-sn", "-dn", "-movflags", "+faststart", "-f", "mp4", str(target)]
    run(args, timeout=FFMPEG_TIMEOUT_S)


def _poster(video: Path, target: Path, at_s: float) -> None:
    args = [tool("ffmpeg"), "-hide_banner", "-nostdin", "-y", "-v", "error"]
    args += ["-ss", f"{at_s:.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "3"]
    args += ["-c:v", "mjpeg", "-update", "1", "-f", "image2", str(target)]
    run(args, timeout=600)
    check_image(target)


def _thumb_strips(video: Path, folder: Path, interval_s: float) -> list[Path]:
    pattern = folder / "strip_%03d.jpg"
    # The first frame of each interval (0, N, 2N, … s). `select` rather than `fps`: `fps` emits
    # nothing for a video shorter than half an interval.
    bucket, previous = f"floor(t/{interval_s})", f"floor(prev_selected_t/{interval_s})"
    pick = f"select='isnan(prev_selected_t)+gte({bucket}\\,{previous}+1)'"
    vf = f"{pick},scale=-2:{THUMB_HEIGHT},tile={STRIP_TILES}x1"
    args = [tool("ffmpeg"), "-hide_banner", "-nostdin", "-y", "-v", "error", "-i", str(video)]
    args += ["-an", "-vf", vf, "-fps_mode", "vfr", "-q:v", "4", "-start_number", "0"]
    args += ["-f", "image2", str(pattern)]
    run(args, timeout=FFMPEG_TIMEOUT_S)
    strips = sorted(folder.glob("strip_*.jpg"))
    if not strips:
        raise MediaError(f"ffmpeg wrote no thumbnail strip for {video}")
    for strip in strips:
        check_image(strip)
    index = {
        "interval_s": interval_s,
        "tile": [STRIP_TILES, 1],
        "thumb_height": THUMB_HEIGHT,
        "strips": [strip.name for strip in strips],
    }
    (folder / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return strips


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def normalize(
    source: Path,
    out_dir: Path,
    *,
    height: int = TARGET_HEIGHT,
    thumb_interval_s: float = THUMB_INTERVAL_S,
) -> NormalizedMedia:
    """Normalise `source` into `out_dir` (`video.mp4`, `poster.jpg`, `thumbs/`).

    Raises `MediaError` if the source is missing or isn't a video, or if FFmpeg fails. Then no new
    `video.mp4` is left in `out_dir`, and an existing one is not touched.
    """
    if height <= 0 or height % 2:
        raise ValueError(f"height must be a positive even number, not {height}")
    if thumb_interval_s <= 0:
        raise ValueError(f"thumb_interval_s must be positive, not {thumb_interval_s}")
    info = probe(source)
    out_dir.mkdir(parents=True, exist_ok=True)

    video, video_part = out_dir / VIDEO_NAME, out_dir / f"{VIDEO_NAME}.part"
    poster, poster_part = out_dir / POSTER_NAME, out_dir / f"{POSTER_NAME}.part"
    thumbs, thumbs_part = out_dir / THUMBS_DIR, out_dir / f"{THUMBS_DIR}.part"
    try:
        _encode(source, video_part, height=height, has_audio=info.has_audio)
        result = probe(video_part)
        _poster(video_part, poster_part, result.duration_s * POSTER_AT)
        _remove(thumbs_part)
        thumbs_part.mkdir()
        strips = _thumb_strips(video_part, thumbs_part, thumb_interval_s)
    except BaseException:
        for part in (video_part, poster_part, thumbs_part):
            _remove(part)
        raise

    os.replace(video_part, video)
    os.replace(poster_part, poster)
    _remove(thumbs)
    os.replace(thumbs_part, thumbs)
    return NormalizedMedia(
        video=video,
        poster=poster,
        thumbs=tuple(thumbs / strip.name for strip in strips),
        duration_s=result.duration_s,
        width=result.width,
        height=result.height,
        has_audio=result.has_audio,
    )
