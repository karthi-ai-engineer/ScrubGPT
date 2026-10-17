# Dev1 Status: Brain track

> **Only Dev1's Claude edits this file.** Dev2's Claude reads it, especially **"Requests for Dev2"**.
> Folders: `knowledge/`, `brain/`. Machine: office PC (all video work) + home Surface (code, prompts).

**Last updated:** 2026-10-18
**Current task:** Block 1 on `dev1/b1`, plus the OpenAI-free Block 2 items D-070 allows (C7, C8, the OpenAI gateway).
- Pushed e0b1bb8 (Block 1 T1 PASS 522/527 + A6 + B2 synthetic voice).
- Local, in **T1 round 3**: C7, C8, the gateway and the T1 spec-gap fixes, head 14de8b5. They are held back from the push until T1 updates one scope test that D-070 changed.
- The rest of Block 1 waits on the owner (#18 YouTube, the GraSP download, the Drive folder).

## Two tabs on the Surface, from 2026-10-18 (owner's request; D-065)

The owner runs **two Claude sessions at once**. Each has its own folders; never work in the other tab's folders.

| | **Tab A: Dev1 covering Dev2 + orchestrator** | **Tab B: Dev1's own Brain track** |
|---|---|---|
| Work folder | `C:\Users\karth\ScrubGPT` (`p0/contracts`, then `dev2/b1` after the tag) | `C:\Users\karth\ScrubGPT-b1` (`dev1/b1`); start Claude **in this folder** |
| Tester checkout | `..\ScrubGPT-test-b1` (T2), `..\ScrubGPT-test` (T1 for the last #10 run) | `..\ScrubGPT-t1` (T1; created 2026-10-18, detached, synced) |
| Does | Dev2's open work (D-065); the Phase 0 PR, merge, tag `contracts-v1.0`, `dev2/b1`; `project.md`, `DECISIONS.md`, the Process Visualizer; `dev2.md` | `knowledge/`, `brain/` only; T1; `dev1.md` (checklist, session log) |
| Never | Dev1's Brain work | `contracts/`, `app/`, `docs/` other than `dev1.md`; merging PRs; tags |

- **`main` edits** (status files): both tabs use `..\ScrubGPT-main`, one quick step at a time: `git pull --rebase`, edit, commit, push right away. If git reports `index.lock`, wait a few seconds and retry.
- **Talking to each other:** decisions, requests and questions go to GitHub (issues, `/team-lead`), as always. For quick pings, use `ListAgents` + `SendMessage` (both sessions run on this machine).
- **After the tag** (done): `main` merged into `dev1/b1` (9b94137); A1–A4 criterion 12 passed; the reference export and B1–B4 built (D-067 order).

**Branches:**
- `dev1/b1`:
  - pushed e0b1bb8, CI green;
  - local head 14de8b5: e0b1bb8 + C7 (ecdb0ca), C8 (a81d95c), the gateway (eeab9af) and the T1 spec gaps (14de8b5).
  - Holds `knowledge/` (A1–A4, the GraSP crosswalk, the A6 atlas index) and `scrubgpt-brain`: B1 labels, B2, B3, B4, C1, the loader, C3, the C5 pixel signals, D1, the reference export, A6, C7, C8 and the OpenAI gateway.
- `p0/contracts`: merged as PR #15 (tag `contracts-v1.0`).
- **To delete, waiting for the owner's OK** (the work is on `main` via 948431e): `contracts/question-id` (local and remote) and `local/q10-rebased`.

## Next session (handoff, written 2026-10-18 on the Surface, Tab B)

1. **T1 round 3** (A6, C7, C8, the gateway; the brief is in this session, with criteria from #17 and the brain README).
   - On PASS: cherry-pick the `T1:` commit onto `dev1/b1`, run the full suite, and push.
   - Then tick C7 and C8 (D-070 condition 2: all buildable Block 1 has T1 PASS), and log "OpenAI gateway, T1 PASS".
   - A6 stays open until its images are cut from the GraSP videos.
   - If the round wasn't finished, re-brief T1 at the pushed head with the same criteria.
2. **Owner inputs, then the data runs:**
   - **GraSP** (the 13 videos + 1 fps annotations) → per case:
     - `scrubgpt-brain normalize` (B3), `case` (B4, `source: grasp`), `frames` (C1);
     - `ground-truth <case_dir> <file> <CASE>` (B1 + C8);
     - `atlas frames <videos>` (A6) once for the atlas.
   - **YouTube**, after #18: `scrubgpt-brain youtube <url> --case-id … --download …`. Review every suggestion: watch, settle `unsure`, translate the title, set `synthetic_speech` for アニウロ. Then `case`, `normalize`, `frames`, `audio`.
3. **Block 1 PR** when Block 1 is done (D-051: not before). Under D-070, C7/C8/gateway are ticked with their `T1:` commit or listed "built, not ticked".
4. **For the urologist review (C3, E2):** surgeons go back to earlier steps in 12 of 13 GraSP cases.
   - A dry run on GraSP's 5 test cases: B1 truth → simulated perfect window evidence → C3 → C7. It tops out at about **0.95 frame accuracy, 0.67 segment F1**, because C3 never moves backward (CASE041: 22 true segments, 13 decoded).
   - Repeatable steps are worth a rule-book decision before C2 tuning.
5. GraSP's test split (CASE041, 047, 050, 051, 053) is for C7 only. The atlas uses the train split, and GC1 should be a test case.

## Blockers

- (none)

## Requests for Dev2

Things this track needs from the other one. The other developer's Claude reads this at the start of every session.

- (none open) The Phase 0 requests (#10 `question_id`, D-056, #9 re-run, the #5 review) were all settled in PR #15.

## Drop results

- (Dev2 records drop results in `dev2.md`)

## Phase 0 tasks (Dev1)

All Phase 0 work is on the **shared branch `p0/contracts`** (D-030). Touch only Dev1's files in `contracts/` (D-031), and run `git pull --rebase=merges` before every push. Commit prefix `P0:`.

- [ ] **Day 1** (Mon 19 Oct) — *partly done 2026-10-16: tools OK on the office PC, `.env` created (temporary `DATA_DIR=./data`); OpenAI key + model names deferred by the owner (D-050); Google Drive for desktop not installed on the office PC; Surface checked and set up 2026-10-16 (Drive installed there, not signed in)*: environment check on the office PC (already OK: uv, Python 3.13, Node 26, FFmpeg, gh) and on the Surface. Put the OpenAI key in `.env`; confirm the real model names for each tier and write them into `.env.example` as comments. Create the Drive folder `ScrubGPT-data` and share it with Dev2.
- [x] **Day 2, morning** (create `p0/contracts` from `main`): *done 2026-10-16, d317cc3 (T1 PASS)*
  1. Replace the **placeholder** `contracts/pyproject.toml` with the real package `scrubgpt-contracts` (import `scrubgpt_contracts`; deps: pydantic, fastapi, uvicorn, uuid6; console scripts `scrubgpt-validate`, `scrubgpt-mock-brain`, `scrubgpt-codegen`).
  2. Write `scrubgpt_contracts/models/common.py` **exactly as plan §4.1** (Bilingual, TrustLabel, Role, Provenance, Evidence, ApiError, ID types, field-path syntax, `contract_version`).
  3. **Push by midday, and tell Dev2** (they import it).
- [x] **Day 2, rest:** *done: merged in PR #15 (2026-10-18)* *models done 2026-10-16 (T1 PASS); Dev2's `brain_api.py` / `brain_api.md` read and consistent; the formal confirmation goes in the Phase 0 PR comment*
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
- [x] **Day 3, both:** *done 2026-10-18: PR #15 merged, tagged `contracts-v1.0` (orchestrator, D-065)*
  - Run `scrubgpt-codegen`; `scrubgpt-validate live --base-url http://localhost:8101` passes; CI green.
  - Open one PR `p0/contracts` → `main` (milestone "Phase 0 · Contracts", labels `contracts`, `dev1`, `dev2`). The Team Lead reviews it automatically: **READY**, then **approved by Dev2**.
  - The orchestrator merges, tags `contracts-v1.0`, creates `dev1/b1` + `dev2/b1`, and builds the Process Visualizer's Phase 0 section.

## Phase 1 checklist (live: tick here, not in Work_Split.md)

### Block 1 · Thu 22 – Tue 27 Oct (4 days): data and knowledge (branch `dev1/b1`)
- [ ] **B1** Download GraSP (+ PSI-AVA) and convert the ground-truth labels into cases: *label import built (93d6d8d), T1 PASS 2026-10-18 (cb7d8c8; checked on the 13 real annotation files: 235 segments). The download waits on the owner.*
- [ ] **B2** Pick and download 10–12 YouTube RARP videos (about 6 English, about 4 Japanese, 1–2 without narration; prefer difficult cases): *importer built (cd3843e, e0b1bb8), T1 PASS 2026-10-18 (cb7d8c8). 12 picks proposed, owner decision #18 (permission, GC2 synthetic narration).*
- [x] **B3** Normalise every video (720p MP4, 16 kHz audio, poster, thumbnails): *the normaliser itself is done, 2026-10-17, ee5b2e6, T1 PASS (D-063; FFmpeg tests skip in CI, which has no FFmpeg). Running it on every real video comes with B1/B2 after the tag.*
- [x] **B4** Write `case.json` for each case: source, language, narrated, **edited or full**: *registry → `case.json` (93d6d8d, CLI `case` cd3843e), T1 PASS 2026-10-18 (cb7d8c8). Each real case gets its entry as it arrives.*
- [x] **A1** *(written early, 3a7e208 + fixes 9200317; criterion 12 T1 PASS after the tag, 2026-10-18, cb7d8c8)* `knowledge/rulebooks/rarp.yaml` v0.9 (from the plan's Appendix A + GraSP's phases)
- [x] **A2** *(written early, a4b1763 + fixes 9200317; T1 PASS incl. criterion 12, 2026-10-18; OntoSPM IRIs pending, D-053)* Core ontology (Layer 0) `knowledge/ontology/core.yaml`
- [x] **A3/A4** *(written early, 2b033cf + 3dd11e3, A3 fixes 9200317; T1 PASS incl. criterion 12, 2026-10-18)* Obstacle taxonomy + bilingual vocabulary
- [x] Export the **Procedure Reference** `<DATA_DIR>/reference/rarp.json` from the rule book + taxonomy (D-035); the IDs stay stable from here on: *098ffd0, T1 PASS 2026-10-18 (cb7d8c8). Exported on the Surface; re-run `scrubgpt-brain reference` into the Drive `DATA_DIR`.*
- [ ] **A6** Step atlas: 2–3 reference frames per step from GraSP ground truth: *built (ac85f55): index `knowledge/atlas/rarp.yaml` picked from the train split, 36 frames for 13/20 steps (7 steps have no GraSP label). T1 round 3 running. The images wait on the GraSP videos.*
- [x] **C1** Frame sampler: *done 2026-10-17, ee5b2e6, T1 PASS: every 5 s plus scene changes (D-063; FFmpeg tests skip in CI)*

### Block 2 · Wed 28 Oct – Tue 3 Nov (5 days): seeing and listening
- [ ] **C2** GPT step recognition on 1-minute windows (with the atlas as examples)
- [x] **C3** Rule-book decoding (Viterbi) into clean step segments: *0841873, T1 PASS on #14 (round 2, 2026-10-18; D-067). Accuracy on GraSP comes with C2.*
- [ ] **C5** Events: bleeding (red-pixel ratio + GPT check), camera out of body, idle: *pixel signals 71ac014, T1 PASS (D-067: not ticked until the GPT check lands)*
- [ ] **C7/C8** Accuracy against GraSP ground truth → `metrics.json`; ground-truth mode: *built under D-070 (ecdb0ca, a81d95c), T1 round 3 running*
- [ ] **OpenAI gateway** (no feature ID; D-070): *built (eeab9af), offline, stub transport; T1 round 3 running. The price list starts empty.*
- [x] **D1** Audio chunking: *0a12e7e + fix 7b97631, T1 PASS on #14 (round 2, 2026-10-18; D-067)*
- [ ] **D2–D4** Audio: transcribe with timestamps → translate JA↔EN → classify (needs the OpenAI key)
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

- 2026-10-18 (Surface, Tab B, night; Dev1 also covers Dev2 in Tab A, D-065):
  - **Built:** post-tag Block 1 (reference export 098ffd0; B1 labels + B4 93d6d8d; B2 cd3843e; D1 fix 7b97631) → **T1 PASS 522/527 (5 pre-tag skips), full suite 4106**; #14 closed (C3, D1 ticked; C5 pixel signals PASS).
  - **Also built:** A6 atlas index (ac85f55), B2 synthetic-voice detection (e0b1bb8) → pushed e0b1bb8 (full suite 4118 passed). #17 → D-070: C7, C8 and the gateway built (local, T1 round 3). #18 opened: owner decision on YouTube.

- 2026-10-17 (Surface, evening): while Dev2 is away. Team Lead allowed contract-independent `brain/` work (#12, D-063). `/code-review` of Dev1's Phase 0 files: 6 fixes + 3 Team Lead rulings (#13, D-064) → **T1 PASS 1308/1308**, pushed 7924b48. **B3 normaliser + C1 frame sampler** built in the new `scrubgpt-brain` package → **T1 PASS (81 new tests)**, pushed 91cdc75. GraSP crosswalk checked against the dataset's annotation files, 21 steps mapped. #10 replayed onto the new head (local/q10-rebased). CI green on both branches.
- 2026-10-17 (Surface, later): Phase 1 Block 1 continued early (D-051). `main` merged into `dev1/b1`. PyYAML allowed by the Team Lead (#11, D-062) and added (4201826). **A1–A4 T1: FAIL 111/122 (2 Appendix A obstacles missing, ontology endpoints/notes) → fixes (fixture fc59744 on `p0/contracts`, 9200317) → 122/127 PASS, 5 BLOCKED until the tag**; pushed 36a6ca8, CI green. Not ticked until criterion 12 runs after the tag.
- 2026-10-17 (Surface, re-cloned): fresh clone, worktrees and `.claude/settings.local.json`; all checks pass on ARM64. #9 and #10 analysed (ACCEPT; D-058, D-059). #9 + D-056 rule 1 built: **T1 FAIL 1077/1079 (AC4 `./video.mp4`) → fix → Team Lead ruling on 4 spec gaps (D-060) → T1 PASS 1174/1174**; pushed b55d036, CI green; T1 reports on #9 and #5. #10 built (dd19775) and parked on `contracts/question-id` until Dev2's fake Brain carries `question_id` (today it would break 561 tests).
- 2026-10-16 (Surface, first session): machine set up per `docs/ONBOARDING.md` (Python 3.13, Node 26.3.1, Google Drive installed; identity, `.env`, worktrees incl. `../ScrubGPT-test`). On ARM64, `p0/contracts` 9ac2d46: pytest 2074 passed + 4 skipped (no Node yet; the 4 then passed), ruff clean, codegen no diff, `validate` case/reference/live PASS. No ARM64 problems. No code changes.
- 2026-10-16 (office PC, afternoon): Dev2's half landed (#5 ACCEPT, T2 PASS); `validate live` PASS against the fake Brain. Team Lead rulings #7 (D-052, D-055), #8 (D-053), #5 (D-054, D-056) applied on `p0/contracts`: grounding paths name whole fields, exit codes, draft-only nullable cue/action. **T1: FAIL 667/671 → fix → PASS 737/737 → PASS 839/839.** Block 1 early on `dev1/b1`: A4, A3, A1, A2 written (T1 pending). Handoff above.
- 2026-10-16 (office PC): Phase 0 Dev1 side built early (D-050): package + common (d317cc3), DecisionRecord (8de8ac8), Case Package + Reference models (04f80a4), fixtures (b303367), scrubgpt-validate (7d7149b, fix dbfbab8). Team Lead Q&A #3, #4, #6, #7; request #5 to Dev2. **T1 FAIL 418/420 → fix → PASS 420/420.** Next: `dev1/b1` A1–A4 (D-051).
- 2026-10-16: file created by the orchestrator.
