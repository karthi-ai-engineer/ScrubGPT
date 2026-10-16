# Dev1 Status: Brain track

> **Only Dev1's Claude edits this file.** Dev2's Claude reads it, especially **"Requests for Dev2"**.
> Folders: `knowledge/`, `brain/`. Machine: office PC (all video work) + home Surface (code, prompts).

**Last updated:** 2026-10-16
**Current task:** Block 1 (early, #6 / D-051): A1–A4 in `knowledge/` only, until `contracts-v1.0`. Phase 0 (Dev1 side) is done and waits for Dev2's files (#5).
**Branch:** `p0/contracts` (Phase 0, Dev1 files done at dbfbab8) · `dev1/b1` (created early from `main`, `knowledge/` only, D-051)

## Blockers

- (none)

## Requests for Dev2

Things this track needs from the other one. The other developer's Claude reads this at the start of every session.

- **#5** `ENDPOINTS` registry shape + request fixtures (incl. synthetic `transcribe.request.audio.<ext>`) so `scrubgpt-validate live` can call the fake Brain. Routed to Dev2 by the Team Lead (label `analysis`): **please analyse it at your next session start**, before `brain_api.py`.
- **For your review on the Phase 0 PR (D-033):** Dev1's contract files on `p0/contracts` (common, decision_record, case_package, reference, validate, fixture case + reference). Shapes your loader depends on are in D-048/D-049 (e.g. `case_id` in every case file, `class` on the wire for utterances, instrument `key`).

## Drop results

- (Dev2 records drop results in `dev2.md`)

## Phase 0 tasks (Dev1)

All Phase 0 work is on the **shared branch `p0/contracts`** (D-030). Touch only Dev1's files in `contracts/` (D-031), and run `git pull --rebase=merges` before every push. Commit prefix `P0:`.

- [ ] **Day 1** (Mon 19 Oct) — *partly done 2026-10-16: tools OK on the office PC, `.env` created (temporary `DATA_DIR=./data`); OpenAI key + model names deferred by the owner (D-050); Google Drive for desktop not installed on the office PC; Surface not checked*: environment check on the office PC (already OK: uv, Python 3.13, Node 26, FFmpeg, gh) and on the Surface. Put the OpenAI key in `.env`; confirm the real model names for each tier and write them into `.env.example` as comments. Create the Drive folder `ScrubGPT-data` and share it with Dev2.
- [x] **Day 2, morning** (create `p0/contracts` from `main`): *done 2026-10-16, d317cc3 (T1 PASS)*
  1. Replace the **placeholder** `contracts/pyproject.toml` with the real package `scrubgpt-contracts` (import `scrubgpt_contracts`; deps: pydantic, fastapi, uvicorn, uuid6; console scripts `scrubgpt-validate`, `scrubgpt-mock-brain`, `scrubgpt-codegen`).
  2. Write `scrubgpt_contracts/models/common.py` **exactly as plan §4.1** (Bilingual, TrustLabel, Role, Provenance, Evidence, ApiError, ID types, field-path syntax, `contract_version`).
  3. **Push by midday, and tell Dev2** (they import it).
- [ ] **Day 2, rest:** *models done 2026-10-16, 8de8ac8 + 04f80a4 (T1 PASS); reviewing Dev2's models waits for their files (#5)*
  - `models/decision_record.py`: **`DecisionRecord` + `DecisionRecordDraft`** (plan §4.3, fully bilingual). Push early, because Dev2's extract models need it.
  - `models/case_package.py`: `case`, `timeline`, `moments`, `questions`, `seed_records`, `metrics` (plan §4.2: ids, `t_start`/`t_end`, provenance, `track`, `.qN`/`.rN` question IDs, `tap_options[]`).
  - `models/reference.py`: `ProcedureReference` (plan §4.2b, D-035).
  - Review Dev2's Brain API models as they land.
- [x] **Day 3:** *done 2026-10-16: fixtures b303367, `scrubgpt-validate` 7d7149b + dbfbab8 (T1 PASS)*
  - **Fake case** `contracts/fixtures/cases/case-fixture-01/`:
    - synthetic media via the D-036 FFmpeg command (300 s, ≈1.8 MB) + clips + posters;
    - hand-written JSON with moments `case-fixture-01.m01`…`m06`, operating and reviewer questions, 5 seed records (`simulated`);
    - total ≤ 5 MB.
  - **Fixture reference** `contracts/fixtures/reference/rarp.json`: Appendix A phases as `rarp.p01`…`p13`, a few steps and checkpoints, the 8 fixed families + a few leaves.
  - **`scrubgpt-validate`**:
    - `case <dir>`: schema + cross-file references + files exist + times within duration;
    - `reference <file>`;
    - `response <endpoint> <file>`;
    - `live --base-url <url>`: calls every endpoint in Dev2's `ENDPOINTS` registry with `fixtures/brain_api/*.request.json` and validates the responses.
- [x] **Day 3, tester:** *T1 PASS 420/420 at dbfbab8 (tests abc9527)* brief **`tester-brain` (T1)** on your contract files: acceptance criteria from plan §4 and D-034 … D-037 (`docs/TEAM.md` §6). It writes `contracts/tests/acceptance/t1/` and commits `T1: …`. **PASS before the PR.**
- [ ] **Day 3, both:**
  - Run `scrubgpt-codegen`; `scrubgpt-validate live --base-url http://localhost:8101` passes; CI green.
  - Open one PR `p0/contracts` → `main` (milestone "Phase 0 · Contracts", labels `contracts`, `dev1`, `dev2`). The Team Lead reviews it automatically: **READY**, then **approved by Dev2**.
  - The orchestrator merges, tags `contracts-v1.0`, creates `dev1/b1` + `dev2/b1`, and builds the Process Visualizer's Phase 0 section.

## Phase 1 checklist (live: tick here, not in Work_Split.md)

### Block 1 · Thu 22 – Tue 27 Oct (4 days): data and knowledge (branch `dev1/b1`)
- [ ] **B1** Download GraSP (+ PSI-AVA) and convert the ground-truth labels into cases
- [ ] **B2** Pick and download 10–12 YouTube RARP videos (about 6 English, about 4 Japanese, 1–2 without narration; prefer difficult cases)
- [ ] **B3** Normalise every video (720p MP4, 16 kHz audio, poster, thumbnails)
- [ ] **B4** Write `case.json` for each case: source, language, narrated, **edited or full**
- [ ] **A1** `knowledge/rulebooks/rarp.yaml` v0.9 (from the plan's Appendix A + GraSP's phases)
- [ ] **A2** Core ontology (Layer 0) `knowledge/ontology/core.yaml`
- [ ] **A3/A4** Obstacle taxonomy + bilingual vocabulary
- [ ] Export the **Procedure Reference** `<DATA_DIR>/reference/rarp.json` from the rule book + taxonomy (D-035); the IDs stay stable from here on
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
- [ ] **H5** `/v1/translate`
- [ ] Seed records (🧪 simulated answers run through G2)
- [ ] Process all 12+ cases
- [ ] **Drop 3 (Fri 13 Nov):** complete golden cases + all other cases

### Block 5 · Tue 17 – Fri 20 Nov (4 days): Should-features
- [ ] **D5–D7** Term normalisation, synthetic OR speech for GraSP, narration mining (🎙️)
- [ ] **F4, G4, H3, H4** Knowledge-base-aware questions, new-term detection, briefing, trainee scenarios (`trainee.json` = MINOR contract addition, via `contracts/<slug>`)
- [ ] **C4** Instrument tagging (from the same GPT window call as C2)
- [ ] Record the offline cache for every demo path
- [ ] **Drop 4 (Fri 20 Nov):** final case packages, including Should-feature outputs

## Session log (newest first, one or two lines per session)

- 2026-10-16 (office PC): Phase 0 Dev1 side built early (D-050): package + common (d317cc3), DecisionRecord (8de8ac8), Case Package + Reference models (04f80a4), fixtures (b303367), scrubgpt-validate (7d7149b, fix dbfbab8). Team Lead Q&A #3, #4, #6, #7; request #5 to Dev2. **T1 FAIL 418/420 → fix → PASS 420/420.** Next: `dev1/b1` A1–A4 (D-051).
- 2026-10-16: file created by the orchestrator.
