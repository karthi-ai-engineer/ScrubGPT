# app/server/: Dev2 track (App server and knowledge store)

**Owner:** Dev2. **Scope:** `app/` only. Read the root `CLAUDE.md` first; its rules apply here too.

**What this part delivers** (feature IDs from `docs/MVP_Master_Plan.md` §2): **I1–I8**. That covers:
- the case loader with contract validation;
- the SQLite knowledge store (entities, edges, provenance, decision records, viewpoints);
- pattern counts and retrieval;
- SSE live updates;
- the brain client (mock or real);
- demo seed and reset;
- the audit log.

## Rules

1. **Never call OpenAI directly.** All AI goes through the **brain client**:
   - `BRAIN_MODE=mock` serves fixture responses from `contracts/mock_brain` and is the default until integration.
   - `BRAIN_MODE=real` calls the Brain API at `BRAIN_URL`.
2. **The case loader validates every case package** against the contracts. It **rejects** an invalid package with a clear error and never patches it silently. The same loader validates the Friday data drop (`<DATA_DIR>/drop/`).
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
