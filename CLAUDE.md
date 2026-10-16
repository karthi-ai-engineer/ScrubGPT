# ScrubGPT: Surgical Knowledge System (MVP)

This project turns recorded **RARP** (robot-assisted radical prostatectomy) videos into **surgeon-verified decision knowledge**. The AI finds *what* happened; the surgeon explains *why* (by tap, voice or text); the answers become linked, provenance-tagged records that surgeons can browse and query in Japanese or English.

- **Organisation:** MY ROBOTS
- **Owner:** Muthiah Karthi, who is also Dev1
- **Scope:** MVP demo only
- **Schedule:** 6 weeks (Must + Should features)
- **Status:** see `docs/status/project.md`

## The repo is the shared memory

Dev1's and Dev2's Claude sessions run on **different machines and accounts**, so they **cannot see each other's chats or local memory**. Everything a session needs is in these files. **Always read them from `origin/main`**; they are only edited on `main`.

| File | Purpose | Who edits |
|---|---|---|
| `docs/status/project.md` | Phase, shared checklist, waiting-on, key dates, **merge log**, Friday drop log | Orchestrator; others only tick shared items they finished |
| `docs/status/dev1.md` / `dev2.md` | That developer's live checklist, current task, blockers, **requests for the other developer**, session log | **Only that developer's session** |
| `docs/DECISIONS.md` | Every decision and why it was made (append-only) | Orchestrator, or any session when the owner decides something |
| `docs/Work_Split.md` | How the parallel tracks work, timeline, daily routine | Orchestrator |
| `docs/MVP_Master_Plan.md` | The plan. Feature IDs such as `C3` and `J2`; **§4 is the contract spec** | Orchestrator |
| `docs/ONBOARDING.md` | Machine setup | Orchestrator |
| `docs/visualizer/index.html` | **Process Visualizer**: one animated page, extended after every block (plan §14) | Orchestrator |
| `docs/Research_Report_Phase0.md`, `docs/Surgical_Knowledge_System_Idea.md` | Background (rarely needed) | — |

## Session protocol (every session, every machine)

