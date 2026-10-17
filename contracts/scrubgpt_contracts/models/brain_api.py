"""Contract #2: the Brain API (plan §4.4; D-023, D-025, D-034, D-037). Field spec: `brain_api.md`.

The Brain is stateless: the app server sends it full objects (question, moment, case context,
candidate records), never IDs it would have to look up. The real Brain serves these endpoints on
`:8100`, the fake Brain (`scrubgpt-mock-brain`) the same endpoints and shapes on `:8101`.

- Every response model is a `VersionedModel`: it carries `contract_version`.
- Every error body is an `ApiError` (`common.py`), with the HTTP status `ERROR_HTTP_STATUS[code]`.
  FastAPI's 422 validation error is mapped to 400 `bad_request`.
- Request and response models are tolerant readers (`extra="ignore"`, D-023), like every contract
  model. v1.0 fields are required keys, nullable where a value may be absent (D-034).

`ENDPOINTS` maps each endpoint name to its method, path, request model, response model and
multipart file fields. `scrubgpt-validate response|live` iterates it, and so does the app's Brain
client (I7).
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, StrictInt, model_validator

from scrubgpt_contracts.models.case_package import Case, Moment, Question
from scrubgpt_contracts.models.common import (
    OPERATING_QUESTION_ID_PATTERN,
    REVIEWER_QUESTION_ID_PATTERN,
    AnswerId,
    Bilingual,
    ContractModel,
    FieldPath,
    Lang,
    NonEmptyStr,
    RecordId,
    Role,
    VersionedModel,
    get_at_path,
)
from scrubgpt_contracts.models.decision_record import DecisionRecord, DecisionRecordDraft
from scrubgpt_contracts.models.reference import Step

MAX_AUDIO_BYTES = 25 * 1024 * 1024
"""Largest `audio` part `/v1/answers/transcribe` accepts; a larger one gets 413
`payload_too_large`."""


def _unique_records(candidates: list[DecisionRecord]) -> None:
    seen: set[object] = set()
    for record in candidates:
        if record.id in seen:
            raise ValueError(f"candidate record {record.id} is sent twice")
        seen.add(record.id)


# ── GET /health ───────────────────────────────────────────────────────────────


class HealthStatus(StrEnum):
    """Whether the Brain can serve every endpoint."""

    OK = "ok"
    DEGRADED = "degraded"


class BrainMode(StrEnum):
    """`real` = the Brain API (`:8100`), `mock` = the fake Brain (`:8101`)."""

    REAL = "real"
    MOCK = "mock"


class CacheMode(StrEnum):
    """The Brain's response cache (`CACHE_MODE` in `.env`)."""

    READWRITE = "readwrite"
    READONLY = "readonly"
    OFF = "off"


class HealthResponse(VersionedModel):
    """`GET /health`."""

    status: HealthStatus
    mode: BrainMode
    model_tiers: dict[str, NonEmptyStr | None]
    """Each `.env` model tier (e.g. `TEXT_SMART`) → the model it resolves to; `null` if unset."""
    cache_mode: CacheMode


# ── POST /v1/answers/transcribe (multipart) ───────────────────────────────────


class LangHint(StrEnum):
    """The language the speaker is expected to use; `auto` lets the Brain detect it."""

    JA = "ja"
    EN = "en"
    AUTO = "auto"


class TranscribeForm(ContractModel):
    """The form fields of `/v1/answers/transcribe`. The file part is `audio` (webm/opus or
    mp4/aac, at most `MAX_AUDIO_BYTES`)."""

    lang_hint: LangHint
    answer_id: AnswerId
    """The app's UUIDv7 for this answer; the same id is sent to `/v1/answers/extract`."""


class TranscribeResponse(VersionedModel):
    """The transcript of one spoken answer."""

    text: str
    """Verbatim, in the language spoken; an empty string if no speech was heard."""
    lang: Lang
    """The language detected (or the hint, when it isn't `auto`)."""


# ── POST /v1/answers/extract ──────────────────────────────────────────────────


