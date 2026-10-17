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

**Rule-book loader** (`scrubgpt_brain.engines.rulebook`):

```python
from scrubgpt_brain.engines.rulebook import load_knowledge
knowledge = load_knowledge()          # or load_knowledge(Path("some/knowledge"))
book = knowledge.rulebook             # phases → steps (rule-book order), order rules, GraSP crosswalk
knowledge.leaves(), knowledge.terms   # obstacle taxonomy leaves, vocabulary terms
```

It is the one reader of `knowledge/` that step recognition, decoding, deviation detection and the reference export share. It returns typed, frozen objects: `RuleBook`, `Phase`, `Step` (bilingual name, typical duration p25/p50/p75, anatomy, instruments, checkpoints, known obstacles), `ObstacleFamily`/`ObstacleLeaf`, `Term`, `OrderRules` and `GraspCrosswalk`. It checks:
- unique ids;
- every reference resolves (step → obstacle leaf and vocabulary term, leaf → step and term, order rules → phases, GraSP → rule-book ids);
- the rule book's `known_obstacles` and the taxonomy's leaf `steps` list the same pairs;
- bilingual names;
- 0 < p25 ≤ p50 ≤ p75.

Any problem raises `KnowledgeError`, listing each one as `<file>: <id>: <what's wrong>`. It reads only the folder it is given (default: the repo's `knowledge/`), never `DATA_DIR` or `.env`.

**C3 Rule-book decoding** (`scrubgpt_brain.engines.decode`):

```python
plan = plan_from_rulebook(knowledge.rulebook)            # columns = plan.step_ids
segments = decode(windows, probabilities, plan)          # windows: [(t_start, t_end)], seconds
segments = decode(windows, probabilities, plan, use_durations=False)   # edited videos
```

It turns GPT's noisy per-window step probabilities (C2, Block 2) into clean, ordered step segments, using a segmental Viterbi (a hidden semi-Markov model) that scores evidence, order and duration together.

- **Evidence:** the log of each window's probability for its step. Rows are **normalised** (a row of zeros = no information), and probabilities are floored at 1e-4.
- **Order:**
  - To the next step: free.
  - Skipping forward: each skipped step of a **required** phase costs `skip_penalty` (default log 0.02). Steps of an optional phase (`order_rules.optional_phases`) are skipped free.
  - A movable phase (`order_rules.movable_phases`, lymph node dissection) can appear at each place it `may_follow`, free to skip at either.
  - **Never backward** (`default: sequential`).
  - The recording may start and end at any step.
- **Duration:** log(duration) is normal around log(p50), with its spread from p25/p75. A fully observed segment scores −z²/2, which is 0 at the median. The first and last segment may be cut off by the recording, so they score the chance of lasting at least that long. `use_durations=False` turns durations off for edited videos.

Output: `Segment(step_id, t_start, t_end, confidence, n_windows)`, contiguous float-second segments from the first window's start to the last window's end. A gap between windows belongs to the segment before it. Bad input raises `ValueError`: no windows, a wrong number of columns, negative values or NaN, window times that aren't strictly increasing.

**Two things to know:**
- A required step that the evidence argues against only moderately can come out as a one-window "phantom" rather than a skip. E2 should read a one-window required step as possibly skipped.
- On independent synthetic noise, the decoder lifts window accuracy from 13–23 % (raw argmax) to 96–98 %. GPT's real errors are correlated, so the real gain is measured on GraSP in Block 2 (C7).

**Tests:** `uv run pytest brain/tests/unit`. They make synthetic FFmpeg test-pattern media in a temporary folder (D-036) and skip when FFmpeg isn't installed, as on the CI runner.
