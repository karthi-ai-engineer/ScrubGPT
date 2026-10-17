# brain/ (Dev1)

Offline pipeline + stateless Brain API. See `brain/CLAUDE.md` for the rules and `docs/MVP_Master_Plan.md` §2 for the features (B, C, D, E, F, G, H).

The package is `scrubgpt_brain` (`brain/scrubgpt_brain/`), with the console script `scrubgpt-brain`. Until `contracts-v1.0` it holds only contract-independent code (D-051, D-062, D-063). Everything video-related goes through the **FFmpeg CLI** (`ffmpeg` and `ffprobe` on PATH); there is no OpenCV or PyTorch.

## Usage

**B3 Normaliser** (`scrubgpt_brain.pipeline.normalize`):

```
uv run scrubgpt-brain normalize <source video> <out_dir> [--height 720] [--thumb-interval 10]
```

It turns one source video into the normalised media of a case, written into `<out_dir>`:
- `video.mp4`: H.264, 720 px high (aspect ratio kept, even width, square pixels), a keyframe every 2 s, "faststart", and one AAC track, mono, 16 kHz.
- `poster.jpg`: the frame at 10 % of the video.
- `thumbs/`: thumbnail strips for the seek bar (`strip_000.jpg`, …), 10 thumbnails side by side, one every 10 s from 0 s, described in `thumbs/index.json`.

**A source without audio gives a `video.mp4` without an audio track**: no silent track is made up, and the audio stages skip such a case. A missing file, a non-video input (a text file or a still image) or an FFmpeg failure exits 1 with `scrubgpt-brain: error: …`. In that case no new or half-written output is left in `<out_dir>`, and earlier outputs stay as they were. In Python: `normalize(source, out_dir)` returns a `NormalizedMedia`, or raises `MediaError`.

**C1 Frame sampler** (`scrubgpt_brain.pipeline.frames`):

```
uv run scrubgpt-brain frames <video> <out_dir> [--interval 5] [--scene-threshold 0.3 | --no-scenes]
```

It writes one frame every N seconds (0, N, 2N, … below the duration, default 5 s), plus an extra frame wherever the scene changes. A scene change is a frame whose FFmpeg `scene` score is above 0.3: a cut, the camera leaving the body, a change of view.
- A flicker gives one frame: scene frames less than 1 s after the previous one are dropped.
- A scene frame on the same video frame as an interval frame isn't added twice.
- Frames are JPEGs named by time in milliseconds (`000025000.jpg` = 25.0 s).
- `frames.json` lists them sorted by time, as `{"t", "file", "reason": "interval" | "scene"}`. Timestamps are float seconds from the start of the video.
- A re-run replaces the frame files and `frames.json`, and leaves other files in `<out_dir>` alone.

In Python: `sample_frames(video, out_dir)` returns a list of `Frame(t, path, reason)`. Run it on the normalised `video.mp4` (its 2 s keyframes keep the seeks fast).

**Tests:** `uv run pytest brain/tests/unit`. They make synthetic FFmpeg test-pattern media in a temporary folder (D-036) and skip when FFmpeg isn't installed, as on the CI runner.