class CaseContext(ContractModel):
    """What the Brain needs to know about the case: `case.json` and the moment's step."""

    case: Case
    """The content of `case.json`."""
    step: Step
    """The moment's step object from the Procedure Reference (§4.2b)."""


class AnswerMode(StrEnum):
    """How the surgeon answered (J3: tap, voice and text side by side)."""

    TAP = "tap"
    VOICE = "voice"
    TEXT = "text"


class Verdict(StrEnum):
    """The built-in verdict on the question's AI draft (never a tap option id)."""

    CONFIRM = "confirm"
    EDIT = "edit"
    REJECT = "reject"


class TapAnswer(ContractModel):
    """A one-tap answer: a verdict plus any tap options chosen."""

    verdict: Verdict
    choice_ids: list[NonEmptyStr]
    """Ids of the question's `tap_options`, in the order tapped; may be empty."""


class Answer(ContractModel):
    """One answer to one question."""

    answer_id: AnswerId
    """UUIDv7, assigned by the app; the same id as in `/v1/answers/transcribe`."""
    mode: AnswerMode
    tap: TapAnswer | None
    """Set exactly when `mode` is `tap`."""
    text: NonEmptyStr | None
    """The typed text, or the transcript of a voice answer (both required), or the edited text
    of an `edit` verdict (required); `null` for a tap answer without added text."""
    lang: Lang
    """The language the surgeon answered in."""
    audio_uri: NonEmptyStr | None
    """Where the app stored the recording of a voice answer; `null` otherwise."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.mode is AnswerMode.TAP) != (self.tap is not None):
            raise ValueError("tap is set exactly when mode is 'tap'")
        if self.mode is not AnswerMode.TAP and self.text is None:
            raise ValueError(f"a {self.mode.value} answer needs its text")
        if self.tap is not None and self.tap.verdict is Verdict.EDIT and self.text is None:
            raise ValueError("an 'edit' verdict needs the edited text")
        if self.mode is not AnswerMode.VOICE and self.audio_uri is not None:
            raise ValueError("audio_uri is only for voice answers")
        return self


ANSWERER_ROLES: tuple[Role, ...] = (
    Role.OPERATING_SURGEON,
    Role.REVIEWER,
    Role.DEV_TEAM_SIMULATED,
    Role.EXPERT,
)
"""Who can answer a question. The draft's `trust_label` follows them (§4.3); `ai`, `dataset` and
`narrator` have none, so they don't answer questions (issue #10)."""

_QUESTION_STYLE = {
    Role.OPERATING_SURGEON: (OPERATING_QUESTION_ID_PATTERN, "operating (.qN)"),
    Role.REVIEWER: (REVIEWER_QUESTION_ID_PATTERN, "reviewer (.rN)"),
}
"""The questions each answerer may answer; role-play and experts may answer either. The request
side of the Decision Record rule (issue #10), so no request asks for a draft it forbids."""


class ExtractRequest(ContractModel):
    """Turn one answer into a Decision Record draft (G1–G3)."""

    question: Question
    """The full question (`questions.json`), operating or reviewer."""
    moment: Moment
    """The full moment it is about (`moments.json`)."""
    case_context: CaseContext
    answer: Answer
    answerer_role: Role
    """Who answered (one of `ANSWERER_ROLES`); the draft's `provenance.trust_label` follows it
    (§4.3)."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.answerer_role not in ANSWERER_ROLES:
            raise ValueError(f"answerer_role {self.answerer_role.value!r} doesn't answer questions")
        style = _QUESTION_STYLE.get(self.answerer_role)
        if style is not None and not re.match(style[0], self.question.id):
            raise ValueError(
                f"a {self.answerer_role.value} answers {style[1]} questions, not {self.question.id}"
            )
        if self.question.moment_id != self.moment.id:
            raise ValueError(f"question {self.question.id} is not about moment {self.moment.id}")
        case_id = self.case_context.case.id
        if not self.moment.id.startswith(f"{case_id}."):
            raise ValueError(f"moment {self.moment.id} is not in case {case_id}")
        if self.case_context.step.id != self.moment.step_id:
            raise ValueError(
                f"case_context.step is {self.case_context.step.id}, "
                f"but the moment's step is {self.moment.step_id}"
            )
        if self.answer.tap is not None:
            options = {option.id for option in self.question.tap_options}
            chosen = self.answer.tap.choice_ids
            if len(set(chosen)) != len(chosen):
                raise ValueError("answer.tap.choice_ids has duplicates")
            unknown = [choice for choice in chosen if choice not in options]
            if unknown:
                raise ValueError(f"not tap options of {self.question.id}: {unknown}")
        return self


class Chip(ContractModel):
    """One extracted field, shown to the surgeon to confirm or edit. Chips show what the AI read,
    so there is never a chip for a null field (D-056)."""

    field: FieldPath
    """The draft field it shows, e.g. `reason` or `alternatives[0].why_not`."""
    value: Bilingual
    """The field's value in the draft."""
    editable: StrictBool


