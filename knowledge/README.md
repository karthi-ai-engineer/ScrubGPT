# knowledge/: Dev1 (Brain track)

This folder holds the structured surgical knowledge that the AI compares every case against. It does **not** hold code. Feature IDs **A1–A6** in `docs/MVP_Master_Plan.md`.

| Path | Content |
|---|---|
| `rulebooks/rarp.yaml` | **The RARP Rule Book**: phases, steps, expected order, typical durations, anatomy, instruments, safety checkpoints, known obstacles per step, and JA/EN terms |
| `taxonomy/obstacles.yaml` | **Obstacle family tree**: 8 universal families plus RARP-specific leaves, and the cause attribution |
| `vocab/terms.yaml` | **Bilingual vocabulary**: JA/EN terms with synonyms |
| `atlas/` | Index of the reference frames for each step, taken from GraSP ground truth (images live in `DATA_DIR`) |

Every file carries `review_status: draft_pending_urologist_review` until a surgeon has reviewed it. Adding a new surgery later should only mean adding a new rule book here, not changing the engine.
