# data/: never committed

Everything here except this README is git-ignored. Videos, case packages and API caches are shared between Dev1 and Dev2 through **Google Drive**, not git.

## Setup (each machine)

1. Install **Google Drive for desktop**. Set the shared folder `ScrubGPT-data` to **"Available offline"** (or use mirror mode) so videos play smoothly.
2. In your `.env`, point `DATA_DIR` at it, for example:
   ```
   DATA_DIR=G:/My Drive/ScrubGPT-data
   ```
   All code reads paths from `DATA_DIR`, and nothing hard-codes this folder.

## Layout

```
<DATA_DIR>/
├─ raw/            ← original downloads (GraSP, PSI-AVA, YouTube). Dev1 only.
├─ cases/<case_id>/← CASE PACKAGES (contract #1). Written by Dev1, read by Dev2.
├─ cache/          ← OpenAI response cache (Brain). Needed for the offline demo.
└─ drop/YYYY-MM-DD/← Friday data drop: Dev1 copies the latest case packages here; Dev2 validates them.
```

## Rules

- Demo data is for **private, internal demo use only**. Never upload or redistribute it.
- No real patient data or hospital videos in the MVP.