REQUIRED_TO_CONFIRM: tuple[str, ...] = ("situation_cue.text", "action.text")
"""Draft fields that may be null but must be filled before Confirm (D-054). A null one must be in
`missing_fields`, which is the app's fill-in prompt for it (D-056)."""


class ExtractResponse(VersionedModel):
    """The draft, plus what the answer app shows: read-back, chips and missing fields."""

    draft: DecisionRecordDraft
    readback: Bilingual
    """What the app reads back to the surgeon before Confirm."""
    chips: list[Chip]
    missing_fields: list[FieldPath]
    """Draft fields the surgeon did not state (each `null` or an empty list). The app shows each
    one as a fill-in input (D-056)."""

    @model_validator(mode="after")
    def _paths_match_the_draft(self) -> Self:
        for path in self.missing_fields:
            try:
                value = get_at_path(self.draft, path)
            except LookupError:
                raise ValueError(f"missing field {path!r} doesn't exist") from None
            if value not in (None, []):
                raise ValueError(f"missing field {path!r} is filled in the draft")
        for i, chip in enumerate(self.chips):
            try:
                value = get_at_path(self.draft, chip.field)
            except LookupError:
                raise ValueError(f"chips[{i}].field {chip.field!r} doesn't exist") from None
            if value is None:
                raise ValueError(
                    f"chips[{i}].field {chip.field!r} is null in the draft: "
                    "a null field gets no chip (D-056)"
                )
            if chip.value != value:
                raise ValueError(f"chips[{i}].value is not the draft's {chip.field}")
        for path in REQUIRED_TO_CONFIRM:
            if get_at_path(self.draft, path) is None and path not in self.missing_fields:
                raise ValueError(f"{path} is null: list it in missing_fields (D-056)")
        return self


# ── POST /v1/translate ────────────────────────────────────────────────────────


class TranslateText(ContractModel):
    """One text to make bilingual."""

    text: NonEmptyStr
    from_lang: Lang


class TranslateRequest(ContractModel):
    """Make texts bilingual, e.g. a chip the surgeon edited (H5)."""

    texts: Annotated[list[TranslateText], Field(min_length=1)]


class TranslateResponse(VersionedModel):
    """`items[i]` is `texts[i]` in both languages; its `from_lang` half is the input, verbatim."""

    items: list[Bilingual]


# ── POST /v1/embed ────────────────────────────────────────────────────────────


class EmbedRequest(ContractModel):
    """Embed texts for retrieval (I4)."""

    texts: Annotated[list[NonEmptyStr], Field(min_length=1)]


Component = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class EmbedResponse(VersionedModel):
    """`vectors[i]` embeds `texts[i]`. The app must not assume a dimension: read `dim`."""

    vectors: list[list[Component]]
    dim: Annotated[StrictInt, Field(ge=1)]
    model: NonEmptyStr
    """The embedding model; vectors from different models are not comparable."""

    @model_validator(mode="after")
    def _dimensions(self) -> Self:
        for i, vector in enumerate(self.vectors):
            if len(vector) != self.dim:
                raise ValueError(f"vectors[{i}] has {len(vector)} components, not dim={self.dim}")
        return self


