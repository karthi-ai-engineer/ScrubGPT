# data/: never committed

Everything here except this README is git-ignored. Videos, case packages, the procedure reference and API caches are shared through **Google Drive**, not git. The code finds them through `DATA_DIR` in `.env`. Relative paths resolve against the repo root.

## Which DATA_DIR to use

| Who | `DATA_DIR` | Why |
|---|---|---|
| **Dev1** (all machines) | The Google Drive folder, e.g. `G:/My Drive/ScrubGPT-data` | Dev1's pipeline writes the real case packages here |
| **Dev2**, until integration (Week 6) | `./contracts/fixtures` | The app is built on the fake case (D-026). Friday drops are validated **by path** from the Drive folder |
| **Everyone**, from integration on | The Google Drive folder | Real cases |

## Google Drive setup (each machine)

1. Install **Google Drive for desktop**.
2. Add the shared folder `ScrubGPT-data` to "My Drive".
3. Set it to **"Available offline"**, so videos play smoothly.

## Layout

```
<DATA_DIR>/
├─ raw/                ← original downloads (GraSP, PSI-AVA, YouTube). Dev1 only.
├─ work/<case_id>/     ← pipeline intermediates (frames, partial results). Dev1 only.
├─ atlas/              ← step-atlas reference images (indexed by knowledge/atlas/). Dev1 only.
├─ cases/<case_id>/    ← CASE PACKAGES (contract #1). Written by Dev1, read by Dev2.
├─ reference/<procedure_id>.json ← PROCEDURE REFERENCE (contract #1b, D-035).
├─ cache/              ← OpenAI response cache (Brain). Needed for the offline demo.
└─ drop/YYYY-MM-DD/    ← Friday data drop (D-038): JSON, clips and posters (+ video.mp4 for golden cases).
```

## Rules

- Demo data is for **private, internal demo use only**. Never upload or redistribute it, and never copy it into the (public) repo.
- No real patient data or hospital videos in the MVP.
- Never put the app's SQLite database here; Drive sync can corrupt a live database.
