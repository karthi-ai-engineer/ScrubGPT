# contracts/: shared by Dev1 and Dev2

This folder is **the only coupling** between the Brain track (Dev1) and the App track (Dev2). The spec is in `docs/MVP_Master_Plan.md` §4; the shared primitives are in §4.1.

| Path | What | Phase 0 author → approver |
|---|---|---|
| `pyproject.toml` | Package `scrubgpt-contracts` (uv workspace member) | Dev1 |
| `models/common.py` | **Shared primitives**: `Bilingual`, `TrustLabel`, `Role`, `Provenance`, `Evidence`, `ApiError`, ID types | Dev1 → Dev2 |
| `models/` (Case Package + DecisionRecord) | `case`, `timeline`, `moments`, `questions`, `seed_records`, `metrics`, `trainee`, `DecisionRecord` | Dev1 → Dev2 |
| `models/` (Brain API) + `brain_api.md` | Request and response models for every endpoint, plus the field-level spec | Dev2 → Dev1 |
| `schema/`, `ts/` | **Generated.** Never edit by hand | — |
| `codegen/` | Pydantic → JSON Schema (`mode="serialization"`) → TS (`npx json-schema-to-typescript`, pinned) | Dev2 → Dev1 |
| `fixtures/cases/case-fixture-01/` | The fake case: **synthetic media only**; IDs `case-fixture-01.m01`…`m06` | Dev1 → Dev2 |
| `mock_brain/` | The fake Brain: HTTP on **`:8101`**, same endpoints and shapes as the real Brain, deterministic | Dev2 → Dev1 |
| `validate.py` | Validates case packages and API responses | Dev1 → Dev2 |

## Rules

- **Versions:** `contract_version` is `"MAJOR.MINOR"`, starting at `"1.0"`. Adding an optional field bumps MINOR; anything breaking bumps MAJOR.
- **Tolerant readers:** every contract model uses `extra="ignore"`, so older code accepts newer MINOR versions.
- **Branches:** Phase 0 uses `p0/dev1-<slug>` and `p0/dev2-<slug>`. After `contracts-v1.0`, use `contracts/<slug>`. **Every change is approved by the other developer** before merging. After the merge, both developers merge `main` into their current branch (Claude does this).
