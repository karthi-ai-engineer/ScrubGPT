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

**B4 Case registry** (`scrubgpt_brain.pipeline.cases`):

```python
path = register_case(registry, "yt-ja-01", video, out_dir)  # → out_dir/case.json
```

Or from the command line: `uv run scrubgpt-brain case <registry.yaml> <case_id> <video.mp4> <out_dir>`.

`case.json` is a case's identity card in the App:
- its bilingual title;
- its source (GraSP / PSI-AVA / YouTube / synthetic) and `source_url`;
- its spoken `language` and whether it is `narrated` or uses `synthetic_speech`;
- full-length or `edited` (an edited video never produces duration deviations, E2);
- its `default_step_track`, and a bilingual `data_note`.

The team keeps one **registry**, a YAML list with one entry per case and those fields, in `DATA_DIR`, never in git: it holds video URLs and notes. A missing `data_note` gets the source's default note (e.g. "public YouTube video, private internal demo use only"). B4 adds `duration_s`, measured from the normalised `video.mp4` (B3), and `status` (`partial` until the package is complete). It validates the result with the contract's `Case` model and writes it atomically into the folder it is given, normally `<DATA_DIR>/work/<case_id>/` (brain/CLAUDE.md rule 4). Registry problems raise `RegistryError`, listing each one with the case id and field: a duplicate id, an unknown field, a value the contract rejects (e.g. `language: none` with `narrated: true`).

**B2 YouTube importer** (`scrubgpt_brain.pipeline.youtube`):

```
uv run scrubgpt-brain youtube <url> --case-id yt-ja-01 [--download <out_dir>] [--cookies <cookies.txt>]
```

It reads one YouTube video's metadata with yt-dlp, without downloading it, and prints a **suggested registry entry** for B4 as YAML: a one-entry list, ready to paste into the registry. Comments above the entry give the video's duration, audio, yt-dlp language and chapters, its channel, upload date and licence, and the fields the importer is `unsure` of. With `--download`, it also saves the video as `<out_dir>/source.mp4` (the best video up to 1080 px high plus the best audio, merged by FFmpeg), which B3 then normalises.

