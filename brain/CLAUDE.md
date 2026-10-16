# brain/: Dev1 track (Brain)

**Owner:** Dev1. **Scope:** `brain/` and `knowledge/` only. Read the root `CLAUDE.md` first; its rules apply here too.

**What this track delivers** (feature IDs from `docs/MVP_Master_Plan.md` §2):
- **A** Knowledge foundation (in `knowledge/`)
- **B** Ingestion
- **C** Perception (GPT vision only)
- **D** Audio and language
- **E** Timeline and moment engine
- **F** Question engine
- **G** Answer-to-knowledge (runtime)
- **H** Knowledge services (runtime)

Output: **Case Packages** (contract #1) and the **Brain API** (contract #2).

## Layout

```
brain/
├─ pipeline/   offline steps, one module per stage: ingest · normalize · frames · perception ·
│              audio · fuse · moments · questions · seed · package (writes the case package)
├─ engines/    reusable logic: rulebook loader · viterbi decoder · deviation rules · ranking ·
│              extraction · ask · openai gateway
├─ api/        FastAPI Brain API (stateless)
├─ prompts/    versioned prompt files, e.g. step_window.v1.md (the version goes into provenance)
└─ cli.py      Typer CLI, e.g. `brain run <case_id> --until moments`
```

## Rules

1. **One OpenAI gateway** (`engines/openai_gateway.py`), and every OpenAI call goes through it. The gateway:
   - resolves model **tiers** from `.env`;
   - handles retries and backoff;
   - writes a **disk cache keyed by a hash of the request** in `<DATA_DIR>/cache/`, honouring `CACHE_MODE` (`readwrite` / `readonly` / `off`);
   - logs token use and cost per call.
2. **Structured outputs:** use strict JSON Schema built from the Pydantic models in `contracts/models/`. Every key is required, `null` is allowed where a value may be missing, and `additionalProperties` is false. Always check for refusals and truncation.
3. **Validate before writing.** Every Case Package file and every API response is validated against the contracts. An invalid output is a bug; never "fix it up" downstream.
4. **Pipeline stages are idempotent and resumable per case.**
   - Intermediate files go to `<DATA_DIR>/work/<case_id>/`.
   - Only final, valid files go to `<DATA_DIR>/cases/<case_id>/`.
   - `brain run <case> --from X --until Y` re-runs a slice of the pipeline.
5. **Bulk offline calls use the Batch API.** Cache the step atlas with prompt caching.
6. **Edited videos** (`video_type: edited`) never produce duration-based deviations.
7. **The Brain API is stateless.** It never reads or writes the app database. Callers send whatever records it needs.
8. **Measure honestly.** On GraSP cases, step recognition is evaluated against ground truth and written to `metrics.json`. Never tune prompts on the test videos you report.
9. **Grounding (G5).** Every filled field of an extracted DecisionRecord carries a `grounding` quote from the answer; anything not stated stays `null`.
10. **Bilingual.** Every human-readable output carries both `ja` and `en`.
11. **No heavy machine-learning dependencies.** No PyTorch, CUDA or OpenCV. Use Pillow, numpy, the FFmpeg CLI and yt-dlp, so everything runs on x64 and ARM64.
12. **Prompts are files, not inline strings.** When a prompt changes, bump its version (`*.v2.md`).

## Knowledge files (`knowledge/`)

- `rulebooks/rarp.yaml`: phases, steps, order, typical durations, anatomy, instruments, checkpoints, known obstacles, bilingual terms. Its `review_status` stays `draft_pending_urologist_review` until a surgeon reviews it.
- `taxonomy/obstacles.yaml`: the 8 universal families plus RARP-specific leaves, and the cause attribution (patient / event / technical / equipment / unknown).
- `vocab/terms.yaml`: JA/EN terms and synonyms.
- `atlas/`: an index of the reference frames for each step (the images themselves live in `DATA_DIR`).
