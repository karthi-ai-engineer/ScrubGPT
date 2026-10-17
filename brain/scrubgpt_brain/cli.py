"""`scrubgpt-brain`: the Brain's command line.

    scrubgpt-brain normalize <source> <out_dir> [--height 720] [--thumb-interval 10]
    scrubgpt-brain frames <video> <out_dir> [--interval 5] [--scene-threshold 0.3 | --no-scenes]

Exit codes: 0 = done, 1 = the input is missing, isn't a video, or FFmpeg failed, 2 = usage error.
"""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from scrubgpt_brain.engines.media import MediaError
from scrubgpt_brain.pipeline import frames, normalize


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scrubgpt-brain", description="ScrubGPT Brain (Dev1)")
    commands = parser.add_subparsers(dest="command", required=True)

    norm = commands.add_parser("normalize", help="B3: 720p faststart video, poster, thumbnails")
    norm.add_argument("source", type=Path)
    norm.add_argument("out_dir", type=Path)
    norm.add_argument("--height", type=int, default=normalize.TARGET_HEIGHT)
    norm.add_argument(
        "--thumb-interval", type=float, default=normalize.THUMB_INTERVAL_S, help="seconds"
    )

    sample = commands.add_parser("frames", help="C1: a frame every N s, plus scene changes")
    sample.add_argument("video", type=Path)
    sample.add_argument("out_dir", type=Path)
    sample.add_argument("--interval", type=float, default=frames.DEFAULT_INTERVAL_S, help="s")
    scenes = sample.add_mutually_exclusive_group()
    scenes.add_argument("--scene-threshold", type=float, default=frames.SCENE_THRESHOLD)
    scenes.add_argument("--no-scenes", action="store_true", help="interval frames only")
    return parser


def main(argv: list[str] | None = None, *, out: Callable[[str], None] = print) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "normalize":
            result = normalize.normalize(
                args.source, args.out_dir, height=args.height, thumb_interval_s=args.thumb_interval
            )
            audio = "mono 16 kHz audio" if result.has_audio else "no audio track (none in source)"
            out(
                f"normalized {args.source} -> {result.video}: {result.width}x{result.height}, "
                f"{result.duration_s:.2f} s, {audio}; poster + {len(result.thumbs)} thumb strip(s)"
            )
        else:
            sampled = frames.sample_frames(
                args.video,
                args.out_dir,
                interval_s=args.interval,
                scene_threshold=None if args.no_scenes else args.scene_threshold,
            )
            n_scene = sum(1 for frame in sampled if frame.reason == "scene")
            out(
                f"sampled {len(sampled)} frame(s) from {args.video} into {args.out_dir} "
                f"({len(sampled) - n_scene} interval, {n_scene} scene change)"
            )
    except (MediaError, ValueError) as exc:
        out(f"scrubgpt-brain: error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
