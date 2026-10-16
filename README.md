# ScrubGPT

**Surgical Knowledge System, MVP (MY ROBOTS).**

This project turns recorded robot-assisted radical prostatectomy (RARP) videos into structured, searchable, **surgeon-verified** knowledge. The AI finds *what* happened; the surgeon explains *why* by tap, voice or text, in Japanese or English. Every fact shows where it came from.

> Education/reference tool only. It does not give clinical advice.

## Status

**Phase 0: Contract Sprint.** No application code yet.

## Documents

| Doc | What |
|---|---|
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

To be added in Phase 0. Copy `.env.example` to `.env` and fill it in. Never commit `.env` or any media.