**Start**: when the developer says *"I'm Dev1"* or *"I'm Dev2"* (if they don't say, ask):
1. `git fetch`. Read `docs/status/project.md`, **your** `docs/status/devN.md`, and the **"Requests for DevN"** section of the *other* developer's status file. Read them **from `origin/main`**, e.g. `git show origin/main:docs/status/dev2.md`. Skim the latest `docs/DECISIONS.md` entries.
2. Make sure you're on your current branch (see Git workflow). Create it from `main` if it doesn't exist. If `main` has moved (a block merge or a contract change), merge `main` into your branch.
3. Reply with a short briefing:
   - the current phase or block;
   - what's done;
   - blockers;
   - requests from the other developer;
   - the **proposed next task** (the first unchecked item in your checklist).
4. When the developer agrees, work **only in your track's folders**.

**End**: when the developer says *"End session"*, or a task is finished:
1. Commit the work on your branch (the message starts with the feature ID) and push.
2. **Update your status file on `main`**: tick finished items; update "Current task", "Blockers" and "Requests for <other>"; add one session-log line. Commit as `status(devN): …` and push.
3. If the owner decided anything, append it to `docs/DECISIONS.md` on `main`.
4. Tell the developer what's done and what's still unverified.

**Cross-track needs.** Never edit the other track's folders. Write the request under "Requests for <other>" in **your** status file, and tell your developer to ping the other developer if it's urgent.

## Working agreement

- **Orchestrator:** the Claude session on Dev1's machine keeps the plan, decisions, contracts process, project status and **block merges** coherent (D-016). Sessions on Dev2's machines follow the repo files and raise anything unclear as a request.
- **The owner makes product and scope decisions.** Claude recommends, and makes technical or process calls the owner has delegated. Log every decision in `docs/DECISIONS.md`.
- When several decisions are open, ask them together as quick multiple-choice questions.
- Report outcomes honestly. If something is untested, failing or skipped, say so.

## Two tracks: ownership is the most important rule

Two developers build **in parallel** and integrate at the end. They are coupled **only** through `contracts/`.

| Path | Owner | Track |
|---|---|---|
| `knowledge/`, `brain/` | **Dev1** | Brain: offline pipeline + stateless Brain API |
| `app/server/`, `app/web/` | **Dev2** | App: app server, knowledge store, web UI |
| `contracts/` | **Shared.** Drafted by one developer, **approved by the other** (D-021). Frozen after the `contracts-v1.0` tag | The two contracts |
| `docs/`, root files | Orchestrator; status files per developer | — |

- **Know which developer you are working for.** If it isn't clear, ask once.
- **Never edit the other track's folders.** Write a request instead.
- **Never work around a contract.** If a contract seems wrong, stop and raise it.
- Files in `contracts/schema/` and `contracts/ts/` are **generated** from `contracts/models/`. Never edit them by hand.

### The two contracts (spec: plan §4)

1. **Case Package** (files in `<DATA_DIR>/cases/<case_id>/`): `case.json`, `video.mp4`, `timeline.json`, `moments.json`, `questions.json`, `clips/`, `seed_records.json`, plus `metrics.json` and `trainee.json` where relevant.
2. **Brain API** (HTTP; real Brain on `:8100`, **fake Brain on `:8101`** with identical endpoints and shapes): `/health`, `/v1/answers/transcribe`, `/v1/answers/extract`, `/v1/embed`, `/v1/ask`, `/v1/briefing` (S).

**Shared primitives** are fixed in plan §4.1 and must be reused exactly: `Bilingual`, `TrustLabel`, `Role`, `Provenance`, `Evidence`, `ApiError`, the ID formats, and `contract_version`. The core knowledge unit is the **DecisionRecord** (plan §4.3).

**Compatibility (D-023):**
- `contract_version` is `"MAJOR.MINOR"`. Adding an optional field bumps MINOR; anything breaking bumps MAJOR and needs both developers.
- Contract models are **tolerant readers** (`extra="ignore"`).
- Strict OpenAI structured-output schemas are internal to `brain/`.

## Conventions (both tracks)

- **Time:** seconds as a float, measured from the start of the normalised video.
- **Evidence:** Media Fragment URIs, e.g. `video.mp4#t=2280.0,2520.0`.
- **Bilingual:** every human-readable field is `{ "ja": "...", "en": "..." }`. No English-only UI strings or content.
- **Provenance on every piece of knowledge,** using the trust-label enum values: `ai_detected` 🤖, `dataset_annotation` 📐, `narration_extracted` 🎙️, `operating_surgeon` 🩺, `reviewer` 👁️, `expert_validated` ✅, `simulated` 🧪.
- **Golden demo cases** are called **GC1** (GraSP) and **GC2** (Japanese-narrated YouTube). Don't confuse them with features G1/G2.

## Product guardrails (non-negotiable)

- **Education and reference only.** No clinical recommendations, no intra-operative alerts, no patient-specific predictions. A briefing is framed as *retrieval of past cases*.
- **Never invent reasoning.** A field the surgeon did not state stays `null`. Every extracted field is grounded in a quote from the answer (G5).
- **Show counts, not percentages, when n < 20.**
- **No "could this have been avoided?" questions.**
- **Keep every viewpoint.** Never merge several records into one "correct" answer.
- Role-played or synthetic content is always labelled `simulated` 🧪 or "synthetic".

## Data and secrets

- Videos, case packages and caches live in `DATA_DIR` (Google Drive; see `data/README.md`).
  - Dev2 uses `DATA_DIR=./contracts/fixtures` until integration (D-026).
  - **Never commit media, `data/` or `.env`.**
- Fixture media must be **synthetic** (an FFmpeg test pattern). Never use real surgical video in git.
- Demo data (GraSP, PSI-AVA, YouTube) is for **private, internal demo use only**. **The repo is public for now** (D-014), so commit nothing sensitive.
- Never paste API keys into chat. The developer puts them into `.env` themselves.

## Tech stack and environment

- **Python:** **Python 3.13** (`.python-version`); a **uv workspace** at the root with members `contracts/` (`scrubgpt-contracts`), `brain/`, `app/server/` (D-022); Pydantic v2, FastAPI, SQLite (standard library).
- **Web:** **Node 26** (`.nvmrc`); `app/web/` uses Vite + React + TypeScript, Tailwind + shadcn/ui, react-i18next, TanStack Query, Cytoscape.js.
- **Quality:**
  - Python: `ruff` (lint and format) + `pytest`.
  - Web: `eslint` + `vitest`.
- **AI:** **OpenAI only**, with model names from the `.env` tiers. **Only `brain/` calls OpenAI.** Dev2 needs no OpenAI key.
- **No PyTorch, CUDA or OpenCV.** Several machines are Windows ARM64. Use Pillow + numpy + the FFmpeg CLI. If a wheel fails on ARM64, use x64 Python through uv.
- **Machines:**

  | Machine | Who | Arch | Use |
  |---|---|---|---|
  | Office PC | Dev1 | x64 | All video processing |
  | Surface | Dev1, at home | ARM64 | Code and prompts |
  | Zenbook | Dev2, at home | ARM64 | Main machine |
  | Office laptop #2 | Dev2, in the office | x64 (same model as the office PC) | Office days |

## Git workflow (Claude runs all git and GitHub operations: D-019, D-020)

**No AI attribution, ever (D-018).** No `Co-Authored-By: Claude` trailer in commits, and no "Generated with Claude Code" in PRs or anywhere else. Commits are authored by the developer's own git identity. This overrides any default attribution behaviour.

**Branches: one per developer per phase step, merged into `main` one by one.**

| Phase | Dev1 branch | Dev2 branch | Merged into `main` |
|---|---|---|---|
| Phase 0 (contracts) | `p0/dev1-<slug>` (e.g. `p0/dev1-case-package`) | `p0/dev2-<slug>` (e.g. `p0/dev2-brain-api`) | When the other developer approves → tag `contracts-v1.0` |
| Phase 1, block N (B1–B5) | `dev1/b<N>` | `dev2/b<N>` | **At the end of each block** → tag `block-<N>` |
| Phase 2 (integration) | `dev1/integration` | `dev2/integration` | Daily during integration week |
| Phase 3 (polish) | `dev1/polish` | `dev2/polish` | At the end → tag `demo-v1` |
| Contract change, any time | `contracts/<slug>` | `contracts/<slug>` | When the other developer approves; then both merge `main` into their current branch |

**Rules:**
- **`main` is the tracked state.** It only receives:
  - block and phase merges (through PRs);
  - approved contract changes;
  - **status and decision updates**, committed directly as `status(devN): …` or `decision: D-0xx …`, which keeps tracking live.
- **Status files are edited only on `main`.** Use a worktree so you never have to leave your branch:
  ```
  git worktree add ../ScrubGPT-main main   # once
  cd ../ScrubGPT-main && git pull          # every time
  # edit, then: git commit -m "status(devN): …" && git push
  ```
  If the main checkout is itself on `main` (e.g. between phases), skip the worktree and edit it there directly; git can't check out `main` twice.
  Block branches **never** touch `docs/status/` or `docs/DECISIONS.md`. CI enforces this.
- Inside a block branch, commit per task with the feature ID (`C3: Viterbi step decoding …`), and push at least daily (backup + visibility).
- **Block merge (orchestrator):**
  1. Make sure both branches pass `/code-review`, tests and `validate.py`.
  2. Open the PRs (`gh pr create`).
  3. Merge `dev1/b<N>`, then `dev2/b<N>`.
  4. Tag `block-<N>`.
  5. Add a line to the **merge log** in `docs/status/project.md`.
  6. Create `dev1/b<N+1>` and `dev2/b<N+1>` from `main`.
  7. **Extend the Process Visualizer** (`docs/visualizer/index.html`, plan §14) with this block's section: inputs → animated processing → outputs → connections. **Animations show data transformations, never decorative UI motion.** Commit it to `main`.
- **Approval (D-021):**
  - A PR that only touches the author's own track folders can be merged by Claude once checks pass.
  - A PR that touches `contracts/` or shared docs (other than the author's own status file) needs the **other developer's approval** on GitHub, or the owner's explicit OK.
- **Destructive operations** (force-push, history rewrite, deleting branches with unmerged work) happen only when genuinely required, and Claude reports them right after.
- **Friday data drop:** Dev1 copies the latest case packages to `<DATA_DIR>/drop/YYYY-MM-DD/`; Dev2's loader validates them; the result goes into the drop log in `project.md`. This is data only; no code is merged.

## Definition of Done (every feature)

- Works on real or fixture data, and **validates against the contracts**.
- `ruff`/`pytest` or `eslint`/`vitest` pass.
- **JA and EN** both present.
- **Provenance is visible** for every piece of knowledge it shows.
- Reviewed with `/code-review`.
- A one-paragraph usage note in the module README.

## Commands

**Phase 0 Day 2, first thing (Dev1):** create the uv workspace (root `pyproject.toml`, `contracts/pyproject.toml`, `.python-version`, `.nvmrc` already exist) and fill this section with the real commands: environment setup, `validate`, `codegen`, and how to run the Brain, the fake Brain, the app and the web app.