# ── POST /v1/ask and POST /v1/briefing ────────────────────────────────────────


class Citation(ContractModel):
    """A record an answer is based on, and optionally one of its evidence items."""

    record_id: RecordId
    """One of the candidate records sent in the request."""
    evidence_index: Annotated[StrictInt, Field(ge=0)] | None
    """An index into that record's `evidence[]` (e.g. the clip to play); `null` for the whole
    record."""


class Coverage(StrEnum):
    """How well the candidate records cover the question."""

    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"


class AskRequest(ContractModel):
    """Answer a question from past records only (H2). The app sends the top-k candidates."""

    query: NonEmptyStr
    lang: Lang
    """The language of the query."""
    candidates: list[DecisionRecord]
    """Full records from the knowledge store (top-k by retrieval); may be empty."""

    @model_validator(mode="after")
    def _unique(self) -> Self:
        _unique_records(self.candidates)
        return self


class AskResponse(VersionedModel):
    """An answer built only from the cited records: retrieval of past cases, never advice."""

    answer: Bilingual
    citations: list[Citation]
    coverage: Coverage
    """`none` exactly when nothing is cited."""

    @model_validator(mode="after")
    def _coverage_matches_citations(self) -> Self:
        if (self.coverage is Coverage.NONE) != (not self.citations):
            raise ValueError("coverage is 'none' exactly when there are no citations")
        return self


class BriefingRequest(ContractModel):
    """A pre-case briefing from past records (H3, S), framed as retrieval of past cases."""

    case_factors: list[Bilingual]
    """Factors of the coming case (e.g. a median lobe); may be empty."""
    lang: Lang
    """The language the briefing is requested in."""
    candidates: list[DecisionRecord]
    """Full records from the knowledge store; may be empty."""

    @model_validator(mode="after")
    def _unique(self) -> Self:
        _unique_records(self.candidates)
        return self


class BriefingSection(ContractModel):
    """One section of a briefing."""

    title: Bilingual
    body: Bilingual
    citations: list[Citation]


class BriefingResponse(VersionedModel):
    """The briefing, section by section."""

    sections: list[BriefingSection]


# ── The registry ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Endpoint:
    """One Brain API endpoint."""

    method: Literal["GET", "POST"]
    path: str
    request: type[ContractModel] | None
    """The JSON body model; for a multipart endpoint, the model of its form fields; `None` for
    GET."""
    response: type[VersionedModel]
    """The model of a 200 body. Every error body is an `ApiError`."""
    files: tuple[str, ...]
    """The multipart file fields (`("audio",)` for transcribe), `()` otherwise."""
    timeout_s: float
    """Suggested client timeout in seconds."""


ENDPOINTS: Mapping[str, Endpoint] = MappingProxyType(
    {
        "health": Endpoint("GET", "/health", None, HealthResponse, (), 5.0),
        "transcribe": Endpoint(
            "POST", "/v1/answers/transcribe", TranscribeForm, TranscribeResponse, ("audio",), 120.0
        ),
        "extract": Endpoint(
            "POST", "/v1/answers/extract", ExtractRequest, ExtractResponse, (), 60.0
        ),
        "translate": Endpoint(
            "POST", "/v1/translate", TranslateRequest, TranslateResponse, (), 60.0
        ),
        "embed": Endpoint("POST", "/v1/embed", EmbedRequest, EmbedResponse, (), 60.0),
        "ask": Endpoint("POST", "/v1/ask", AskRequest, AskResponse, (), 60.0),
        "briefing": Endpoint("POST", "/v1/briefing", BriefingRequest, BriefingResponse, (), 60.0),
    }
)
"""Every Brain API endpoint by name: `health`, `transcribe`, `extract`, `translate`, `embed`,
`ask`, `briefing` (plan §4.4)."""
