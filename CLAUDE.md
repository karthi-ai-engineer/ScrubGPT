# ScrubGPT: Surgical Knowledge System (MVP)

This project turns recorded **RARP** (robot-assisted radical prostatectomy) videos into **surgeon-verified decision knowledge**. The AI finds *what* happened; the surgeon explains *why* (by tap, voice or text); the answers become linked, provenance-tagged records that surgeons can browse and query in Japanese or English.

- **Organisation:** MY ROBOTS
- **Scope:** MVP demo only
- **Schedule:** 6 weeks (M + S features)
- **Status:** Phase 0, Contract Sprint

**Read first:**
- `docs/MVP_Master_Plan.md` (the plan; features have IDs like `C3`, `J2`)
- `docs/Research_Report_Phase0.md` (why things are the way they are)
- `docs/Surgical_Knowledge_System_Idea.md` (the original idea)

## Working agreement

- **The project owner makes the decisions.** Claude analyses, reports, recommends and implements what was agreed. Claude does not change scope, switch phases or override a decision on its own.
- When several decisions are open, ask them together as quick multiple-choice questions.
- Report outcomes honestly. If something is untested, failing or skipped, say so.

## Two tracks: ownership is the most important rule

Two developers build **in parallel** and integrate at the end. They are coupled **only** through `contracts/`.

| Path | Owner | Track |
|---|---|---|
| `knowledge/`, `brain/` | **Dev1** | Brain: offline pipeline + stateless Brain API |
| `app/server/`, `app/web/` | **Dev2** | App: app server, knowledge store, web UI |
| `contracts/` | **Both, frozen after the `contracts-v1.0` tag** | The two contracts |
| `docs/`, `scripts/`, root files | Both (coordinate) | — |

- **Know which developer you are working for** (Dev1 or Dev2). If it isn't clear from context, ask once.
- **Never edit the other track's folders.** If you need something from the other track, write down the request for your developer to pass on.
- **Never work around a contract.** If a contract seems wrong, stop and raise it. After `contracts-v1.0`, the only change allowed without both developers is adding a new **optional** field. Anything else needs both developers' agreement, a `contract_version` bump, and a `contracts/<slug>` branch.
- Files in `contracts/schema/` and `contracts/ts/` are **generated** from `contracts/models/` (Pydantic). Never edit them by hand.

### The two contracts

1. **Case Package** (files in `<DATA_DIR>/cases/<case_id>/`): `case.json`, `video.mp4`, `timeline.json`, `moments.json`, `questions.json`, `clips/`, `seed_records.json`, plus `metrics.json` and `trainee.json` where relevant. Plan §4.2.
2. **Brain API** (HTTP `:8100`, stateless): `/health`, `/v1/answers/transcribe`, `/v1/answers/extract`, `/v1/embed`, `/v1/ask`, `/v1/briefing` (S). Plan §4.4.

The core knowledge unit is the **DecisionRecord** (extended model, plan §4.3).

## Conventions (both tracks)

- **Time:** seconds as a float, measured from the start of the *normalised* video.
- **Evidence:** Media Fragment URIs, e.g. `video.mp4#t=2280.0,2520.0`.
- **IDs:**
  - Cases: `grasp-01`, `yt-en-03`, `yt-ja-02`
  - Moments: `<case>.m07`
  - Questions: `<case>.m07.q1`
  - Records: UUIDv7
- **Bilingual:** every human-readable field is `{ "ja": "...", "en": "..." }`. No English-only UI strings or content.
- **Provenance on every piece of knowledge.** Trust labels:
  - 🤖 AI-detected
  - 📐 Dataset annotation
  - 🎙️ Extracted from narration
  - 🩺 Explained by operating surgeon
  - 👁️ Interpreted by reviewer
  - ✅ Expert-validated
  - 🧪 Simulated (demo)
- Every contract file carries `"contract_version"`.

## Product guardrails (non-negotiable)

- **Education and reference only.** No clinical recommendations, no intra-operative alerts, no patient-specific predictions. A briefing is framed as *retrieval of past cases*.
- **Never invent reasoning.** A field the surgeon did not state stays empty ("not stated"). Every extracted field is grounded in a quote from the answer (G5).
- **Show counts, not percentages, when n < 20** ("seen in 3 of 9 cases").
- **No "could this have been avoided?" questions.**
- **Keep every viewpoint.** Several records per moment are expected; never merge them into one "correct" answer.
- Role-played or synthetic content is always labelled 🧪 or "synthetic".

## Data and secrets

- Videos, case packages and caches live in `DATA_DIR` (a Google Drive-synced folder; see `data/README.md`). **Never commit media, `data/` or `.env`.**
- Fixture media in `contracts/fixtures/` must be **synthetic** (e.g. an FFmpeg test pattern) and small. Never use real surgical video there.
- Demo data (GraSP, PSI-AVA, YouTube) is for **private, internal demo use only**.
- Do not paste API keys into chat. The developer puts them into `.env` themselves.

## Tech stack and environment

- **Python:** **uv**; Python 3.13 (the same minor version on every machine); Pydantic v2; FastAPI; SQLite (standard library).
- **Web:** Vite + React + TypeScript; Tailwind + shadcn/ui; react-i18next; TanStack Query; Cytoscape.js.
- **AI:** **OpenAI only.** Model names come from `.env` tiers (`VISION_FAST_MODEL`, and so on). **Only `brain/` calls OpenAI.** The app talks to the Brain API.
- **No PyTorch, CUDA or OpenCV.** Two of the three machines are Windows ARM64 (Snapdragon / Surface). Use Pillow + numpy + the FFmpeg CLI. If a wheel fails on ARM64, use x64 Python through uv (runs under emulation).
- **Machines:**
  - Office PC (x64, Dev1): all video processing.
  - Surface (ARM64, Dev1 at home).
  - Zenbook (ARM64, Dev2).

## Git workflow

- `main` stays runnable. Work on branches named `dev1/<feature-id>-<slug>` or `dev2/<feature-id>-<slug>`, and merge through PRs.
- Commit messages start with the feature ID, e.g. `C3: Viterbi step decoding with rule-book priors`.
- Each branch touches **only its own track's folders**. Contract changes go through `contracts/<slug>` branches that both developers review.
- **Friday data drop:** Dev1 copies the latest case packages to `<DATA_DIR>/drop/YYYY-MM-DD/`. Dev2's loader validates them. This is data only; no code is merged.

## Definition of Done (every feature)

- Works on real or fixture data, and **validates against the contracts**.
- **JA and EN** both present.
- **Provenance is visible** for every piece of knowledge it shows.
- Reviewed with `/code-review`.
- A one-paragraph usage note in the module README.

## Commands

To be filled in during Phase 0 Day 2 and later (environment setup, contract generation, validation, running the Brain, app and web).