**How it suggests**, from the title, the first 500 characters of the description and the duration. It never looks at the picture or listens to the sound.
- `language`: yt-dlp's spoken language (the video's, else its audio track's) if it is `ja` or `en`. Otherwise it guesses, marked unsure: Japanese kana or kanji in the title or description → `ja`, else `en`. No audio track → `none`.
- `narrated`: true when there is audio, a `ja`/`en` language, and narration wording in the title or description ("narrated", "commentary", "explained", "voice-over", "lecture", 解説, ナレーション, 実況, 講義, …). Otherwise false, and unsure.
- `video_type`: `edited` if the video is shorter than 45 min (a full-length RARP takes about 1.5–3 h), or if the text says it was cut down ("edited", "condensed", "highlights", "time-lapse", 要約, ダイジェスト, 編集版, …; "unedited" doesn't count). Otherwise `full`, unsure when the video is under 90 min or its duration is unknown. When in doubt, `edited` is the safer value: a wrong `edited` only switches off duration deviations (E2), while a wrong `full` produces false ones.
- `title`: the original title in both halves. The other language's half starts with `【要翻訳】` or `[to translate] `, so `title` is always unsure.
- `synthetic_speech`: true when the title or description names a generated voice (VOICEVOX, 合成音声, ゆっくり, "text-to-speech", …), which also makes it `narrated`. The contract then labels the case's speech synthetic everywhere. Otherwise false.
- Fixed values: `source: youtube`, `source_url` (the video page, without `&list=`), `default_step_track: ai`, and `data_note: null`, so B4 uses the default YouTube note.

**A person always reviews the suggestion before it goes into the registry.** They watch the video, settle every `unsure` field and translate the title; B4 then validates the entry against the contract.

**Errors** exit 1 with `scrubgpt-brain: error: …`, keeping yt-dlp's reason:
- a playlist, a channel, or a live or upcoming stream;
- any yt-dlp failure (network, a removed or private video, an age gate);
- an invalid case id.

**Access:**
- Many surgical videos are age-restricted. For those, pass `--cookies` with a Netscape `cookies.txt` exported from a signed-in browser; it holds a login, so keep it outside the repo.
- yt-dlp needs a JavaScript runtime for YouTube (Node.js or deno) and FFmpeg for the merge.
- A failed download leaves no `source.*` behind and keeps an earlier one.

**Whether a video may be downloaded at all is the owner's decision** (YouTube's terms; decision issue #18). The tool doesn't make that call.

**B1 GraSP importer, labels** (`scrubgpt_brain.pipeline.grasp`):

```python
segments, report = import_grasp_steps(annotation_json, "CASE001", "grasp-case001", video_fps=fps)
```

It turns one GraSP case's expert labels (`grasp_long-term_*.json`: one phase + one step per second) into rule-book step segments on the **dataset track** (📐 `dataset_annotation`). These are the ground truth for ground-truth mode (C8) and for scoring our AI steps (C7).

**Checks:** the file's category lists must equal the A1 crosswalk (ids, codes, names), or the import stops.

**Time:** a keyframe's time is `frame_num / fps`. Pass the source video's `video_fps`; without it, the rate is estimated from the keyframes' 1 s spacing.

**Mapping:**
- Each label goes through the crosswalk (`maps_to`, `by_phase`, or `phase` for generic acts like suction or cutting).
- With several candidate steps, the current step is kept if possible, else the first one not earlier in rule-book order.
- Idle gives no segment. A pause inside a step (the same step before and after) is bridged, so a gap remains only where the step changes.

`report` gives seconds per rule-book step, idle seconds and any unmapped labels.

**Checked on GraSP's 13 real cases** (annotations only, never committed): 7–26 segments per case, 235 in total. Idle is about a third of the time. **Every case but one goes backward 2–9 times** (surgeons return to earlier steps), which a strictly sequential rule book can't express; the urologist review should consider repeatable steps (C3, E2). Downloading the GraSP videos (owner) and building the full case packages come next.

**A6 Step atlas** (`scrubgpt_brain.pipeline.atlas`):

```
uv run scrubgpt-brain atlas pick <grasp_long-term_train.json> [--out <index.yaml>] [--per-step 3] [--min-run 10] [--cases CASE001 …]
uv run scrubgpt-brain atlas frames <grasp_videos_dir> [<data_dir>] [--index <index.yaml>]
```

The atlas gives C2 2–3 example pictures of every step, taken where GraSP's experts labelled that step, so GPT sees what "seminal vesicle dissection" looks like before it is asked about a new video (few-shot, no training). It works in two stages, so the choice is made and checked before any video is at hand:
- **`pick`** chooses the moments from the labels alone and writes the index `knowledge/atlas/rarp.yaml` (in git): per step, the GraSP case, the second, the run it sits in, the GraSP label and the basis. Use GraSP's **1 fps** train file, where `frame_num` is the second.
- **`frames`** cuts those moments from the GraSP videos (`<dir>/<CASE>.mp4`, or a B3 folder `<dir>/<CASE>/video.mp4`) into `<data_dir>/atlas/rarp/<step_id>/<CASE>_<ms>.jpg`, 720 px high like B3's video, and writes `atlas.json`. C2 reads the images with `load_atlas(data_dir)`. Images never go into git.

**How it picks:**
- **Only the train cases.** GraSP's 5 test cases (CASE041, 047, 050, 051, 053) are refused: they are kept for C7's accuracy score, which would otherwise be flattering (brain/CLAUDE.md rule 8).
- **Exact labels first.** A keyframe is `exact` when its GraSP label names that one step. A label naming several steps (`ambiguous`, e.g. `Cut_Bladder` → p05.s01 or p06.s01, resolved by continuity) only fills up a step with too few frames. Generic acts (suction, cutting) are never used: they look alike in every step.
- **Well inside a step:** the middle second of a run (consecutive keyframes of the step) at least `--min-run` seconds long, away from the transitions.
- **Variety:** different cases first (other patients and camera set-ups), longest run first; a second frame from one case must be at least 60 s from its first.
- Steps no GraSP label reaches are listed under `missing`. Their examples have to come from elsewhere (PSI-AVA or a YouTube case).

The same labels always give the same index. The index keeps `review_status: draft_pending_urologist_review`, as all knowledge files do, until a surgeon has looked at the images; a re-pick resets it.

**Errors** exit 1 with `scrubgpt-brain: error: …`:
- a test case, a case missing from the file, or a file that doesn't match the crosswalk (B1's check);
- an invalid index (an unknown step id, a test case, a time outside its run);
- a missing video, or a frame past a video's end (the wrong video). These are checked for every case before anything is cut.

Frames already cut are kept, so a re-run only cuts what is missing.

