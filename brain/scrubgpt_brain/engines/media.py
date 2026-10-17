"""FFmpeg CLI helpers for the pipeline: probe a file, run a command, check an image.

No OpenCV, PyTorch or CUDA (brain/CLAUDE.md rule 11): video work goes through the FFmpeg CLI, and
images are checked with Pillow, so everything runs on x64 and ARM64.
"""

import json
import shutil
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from PIL import Image, UnidentifiedImageError


class MediaError(Exception):
    """A media file is missing, isn't a video, or FFmpeg failed on it."""


def tool(name: str) -> str:
    """The path of an FFmpeg CLI tool (`ffmpeg`, `ffprobe`), or `MediaError` if it isn't on PATH."""
    path = shutil.which(name)
    if path is None:
        raise MediaError(f"{name} not found on PATH: install FFmpeg (docs/ONBOARDING.md)")
    return path


def run(args: list[str], *, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    """Run an FFmpeg CLI command. A non-zero exit or a timeout raises `MediaError` with the last
    lines of its stderr."""
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        tail = " | ".join((exc.stderr or "").strip().splitlines()[-3:])
        raise MediaError(
            f"{Path(args[0]).stem} failed: {tail or f'exit {exc.returncode}'}"
        ) from None
    except subprocess.TimeoutExpired:
        raise MediaError(f"{Path(args[0]).stem} timed out after {timeout} s") from None
    except OSError as exc:
        raise MediaError(f"can't run {args[0]}: {exc}") from None


@dataclass(frozen=True)
class MediaInfo:
    """What ffprobe says about a video file."""

    duration_s: float
    width: int
    height: int
    display_aspect: float
    """Width / height as displayed (storage size times the sample aspect ratio)."""
    fps: float | None
    video_codec: str
    has_audio: bool
    audio_codec: str | None
    audio_rate: int | None
    audio_channels: int | None


def _ratio(text: str | None) -> Fraction | None:
    if not text or text in ("0/0", "N/A"):
        return None
    try:
        value = Fraction(text.replace(":", "/"))
    except (ValueError, ZeroDivisionError):
        return None
    return value if value > 0 else None


def probe(path: Path) -> MediaInfo:
    """Probe a video file. Raises `MediaError` if it is missing, unreadable, has no video stream
    (a still image or an audio file counts as no video) or has no known duration."""
    if not path.is_file():
        raise MediaError(f"not a file: {path}")
    result = run(
        [tool("ffprobe"), "-v", "error", "-print_format", "json", "-show_format"]
        + ["-show_streams", str(path)],
        timeout=120,
    )
    try:
        data = json.loads(result.stdout)
    except ValueError:
        raise MediaError(f"ffprobe gave no readable output for {path}") from None
    streams = data.get("streams", [])
    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        ),
        None,
    )
    if video is None:
        raise MediaError(f"no video stream in {path}")
    try:
        duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    except ValueError:
        duration = 0.0
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    fps = _ratio(video.get("avg_frame_rate")) or _ratio(video.get("r_frame_rate"))
    # ffprobe opens a still image as a one-frame "video" in an image container: not a video here.
    container = str(data.get("format", {}).get("format_name", ""))
    still = container == "image2" or container.endswith("_pipe")
    if still or duration <= 0 or width <= 0 or height <= 0:
        raise MediaError(f"not a video (no duration or frame size): {path}")
    sar = _ratio(video.get("sample_aspect_ratio")) or Fraction(1)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    return MediaInfo(
        duration_s=duration,
        width=width,
        height=height,
        display_aspect=float(Fraction(width) * sar / height),
        fps=float(fps) if fps else None,
        video_codec=str(video.get("codec_name")),
        has_audio=audio is not None,
        audio_codec=str(audio.get("codec_name")) if audio else None,
        audio_rate=int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
        audio_channels=int(audio["channels"]) if audio and audio.get("channels") else None,
    )


def check_image(path: Path) -> tuple[int, int]:
    """The `(width, height)` of an image file, or `MediaError` if Pillow can't decode it."""
    try:
        with Image.open(path) as image:
            image.load()
            return image.size
    except (OSError, UnidentifiedImageError) as exc:
        raise MediaError(f"not a decodable image: {path} ({exc})") from None
