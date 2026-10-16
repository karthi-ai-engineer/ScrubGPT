# Project Status (shared)

> **Maintained by the orchestrator** (the Claude session on Dev1's machine). Other sessions read this file; they only edit it to tick a shared item they finished.
> Per-developer progress lives in `dev1.md` and `dev2.md` in this folder.

**Last updated:** 2026-10-16
**Phase:** 0, Contract Sprint (not started; planned Mon 19 – Wed 21 Oct)
**Contracts:** not written yet (target tag `contracts-v1.0`, Wed 21 Oct)
**Branching:** a branch per developer per phase step, merged into `main` one by one (D-020). Status files go straight to `main`.

## Phase 0 checklist

- [x] Repo created and folder layout in place
- [x] `CLAUDE.md` files (root + per track)
- [x] `.gitignore`, `.gitattributes`, `.env.example`
- [x] Work split, decision log, status files, onboarding guide
- [ ] **Dev1 environment:** OpenAI key in `.env`, model names confirmed for each tier
- [ ] **Dev2 onboarded** (`docs/ONBOARDING.md` done, repo cloned, Claude Code working)
- [ ] Shared Google Drive folder `ScrubGPT-data` created and shared with Dev2
- [ ] **Day 2:** uv workspace (Dev1, first thing) · `common.py` + Case Package + DecisionRecord (Dev1) · Brain API models + `brain_api.md` (Dev2) · each approved by the other
- [ ] **Day 3:** fake case + `validate.py` (Dev1) · fake Brain + codegen (Dev2) · everything validates → tag `contracts-v1.0`
- [ ] **After the tag:** Process Visualizer, Phase 0 section (orchestrator, D-029)

## Waiting on

| Item | From | Needed for |
|---|---|---|
| Dev2's GitHub username | Owner | Collaborator access, CODEOWNERS |
| OpenAI API key (with a spend limit) in Dev1's `.env` | Owner | Day 1 environment check |
| Google Drive folder `ScrubGPT-data` | Owner | Sharing case packages |

## Key dates

| Date | Milestone |
|---|---|
| Mon 19 – Wed 21 Oct | Phase 0 (contracts) |
| Fri 30 Oct, 6 Nov, 13 Nov, 20 Nov | Friday data drops |
| Mon 16 Nov | All **Must** features done on both tracks |
| Mon 23 – Wed 25 Nov | Integration |
| Thu 26 – Fri 27 Nov | Polish + rehearsal → demo-ready |

## Merge log (what landed on `main`)

| Date | Merged | Tag | Notes |
|---|---|---|---|
| 2026-10-16 | Repo scaffold, CLAUDE.md files, planning docs, shared-memory system | — | Phase 0 setup by the orchestrator |

## Friday drop log

| Date | Case packages dropped | Validated by Dev2? | Issues |
|---|---|---|---|
| — | — | — | — |
