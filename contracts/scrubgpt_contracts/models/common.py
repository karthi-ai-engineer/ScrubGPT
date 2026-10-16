"""Shared primitives for every ScrubGPT contract (plan §4.1; D-023, D-024, D-034, D-035).

Rules every contract model follows:
- **Tolerant readers** (D-023): unknown fields are ignored, so old readers accept a newer MINOR.
- **v1.0 fields are required keys** (D-034): nullable (`T | None`, sent as `null`) where a value may
  be absent, never omitted and never defaulted. A field added in a MINOR bump is `T | None = None`,
  the only allowed default. Producers therefore never dump with `exclude_none`.
- **Bilingual:** every human-readable field is `Bilingual`, both halves non-empty. Verbatim quotes
  (grounding, transcript and answer evidence) stay plain strings in the original language.
- **Time:** seconds as floats from the start of the normalised video; spans are `t_start`/`t_end`.
  Wall-clock timestamps are ISO 8601 UTC (`2026-10-21T09:30:00Z`).
- Numbers and booleans are strict: `"1.5"` is not a number and `"true"` is not a boolean.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

import uuid6
from pydantic import (
    UUID7,
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    model_validator,
)

# ── Versions ──────────────────────────────────────────────────────────────────

CONTRACT_VERSION = "1.0"
"""The version producers write into every contract file and every API response."""

ContractVersion = Annotated[str, StringConstraints(pattern=r"^1\.(?:0|[1-9][0-9]*)$")]
"""`"MAJOR.MINOR"`. A v1 reader accepts any 1.x and rejects another MAJOR (D-023, D-033)."""


# ── Base models ───────────────────────────────────────────────────────────────


class ContractModel(BaseModel):
    """Base of every contract model: a tolerant reader (`extra="ignore"`, D-023)."""

    model_config = ConfigDict(
        extra="ignore",
        allow_inf_nan=False,
        use_attribute_docstrings=True,
    )


class VersionedModel(ContractModel):
    """Base of every top-level contract document: each file and each API response."""

    contract_version: ContractVersion
    """`"MAJOR.MINOR"`, currently `"1.0"`."""


# ── Scalars ───────────────────────────────────────────────────────────────────

NonEmptyStr = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
"""A string with at least one non-whitespace character."""

Seconds = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0.0)]
"""Seconds from the start of the normalised video."""

UnitInterval = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0.0, le=1.0)]
"""A number from 0 to 1 (confidence, score, accuracy)."""

Confidence = UnitInterval


def _require_utc(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("timestamps must be in UTC, e.g. 2026-10-21T09:30:00Z")
    return value.astimezone(UTC)


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_require_utc)]
"""ISO 8601 timestamp in UTC; serialized as `2026-10-21T09:30:00Z`."""


class Lang(StrEnum):
    """A language the system works in."""

    JA = "ja"
    EN = "en"


class Bilingual(ContractModel):
    """Human-readable text in Japanese and English. Both halves are non-empty."""

    ja: NonEmptyStr
    en: NonEmptyStr


# ── IDs (plan §4.1, §4.2b; D-034, D-035) ─────────────────────────────────────
# Digit counts are minimum widths, zero-padded (`mNN` = 2 or more digits): widening a pattern
# later would make old readers reject new IDs, which is MAJOR (Team Lead, issue #3).

_CASE = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_PROCEDURE = r"[a-z][a-z0-9_]*"
_SLUG = r"[a-z0-9]+(?:_[a-z0-9]+)*"


class ObstacleFamily(StrEnum):
    """The 8 fixed obstacle families of the taxonomy (D-035)."""

    BLEEDING = "bleeding"
    ANATOMICAL_VARIATION = "anatomical_variation"
    TISSUE_CONDITION = "tissue_condition"
    VISIBILITY = "visibility"
    TECHNICAL_DIFFICULTY = "technical_difficulty"
    EQUIPMENT = "equipment"
    PATIENT_CONDITION = "patient_condition"
    UNEXPECTED_FINDING = "unexpected_finding"


_FAMILIES = "|".join(f.value for f in ObstacleFamily)

CASE_ID_PATTERN = rf"^{_CASE}$"
MOMENT_ID_PATTERN = rf"^{_CASE}\.m[0-9]{{2,}}$"
QUESTION_ID_PATTERN = rf"^{_CASE}\.m[0-9]{{2,}}\.[qr][1-9][0-9]*$"
OPERATING_QUESTION_ID_PATTERN = rf"^{_CASE}\.m[0-9]{{2,}}\.q[1-9][0-9]*$"
REVIEWER_QUESTION_ID_PATTERN = rf"^{_CASE}\.m[0-9]{{2,}}\.r[1-9][0-9]*$"
EVENT_ID_PATTERN = rf"^{_CASE}\.e[0-9]{{3,}}$"
UTTERANCE_ID_PATTERN = rf"^{_CASE}\.u[0-9]{{4,}}$"
SEGMENT_ID_PATTERN = rf"^{_CASE}\.s[0-9]{{3,}}$"
INSTRUMENT_SPAN_ID_PATTERN = rf"^{_CASE}\.i[0-9]{{3,}}$"
PROCEDURE_ID_PATTERN = rf"^{_PROCEDURE}$"
PHASE_ID_PATTERN = rf"^{_PROCEDURE}\.p[0-9]{{2,}}$"
STEP_ID_PATTERN = rf"^{_PROCEDURE}\.p[0-9]{{2,}}\.s[0-9]{{2,}}$"
CHECKPOINT_ID_PATTERN = rf"^{_PROCEDURE}\.p[0-9]{{2,}}\.s[0-9]{{2,}}\.c[1-9][0-9]*$"
OBSTACLE_LEAF_ID_PATTERN = rf"^(?:{_FAMILIES})\.{_SLUG}$"

CaseId = Annotated[str, StringConstraints(pattern=CASE_ID_PATTERN)]
"""e.g. `grasp-01`, `yt-en-03`, `case-fixture-01`."""
MomentId = Annotated[str, StringConstraints(pattern=MOMENT_ID_PATTERN)]
"""`<case>.mNN`, e.g. `case-fixture-01.m07`."""
QuestionId = Annotated[str, StringConstraints(pattern=QUESTION_ID_PATTERN)]
"""An operating (`<case>.mNN.qN`) or reviewer (`<case>.mNN.rN`) question."""
OperatingQuestionId = Annotated[str, StringConstraints(pattern=OPERATING_QUESTION_ID_PATTERN)]
"""`<case>.mNN.qN`, e.g. `case-fixture-01.m07.q1`."""
ReviewerQuestionId = Annotated[str, StringConstraints(pattern=REVIEWER_QUESTION_ID_PATTERN)]
"""`<case>.mNN.rN`, e.g. `case-fixture-01.m07.r1`."""
EventId = Annotated[str, StringConstraints(pattern=EVENT_ID_PATTERN)]
"""`<case>.eNNN`, e.g. `case-fixture-01.e012`."""
UtteranceId = Annotated[str, StringConstraints(pattern=UTTERANCE_ID_PATTERN)]
"""`<case>.uNNNN`, e.g. `case-fixture-01.u0042`."""
SegmentId = Annotated[str, StringConstraints(pattern=SEGMENT_ID_PATTERN)]
"""A step segment on the timeline: `<case>.sNNN`, e.g. `case-fixture-01.s004`."""
InstrumentSpanId = Annotated[str, StringConstraints(pattern=INSTRUMENT_SPAN_ID_PATTERN)]
"""An instrument span on the timeline: `<case>.iNNN`, e.g. `case-fixture-01.i002`."""
ProcedureId = Annotated[str, StringConstraints(pattern=PROCEDURE_ID_PATTERN)]
"""e.g. `rarp`."""
PhaseId = Annotated[str, StringConstraints(pattern=PHASE_ID_PATTERN)]
"""`<procedure>.pNN`, e.g. `rarp.p05`."""
StepId = Annotated[str, StringConstraints(pattern=STEP_ID_PATTERN)]
"""`<procedure>.pNN.sNN`, e.g. `rarp.p05.s01`."""
CheckpointId = Annotated[str, StringConstraints(pattern=CHECKPOINT_ID_PATTERN)]
"""`<procedure>.pNN.sNN.cN`, e.g. `rarp.p06.s02.c1`."""
ObstacleLeafId = Annotated[str, StringConstraints(pattern=OBSTACLE_LEAF_ID_PATTERN)]
"""`<family>.<slug>`, e.g. `anatomical_variation.median_lobe`."""
RecordId = UUID7
"""A Decision Record id: UUIDv7."""
AnswerId = UUID7
"""An answer id, assigned by the app: UUIDv7."""


def new_uuid7() -> uuid.UUID:
    """A new UUIDv7 for a record or an answer (Python 3.13 has no built-in UUIDv7)."""
    return uuid.UUID(int=uuid6.uuid7().int)


def _checked(value: str, pattern: str, what: str) -> str:
    if not re.match(pattern, value):
        raise ValueError(f"not a valid {what}: {value!r}")
    return value


def moment_id(case_id: str, n: int) -> str:
    """`moment_id("grasp-01", 7)` → `"grasp-01.m07"`."""
    return _checked(f"{case_id}.m{n:02d}", MOMENT_ID_PATTERN, "moment id")


def question_id(moment: str, n: int, *, reviewer: bool = False) -> str:
    """`question_id("grasp-01.m07", 1)` → `"grasp-01.m07.q1"` (`.r1` for a reviewer question)."""
    return _checked(f"{moment}.{'r' if reviewer else 'q'}{n}", QUESTION_ID_PATTERN, "question id")


def event_id(case_id: str, n: int) -> str:
    """`event_id("grasp-01", 12)` → `"grasp-01.e012"`."""
    return _checked(f"{case_id}.e{n:03d}", EVENT_ID_PATTERN, "event id")


def utterance_id(case_id: str, n: int) -> str:
    """`utterance_id("grasp-01", 42)` → `"grasp-01.u0042"`."""
    return _checked(f"{case_id}.u{n:04d}", UTTERANCE_ID_PATTERN, "utterance id")


def segment_id(case_id: str, n: int) -> str:
    """`segment_id("grasp-01", 4)` → `"grasp-01.s004"`."""
    return _checked(f"{case_id}.s{n:03d}", SEGMENT_ID_PATTERN, "segment id")


def instrument_span_id(case_id: str, n: int) -> str:
    """`instrument_span_id("grasp-01", 2)` → `"grasp-01.i002"`."""
    return _checked(f"{case_id}.i{n:03d}", INSTRUMENT_SPAN_ID_PATTERN, "instrument span id")


# ── Field paths (grounding, chips, missing_fields) ────────────────────────────

FIELD_PATH_PATTERN = r"^[a-z_][a-z0-9_]*(?:\[[0-9]+\])*(?:\.[a-z_][a-z0-9_]*(?:\[[0-9]+\])*)*$"
FieldPath = Annotated[str, StringConstraints(pattern=FIELD_PATH_PATTERN)]
"""A path into a document, `a.b[0].c`, e.g. `action.text` or `alternatives[0].why_not`."""

_PATH_TOKEN = re.compile(r"([a-z_][a-z0-9_]*)|\[([0-9]+)\]")


def parse_field_path(path: str) -> tuple[str | int, ...]:
    """`"alternatives[0].why_not"` → `("alternatives", 0, "why_not")`."""
    if not re.match(FIELD_PATH_PATTERN, path):
        raise ValueError(f"not a valid field path: {path!r}")
    return tuple(name if name else int(index) for name, index in _PATH_TOKEN.findall(path))


def get_at_path(data: Any, path: str) -> Any:
    """The value at `path` inside a contract model or JSON-like data (dicts and lists).

    Raises `LookupError` if the path doesn't exist.
    """
    current = data
    for part in parse_field_path(path):
        if isinstance(part, int):
            if not isinstance(current, list) or part >= len(current):
                raise LookupError(f"{path}: no item [{part}]")
            current = current[part]
        elif isinstance(current, BaseModel):
            if part not in type(current).model_fields:
                raise LookupError(f"{path}: no field {part!r}")
            current = getattr(current, part)
        elif isinstance(current, dict):
            if part not in current:
                raise LookupError(f"{path}: no field {part!r}")
            current = current[part]
        else:
            raise LookupError(f"{path}: {part!r} is inside a value that has no fields")
    return current


# ── Spans ─────────────────────────────────────────────────────────────────────


class TimeSpan(ContractModel):
    """A span of the normalised video. Zero-length spans are allowed."""

    t_start: Seconds
    """Seconds from the start of the normalised video."""
    t_end: Seconds
    """Seconds from the start of the normalised video; never before `t_start`."""

    @model_validator(mode="after")
    def _end_not_before_start(self) -> Self:
        if self.t_end < self.t_start:
            raise ValueError(f"t_end ({self.t_end}) is before t_start ({self.t_start})")
        return self


# ── Trust and provenance ──────────────────────────────────────────────────────


class TrustLabel(StrEnum):
    """How far a piece of knowledge can be trusted. The emoji are for display only."""

    AI_DETECTED = "ai_detected"
    DATASET_ANNOTATION = "dataset_annotation"
    NARRATION_EXTRACTED = "narration_extracted"
    OPERATING_SURGEON = "operating_surgeon"
    REVIEWER = "reviewer"
    EXPERT_VALIDATED = "expert_validated"
    SIMULATED = "simulated"


TRUST_LABEL_EMOJI: dict[TrustLabel, str] = {
    TrustLabel.AI_DETECTED: "🤖",
    TrustLabel.DATASET_ANNOTATION: "📐",
    TrustLabel.NARRATION_EXTRACTED: "🎙️",
    TrustLabel.OPERATING_SURGEON: "🩺",
    TrustLabel.REVIEWER: "👁️",
    TrustLabel.EXPERT_VALIDATED: "✅",
    TrustLabel.SIMULATED: "🧪",
}


class Role(StrEnum):
    """Who a piece of knowledge is attributed to."""

    AI = "ai"
    DATASET = "dataset"
    NARRATOR = "narrator"
    OPERATING_SURGEON = "operating_surgeon"
    REVIEWER = "reviewer"
    EXPERT = "expert"
    DEV_TEAM_SIMULATED = "dev_team_simulated"


class GeneratedBy(ContractModel):
    """The model and prompt that produced an AI output."""

    model_tier: NonEmptyStr
    """The `.env` tier, e.g. `VISION_FAST` or `TEXT_SMART` (plan §3.1)."""
    model: NonEmptyStr
    """The concrete model name the tier resolved to."""
    prompt_version: NonEmptyStr | None
    """The prompt file and version, e.g. `step_window.v1`; `null` when no prompt was used."""


class Provenance(ContractModel):
    """Where a piece of knowledge came from, and who confirmed it."""

    trust_label: TrustLabel
    attributed_to: Role
    generated_by: GeneratedBy | None
    """`null` unless an AI model produced it."""
    confirmed_by: NonEmptyStr | None
    confirmed_at: UtcDatetime | None


# ── Evidence (tagged by `kind`) ───────────────────────────────────────────────

MEDIA_FRAGMENT_PATTERN = r"^([^#\s\\]+)#t=([0-9]+(?:\.[0-9]+)?),([0-9]+(?:\.[0-9]+)?)$"
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _check_media_fragment(value: str) -> str:
    match = re.match(MEDIA_FRAGMENT_PATTERN, value)
    if match is None:  # pragma: no cover (the pattern constraint runs first)
        raise ValueError("expected <path>#t=<start>,<end>")
    path, start, end = match.groups()
    if _URI_SCHEME.match(path) or path.startswith("/") or ".." in path.split("/"):
        raise ValueError(f"the path must be relative to the case folder: {path!r}")
    if float(start) > float(end):
        raise ValueError(f"the fragment starts after it ends: {value!r}")
    return value


MediaFragmentUri = Annotated[
    str,
    StringConstraints(pattern=MEDIA_FRAGMENT_PATTERN),
    AfterValidator(_check_media_fragment),
]
"""`<path>#t=<start>,<end>`, e.g. `video.mp4#t=2280.0,2520.0`.

