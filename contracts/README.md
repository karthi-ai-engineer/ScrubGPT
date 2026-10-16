# contracts/: shared by Dev1 and Dev2

This folder is **the only coupling** between the Brain track (Dev1) and the App track (Dev2). Its content is written together in **Phase 0** and frozen at the git tag **`contracts-v1.0`**.

| Path | What | Edited by hand? |
|---|---|---|
| `models/` | **Pydantic v2 models: the single source of truth** (Case Package files, DecisionRecord, Brain API requests and responses) | Yes, by both developers together |
| `schema/` | JSON Schema generated from `models/` | **No** |
| `ts/` | TypeScript types generated from `schema/` | **No** |
| `brain_api.md` | Brain API endpoint spec (contract #2) | Yes, by both |
| `fixtures/` | A hand-made example Case Package (`case-fixture-01`) using **synthetic media only** | Yes, by both |
| `mock_brain/` | A tiny FastAPI app that returns fixture responses for every Brain API endpoint | Yes, by both |
| `validate.py` | Validates any case package or API response against the schemas | Yes, by both |

## Change process (after `contracts-v1.0`)

- **Adding a new optional field:** allowed. Tell the other developer, bump the patch version, and regenerate.
- **Any other change** (rename, removal, a field that becomes required, a change of meaning):
  1. Create a `contracts/<slug>` branch.
  2. Both developers review it.
  3. Bump the minor version and regenerate.
  4. Both tracks update.

The specification is in `docs/MVP_Master_Plan.md` §4.
