"""`scrubgpt-brain`: the Brain's command line.

    scrubgpt-brain normalize <source> <out_dir> [--height 720] [--thumb-interval 10]
    scrubgpt-brain frames <video> <out_dir> [--interval 5] [--scene-threshold 0.3 | --no-scenes]
    scrubgpt-brain audio <source> <out_dir> [--max-chunk 600]
    scrubgpt-brain reference [<data_dir>]     (default: $DATA_DIR, relative to the repo root)
    scrubgpt-brain youtube <url> --case-id <id> [--download <out_dir>] [--cookies <cookies.txt>]
    scrubgpt-brain case <registry.yaml> <case_id> <video.mp4> <out_dir>

Results go to stdout, errors to stderr. Exit codes:
- 0 = done;
- 1 = the input is missing, isn't a video, or FFmpeg failed; for `audio` also a video without an
  audio track or a setting out of range; for `youtube` also a yt-dlp failure or an invalid case id;
  for `reference` also inconsistent knowledge or no data folder;
- 2 = usage error.
"""

import argparse
import itertools
import os
import sys
from collections.abc import Callable
from pathlib import Path

from scrubgpt_brain.engines.media import MediaError
from scrubgpt_brain.engines.rulebook import KNOWLEDGE_DIR, KnowledgeError
from scrubgpt_brain.pipeline import audio as chunker
from scrubgpt_brain.pipeline import cases, frames, normalize, reference, youtube

REPO_ROOT = KNOWLEDGE_DIR.parent


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

    chunk = commands.add_parser("audio", help="D1: FLAC chunks under 25 MB, cut at pauses")
    chunk.add_argument("source", type=Path)
    chunk.add_argument("out_dir", type=Path)
    chunk.add_argument("--max-chunk", type=float, default=chunker.MAX_CHUNK_S, help="seconds")

    registry = commands.add_parser("case", help="B4: case.json from the registry + its video")
    registry.add_argument("registry", type=Path)
    registry.add_argument("case_id")
    registry.add_argument("video", type=Path, help="the normalised video.mp4 (B3)")
    registry.add_argument("out_dir", type=Path)

    export = commands.add_parser("reference", help="export knowledge/ as the Procedure Reference")
    export.add_argument("data_dir", type=Path, nargs="?", help="default: $DATA_DIR")

    tube = commands.add_parser("youtube", help="B2: suggest a registry entry; optionally download")
    tube.add_argument("url")
    tube.add_argument("--case-id", required=True, help="e.g. yt-ja-01")
    tube.add_argument("--download", type=Path, metavar="OUT_DIR", help="also save source.mp4 here")
    tube.add_argument(
        "--cookies", type=Path, metavar="FILE", help="cookies.txt for age-restricted videos"
    )
    return parser


def _data_dir(given: Path | None) -> Path:
    """The data folder: as given, else `DATA_DIR`, whose relative paths resolve against the repo
    root (CLAUDE.md)."""
    if given is not None:
        return given
    value = os.environ.get("DATA_DIR")
    if not value:
        raise ValueError("give a data folder or set DATA_DIR")
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def _stderr(line: str) -> None:
    print(line, file=sys.stderr)


def main(
    argv: list[str] | None = None,
    *,
    out: Callable[[str], None] = print,
    err: Callable[[str], None] = _stderr,
) -> int:
    """Run one command: results go to `out` (stdout), errors to `err` (stderr)."""
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
        elif args.command == "case":
            path = cases.register_case(args.registry, args.case_id, args.video, args.out_dir)
            out(f"wrote {path}")
        elif args.command == "reference":
            path = reference.export_reference(_data_dir(args.data_dir))
            out(f"exported the Procedure Reference to {path}")
        elif args.command == "youtube":
            meta = youtube.fetch_metadata(args.url, cookie_file=args.cookies)
            entry, unsure = youtube.suggest_entry(meta, args.case_id)
            out(youtube.suggestion_yaml(meta, entry, unsure))
            if args.download is not None:
                path = youtube.download(meta.url, args.download, cookie_file=args.cookies)
                out(f"# downloaded {meta.url} -> {path}")
        elif args.command == "audio":
            chunks = chunker.chunk_audio(args.source, args.out_dir, max_chunk_s=args.max_chunk)
            end_s = chunks[-1].offset_s + chunks[-1].duration_s
            hard = sum(
                1
                for a, b in itertools.pairwise(chunks)
                if b.offset_s < a.offset_s + a.duration_s - 1e-6
            )
            out(
                f"chunked the audio of {args.source} into {len(chunks)} FLAC chunk(s) in "
                f"{args.out_dir}: {end_s:.2f} s, {len(chunks) - 1 - hard} cut(s) at pauses, "
                f"{hard} hard cut(s)"
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
    except (MediaError, KnowledgeError, ValueError) as exc:
        err(f"scrubgpt-brain: error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
