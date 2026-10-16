# app/server/: Dev2 track (App server and knowledge store)

**Owner:** Dev2. **Scope:** `app/`, plus Dev2's assigned files in `contracts/` during Phase 0 and approved contract changes (D-031). Read the root `CLAUDE.md` first; its rules apply here too.

`app/server/pyproject.toml` is a placeholder until Block 1. Replace it with the real `scrubgpt-app` project (depends on `scrubgpt-contracts` through the workspace).

**What this part delivers** (feature IDs from `docs/MVP_Master_Plan.md` §2): **I1–I8**. That covers:
- the case loader with contract validation;
- the SQLite knowledge store (entities, edges, provenance, decision records, viewpoints);
- pattern counts and retrieval;
- SSE live updates;
- the brain client (mock or real);
- demo seed and reset;
- the audit log.

## Rules

1. **Never call OpenAI directly.** All AI goes through the **brain client**, including `/v1/translate`, which keeps edited chips bilingual (D-034). The app assigns `answer_id` (UUIDv7) and stores answer audio locally:
   - `BRAIN_MODE=mock` calls the **fake Brain** (an HTTP server from `contracts/mock_brain`) at `MOCK_BRAIN_URL` (`:8101`). This is the default until integration.
   - `BRAIN_MODE=real` calls the real Brain API at `BRAIN_URL` (`:8100`). Both have identical endpoints and shapes.
   - Handle `ApiError` (plan §4.1). Map 503 and 504 to "Brain unavailable" for the UI.
2. **The case loader validates every case package** against the contracts (reuse `scrubgpt_contracts`), and loads the **Procedure Reference** (`<DATA_DIR>/reference/`) for step and obstacle names. It loads **only complete packages** (required files: plan §4.2). It rejects invalid ones with a clear error and never patches them silently.
   - **Drop mode** (D-038) validates a Friday drop (`<Drive>/drop/YYYY-MM-DD/`) **file by file** and reports per file, because partial packages are expected.
   - Record the result in `docs/status/dev2.md` → "Drop results".
3. **SQLite:**
   - Use WAL mode, and keep the database file **local** (`APP_DB_PATH`). **Never put it in the Google Drive folder**; sync can corrupt a live database.
   - Schema changes are migration scripts, kept small and ordered.
4. **The knowledge store keeps every viewpoint.** Many records can point to one moment. Never overwrite one surgeon's record with another's.
5. **Provenance is required.** A record can't be stored without a trust label, `attributed_to`, `generated_by` and confirmation info.
6. **Pattern counts** always return `n`. Return percentages only when `n ≥ 20`.
7. **Serve video and clips with HTTP Range support** so the browser can seek and play at 8–16×.
8. **SSE events** (`answer.confirmed`, `record.created`, `graph.updated`, `case.ended`) are documented in this folder's README. They are internal to the app track, not a contract.
9. **Seed and reset are one idempotent command** that rebuilds the database from the case packages and their `seed_records.json`.
10. **Bilingual:** API responses pass through both `ja` and `en` text.
