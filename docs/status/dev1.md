# Dev1 Status: Brain track

> **Only Dev1's Claude edits this file.** Dev2's Claude reads it, especially **"Requests for Dev2"**.
> Folders: `knowledge/`, `brain/`. Machine: office PC (all video work) + home Surface (code, prompts).

**Last updated:** 2026-10-16
**Current task:** Phase 0 last steps: analyse #9 and #10, then implement them with D-056 rule 1 (see "Next session" below), then the single Phase 0 PR. Block 1 runs early in `knowledge/` (D-051): A1–A4 written, waiting for T1.
**Branch:** `p0/contracts` (HEAD 9ac2d46, pushed; T1 PASS 839/839, full suite 2078 passed, CI green) · `dev1/b1` (HEAD a4b1763, pushed; `knowledge/` only, D-051)

## Next session (handoff, written 2026-10-16 17:40 on the office PC)

Start with "I'm Dev1. Start session." Then, in order:
0. ~~**First time on the Surface (ARM64)**~~ *done 2026-10-16* (Surface Laptop 7, Snapdragon X, 16 GB):
   - Tools: git, gh (`karthi-ai-engineer` active), uv 0.12.22 (native ARM64), FFmpeg 9.0.2, Claude Code; installed Python 3.13.16, Node 26.3.1 (native ARM64), Google Drive for desktop (not signed in yet).
   - Repo-local identity and push account set; `git push --dry-run` OK. `.env` has `DATA_DIR=./data`, no OpenAI key (D-050).
   - On `p0/contracts` 9ac2d46: `pytest` 2074 passed + 4 skipped (Node not yet on PATH); those 4 codegen tests then passed with Node. Ruff clean, `scrubgpt-codegen` leaves no diff, `validate case`/`reference` PASS, `validate live` against the fake Brain PASS.
   - **ARM64 notes:** no failures. uv picks **x64** CPython 3.13 on this machine (native ARM64 is "not yet mature" per uv), so Python runs under emulation, like the office PC's arch. Without Node on PATH, 4 codegen tests skip (not fail); open a new terminal after installing Node.
1. **Analyses due first** (labels `analysis` + `dev1`; show each to the developer before posting; template `docs/TEAM.md` §7). Both must land on `p0/contracts` before the Phase 0 PR, because Dev2's approval waits on them:
   - **#9 [bug]**, from Dev2's D-033 review of Dev1's files. The Team Lead's triage already decides the fixes:
     - strict ISO timestamps on the wire, matching `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$`;
     - provenance coherence: `dev_team_simulated` ⇒ `simulated`, and seed records are only `simulated` / `narration_extracted`;
     - which cross-file mismatches are errors and which are warnings in `validate case`;
     - canonical UUIDs, fixture coverage and dependency bounds.
     Read the full triage, write the analysis (ACCEPT), then log its decision (`to-log`) in `docs/DECISIONS.md`.
   - **#10 [question]** `question_id: QuestionId | None` on `DecisionRecord` + draft (operating `.qN` = "done", reviewer `.rN` = "would do"). The Team Lead recommends option (a) with 6 rules; it **needs Dev1's agreement**. The second `m01` seed record should point to an `.rN` question; decide whether to reword its `action.text`. Then log it (`to-log`).
   - Then implement #9, #10 and D-056 rule 1 together, regenerate `schema/`/`ts/` (`uv run scrubgpt-codegen`), and run **one** T1 brief covering 12e, #9 and #10.
