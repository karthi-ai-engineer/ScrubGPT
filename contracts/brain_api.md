# Brain API: field-level spec (contract v1.0)

> Contract #2 (plan §4.4). **Author:** Dev2; **approver:** Dev1 (D-031, D-033). Models: `scrubgpt_contracts/models/brain_api.py`; the registry `ENDPOINTS` lists every endpoint. Shared primitives (`Bilingual`, `Role`, `ApiError`, ID formats, field paths) are in plan §4.1 / `models/common.py`.

The **real Brain** serves this API on `:8100` (Dev1, `brain/`), and the **fake Brain** serves the same endpoints and shapes on `:8101` (`scrubgpt-mock-brain`, D-025). The app server is the only client. Dev2 needs no OpenAI key.

## General rules

| Rule | Detail |
|---|---|
| **Stateless** | The Brain never touches the database. **Full objects travel, not IDs**: the app sends the question, the moment, the case context and the candidate records. |
| **Versions** | Every 200 body **and** every error body carries `"contract_version": "1.0"`. A reader accepts any `1.x` (D-023). |
| **Tolerant readers** | Every model ignores unknown fields (`extra="ignore"`): requests and responses. |
| **Required keys** | Every v1.0 field is a required key. A value that may be absent is `null`, never omitted (D-034). Fields added later are optional (MINOR). |
| **Bilingual** | Every human-readable output is `{ "ja": "…", "en": "…" }`, both non-empty. Verbatim quotes (`grounding[].quote`, `Evidence` quotes, the transcript) stay in the original language (D-048). |
| **Strict values** | Numbers are numbers (`"1.5"` is rejected), booleans are booleans. No NaN or infinity. UUIDs are UUIDv7. |
| **Encoding** | JSON is UTF-8 (`Content-Type: application/json`); `/v1/answers/transcribe` is `multipart/form-data`. |

## Errors

Every non-200 body is an **`ApiError`**: `{ "contract_version": "1.0", "error": { "code", "message", "retryable" } }`. `message` is English developer text; **the UI localises by `code`**.

| `code` | HTTP | `retryable` (default) | When |
|---|---|---|---|
| `bad_request` | 400 | false | The body doesn't match the request model, including **FastAPI's 422 validation error, which is always mapped to 400**, invalid JSON, a missing multipart part, and the cross-checks listed per endpoint |
| `not_found` | 404 | false | Unknown path |
| `payload_too_large` | 413 | false | `audio` larger than 25 MB (`MAX_AUDIO_BYTES` = 26 214 400 bytes) |
| `unavailable` | 503 | true | The Brain can't serve now (e.g. no API key, starting up) |
| `upstream_error` | 502 | true | OpenAI returned an error |
| `refused` | 502 | false | OpenAI refused the content |
| `timeout` | 504 | true | OpenAI didn't answer in time |

The app shows "Brain unavailable" for 503 and 504.

## Endpoints

| Name | Method and path | Request | 200 response | Suggested client timeout |
|---|---|---|---|---|
| `health` | `GET /health` | — | `HealthResponse` | 5 s |
| `transcribe` | `POST /v1/answers/transcribe` | multipart: `audio` + `TranscribeForm` fields | `TranscribeResponse` | 120 s |
| `extract` | `POST /v1/answers/extract` | `ExtractRequest` | `ExtractResponse` | 60 s |
| `translate` | `POST /v1/translate` | `TranslateRequest` | `TranslateResponse` | 60 s |
| `embed` | `POST /v1/embed` | `EmbedRequest` | `EmbedResponse` | 60 s |
| `ask` | `POST /v1/ask` | `AskRequest` | `AskResponse` | 60 s |
| `briefing` (S) | `POST /v1/briefing` | `BriefingRequest` | `BriefingResponse` | 60 s |

`ENDPOINTS[name]` is a frozen `Endpoint(method, path, request, response, files, timeout_s)`. `request` is `None` for `GET /health`, and is the **form-field model** for transcribe; `files` is `("audio",)` for transcribe and `()` otherwise.

### `GET /health`

| Field | Type | Notes |
|---|---|---|
| `status` | `"ok"` \| `"degraded"` | `degraded`: some endpoints can't work (e.g. no API key) |
| `mode` | `"real"` \| `"mock"` | The fake Brain always says `mock` |
| `model_tiers` | `{ <tier>: string \| null }` | Each `.env` tier (`VISION_FAST`, `VISION_DEEP`, `TEXT_SMART`, `TEXT_FAST`, `STT`, `STT_DIARIZE`, `TTS`, `EMBED`) → the model it resolves to, `null` if unset |
| `cache_mode` | `"readwrite"` \| `"readonly"` \| `"off"` | `CACHE_MODE` |

