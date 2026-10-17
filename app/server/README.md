# app/server/ (Dev2)

App server + SQLite knowledge store. See `app/server/CLAUDE.md` for the rules and `docs/MVP_Master_Plan.md` §2.9 for the features (I1–I8).

## SSE events (internal to the App track)

| Event | Payload | Sent when |
|---|---|---|
| `case.ended` | `case_id` | Replay reaches the end of the video |
| `answer.confirmed` | `question_id`, `record_id` | Surgeon taps Confirm |
| `record.created` | DecisionRecord | Record stored |
| `graph.updated` | changed node and edge IDs | Graph changes |

## Usage

```
uv sync --all-packages
uv run scrubgpt-app serve                      # http://127.0.0.1:8000 (APP_PORT), DATA_DIR from .env
uv run scrubgpt-app check                      # validate every package under DATA_DIR
uv run scrubgpt-app drop <Drive>/drop/2026-10-30 [--reference FILE]   # a Friday drop, file by file
uv run pytest -q app/server                    # unit tests (tests/acceptance/ belongs to Tester 2)
```

**Settings** come from the environment, then the repo-root `.env`, then defaults: `DATA_DIR` (default `./contracts/fixtures`, D-026), `APP_PORT` (8000), `BRAIN_MODE` (`mock`), `MOCK_BRAIN_URL`, `BRAIN_URL`, `APP_DB_PATH`. Relative paths start at the repo root. An empty value (`APP_PORT=`) counts as unset. `--data-dir` overrides `DATA_DIR` for one run. An invalid value (`APP_PORT` not 1–65535, `BRAIN_MODE` not `mock`/`real`) stops every command with a message naming the setting (exit 2).

**Case loader (I1).** At start-up the server validates every `DATA_DIR/cases/<case_id>/` with `scrubgpt_contracts.validate.validate_case`, the same check as `scrubgpt-validate case`. Only complete, valid packages load. A package with any error is rejected with its reasons (`GET /api/catalog`, `scrubgpt-app check`) and is never patched. Procedure References load from `DATA_DIR/reference/`. **Drop mode** (D-038) reports a drop per package and per file; `video.mp4` may be missing (a warning), but such a package isn't loadable yet. Without `--reference`, the drop is checked against the only `*.json` in `<drop>/reference/`, else the only one in `DATA_DIR/reference/`, else the validator's own lookup. Copy the result into `docs/status/dev2.md` → "Drop results". Exit codes for `check` and `drop`: 0 all loadable, 1 not all, 2 the check couldn't run.

**API.** This is the app track's internal API (not a contract, like the SSE events above): every error is an `ApiError` body (plan §4.1; the UI localises by `code`), `/api/health` carries `contract_version`, and every contract document inside a response carries its own.

| Method and path | Body |
|---|---|
| `GET /api/health` | `status`, `contract_version`, `brain_mode`, `cases: {loaded, rejected}` |
| `GET /api/cases` | `{cases: CaseSummary[]}`, by case id. `CaseSummary` = `{case, media: {video, poster}, counts: {moments, operating_questions, reviewer_questions, seed_records}, trust_labels[], has_metrics}` |
| `GET /api/cases/{case_id}` | `CaseSummary` + `timeline`, `moments`, `questions`, `seed_records`, `metrics` (or null), unchanged contract documents |
| `GET /api/catalog` | loaded ids with warnings, rejected packages and references with their problems |
| `GET /api/references/{procedure_id}` | the Procedure Reference |
| `GET /media/cases/{case_id}/{path}` | `video.mp4`, `poster.jpg`, `clips/*.mp4\|jpg`, `thumbs/*`, with HTTP Range (206) for seeking and 8–16× play; nothing else in a case folder |

`trust_labels` are the distinct labels in the package (timeline items, moments, seed records), in enum order. When `app/web/dist` exists (`npm run build`), the server also serves the web app at `/` for the offline demo.
