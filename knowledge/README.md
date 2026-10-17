# knowledge/: Dev1 (Brain track)

This folder holds the structured surgical knowledge that every case is compared against. It holds data files, not code. Feature IDs **A1–A6** in `docs/MVP_Master_Plan.md`.

| Path | Content | Feature |
|---|---|---|
| `ontology/core.yaml` | **Core ontology (Layer 0)**: entity and relation types, aligned to OntoSPM and PROV-O IRIs | A2 |
| `rulebooks/rarp.yaml` | **The RARP Rule Book**: phases, steps, expected order, typical durations, anatomy, instruments, safety checkpoints, known obstacles per step, JA/EN terms | A1 |
| `taxonomy/obstacles.yaml` | **Obstacle family tree**: the 8 fixed families (D-035) + RARP-specific leaves, and the cause attribution | A3 |
| `vocab/terms.yaml` | **Bilingual vocabulary**: JA/EN terms with synonyms | A4 |
| `atlas/rarp.yaml` | **Step atlas index**: the reference frames of each step (GraSP case + second), taken from GraSP ground truth by `scrubgpt-brain atlas pick`. The images live in `<DATA_DIR>/atlas/`, never in git | A6 |

- **Trust labels (A5)** are delivered as the `TrustLabel` enum in `contracts/` (Phase 0).
- **What the app sees:** the app never reads this folder. Dev1 **exports** the rule book and taxonomy into the **Procedure Reference** contract (`<DATA_DIR>/reference/rarp.json`, D-035) in Block 1. The step and obstacle IDs must stay stable after that export.
- **Review status:** every file carries `review_status: draft_pending_urologist_review` until a surgeon has reviewed it.
- **New surgeries:** adding one later should only mean adding a new rule book here, not changing the engine.
