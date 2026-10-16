# Project Status (shared)

> **Maintained by the orchestrator** (the Claude session on Dev1's machine). Other sessions read this file; they only edit it to tick a shared item they finished.
> Per-developer progress lives in `dev1.md` and `dev2.md` in this folder.

**Last updated:** 2026-10-16
**Phase:** 0, Contract Sprint — started early on Fri 16 Oct and runs continuously (D-050). Both halves built and tested (T1 PASS 839/839, T2 PASS 921/921; `validate live` PASS; CI green). Left before the Phase 0 PR: D-056 (Dev1 rule 1 + T1 12e; Dev2 `ExtractResponse` rule + T2 12b/12d–12g)
**Contracts:** complete draft on `p0/contracts` (9ac2d46). Tag `contracts-v1.0` after the single Phase 0 PR
**Branching:** a branch per developer per phase step, merged into `main` one by one (D-020). Phase 0 uses one shared branch, `p0/contracts` (D-030). Status files go straight to `main`.

## Phase 0 checklist

- [x] Repo created and folder layout in place
- [x] `CLAUDE.md` files (root + per track)
- [x] `.gitignore`, `.gitattributes`, `.env.example`
- [x] Work split, decision log, status files, onboarding guide
- [x] GitHub ready: CI guard (green), PR and issue templates, labels, 8 milestones, rulesets, merge commits only, attribution off (D-040)
- [x] uv workspace bootstrapped: root `pyproject.toml` + `uv.lock` + placeholder members (D-031)
- [x] Repo verified by fresh Dev1/Dev2 session simulations + consistency audit (2026-10-16)
- [x] **Agent team** (`docs/TEAM.md`, D-042 … D-046): Team Lead on GitHub + research assistant + system designer, Tester 1 / Tester 2, issue life-cycle labels, "Ask the Team Lead" form, CI tester split
- [x] Dev2 (Tharun, `TharunAppireddy`) added as a collaborator; CODEOWNERS updated
- [x] **Only two accounts (D-046):** `main`'s history rewritten to the owner's noreply email (a third, company account removed); repo-local identity and push account on the office PC; CI account check; interaction limit (collaborators only, until 2027-04-16)
- [x] **Team Lead switched on and live-tested** (D-047): secret `CLAUDE_CODE_OAUTH_TOKEN` added by the owner; question issue #1 answered correctly; test PR #2 reviewed automatically (both closed)
- [ ] **Dev1 environment:** OpenAI key in `.env`, model names confirmed for each tier
- [ ] **Dev2 onboarded** (`docs/ONBOARDING.md` done, repo cloned, Claude Code working)
- [ ] Shared Google Drive folder `ScrubGPT-data` created and shared with Dev2
- [ ] **Day 2** (branch `p0/contracts`) — *Dev1 part done (T1 PASS); Dev2 part open*: contracts package + `common.py` first, then DecisionRecord(+Draft) + Case Package + Reference models (Dev1) · `brain_api.md` + Brain API models + `ENDPOINTS` (Dev2)
- [ ] **Day 3** — *Dev1 part done (T1 PASS 420/420); `dev1/b1` created early (#6, D-051), so only `dev2/b1` is still created after the tag*: fake case + fixture reference + `scrubgpt-validate` (Dev1) · fake Brain + request fixtures + `scrubgpt-codegen` (Dev2) · both testers PASS · `scrubgpt-validate live` passes · one PR (Team Lead READY, approved by Dev2) → merge, tag `contracts-v1.0`, create `dev1/b1` + `dev2/b1` (orchestrator)
- [ ] **After the tag:** Process Visualizer, Phase 0 section (orchestrator, D-029)

## Waiting on

| Item | From | Needed for |
|---|---|---|
| Dev2 onboarding on the Zenbook and office laptop #2 (`docs/ONBOARDING.md`) | Dev2 | Day 1 |
| D-056 on `p0/contracts`: Dev1 rule 1 (+ T1 12e), Dev2 `ExtractResponse` rule and `brain_api.md` (+ T2 12b/12d–12g) | Dev1, Dev2 | The Phase 0 PR and `contracts-v1.0` |
| OpenAI API key (with a spend limit) in Dev1's `.env` — deferred (D-050) | Owner | Block 2 (first OpenAI calls) |
| Google Drive folder `ScrubGPT-data` + Google Drive for desktop on the office PC (not installed) | Owner | Block 1 data (B1–B3) and sharing case packages |

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
| 2026-10-16 | Repo scaffold, CLAUDE.md files, planning docs, shared-memory system | — | Phase 0 setup by the orchestrator (b34ce00, 2719c7f; were c317292, 9853d3d) |
| 2026-10-16 | GitHub automation: CI guard, PR and issue templates (fe36cc0, was 4bf1b65); labels, milestones, rulesets | — | D-040 |
| 2026-10-16 | Fixes from the verification round: D-030…D-041, uv workspace, Procedure Reference contract, `.claude/settings.json` | — | Phase 0 setup by the orchestrator |
| 2026-10-16 | `main` history rewritten (approved by the owner): commit emails moved from a company account to `karthi-ai-engineer`'s noreply address. c317292 → b34ce00, 9853d3d → 2719c7f, 4bf1b65 → fe36cc0, bf0201c → 2fcffc0 (same files, messages and dates) | — | D-046 |
| 2026-10-16 | Agent team: Team Lead workflow + role, researcher, system designer, testers, labels, forms, CI tester split and account check, Dev2 in CODEOWNERS | — | D-042 … D-046 |
| 2026-10-16 | Team Lead live tests: sandbox fix (bubblewrap + socat), posts directly, reads issue/PR descriptions; issue #1 and test PR #2 passed and closed | — | D-047 |

## Friday drop log

| Date | Case packages dropped | Validated by Dev2? | Issues |
|---|---|---|---|
| — | — | — | — |
