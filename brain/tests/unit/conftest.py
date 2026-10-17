"""Synthetic media for Dev1's Brain unit tests (FFmpeg test sources only, D-036).

Tests that need FFmpeg take the `media` fixture; it skips them when the FFmpeg CLI isn't on PATH
(the CI runner has none), so they run wherever FFmpeg is installed.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


class Media:
    """Makes synthetic videos with FFmpeg's test sources and probes files."""

    @staticmethod
    def _ffmpeg(*args: str) -> None:
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-v", "error", *args], check=True
        )

    def video(
        self,
        path: Path,
        *,
        size: str = "320x240",
        duration: float = 6,
        rate: int = 10,
        audio: bool = True,
    ) -> Path:
        """A testsrc2 video (H.264), optionally with a 440 Hz stereo tone."""
        args = ["-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration={duration}"]
        if audio:
            tone = f"sine=frequency=440:sample_rate=44100:duration={duration}"
            args += ["-f", "lavfi", "-i", tone, "-c:a", "aac", "-ac", "2"]
        self._ffmpeg(*args, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", str(path))
        return path

    def cut_video(self, path: Path, *, cut_at: float = 12, total: float = 20) -> Path:
        """testsrc2 until `cut_at`, then SMPTE bars: one hard cut."""
        self._ffmpeg(
            "-f", "lavfi", "-i", f"testsrc2=size=320x240:rate=10:duration={cut_at}",
            "-f", "lavfi", "-i", f"smptebars=size=320x240:rate=10:duration={total - cut_at}",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        )  # fmt: skip
        return path

    @staticmethod
    def streams(path: Path) -> list[dict]:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)["streams"]


@pytest.fixture
def media() -> Media:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("FFmpeg CLI not on PATH (the CI runner has none)")
    return Media()
