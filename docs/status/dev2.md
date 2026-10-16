# Dev2 Status: App track

> **Only Dev2's Claude edits this file.** Dev1's Claude reads it, especially **"Requests for Dev1"**.
> Folders: `app/server/`, `app/web/`. Machines: ASUS Zenbook (ARM64, home) and office laptop #2 (x64, same model as Dev1's office PC).
> Until integration (Week 6), always run with `BRAIN_MODE=mock` and the fake case. **Dev2 does not need an OpenAI key.**

**Last updated:** 2026-10-16
**Current task:** none yet (Phase 0 starts Mon 19 Oct)
**Branch:** — (Phase 0: `p0/dev2-<slug>`; Phase 1 block N: `dev2/b<N>`)

## Blockers

- (none)

## Requests for Dev1

Things this track needs from the other one. The other developer's Claude reads this at the start of every session.

- (none)

## Phase 0 tasks (Dev2)

- [ ] Day 1: onboarding: follow `docs/ONBOARDING.md` on the Zenbook (and on the office laptop when you're there)
- [ ] Day 2 (branch `p0/dev2-brain-api`, after Dev1's workspace is on `main`): draft the **Brain API models** in `contracts/models/brain_api.py`, importing the primitives from `common.py` (plan §4.1), plus `contracts/brain_api.md` → PR, approved by Dev1. **Your draft must decide:**
  - `/health`: response shape (status, model tiers, cache mode, `contract_version`)
  - `/v1/answers/transcribe`: multipart field names, `lang_hint` values (`ja`/`en`/`auto`), 25 MB limit, response (`text`, `lang`)
  - `/v1/answers/extract`: request = full `question` + `moment` + `case_context` + `answer {mode: tap|voice|text, tap_choice: str|null, text: str|null, lang}` + `answerer_role` (Role). Response = DecisionRecord **draft** (id null, unconfirmed), `readback: Bilingual`, `chips[]` (`field`, `value: Bilingual`, editable), `missing_fields[]` (DecisionRecord field paths), `new_terms[]`. Chip edits are applied by the app (no re-extract call in v1)
  - `/v1/embed`: request `texts[]`; response `vectors[][]`, `dim`, `model`
  - `/v1/ask`: request `query`, `lang`, `candidates[]` (full DecisionRecords, top-k from the store); response `answer: Bilingual`, `citations[]` (record IDs, optional evidence index), `coverage` (`full`/`partial`/`none`)
  - `/v1/briefing` (S): request `case_factors: Bilingual[]` (optional), `lang`, `candidates[]`; response `sections[] {title: Bilingual, body: Bilingual, citations[]}`
  - Errors: `ApiError` + HTTP status codes (plan §4.1); timeouts (suggest 60 s for extract and ask, 120 s for transcribe)
- [ ] Day 3 (branch `p0/dev2-mock-brain`): the **fake Brain** `contracts/mock_brain/` (HTTP on `:8101`, deterministic, uses the fixture IDs `case-fixture-01.m01`…; hashed bag-of-words `/embed`, dim 256) + **`contracts/codegen/`** (Pydantic → `schema/` → `ts/`) → PR, approved by Dev1
- [ ] Day 3, both: the fake Brain responses pass `validate.py` → **tag `contracts-v1.0`**

## Phase 1 checklist (live: tick here, not in Work_Split.md)

### Block 1 · Thu 22 – Tue 27 Oct (4 days): foundations
- [ ] **I1** FastAPI app server + case loader (validates every package; rejects invalid ones clearly)
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

- 2026-10-16: file created by the orchestrator.
