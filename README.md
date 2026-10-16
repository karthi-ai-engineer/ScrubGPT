# ScrubGPT

**Surgical Knowledge System, MVP (MY ROBOTS).**

This project turns recorded robot-assisted radical prostatectomy (RARP) videos into structured, searchable, **surgeon-verified** knowledge. The AI finds *what* happened; the surgeon explains *why* by tap, voice or text, in Japanese or English. Every fact shows where it came from.

> Education/reference tool only. It does not give clinical advice.

## Status

**Phase 0: Contract Sprint.** No application code yet.

## Documents

| Doc | What |
|---|---|
| [`docs/ONBOARDING.md`](docs/ONBOARDING.md) | **Start here:** machine setup and how to start a Claude session ("I'm Dev2. Start session.") |
| [`docs/status/`](docs/status/) | **Live status:** `project.md` (shared), `dev1.md`, `dev2.md` |
| [`docs/TEAM.md`](docs/TEAM.md) | **The agent team:** Team Lead on GitHub, research assistant, system designer, one tester per developer; how requests move |
| [`docs/Work_Split.md`](docs/Work_Split.md) | How Dev1 and Dev2 work in parallel: contracts, fakes, Friday drops, timeline |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Every decision and why it was made |
| `docs/visualizer/index.html` | **Process Visualizer**: one animated page showing what each phase does (created after `contracts-v1.0`, extended after every phase or block) |
| [`docs/MVP_Master_Plan.md`](docs/MVP_Master_Plan.md) | **The plan:** feature catalogue, architecture, contracts, schedule, risks |
| [`docs/Research_Report_Phase0.md`](docs/Research_Report_Phase0.md) | Research: clinical review, datasets, tech, market, regulation |
| [`docs/Surgical_Knowledge_System_Idea.md`](docs/Surgical_Knowledge_System_Idea.md) | The original idea |
| [`CLAUDE.md`](CLAUDE.md) | Working rules for both developers and their Claude sessions |

## Repository layout

```
contracts/   shared contracts (frozen after contracts-v1.0): Pydantic models → JSON Schema → TS types
knowledge/   Dev1: RARP rule book, obstacle taxonomy, bilingual vocabulary, step atlas
brain/       Dev1: offline pipeline + stateless Brain API (all OpenAI calls live here)
app/server/  Dev2: app server + SQLite knowledge store
app/web/     Dev2: web UI (Control Room, Answer app, Library, Ask, …)
scripts/     start / reset / validate helpers
data/        git-ignored; videos and case packages are synced via Google Drive (see data/README.md)
docs/        plan, research, idea
```

## Setup

Follow [`docs/ONBOARDING.md`](docs/ONBOARDING.md). In short: install the tools, clone, set the repo-local git identity (your GitHub noreply email and push account, D-046), `uv sync --all-packages`, copy `.env.example` to `.env`, then start Claude Code and say "I'm Dev1/Dev2. Start session." Never commit `.env` or any media.