**Picked from GraSP's real train labels** (8 cases): 36 frames for 13 of the 20 steps, 32 of them exact. p09.s02 has one frame. **Missing: p01.s01, p01.s02, p06.s01, p07.s01, p11.s01, p12.s02, p13.s01**: GraSP has no label for port placement, docking, vas deferens division, the Rocco stitch, the leak test or the low-pressure haemostasis check, and its bladder-neck labels can't tell anterior from posterior (their ambiguous frames all land on p05.s01). Cutting the images waits for the GraSP video download (owner).

**C8 Ground-truth mode** (`scrubgpt_brain.pipeline.ground_truth`; D-070):

```
uv run scrubgpt-brain ground-truth <case_dir> <grasp_long-term.json> <GRASP_CASE> [--video-fps F]
```

For a GraSP case, the App should show the **experts' steps** by default, with the AI's steps alongside for comparison (golden case GC1). This command runs B1's label import for one GraSP case and puts the result into the case's package in `<case_dir>`, its work folder:
- `timeline.json`: the dataset track is replaced by the GraSP segments (📐 `dataset_annotation`, no model), numbered after the AI segments as in the fixture case. AI segments, events, instruments and utterances stay exactly as they were. Without a timeline, an empty one is started.
- `case.json`: `default_step_track: dataset`.

**A case without dataset segments is never switched.** Segments on the wrong track, with an AI trust label, a model, another case's id or an overlap are refused, and nothing is written. Both files are validated by the contract models and written atomically, and the package keeps passing `scrubgpt-validate case`. A re-run with the same labels is byte-identical. In Python: `apply_ground_truth(case_dir, segments)`, or `ground_truth_from_grasp(case_dir, annotations, "CASE041")`.

**C7 Accuracy evaluator** (`scrubgpt_brain.pipeline.evaluate`; D-070):

```
uv run scrubgpt-brain metrics <timeline.json> <out_dir> [--frame-step 1.0]
```

It scores how well the AI found the steps of a GraSP case, against GraSP's expert labels, and writes the contract's `metrics.json` into `<out_dir>` (a work folder; the package step copies it into the case, rule 4). The App shows these as the honest accuracy figures, so they are reported as they come out. The real numbers are measured in Block 2 on GraSP's **test** cases, never on cases a prompt was tuned on (rule 8). In Python, `evaluate(ai_segments, dataset_segments)` returns a `Metrics`.

- **Frames:** every `--frame-step` seconds where the dataset has a label (`n_frames`). A frame the AI left without a step counts as wrong.
- **`frame_accuracy`:** the share of frames whose AI step equals the true step.
- **`per_step`:** frame-level precision and recall for every step in either track, sorted by step id. A step the AI never chose has precision 0.0; a step absent from the ground truth has recall 0.0.
- **`segment_f1`:** an AI segment matches a true segment of the same step when their overlap is at least half their union (IoU ≥ 0.5), one-to-one, best partner first. This catches a timeline that chops a step into pieces or merges steps, which frame accuracy alone hides.
- **`model_info`:** the AI segments' `generated_by`, which must be present and identical on all of them. The tool never fills in a model name.

The same input always gives byte-identical JSON. **Errors** exit 1 with `scrubgpt-brain: error: …`, and no file is written:
- a missing track;
- a segment on the wrong track;
- segments of two cases;
- overlapping segments in one track;
- no frame to score;
- a missing or mixed `generated_by`.

**OpenAI gateway** (`scrubgpt_brain.engines.openai_gateway`; brain/CLAUDE.md rule 1, D-070):

```python
gateway = Gateway()  # tiers from .env, CACHE_MODE, DATA_DIR/cache
result = gateway.call("VISION_FAST", body)  # body = an OpenAI Responses request without `model`
result.json(), result.generated_by("step_window.v1"), result.cost_usd
```