2. **D-056 rule 1 (issue #5, criterion 12e), on `p0/contracts`:**
   - In `decision_record.py`, reject a `grounding[].field` of exactly `situation_cue` while `situation_cue.text` is null, and exactly `action` while `action.text` is null.
   - Keep `action.type` / `action.actor` groundings allowed. Whole-object groundings stay valid when the text is filled.
   - Add unit tests. Run `uv run scrubgpt-codegen` if a docstring changed. Commit `P0: …`.
   - Brief T1 on 12e (criteria in the Team Lead's 08:18 reply on #5). Push on PASS and post the T1 result on #5.
3. **T1's two minor spec gaps** (ask in one "Ask the Team Lead" issue):
   - (a) Package or reference JSON with a UTF-8 BOM is "invalid JSON" (exit 1) today. Allowed, or a defect?
   - (b) The reference lookup when no file gives a step-id prefix (timeline and moments both missing).
4. **Wait for Dev2** (their part of D-056 and of #10: `draft.question_id` from the fake Brain):
   - the `ExtractResponse` rule (a null cue or action must be in `missing_fields`);
   - **no** chip for a null field (their T2 report at 08:22 still mentions a `value: null` chip, which D-056 drops);
   - `brain_api.md` lines 99 and 153; the generic draft never uses the moment title;
   - T2 on 12b and 12d–12g.
5. **Open the Phase 0 PR** once both are green (list `Closes #5`, `Closes #9`; #10 is a question, close it yourself):
   - `gh pr create --base main --head p0/contracts --milestone "Phase 0 · Contracts" --label contracts --label dev1 --label dev2`, title `P0: contracts v1.0`, body with a summary, both tester results and `Closes #5`.
   - Confirm Dev2's files in a PR comment (Dev1 can't approve their own PR). `brain_api.py` and `brain_api.md` were read on 2026-10-16 and are consistent with plan §4.4 and D-048…D-056; still check the generic `/extract` rule (it fills only the field the question asks about).
   - The Team Lead reviews automatically (needs **READY**), and Dev2 approves on GitHub.
   - Then the orchestrator merges, tags `contracts-v1.0`, creates `dev2/b1`, merges `main` into `dev1/b1`, and builds the Process Visualizer's Phase 0 section (D-029, D-039).
6. **A1–A4 on `dev1/b1`:** brief T1 (light path) on 3dd11e3 (A4), 2b033cf (A3), 3a7e208 (A1) and a4b1763 (A2). Checks that need the contracts package (IDs equal to the fixture `rarp.json`) may be BLOCKED until the tag (D-051). Tick only on PASS.

Local only on the office PC (nothing to sync): the worktrees `../ScrubGPT-main` (main) and `../ScrubGPT-b1` (dev1/b1), and `.env` with `DATA_DIR=./data`. The Surface has the same, plus the tester checkout `../ScrubGPT-test` (detached at 9ac2d46, own `.venv`, D-057).

## Blockers

- (none)

## Requests for Dev2

Things this track needs from the other one. The other developer's Claude reads this at the start of every session.

- **#5** (built, T2 PASS; thanks): please finish **your part of D-056**:
  - the `ExtractResponse` rule (a null `situation_cue.text` / `action.text` must be in `missing_fields`);
  - **no chip for a null field** (D-056 drops the `value: null` chip);
  - `brain_api.md` lines 99 and 153;
  - T2 on 12b (amended) and 12d–12g.
  
  Then the Phase 0 PR can open.
- **For your review on the Phase 0 PR (D-033):** Dev1's contract files on `p0/contracts` (common, decision_record, case_package, reference, validate, fixture case + reference). Shapes your loader depends on are in D-048/D-049 (e.g. `case_id` in every case file, `class` on the wire for utterances, instrument `key`).

## Drop results

- (Dev2 records drop results in `dev2.md`)

## Phase 0 tasks (Dev1)

All Phase 0 work is on the **shared branch `p0/contracts`** (D-030). Touch only Dev1's files in `contracts/` (D-031), and run `git pull --rebase=merges` before every push. Commit prefix `P0:`.

- [ ] **Day 1** (Mon 19 Oct) — *partly done 2026-10-16: tools OK on the office PC, `.env` created (temporary `DATA_DIR=./data`); OpenAI key + model names deferred by the owner (D-050); Google Drive for desktop not installed on the office PC; Surface checked and set up 2026-10-16 (Drive installed there, not signed in)*: environment check on the office PC (already OK: uv, Python 3.13, Node 26, FFmpeg, gh) and on the Surface. Put the OpenAI key in `.env`; confirm the real model names for each tier and write them into `.env.example` as comments. Create the Drive folder `ScrubGPT-data` and share it with Dev2.
- [x] **Day 2, morning** (create `p0/contracts` from `main`): *done 2026-10-16, d317cc3 (T1 PASS)*
  1. Replace the **placeholder** `contracts/pyproject.toml` with the real package `scrubgpt-contracts` (import `scrubgpt_contracts`; deps: pydantic, fastapi, uvicorn, uuid6; console scripts `scrubgpt-validate`, `scrubgpt-mock-brain`, `scrubgpt-codegen`).
  2. Write `scrubgpt_contracts/models/common.py` **exactly as plan §4.1** (Bilingual, TrustLabel, Role, Provenance, Evidence, ApiError, ID types, field-path syntax, `contract_version`).
  3. **Push by midday, and tell Dev2** (they import it).
- [ ] **Day 2, rest:** *models done 2026-10-16 (T1 PASS); Dev2's `brain_api.py` / `brain_api.md` read and consistent; the formal confirmation goes in the Phase 0 PR comment*
  - `models/decision_record.py`: **`DecisionRecord` + `DecisionRecordDraft`** (plan §4.3, fully bilingual). Push early, because Dev2's extract models need it.
  - `models/case_package.py`: `case`, `timeline`, `moments`, `questions`, `seed_records`, `metrics` (plan §4.2: ids, `t_start`/`t_end`, provenance, `track`, `.qN`/`.rN` question IDs, `tap_options[]`).
  - `models/reference.py`: `ProcedureReference` (plan §4.2b, D-035).
  - Review Dev2's Brain API models as they land.
- [x] **Day 3:** *done 2026-10-16: fixtures, `scrubgpt-validate` (with the D-052/D-055 exit-code rules), D-054 draft change; T1 PASS 839/839; `validate live` PASS against Dev2's fake Brain*
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
- [x] **Day 3, tester:** *T1 PASS 420/420 at dbfbab8, then 839/839 at c93a9bd after the #7 and #5 rulings* brief **`tester-brain` (T1)** on your contract files: acceptance criteria from plan §4 and D-034 … D-037 (`docs/TEAM.md` §6). It writes `contracts/tests/acceptance/t1/` and commits `T1: …`. **PASS before the PR.**
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
- [ ] **A1** *(written early, 3a7e208, T1 pending)* `knowledge/rulebooks/rarp.yaml` v0.9 (from the plan's Appendix A + GraSP's phases)
- [ ] **A2** *(written early, a4b1763, T1 pending; OntoSPM IRIs pending, D-053)* Core ontology (Layer 0) `knowledge/ontology/core.yaml`
- [ ] **A3/A4** *(written early, 2b033cf + 3dd11e3, T1 pending)* Obstacle taxonomy + bilingual vocabulary
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

- 2026-10-16 (Surface, first session): machine set up per `docs/ONBOARDING.md` (Python 3.13, Node 26.3.1, Google Drive installed; identity, `.env`, worktrees incl. `../ScrubGPT-test`). On ARM64, `p0/contracts` 9ac2d46: pytest 2074 passed + 4 skipped (no Node yet; the 4 then passed), ruff clean, codegen no diff, `validate` case/reference/live PASS. No ARM64 problems. No code changes.
- 2026-10-16 (office PC, afternoon): Dev2's half landed (#5 ACCEPT, T2 PASS); `validate live` PASS against the fake Brain. Team Lead rulings #7 (D-052, D-055), #8 (D-053), #5 (D-054, D-056) applied on `p0/contracts`: grounding paths name whole fields, exit codes, draft-only nullable cue/action. **T1: FAIL 667/671 → fix → PASS 737/737 → PASS 839/839.** Block 1 early on `dev1/b1`: A4, A3, A1, A2 written (T1 pending). Handoff above.
- 2026-10-16 (office PC): Phase 0 Dev1 side built early (D-050): package + common (d317cc3), DecisionRecord (8de8ac8), Case Package + Reference models (04f80a4), fixtures (b303367), scrubgpt-validate (7d7149b, fix dbfbab8). Team Lead Q&A #3, #4, #6, #7; request #5 to Dev2. **T1 FAIL 418/420 → fix → PASS 420/420.** Next: `dev1/b1` A1–A4 (D-051).
- 2026-10-16: file created by the orchestrator.
