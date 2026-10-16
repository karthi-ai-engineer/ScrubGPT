# Dev1 Status: Brain track

> **Only Dev1's Claude edits this file.** Dev2's Claude reads it, especially **"Requests for Dev2"**.
> Folders: `knowledge/`, `brain/`. Machine: office PC (all video work) + home Surface (code, prompts).

**Last updated:** 2026-10-16
**Current task:** none yet (Phase 0 starts Mon 19 Oct)
**Branch:** — (Phase 0: `p0/dev1-<slug>`; Phase 1 block N: `dev1/b<N>`)

## Blockers

- (none)

## Requests for Dev2

Things this track needs from the other one. The other developer's Claude reads this at the start of every session.

- (none)

## Phase 0 tasks (Dev1)

- [ ] Day 1: environment check (office PC + Surface): uv, Python 3.13, Node 26, FFmpeg; OpenAI key in `.env`; confirm the model names for each tier
- [ ] Day 2, first thing (on `main`): create the **uv workspace** (root `pyproject.toml`, `contracts/pyproject.toml` = `scrubgpt-contracts`), fill in the `CLAUDE.md` "Commands" section, push. **Tell Dev2 when it's on `main`** (Dev2's models import `common.py`)
- [ ] Day 2 (branch `p0/dev1-case-package`): `contracts/models/common.py` (primitives exactly as in plan §4.1) → push early so Dev2 can import it. Then `case`, `timeline`, `moments`, `questions`, `seed_records`, `metrics`, `trainee`, **`DecisionRecord` (fully bilingual, plan §4.3)** → PR, approved by Dev2
- [ ] Day 3 (branch `p0/dev1-fixture`): the **fake case** `contracts/fixtures/cases/case-fixture-01/`: an FFmpeg test-pattern video of about 10 minutes plus a tone track; clips; hand-written JSON with moments `case-fixture-01.m01`…`m06`, questions, 5 seed records. Plus **`validate.py`** (`validate case <dir>` / `validate response <endpoint> <file>`) → PR, approved by Dev2
- [ ] Day 3, both: the fake Brain responses pass `validate.py` → **tag `contracts-v1.0`**

## Phase 1 checklist (live: tick here, not in Work_Split.md)

### Block 1 · Thu 22 – Tue 27 Oct (4 days): data and knowledge
- [ ] **B1** Download GraSP (+ PSI-AVA) and convert the ground-truth labels into cases
- [ ] **B2** Pick and download 10–12 YouTube RARP videos (about 6 English, about 4 Japanese, 1–2 without narration; prefer difficult cases)
- [ ] **B3** Normalise every video (720p MP4, 16 kHz audio, poster, thumbnails)
- [ ] **B4** Write `case.json` for each case: source, language, narrated, **edited or full**
- [ ] **A1** `knowledge/rulebooks/rarp.yaml` v0.9 (from the plan's Appendix A + GraSP's phases)
- [ ] **A3/A4** Obstacle taxonomy + bilingual vocabulary
- [ ] **A6** Step atlas: 2–3 reference frames per step from GraSP ground truth
- [ ] **C1** Frame sampler

### Block 2 · Wed 28 Oct – Tue 3 Nov (5 days): seeing and listening
- [ ] **C2** GPT step recognition on 1-minute windows (with the atlas as examples)
- [ ] **C3** Rule-book decoding (Viterbi) into clean step segments
- [ ] **C5** Events: bleeding (red-pixel ratio + GPT check), camera out of body, idle
- [ ] **C7/C8** Accuracy against GraSP ground truth → `metrics.json`; ground-truth mode
- [ ] **D1–D4** Audio: chunk → transcribe with timestamps → translate JA↔EN → classify
- [ ] **Drop 1 (Fri 30 Oct):** `timeline.json` for the golden cases

### Block 3 · Wed 4 – Tue 10 Nov (5 days): moments and questions
- [ ] **E1–E6** Timeline fusion, deviations, checkpoints, ranking, clip cutting
- [ ] **C6** Deep look at flagged moments
- [ ] **F1–F3, F5–F7** Question engine: both styles, tap options, quotes from the narration, bilingual
- [ ] **Drop 2 (Fri 6 Nov):** golden-case packages (moments and questions may still be partial)
- [ ] By the end of the block: **complete case packages for the 2 golden cases**

### Block 4 · Wed 11 – Mon 16 Nov (4 days): the runtime Brain · **all Must features done**
- [ ] **G1–G3, G5** `/v1/answers/transcribe`, `/v1/answers/extract` (grounded), read-back
- [ ] **H1–H2** `/v1/embed`, `/v1/ask` (grounded, with citations)
- [ ] Seed records (🧪 simulated answers run through G2)
- [ ] Process all 12+ cases
- [ ] **Drop 3 (Fri 13 Nov):** complete golden cases + all other cases

### Block 5 · Tue 17 – Fri 20 Nov (4 days): Should-features
- [ ] **D5–D7** Term normalisation, synthetic OR speech for GraSP, narration mining (🎙️)
- [ ] **F4, G4, H3, H4** Knowledge-base-aware questions, new-term detection, briefing, trainee scenarios
- [ ] Record the offline cache for every demo path
- [ ] **Drop 4 (Fri 20 Nov):** final case packages, including Should-feature outputs

## Session log (newest first, one or two lines per session)

- 2026-10-16: file created by the orchestrator.
