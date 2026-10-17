# app/server/ (Dev2)

App server + SQLite knowledge store. See `app/server/CLAUDE.md` for the rules and `docs/MVP_Master_Plan.md` §2.9 for the features (I1–I8).

## SSE events (internal to the App track)

`GET /api/events` is a Server-Sent Events stream (I5): `retry: 3000`, then one `id` / `event` / `data` (JSON) block per event, and a `: ping` comment every 15 s. Every connected tab gets every event; a tab that falls 100 events behind is dropped and reconnects.

| Event | Payload | Sent when |
|---|---|---|
| `case.ended` | `case_id`, `questions: {operating, reviewer}` (counted from `questions.json`), `est_seconds` (sum of the operating questions' `est_seconds`) | The Control Room's replay reaches the end of the video and calls `POST /api/cases/{case_id}/replay-ended` |
| `answer.confirmed` | `case_id`, `question_id`, `record_id`, `answer_id` | Surgeon taps Confirm (`POST /api/answers/confirm`), first of three |
| `record.created` | `record` (the stored DecisionRecord) | Second, right after |
| `graph.updated` | `case_id`, `nodes: [{id, kind}]` (new only), `edges: [{src, dst, kind, record_id, trust_label}]` | Third: what the record added to the knowledge graph |

## Usage

```
uv sync --all-packages
uv run scrubgpt-app serve                      # http://127.0.0.1:8000 (APP_PORT), DATA_DIR from .env
uv run scrubgpt-app check                      # validate every package under DATA_DIR
uv run scrubgpt-app drop <Drive>/drop/2026-10-30 [--reference FILE]   # a Friday drop, file by file
uv run pytest -q app/server                    # unit tests (tests/acceptance/ belongs to Tester 2)
```

**Settings** come from the environment, then the repo-root `.env`, then defaults: `DATA_DIR` (default `./contracts/fixtures`, D-026), `APP_PORT` (8000), `BRAIN_MODE` (`mock`), `MOCK_BRAIN_URL`, `BRAIN_URL`, `APP_DB_PATH`. Relative paths start at the repo root. An empty or blank value (`APP_PORT=`) counts as unset. `--data-dir` overrides `DATA_DIR` for one run. An invalid value (`APP_PORT` not 1–65535, `BRAIN_MODE` not `mock`/`real`) stops every command with a message naming the setting (exit 2). `serve --port` follows the same 1–65535 rule (argparse error, exit 2).

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
| `GET /api/events` | the SSE stream (above) |
| `POST /api/cases/{case_id}/replay-ended` | publishes `case.ended` and returns its payload; unknown case → 404 |
| `GET /api/cases/{case_id}/answer-queue?role=operating\|reviewer` | the questions from `questions.json` (never invented), each with its `moment`, `clip`, `poster` and `answered`; `est_seconds` of the unanswered ones |
| `GET /api/cases/{case_id}/records` | the case's stored records: `{record, source: seed\|answer, answer_id, stored_at}` |
| `POST /api/answers/audio` | multipart `audio` + `lang_hint`: the server assigns the UUIDv7 `answer_id`, keeps the file next to the store (`answers/<answer_id>.webm`, never in Drive or git), transcribes it → `{answer_id, audio_uri, text, lang}` |
| `POST /api/answers/draft` | `{case_id, question_id, answerer_role, answer: {answer_id?, mode, tap, text, lang, audio_uri}}` → the server builds the full `ExtractRequest` (question, moment, `case.json`, Reference step) → `{answer_id, extract: ExtractResponse}` |
| `POST /api/translate` | `TranslateRequest` → `TranslateResponse` (through the Brain client) |
| `POST /api/answers/confirm` | `{answer_id, draft, edits: [{field, text, lang}], confirmed_by}`: each edit becomes the field's value in both languages (`/translate`) with one `source: edit` grounding; `confirm_draft()`; stored as a new record; then the three SSE events → 201 `{record}` |
| `GET /api/brain/health` | the Brain's `/health` through the Brain client |
| `GET /media/answers/{answer_id}.{webm\|ogg\|m4a}` | a stored voice answer |

**Brain client (I7).** All AI goes through `scrubgpt_app.brain_client`: `BRAIN_MODE=mock` → `MOCK_BRAIN_URL` (the fake Brain, start it with `uv run scrubgpt-mock-brain --port 8101`), `real` → `BRAIN_URL`. Requests and responses are validated against the contract models both ways. A Brain error passes through as its `ApiError` (same code and status); an unreachable Brain is 503 `unavailable`, a slow one 504 `timeout` (the UI shows "Brain unavailable" for both); an off-contract answer is 502 `upstream_error`.

**Knowledge store (I2).** SQLite (WAL) at `APP_DB_PATH`, kept local. Migrations are ordered and applied once (`schema_migrations`). Every Decision Record is its own row: many records per moment, nothing replaced, edited or merged. A record without `trust_label`, `attributed_to` or `generated_by` is refused, and so is an unconfirmed one, except a narration-mined 🎙️ seed record (stored as not yet confirmed; asked on #20). Each record adds entities (case, step, moment, obstacle, record) and edges tagged with the record and its trust label. At start-up the loaded cases' seed records are stored once.

`trust_labels` are the distinct labels in the package (timeline items, moments, seed records), in enum order. When `app/web/dist` exists (`npm run build`), the server also serves the web app at `/` for the offline demo.