Every OpenAI call of the Brain goes through this one door. That is why each answer can say which model made it, the offline demo can run from the cache, and the spend is known. **No stage calls it yet.** C2 and D2 come when the key arrives (D-050), and until then no key is read and nothing goes to OpenAI.
- **Tiers, not model names:** a call names a tier (`VISION_FAST`, `VISION_DEEP`, `TEXT_SMART`, `TEXT_FAST`, `STT`, `STT_DIARIZE`, `TTS`, `EMBED`), resolved from `<TIER>_MODEL` in `.env`. An unknown or unset tier is an error. The tier and the model go into `generated_by`, the provenance of everything the answer produces.
- **Cache:** one file per request under `<DATA_DIR>/cache/openai/`, keyed by the SHA-256 of the whole request (model, input, schema, every parameter). `CACHE_MODE=readwrite` reads and writes, `readonly` (the offline demo) only reads, and `off` does neither. A hit makes no call and costs nothing.
- **Retries:** 429, 5xx, timeouts and lost connections are retried with doubling backoff (or the server's `Retry-After`), up to 4 times. Other errors are not retried, and the last error reaches the caller.
- **Checks:** a refusal (`RefusalError`) or a cut-off answer (`TruncatedError`) is raised and **never cached**, so the next run asks again.
- **Cost log:** every call logs the tier, model, tokens (input, cached input, output), cost and cache hit (logger `scrubgpt_brain.openai`; `on_call` for a callback). `spent_usd` keeps the total. Prices come from `brain/config/openai_prices.yaml`, which starts **empty** and is filled in on setup day from OpenAI's price list. A model without a price logs cost `null` with a warning, because prices are never guessed.
- **Transport:** injectable. The default sends HTTPS with httpx and reads `OPENAI_API_KEY` only on its first call. The tests use a stub and fail if a socket opens. Batch calls (rule 5) and audio uploads (D2) come with the stages that need them.

**Procedure Reference export** (`scrubgpt_brain.pipeline.reference`; D-035):

```
uv run scrubgpt-brain reference [<data_dir>]     # default: $DATA_DIR (relative = from the repo root)
```

It writes `<data_dir>/reference/rarp.json`, the contract file the App reads to name and order steps, checkpoints and obstacles in both languages; the App never reads `knowledge/`. It holds exactly the public part of the rule book: phases and steps (bilingual name, order, typical duration p25/p50/p75) with their checkpoints, plus the 8 obstacle families and their leaves. Descriptions, visual cues, anatomy, instruments, known obstacles, order rules and the GraSP crosswalk stay Brain-internal.

The result is checked by the contract's `ProcedureReference` model and by `scrubgpt-validate reference`, then moved into place. A failed export (inconsistent knowledge, or a contract error) writes nothing and leaves the earlier file as it was. A re-export of unchanged knowledge is byte-identical. **The ids are stable from the first export on**: they equal the contract fixture (`contracts/fixtures/reference/rarp.json`), and timelines, moments and Decision Records point at them.

**Rule-book loader** (`scrubgpt_brain.engines.rulebook`):

```python
from scrubgpt_brain.engines.rulebook import load_knowledge

knowledge = load_knowledge()  # or load_knowledge(Path("some/knowledge"))
book = knowledge.rulebook  # phases → steps (rule-book order), order rules, GraSP crosswalk
knowledge.leaves(), knowledge.terms  # obstacle taxonomy leaves, vocabulary terms
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
plan = plan_from_rulebook(knowledge.rulebook)  # columns = plan.step_ids
segments = decode(windows, probabilities, plan)  # windows: [(t_start, t_end)], seconds
segments = decode(windows, probabilities, plan, use_durations=False)  # edited videos
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

Output: `Segment(step_id, t_start, t_end, confidence, n_windows)`, contiguous float-second segments from the first window's start to the last window's end. A gap between windows belongs to the segment before it. `confidence` is the mean normalised probability of the segment's step over its windows (0–1). Bad input raises `ValueError`:
- no windows;
- a row count that doesn't match the windows, or a wrong number of columns;
- negative values, NaN or infinity;
- window times that aren't strictly increasing, or windows that overlap.

**Two things to know:**
- A required step that the evidence argues against only moderately can come out as a one-window "phantom" rather than a skip. E2 should read a one-window required step as possibly skipped.
- On independent synthetic noise, the decoder lifts window accuracy from 13–23 % (raw argmax) to 96–98 %. GPT's real errors are correlated, so the real gain is measured on GraSP in Block 2 (C7).

**C5 pixel signals** (`scrubgpt_brain.engines.signals`; C5 isn't done until its GPT check lands, D-067):

```python
frames = load_frames(frames_dir)  # C1's (t, path) pairs from frames.json, sorted (pipeline.frames)
candidates = detect_candidates(frames)  # [Candidate(kind, t_start, t_end, score, status)]
candidates = detect_candidates(frames, min_span_s=5)  # every threshold is a keyword
```

It finds the spans worth C5's GPT check, using plain pixel maths on C1's frames (each downscaled to 160 px wide), so the expensive model only looks where something may be happening. Every result is a **candidate** (`status="candidate"`), never a confirmed event. Each score runs from 0 to 1 (higher = stronger) and is averaged over the span's frames that met the threshold:
- **`bleeding`:** a frame with at least 25 % blood pixels (`min_blood_ratio=0.25`). A blood pixel is a dark, saturated red: red between 40 and 220 (0–255), and at least 2.5 × green and 2.5 × blue. Score: the blood fraction.
- **`out_of_body`:** a frame where at most 25 % of the pixels are lit, warm tissue (`min_out_of_body=0.75`). A warm-tissue pixel has a brightest channel ≥ 40, a saturation ≥ 0.2, and a hue from 320° through red to 70° (pink, red, orange, yellow). Drapes, lights, walls and a covered (dark) lens don't count as warm. Score: 1 − the warm fraction.
- **`idle`:** consecutive frames whose mean absolute pixel difference is at most 3 on the 0–255 scale (`max_idle_change=3.0`). Score: 1 − change / 3, where 1 means identical frames.

**Spans:**
- Runs of one kind with at most one missed frame between them are merged (`max_gap_frames=1`). An idle run also takes in the frame before its first still frame.
- A run of frames at t_a … t_b becomes `t_start = t_a` and `t_end = min(t_b + interval, next frame's t)`, where `interval` is `interval_s` or else the median frame spacing. Both ends are therefore within one sampling interval of the true run.
- Spans shorter than `min_span_s=10` s (two C1 frames) are dropped.

`measure_frames(frames)` returns the per-frame measures, and `find_candidates(signals, …)` turns them into spans, so a tuning run decodes the frames once and tries many thresholds.

**The thresholds are placeholders tuned on synthetic frames only.** They get tuned on GraSP in Block 2, never on the reported test videos (brain/CLAUDE.md). Known limits, for the GPT check to sort out:
- with the camera outside, skin in view looks warm;
- smoke or a dark, instrument-filled view can look "out of body";
- a covered, still lens gives both out_of_body and idle.

**D1 Audio chunker** (`scrubgpt_brain.pipeline.audio`):

```
uv run scrubgpt-brain audio <video> <out_dir> [--max-chunk 600]
```

It cuts the audio track of a video (normally B3's `video.mp4`) into chunks for transcription (D2), small enough for the API's 25 MB file limit, and writes them into `<out_dir>`:
- `chunk_000.flac`, `chunk_001.flac`, …: FLAC, 16 kHz, mono. FLAC is lossless and about half the size of WAV. A chunk is at most 600 s (≈ 19.3 MB even for audio that doesn't compress), and every file is checked against 24,000,000 bytes.
- `chunks.json`: `{"source" (file name), "max_chunk_s", "chunks": [{"index", "file", "offset_s", "duration_s"}]}`. `offset_s` is where the chunk starts in the video, in float seconds, so a word's time in the video is `offset_s` + its time in the chunk.

**How it cuts:**
- A chunk aims to end `max_chunk_s` after it starts.
- It is cut in the latest pause that overlaps the last 60 s before that target, at the pause's middle (or as close to it as the window allows). A pause is ≥ 0.5 s below −30 dBFS (FFmpeg `silencedetect`).
- Chunks cut at a pause don't overlap, so no sentence is split.
- With no pause in the window, the chunk is cut hard at the target, and the next one starts 1 s earlier, so a word cut there is whole in the next chunk. D2 must drop the words it hears twice in that overlap.

The chunks cover the audio from 0 s to its end with no gap. A hard cut is exactly at `max_chunk_s`. The last chunk is at least 1 s long: a pause cut is never placed closer than 1 s to the end, and a hard cut's 1 s overlap already gives the last chunk that much. `max_chunk_s` must be at least 10 s, and the pause window is capped at half of it (so `--max-chunk 30` searches the last 15 s). Offsets are rounded down to the millisecond. An audio track that starts after the video's picture is padded at the start, so offsets are in video time. The audio is decoded once into a temporary FLAC and every chunk is cut from that, which is sample-exact.

**A video without an audio track raises `MediaError` ("… has no audio track") and writes nothing.** B3 makes such videos when the source has no sound; the pipeline skips D1 for them. A missing or non-video input, an FFmpeg failure or an oversized chunk exits 1 with `scrubgpt-brain: error: …`, and earlier chunks stay as they were. A re-run replaces `chunk_*.flac` and `chunks.json` and leaves other files alone. The pause settings are guesses until they are tried on real operating-room audio; more hard cuts in a noisy room are safe because of the overlap. In Python: `chunk_audio(source, out_dir)` returns a list of `AudioChunk(index, path, offset_s, duration_s)`.

**Tests:** `uv run pytest brain/tests/unit`. They make synthetic FFmpeg test-pattern media in a temporary folder (D-036) and skip when FFmpeg isn't installed, as on the CI runner.