### `POST /v1/answers/transcribe` (multipart)

| Part | Type | Notes |
|---|---|---|
| `audio` (file) | webm/opus or mp4/aac | ≤ 25 MB, else 413 `payload_too_large`; empty → 400. **The Brain doesn't trust the part's content type** (clients guess it from the file name) |
| `lang_hint` | `"ja"` \| `"en"` \| `"auto"` | |
| `answer_id` | UUIDv7 | Assigned by the app, **one per answer**; the same id goes to `/extract` |

Response:

| Field | Type | Notes |
|---|---|---|
| `text` | string | Verbatim in the language spoken; `""` if no speech was heard |
| `lang` | `"ja"` \| `"en"` | Detected (or the hint, when it isn't `auto`) |

### `POST /v1/answers/extract`

Request:

| Field | Type | Notes |
|---|---|---|
| `question` | `Question` | The full question from `questions.json` (operating `…qN` or reviewer `…rN`) |
| `moment` | `Moment` | The full moment from `moments.json` |
| `case_context.case` | `Case` | The content of `case.json` |
| `case_context.step` | `Step` | The moment's step object from the Procedure Reference (§4.2b) |
| `answer.answer_id` | UUIDv7 | The app's id for this answer (the same as in `/transcribe`) |
| `answer.mode` | `"tap"` \| `"voice"` \| `"text"` | |
| `answer.tap` | `{ verdict: "confirm" \| "edit" \| "reject", choice_ids: string[] }` \| null | Set **exactly** when `mode` is `tap`. `choice_ids` are ids of `question.tap_options`, in tap order, no duplicates |
| `answer.text` | string \| null | **Required** for `text` and `voice` (the transcript) and for an `edit` verdict (the edited text); otherwise `null` or extra words |
| `answer.lang` | `"ja"` \| `"en"` | The language the surgeon answered in |
| `answer.audio_uri` | string \| null | Where the app stored a voice recording; `null` unless `mode` is `voice` |
| `answerer_role` | `Role` | Usually `operating_surgeon`, `reviewer` or `dev_team_simulated` (role-play) |

Cross-checks (each failure → 400 `bad_request`): `question.moment_id == moment.id`; `moment.id` starts with `case_context.case.id + "."`; `case_context.step.id == moment.step_id`; tap rules above.

Response:

| Field | Type | Notes |
|---|---|---|
| `draft` | `DecisionRecordDraft` (plan §4.3) | Every field present; **a field the surgeon did not state is `null`** (or `[]`). `id`, `provenance.confirmed_by` and `provenance.confirmed_at` are `null`. `provenance.trust_label` follows `answerer_role` (`operating_surgeon` → `operating_surgeon`, `reviewer` → `reviewer`, `dev_team_simulated` → `simulated`, `expert` → `expert_validated`); `attributed_to` = `answerer_role`. Every filled field has a `grounding[]` quote with `source` `answer`, `edit` or `narration` (G5). Answer evidence uses the request's `answer_id`. New vocabulary goes in `draft.new_terms[]` |
| `readback` | `Bilingual` | What the app reads back before Confirm |
| `chips[]` | `{ field: <path>, value: Bilingual, editable: bool }` | One per filled `Bilingual` field the surgeon can check; `field` exists in `draft` and is non-null, and `value` is its current value |
| `missing_fields[]` | `<path>[]` | Fields the surgeon did not state, for a follow-up (each `null` or `[]` in the draft) |

**On Confirm**, the app assigns the record's UUIDv7 `id` and fills `confirmed_by` / `confirmed_at` (`confirm_draft()` in `decision_record.py`). **If the surgeon edits a chip**, the app sends the new text to `/v1/translate`, puts the result into the field, and records the edit's grounding with `source: "edit"`.

### `POST /v1/translate`

| Field | Type | Notes |
|---|---|---|
| request `texts[]` | `{ text: string, from_lang: "ja" \| "en" }`, at least 1 | |
| response `items[]` | `Bilingual[]` | `items[i]` is `texts[i]`: its `from_lang` half is the input **verbatim**, the other half the translation |

### `POST /v1/embed`

| Field | Type | Notes |
|---|---|---|
| request `texts[]` | `string[]`, at least 1, non-empty | |
| response `vectors[][]` | `number[][]` | `vectors[i]` embeds `texts[i]`; every vector has `dim` components |
| response `dim` | integer ≥ 1 | **The app must not assume a dimension** |
| response `model` | string | Vectors from different models aren't comparable: re-embed when it changes |

### `POST /v1/ask`

| Field | Type | Notes |
|---|---|---|
| request `query` | string | |
| request `lang` | `"ja"` \| `"en"` | The query's language |
| request `candidates[]` | `DecisionRecord[]` | Top-k from the app's store (I4); may be empty; ids unique (else 400) |
| response `answer` | `Bilingual` | Built **only** from the cited records: retrieval of past cases, never a recommendation |
| response `citations[]` | `{ record_id, evidence_index: int ≥ 0 \| null }` | `record_id` is one of the candidates; `evidence_index` points into its `evidence[]` (e.g. the clip to play), `null` = the whole record |
| response `coverage` | `"full"` \| `"partial"` \| `"none"` | `none` **exactly when** `citations` is empty |

### `POST /v1/briefing` (S)

| Field | Type | Notes |
|---|---|---|
| request `case_factors[]` | `Bilingual[]` | Factors of the coming case; required key, may be empty |
| request `lang` | `"ja"` \| `"en"` | |
| request `candidates[]` | `DecisionRecord[]` | May be empty; ids unique |
| response `sections[]` | `{ title: Bilingual, body: Bilingual, citations: Citation[] }` | Framed as **retrieval of past cases**; counts, not percentages, when n < 20; no advice |

## The fake Brain (`scrubgpt-mock-brain`, D-037)

```
uv run scrubgpt-mock-brain --port 8101          # --host defaults to 127.0.0.1
uv run scrubgpt-validate live --base-url http://localhost:8101
```

It is deterministic and offline. Texts it makes up are marked as mock in both languages (`(Mock …)` / `（模擬…）`, `[mock translation]` / `［模擬翻訳］`).

| Endpoint | Behaviour |
|---|---|
| `/health` | `status: ok`, `mode: mock`, every tier → `"mock"`, `cache_mode: off` |
| `/transcribe` | Accepts any audio content type. `lang_hint` `ja` or `auto` → a fixed JA sentence; `en` → a fixed EN sentence |
| `/extract` | **Canned:** if the fixture case has a seed record for the question's moment (or, for a record tied to no moment, the moment's step) **in the answer's language** (`answer.lang` = the record's `language`, D-054), the draft is that record, with `id: null`, the request's `moment_id`, `answer_id` and answerer provenance. Its quotes are the seed answer's (fake Brain only; the real Brain quotes only the request), so `extract.request.json` sends that seed answer's text. For `case-fixture-01`: `m01` in `ja` and `en`, `m02` and `m03` in `ja`, `m04` in `en`; any other language or moment gets the generic draft. **Generic** otherwise: the answer (text, tapped labels, or the confirmed AI draft or quote) becomes `action.text`, grounded verbatim; the flagged moment's title becomes `situation_cue.text`; everything else stays `null` and is listed in `missing_fields` |
| `/translate` | The input stays verbatim in its own half; the other half is the input with a mock marker |
| `/embed` | NFKC + lowercase; Latin word tokens + CJK character bigrams; blake2b → 256 buckets; L2-normalised (`dim: 256`, `model: mock-hash-256`). Text without tokens → the zero vector |
| `/ask` | Ranks candidates by cosine to the query. `coverage` = `full` if 2 or more score ≥ 0.3, `partial` if 1, `none` if 0; cites the top matches (at most 3) |
| `/briefing` | A "factors of this case" section (if any), then one section per obstacle family among the candidates (names from the fixture `rarp.json`), with counts and citations |

