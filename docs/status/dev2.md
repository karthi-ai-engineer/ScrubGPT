# Dev2 Status: App track

> **Dev2 = Tharun (GitHub `TharunAppireddy`). Only Dev2's Claude edits this file.** Dev1's Claude reads it, especially **"Requests for Dev1"**.
> Folders: `app/server/`, `app/web/`. Machines: ASUS Zenbook (ARM64, home) and office laptop #2 (x64, same model as Dev1's office PC).
> Until integration (Week 6), always run with `BRAIN_MODE=mock` and the fake case. **Dev2 does not need an OpenAI key.**

**Last updated:** 2026-10-16
**Current task:** Phase 0 Dev2 files done incl. D-054 (T2 PASS 921/921, CI green). Next: approve the Phase 0 PR when the Team Lead says READY; follow #9 (bug for Dev1) and #10 (question_id, Team Lead)
**Branch:** `p0/contracts` (Phase 0: shared `p0/contracts`, D-030; Phase 1 Block N: `dev2/bN`)

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
- [ ] **Day 3, both:**
  - Run codegen; `scrubgpt-validate live --base-url http://localhost:8101` passes; CI green.
  - Once the Team Lead's review says **READY**, **approve** the `p0/contracts` PR on GitHub. The orchestrator then merges, tags `contracts-v1.0`, and creates `dev2/b1` for you.

## Phase 1 checklist (live: tick here, not in Work_Split.md)

### Block 1 · Thu 22 – Tue 27 Oct (4 days): foundations (branch `dev2/b1`)
- [ ] Replace the placeholder `app/server/pyproject.toml` with the real `scrubgpt-app` project (depends on `scrubgpt-contracts` through the workspace)
- [ ] **I1** FastAPI app server + case loader (validates with `scrubgpt_contracts`; loads only complete packages; **drop mode** validates file by file, D-038) + Procedure Reference loading
- [ ] Web skeleton: Vite + React + TS, Tailwind/shadcn, layout, design tokens
- [ ] **J15** i18n: JA/EN for every string, instant toggle
- [ ] **J1** Home / case list
- [ ] Video player component with 1–16× speed (server supports HTTP Range so seeking works)

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

- 2026-10-16 (later): D-054 in the fake Brain (canned drafts only in the answer's language; null cue/action with chips and `missing_fields`); **T2 PASS 921/921**, full suite 1975 passed, CI green. Reviewed Dev1's files for D-033 → bug #9, question #10.
- 2026-10-16 (office laptop #2): setup fixed (repo-local identity, uv/Python 3.13/Node 26/FFmpeg, `.env`); #5 analysed (ACCEPT); built `brain_api.md`, `brain_api.py` + `ENDPOINTS`, request fixtures, fake Brain, `scrubgpt-codegen` + generated `schema/`/`ts/`. **T2 PASS 176/176**, `live` PASS, full suite 895 passed, CI green. Two spec gaps sent to the Team Lead on #5.
- 2026-10-16: file created by the orchestrator.
