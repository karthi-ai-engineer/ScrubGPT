# Dev2 Status: App track

> **Dev2 = Tharun (GitHub `TharunAppireddy`). Only Dev2's Claude edits this file.** Dev1's Claude reads it, especially **"Requests for Dev1"**.
> Folders: `app/server/`, `app/web/`. Machines: ASUS Zenbook (ARM64, home) and office laptop #2 (x64, same model as Dev1's office PC).
> Until integration (Week 6), always run with `BRAIN_MODE=mock` and the fake case. **Dev2 does not need an OpenAI key.**

**Last updated:** 2026-10-18 (by Dev1 covering Dev2, D-065)
**Current task:** Block 1 on `dev2/b1` (built by Dev1 while Dev2 is away): I1 app server + web skeleton (J15, J1, video player) are committed and pushed; **T2 first test running**. Phase 0 is merged and tagged `contracts-v1.0`.
**Branch:** `dev2/b1` (created 2026-10-18 from `main` at the tag). Dev1 works it from the folder `../ScrubGPT-dev2`.

## Covered by Dev1 while Dev2 is away (D-065) — please review on return

Dev1's session builds this track (owner's decision, D-065). Every commit says "Built by Dev1 while covering Dev2's track (D-065)", Dev2-track work is tested by **T2**, and approvals for `contracts/` PRs were the owner's OK plus the Team Lead's READY. **Please review these when you're back**; anything you'd change goes in as a request or a contract change.

