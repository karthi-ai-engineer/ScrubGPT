# contracts/: shared by Dev1 and Dev2

This folder is **the only coupling** between the Brain track (Dev1) and the App track (Dev2).
- **Spec:** `docs/MVP_Master_Plan.md` §4; shared primitives in §4.1.
- **Rules:** decisions D-023, D-030 … D-037.

Until Phase 0 Day 2, `pyproject.toml` here is a **placeholder**. Dev1 turns it into the real package.

## Layout and file ownership (D-031)

| Path | What | Author → approver |
|---|---|---|
| `pyproject.toml` | Package `scrubgpt-contracts` (import `scrubgpt_contracts`); console scripts below | Dev1 → Dev2 |
| `scrubgpt_contracts/models/common.py` | **Shared primitives**: `Bilingual`, `TrustLabel`, `Role`, `Provenance`, `Evidence`, `ApiError`, ID types (plan §4.1). **Pushed first on Day 2** | Dev1 → Dev2 |
| `scrubgpt_contracts/models/case_package.py` | `case`, `timeline`, `moments`, `questions`, `seed_records`, `metrics` | Dev1 → Dev2 |
| `scrubgpt_contracts/models/decision_record.py` | `DecisionRecord` + `DecisionRecordDraft` | Dev1 → Dev2 |
| `scrubgpt_contracts/models/reference.py` | `ProcedureReference`: steps, checkpoints, obstacle taxonomy (D-035) | Dev1 → Dev2 |
| `scrubgpt_contracts/models/brain_api.py` | Request and response models for every endpoint + the `ENDPOINTS` registry | Dev2 → Dev1 |
| `brain_api.md` | Field-level Brain API spec | Dev2 → Dev1 |
| `scrubgpt_contracts/validate.py` | `scrubgpt-validate` | Dev1 → Dev2 |
| `scrubgpt_contracts/mock_brain/` | `scrubgpt-mock-brain`: the **fake Brain**, HTTP on `:8101`, same endpoints and shapes as the real Brain, deterministic (D-037) | Dev2 → Dev1 |
| `scrubgpt_contracts/codegen/` | `scrubgpt-codegen`: Pydantic → `schema/` (JSON Schema, `mode="serialization"`) → `ts/` (`json-schema-to-typescript`, pinned) | Dev2 → Dev1 |
| `schema/`, `ts/` | **Generated.** Never edit by hand; CI fails if they're stale | — |
| `fixtures/cases/case-fixture-01/` | The fake case: **synthetic media only** (D-036); IDs `case-fixture-01.m01`…`m06` | Dev1 → Dev2 |
| `fixtures/reference/rarp.json` | Fixture Procedure Reference (`rarp.p01`…, fixed obstacle family IDs) | Dev1 → Dev2 |
| `fixtures/brain_api/<endpoint>.request.json` | Sample requests used by `scrubgpt-validate live` | Dev2 → Dev1 |

## Commands (from Phase 0 Day 3)

```
uv run scrubgpt-validate case contracts/fixtures/cases/case-fixture-01
uv run scrubgpt-validate reference contracts/fixtures/reference/rarp.json
uv run scrubgpt-validate response <endpoint> <file.json>
uv run scrubgpt-mock-brain --port 8101
uv run scrubgpt-validate live --base-url http://localhost:8101   # calls every endpoint, validates every response
uv run scrubgpt-codegen
```

CI runs all of these automatically once the files exist.

## Synthetic fixture media (D-036, measured on the office PC)

Generate the fixture video (1.76 MB, 300 s):

```
ffmpeg -f lavfi -i "testsrc2=size=426x240:rate=5:duration=300" \
       -f lavfi -i "sine=frequency=440:sample_rate=16000:duration=300" \
       -c:v libx264 -preset veryslow -crf 40 -pix_fmt yuv420p \
       -c:a aac -b:a 16k -ac 1 -movflags +faststart -shortest video.mp4
```

- **Clips:** `ffmpeg -ss <t> -t 20 -i video.mp4 -c copy clips/<moment_id>.mp4` (about 0.18 MB each).
- **Posters:** `ffmpeg -ss <t> -i video.mp4 -frames:v 1 -q:v 5 poster.jpg` (about 10 KB).
- **Limit:** **≤ 5 MB in total under `fixtures/`**, enforced by CI.

## Rules

- **Phase 0** happens on **one shared branch, `p0/contracts`** (D-030). Each developer edits **only their own files** above. Always `git pull --rebase` before pushing. It ends with one PR approved by both.
- **Versions:** `contract_version` is `"MAJOR.MINOR"`, starting at `"1.0"`.
  - v1.0 fields are required keys (nullable where they may be absent).
  - Fields added later are `T | None = None` (MINOR).
  - Breaking changes are MAJOR.
- **Tolerant readers:** every contract model uses `extra="ignore"`.
- **After `contracts-v1.0`:** changes go through `contracts/<slug>` branches.
  - **Every change is approved by the other developer.** A MAJOR change needs agreement before starting (D-033).
  - After the merge, both developers merge `main` into their current branch (Claude does this).