The path is relative to the case folder (POSIX, no scheme, no leading `/`, no `..`). The fragment's
seconds are relative to the file it names, so for a clip they differ from the evidence's
`t_start`/`t_end`, which are always on the normalised video's timeline.
"""


def _seconds_text(t: float) -> str:
    text = f"{t:.3f}".rstrip("0")
    return text + "0" if text.endswith(".") else text


def media_fragment(path: str, t_start: float, t_end: float) -> str:
    """`media_fragment("video.mp4", 2280, 2520)` → `"video.mp4#t=2280.0,2520.0"`."""
    if not 0 <= t_start <= t_end:
        raise ValueError(f"invalid span: {t_start}–{t_end}")
    value = f"{path}#t={_seconds_text(t_start)},{_seconds_text(t_end)}"
    if not re.match(MEDIA_FRAGMENT_PATTERN, value):
        raise ValueError(f"not a valid media fragment: {value!r}")
    return _check_media_fragment(value)


class MediaEvidence(TimeSpan):
    """A span of a case's video. `t_start`/`t_end` are on the normalised video's timeline."""

    kind: Literal["media"]
    case_id: CaseId
    uri: MediaFragmentUri


class TranscriptEvidence(ContractModel):
    """A verbatim quote from a case's narration."""

    kind: Literal["transcript"]
    case_id: CaseId
    utterance_id: UtteranceId
    quote: NonEmptyStr
    """Verbatim, in the original language."""

    @model_validator(mode="after")
    def _utterance_in_case(self) -> Self:
        if not self.utterance_id.startswith(f"{self.case_id}."):
            raise ValueError(f"utterance {self.utterance_id} is not in case {self.case_id}")
        return self