- **Phase 0, merged in PR #15 (`contracts-v1.0`):** your D-056 part (7254820: no chip for a null field, a null cue/action must be in `missing_fields`, `brain_api.md`); your #10 step (b0ea1ff: drafts carry `question_id`, `fixtures/brain_api` candidates carry it, **answerer role ⇔ question style → 400**, D-066); unit tests (98293f2); fake Brain canned draft only for the same question, one `ANSWERER_TRUST` table (8f27129, D-068). T2 PASS 1314/1314 → 1458/1458. Not yet done: a `/code-review` of your original Phase 0 files (64b937c…253f09b), as the Team Lead noted on PR #15.
- **Block 1 on `dev2/b1`:** `053dead` I1 app server (`scrubgpt-app serve|check|drop`, API, media with Range, drop mode; `app/server/README.md`); `d1988df` web skeleton (Vite + React 19 + TS 6, Tailwind 4, react-router 8, i18n; `app/web/README.md`). Choices you may want to revisit: react-router v8 (not v7), `tsconfig.app.json` includes `tests/` (so `tsc -b` type-checks T2's tests), the language is stored under `scrubgpt.lang`, and the procedure for step names is taken from the first moment's step id.

## Blockers

- (none)

## Requests for Dev1

Things this track needs from the other one. The other developer's Claude reads this at the start of every session.

- **#5** is built and tested (label `testing`): `ENDPOINTS`, request fixtures, fake Brain, codegen on `p0/contracts`. Your `scrubgpt-validate live` passes against it. Please list `Closes #5` in the Phase 0 PR.
- **#9** (bug, from Dev2's D-033 review of your files): non-ISO timestamps accepted; provenance coherence (role-play must stay `simulated`); six cross-file checks in `validate case`; minor: UUID forms, fixture coverage, dependency bounds.
- **#10** (question to the Team Lead): should `DecisionRecord` carry `question_id` ("done" vs "would do") before `contracts-v1.0`? It would touch your `decision_record.py` and fixtures.
- **For your D-033 review of Dev2's files:** the generic `/extract` draft fills only the field the question asks about (`brain_api.md`, fake Brain section).
- FYI: `contracts/pyproject.toml` has `uv_build>=0.12.15,<0.13.0`, and uv 0.13.1 (current winget) warns about it. It still builds.

## Drop results

- (Dev2 records the Friday drop validation results here; D-038)

## Phase 0 tasks (Dev2)

All Phase 0 work is on the **shared branch `p0/contracts`** (D-030). Touch only Dev2's files in `contracts/` (D-031), and run `git pull --rebase=merges` before every push. Commit prefix `P0:`. Before Monday: onboarding (`docs/ONBOARDING.md`). Your GitHub account `TharunAppireddy` already has write access. If you cloned the repo before 2026-10-16 evening, delete that clone and clone again: `main`'s history was rewritten to remove a third account (D-046).

- [ ] **Day 1** (Mon 19 Oct): onboarding on the Zenbook *(office laptop #2 done 2026-10-16: identity, uv, Python 3.13, Node 26, FFmpeg, `.env`; Zenbook and Drive share still to do)* (and on the office laptop when you're there). Accept the Drive share. `gh auth status` must show **your** account (`TharunAppireddy`).
- [x] **Day 2, morning:** write the **prose spec `contracts/brain_api.md`** (no code needed yet). The plan (§4.1, §4.4) already fixes most of it:
  - **`/health`:** `status` (`ok`/`degraded`), `mode` (`real`/`mock`), model tiers, `cache_mode`, `contract_version`.
  - **`/v1/answers/transcribe`:** multipart `audio` (webm/opus or mp4/aac, ≤ 25 MB → else `payload_too_large` 413), `lang_hint` (`ja`/`en`/`auto`), `answer_id`. Response: `text`, `lang` (`ja`/`en`).
  - **`/v1/answers/extract`:** request = full `question`, `moment`, `case_context` (`case.json` content + the moment's step object from the Procedure Reference), `answer {answer_id (UUIDv7, assigned by the app), mode: tap/voice/text, tap {verdict: confirm/edit/reject, choice_ids[]} or null, text or null, lang, audio_uri or null}`, `answerer_role` (Role). Response = `draft: DecisionRecordDraft` (Dev1's model), `readback: Bilingual`, `chips[] {field (path a.b[0].c), value: Bilingual, editable}`, `missing_fields[]` (paths).
  - **`/v1/translate`:** `texts[] {text, from_lang}` → `items[]: Bilingual`. The app uses it to keep edited chips bilingual; an edited field's grounding gets `source: edit`.
  - **`/v1/embed`:** `texts[]` → `vectors[][]`, `dim`, `model`.
  - **`/v1/ask`:** `query`, `lang`, `candidates[]` (full DecisionRecords) → `answer: Bilingual`, `citations[] {record_id, evidence_index or null}`, `coverage` (`full`/`partial`/`none`).
  - **`/v1/briefing` (S):** `case_factors: Bilingual[]` (required, may be empty), `lang`, `candidates[]` → `sections[] {title, body (Bilingual), citations[]}`.
  - **Errors:** `ApiError` (plan §4.1), with 422 → 400 `bad_request`, 404 `not_found`. Suggested timeouts: 60 s for extract, ask and translate; 120 s for transcribe.
- [x] **Day 2, after Dev1 pushes `common.py` and `decision_record.py`** (pull `p0/contracts`): `scrubgpt_contracts/models/brain_api.py` with request and response models for every endpoint, plus the **`ENDPOINTS` registry** (endpoint name → method, path, request model, response model). Ask Dev1 (status file or a `request` issue) if anything you need from their models is missing.
- [x] **Day 3:**
  - **Fake Brain** `scrubgpt_contracts/mock_brain/` (`scrubgpt-mock-brain --port 8101`), deterministic, per D-037:
    - extract answers keyed by the fixture question IDs `case-fixture-01.m01.q1`…;
    - `/embed`: NFKC + lowercase, Latin words + CJK character bigrams, blake2b → 256 dims, L2-normalised;
    - `/ask` coverage rule;
    - `/transcribe` with `auto` → the JA sentence;
    - `/health` `mode: mock`.
  - Request fixtures `contracts/fixtures/brain_api/<endpoint>.request.json`.
  - **`scrubgpt-codegen`** (`scrubgpt_contracts/codegen/`), with an `--out <dir>` option (default `contracts/`) so Tester 2 can test it without touching tracked files: Pydantic → `contracts/schema/` (JSON Schema, `mode="serialization"`) → `contracts/ts/` (`npx json-schema-to-typescript@<pinned>`; use `npx.cmd` on Windows). MINOR-added `T | None = None` fields become optional in TS.
- [x] **Day 3, tester:** brief **`tester-app` (T2)** on your contract files: acceptance criteria from plan §4.4, `brain_api.md` and D-037 (`docs/TEAM.md` §6). It writes `contracts/tests/acceptance/t2/` and commits `T2: …`. **PASS before the PR.**
- [x] **Day 3, both:** *done 2026-10-18: PR #15 merged and tagged `contracts-v1.0`; the owner's OK + Team Lead READY stood in for your approval (D-065)*
  - Run codegen; `scrubgpt-validate live --base-url http://localhost:8101` passes; CI green.
  - Once the Team Lead's review says **READY**, **approve** the `p0/contracts` PR on GitHub. The orchestrator then merges, tags `contracts-v1.0`, and creates `dev2/b1` for you.

## Phase 1 checklist (live: tick here, not in Work_Split.md)

### Block 1 · Thu 22 – Tue 27 Oct (4 days): foundations (branch `dev2/b1`)
- [ ] Replace the placeholder `app/server/pyproject.toml` with the real `scrubgpt-app` project (depends on `scrubgpt-contracts` through the workspace) *(built 053dead, Dev1 for Dev2; T2 pending)*
- [ ] **I1** *(built 053dead; T2 pending)* FastAPI app server + case loader (validates with `scrubgpt_contracts`; loads only complete packages; **drop mode** validates file by file, D-038) + Procedure Reference loading
- [ ] Web skeleton: Vite + React + TS, Tailwind/shadcn, layout, design tokens *(built d1988df; T2 pending)*
- [ ] **J15** *(built d1988df; T2 pending)* i18n: JA/EN for every string, instant toggle
- [ ] **J1** *(built d1988df; T2 pending)* Home / case list
- [ ] Video player component with 1–16× speed (server supports HTTP Range so seeking works) *(built d1988df; T2 pending)*

### Block 2 · Wed 28 Oct – Tue 3 Nov (5 days): the "live" Control Room
- [ ] **J2** Replay sync (the video is the master clock), step bar, event markers, transcript ticker, alerts
- [ ] "Surgery ends" → "4 questions ready" flow
- [ ] **J8** Graph panel (Cytoscape) on fake data
- [ ] **I5** SSE plumbing
- [ ] **Drop 1 (Fri 30 Oct):** run the loader on Dev1's drop and report any mismatch

### Block 3 · Wed 4 – Tue 10 Nov (5 days): the answer loop
- [ ] **J3** Answer app in a phone frame: question cards, looping clip, **tap / voice / text** side by side, read-back, confirm/edit chips
- [ ] **I2** Knowledge store (entities, edges, provenance, records, viewpoints)
- [ ] **I7** Brain client (mock ⇄ real switch)
- [ ] Confirming an answer updates the graph live (SSE)
- [ ] **Drop 2 (Fri 6 Nov):** load the golden cases from the drop

### Block 4 · Wed 11 – Mon 16 Nov (4 days): knowledge screens · **all Must features done**
- [ ] **J5** Knowledge Library: obstacle tree, cards, viewpoints side by side, counts
- [ ] **J4** Case Explorer
- [ ] **J6** Ask with cited clips
- [ ] **J9** Provenance drawer, **J16** disclaimers
- [ ] **I3/I4** Pattern counts (n < 20 → counts only), retrieval
- [ ] **I6** One-command seed/reset
- [ ] **Drop 3 (Fri 13 Nov):** load all cases from the drop

### Block 5 · Tue 17 – Fri 20 Nov (4 days): Should-features
- [ ] **J7** Procedure Map
- [ ] **J8** Full graph page for investors
- [ ] **J10** Reviewer queue
- [ ] **J11** Trainee "What would you do?"
- [ ] **J12** Briefing
- [ ] **J14** Admin + accuracy metrics
- [ ] **I8** Audit log
- [ ] **Drop 4 (Fri 20 Nov):** final validation of every case

## Session log (newest first, one or two lines per session)

- 2026-10-18 (Dev1 covering Dev2, D-065, Surface Tab A): Dev2's D-056 part, #10 step, D-066 role check, D-068 canned-by-question built; **T2 PASS 1314/1314 → 1458/1458**; PR #15 merged, `contracts-v1.0` tagged; `dev2/b1` created; Block 1 I1 server (35 unit tests) + web skeleton (63 unit tests) pushed, checked against the real server with screenshots (JA/EN, 1440 and 500 px); T2 first test running.
- 2026-10-16 (later): D-054 in the fake Brain (canned drafts only in the answer's language; null cue/action with chips and `missing_fields`); **T2 PASS 921/921**, full suite 1975 passed, CI green. Reviewed Dev1's files for D-033 → bug #9, question #10.
- 2026-10-16 (office laptop #2): setup fixed (repo-local identity, uv/Python 3.13/Node 26/FFmpeg, `.env`); #5 analysed (ACCEPT); built `brain_api.md`, `brain_api.py` + `ENDPOINTS`, request fixtures, fake Brain, `scrubgpt-codegen` + generated `schema/`/`ts/`. **T2 PASS 176/176**, `live` PASS, full suite 895 passed, CI green. Two spec gaps sent to the Team Lead on #5.
- 2026-10-16: file created by the orchestrator.