## Request fixtures (`contracts/fixtures/brain_api/`)

`<name>.request.json` for each POST endpoint (for transcribe, its form fields) and `transcribe.request.audio.webm` (1 s of a 440 Hz FFmpeg tone, Opus, mono, about 2.5 KB; D-036). They are built from the fixture case: `extract` answers `case-fixture-01.m01.q1`; `ask` and `briefing` send the five seed records. `scrubgpt-validate live` sends each one, plus an empty request per POST endpoint that must get 400 `bad_request`.

## Generated types (`scrubgpt-codegen`)

```
uv run scrubgpt-codegen                 # writes contracts/schema/ and contracts/ts/
uv run scrubgpt-codegen --out <dir>     # somewhere else (Tester 2)
uv run scrubgpt-codegen --schema-only   # JSON Schema only, no Node needed
```

- `schema/<Model>.schema.json`: one JSON Schema (2020-12, `mode="serialization"`) per top-level model: the Case Package files, `ProcedureReference`, `DecisionRecord`, `DecisionRecordDraft`, `ApiError` and every request and response above.
- `ts/contracts.ts`: TypeScript types for all of them (`json-schema-to-typescript@15.0.4`, pinned in `codegen/__init__.py`; on Windows `npx` resolves to `npx.cmd`). v1.0 keys are required; MINOR-added fields come out optional (`?`).
- Both folders are **generated**: never edit them by hand. CI re-runs codegen and fails if they are stale. The output is byte-for-byte reproducible, with LF line endings.