class AnswerAudioEvidence(ContractModel):
    """The recording of a surgeon's spoken answer."""

    kind: Literal["answer_audio"]
    answer_id: AnswerId
    uri: NonEmptyStr


class AnswerTextEvidence(ContractModel):
    """A verbatim quote from a surgeon's answer (typed, or transcribed from voice)."""

    kind: Literal["answer_text"]
    answer_id: AnswerId
    quote: NonEmptyStr
    """Verbatim, in the original language."""


Evidence = Annotated[
    MediaEvidence | TranscriptEvidence | AnswerAudioEvidence | AnswerTextEvidence,
    Field(discriminator="kind"),
]


# ── Brain API errors ──────────────────────────────────────────────────────────


class ErrorCode(StrEnum):
    """Brain API error codes. The UI localises by code."""

    BAD_REQUEST = "bad_request"
    NOT_FOUND = "not_found"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    UNAVAILABLE = "unavailable"
    UPSTREAM_ERROR = "upstream_error"
    REFUSED = "refused"
    TIMEOUT = "timeout"


ERROR_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.BAD_REQUEST: 400,  # FastAPI's 422 validation error is mapped here too
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.PAYLOAD_TOO_LARGE: 413,
    ErrorCode.UNAVAILABLE: 503,
    ErrorCode.UPSTREAM_ERROR: 502,
    ErrorCode.REFUSED: 502,
    ErrorCode.TIMEOUT: 504,
}

RETRYABLE_BY_DEFAULT: frozenset[ErrorCode] = frozenset(
    {ErrorCode.UNAVAILABLE, ErrorCode.UPSTREAM_ERROR, ErrorCode.TIMEOUT}
)


class ApiErrorDetail(ContractModel):
    """What went wrong."""

    code: ErrorCode
    message: NonEmptyStr
    """English developer text; the UI shows a localised text for `code`."""
    retryable: StrictBool


class ApiError(VersionedModel):
    """The body of every Brain API error response."""

    error: ApiErrorDetail


def api_error(code: ErrorCode, message: str, *, retryable: bool | None = None) -> ApiError:
    """An `ApiError` body. `retryable` defaults to `RETRYABLE_BY_DEFAULT`.

    The HTTP status is `ERROR_HTTP_STATUS[code]`.
    """
    if retryable is None:
        retryable = code in RETRYABLE_BY_DEFAULT
    return ApiError(
        contract_version=CONTRACT_VERSION,
        error=ApiErrorDetail(code=code, message=message, retryable=retryable),
    )
