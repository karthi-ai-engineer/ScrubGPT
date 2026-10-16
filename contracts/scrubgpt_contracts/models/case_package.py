"""Contract #1: the Case Package, the files in `<DATA_DIR>/cases/<case_id>/` (plan §4.2, D-034).

Each JSON file has a model here; each carries `contract_version` and `case_id`. Every check that
fits inside one file is in its model (IDs carry the case prefix and are unique, spans are valid).
Checks across files (moments in the Procedure Reference, clips present, times within
`duration_s`, …) are in `scrubgpt-validate case`.
"""

from collections.abc import Iterable
from enum import StrEnum
from typing import Annotated, Self

from pydantic import ConfigDict, Field, StrictBool, StrictInt, StringConstraints, model_validator

from scrubgpt_contracts.models.common import (
    Bilingual,
    CaseId,
    CheckpointId,
    Confidence,
    ContractModel,
    EventId,
    GeneratedBy,
    InstrumentSpanId,
    Lang,
    MomentId,
    NonEmptyStr,
    ObstacleLeafId,
    OperatingQuestionId,
    Provenance,
    QuestionId,
    ReviewerQuestionId,
    SegmentId,
    StepId,
    TimeSpan,
    UnitInterval,
    UtteranceId,
    VersionedModel,
)
from scrubgpt_contracts.models.decision_record import DecisionRecord

PositiveSeconds = Annotated[float, Field(strict=True, allow_inf_nan=False, gt=0.0)]


def _unique(ids: Iterable[str], what: str) -> None:
    seen: set[str] = set()
    for item_id in ids:
        if item_id in seen:
            raise ValueError(f"duplicate {what} id {item_id}")
        seen.add(item_id)


def _in_case(ids: Iterable[str], case_id: str, what: str) -> None:
    for item_id in ids:
        if not item_id.startswith(f"{case_id}."):
            raise ValueError(f"{what} {item_id} is not in case {case_id}")


# ── case.json ─────────────────────────────────────────────────────────────────


class CaseSource(StrEnum):
    """Where the case came from."""

    GRASP = "grasp"
    PSI_AVA = "psi-ava"
    YOUTUBE = "youtube"
    SYNTHETIC = "synthetic"


class CaseLanguage(StrEnum):
    """The language spoken in the video (`none`: no speech)."""

    JA = "ja"
    EN = "en"
    NONE = "none"


class VideoType(StrEnum):
    """A full recording, or an edited video (edited videos never produce duration deviations)."""

    FULL = "full"
    EDITED = "edited"


class StepTrack(StrEnum):
    """Who segmented the steps: the AI, or the dataset's ground truth."""

    AI = "ai"
    DATASET = "dataset"


class CaseStatus(StrEnum):
    """Whether every part of the package has been produced."""

    COMPLETE = "complete"
    PARTIAL = "partial"


class Case(VersionedModel):
    """`case.json`: what the case is."""

    id: CaseId
    title: Bilingual
    source: CaseSource
    source_url: NonEmptyStr | None
    language: CaseLanguage
    video_type: VideoType
    narrated: StrictBool
    synthetic_speech: StrictBool
    """True if the speech was generated (D6); always labelled synthetic."""
    duration_s: PositiveSeconds
    """Length of the normalised video."""
    default_step_track: StepTrack
    status: CaseStatus
    data_note: Bilingual
    """Where the data comes from and how it may be used."""

    @model_validator(mode="after")
    def _speech_matches_language(self) -> Self:
        if self.language is CaseLanguage.NONE and (self.narrated or self.synthetic_speech):
            raise ValueError("a case with language 'none' has no narration or synthetic speech")
        return self


# ── timeline.json ─────────────────────────────────────────────────────────────


class TimelineItem(TimeSpan):
    """Fields every timeline item has."""

    confidence: Confidence
    provenance: Provenance


class StepSegment(TimelineItem):
    """A span of the video in one procedure step."""

    id: SegmentId
    step_id: StepId
    track: StepTrack
    """`ai` (C2/C3) or `dataset` (ground truth); a GraSP case carries both."""


class EventType(StrEnum):
    """What kind of event was detected (C5)."""

    BLEEDING = "bleeding"
    SMOKE = "smoke"
    OUT_OF_BODY = "out_of_body"
    IDLE = "idle"
    SUCTION = "suction"
    OTHER = "other"


class TimelineEvent(TimelineItem):
    """A detected event."""

    id: EventId
    type: EventType
    signals: list[NonEmptyStr]
    """Names of the signals that detected it, e.g. `red_pixel_ratio`, `gpt_check`."""


class InstrumentSpan(TimelineItem):
    """An instrument seen in the video (C4, a Should feature; empty until then)."""

    id: InstrumentSpanId
    key: Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")]
    """A stable snake_case instrument name for grouping, e.g. `needle_driver`."""
    name: Bilingual


class UtteranceClass(StrEnum):
    """What an utterance does (D4)."""

    INSTRUCTION = "instruction"
    CONCERN = "concern"
    EXPLANATION = "explanation"
    DECISION = "decision"
    BOOKMARK = "bookmark"
    TEACHING = "teaching"
    IRRELEVANT = "irrelevant"


class Utterance(TimelineItem):
    """A transcribed utterance. On the wire, the class field is `class`."""

    model_config = ConfigDict(
        serialize_by_alias=True, validate_by_alias=True, validate_by_name=True
    )

    id: UtteranceId
    speaker: NonEmptyStr | None
    """A speaker label from diarisation; `null` when there is none."""
    text: Bilingual
    original_lang: Lang
    class_: UtteranceClass = Field(alias="class")


class Timeline(VersionedModel):
    """`timeline.json`: steps, events, instruments and utterances on the video's timeline."""

    case_id: CaseId
    steps: list[StepSegment]
    events: list[TimelineEvent]
    instruments: list[InstrumentSpan]
    utterances: list[Utterance]

    @model_validator(mode="after")
    def _ids(self) -> Self:
        for what, items in [
            ("step segment", self.steps),
            ("event", self.events),
            ("instrument span", self.instruments),
            ("utterance", self.utterances),
        ]:
            ids = [item.id for item in items]
            _unique(ids, what)
            _in_case(ids, self.case_id, what)
        return self


# ── moments.json ──────────────────────────────────────────────────────────────


class MomentKind(StrEnum):
    """Why the moment was flagged (E1–E5)."""

    DEVIATION = "deviation"
    EVENT = "event"
    SPEECH = "speech"
    CHECKPOINT = "checkpoint"


class FlagReason(ContractModel):
    """One signal behind a flagged moment."""

    signal: NonEmptyStr
    detail: Bilingual


class Moment(TimeSpan):
    """A flagged moment worth asking the surgeon about."""

    id: MomentId
    kind: MomentKind
    step_id: StepId
    title: Bilingual
    why_flagged: list[FlagReason]
    score: UnitInterval
    clip: NonEmptyStr
    """Always `clips/<moment_id>.mp4`."""
    poster: NonEmptyStr
    """Always `clips/<moment_id>.jpg`."""
    deep_look: Bilingual | None
    """The VISION_DEEP description (C6), if it was run."""
    draft_obstacle: ObstacleLeafId | None
    checkpoint_id: CheckpointId | None
    """Set exactly when `kind` is `checkpoint`; a checkpoint of `step_id`."""
    provenance: Provenance

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        for name, expected in [
            ("clip", f"clips/{self.id}.mp4"),
            ("poster", f"clips/{self.id}.jpg"),
        ]:
            if getattr(self, name) != expected:
                raise ValueError(f"{name} of {self.id} must be {expected!r}")
        if (self.kind is MomentKind.CHECKPOINT) != (self.checkpoint_id is not None):
            raise ValueError(f"{self.id}: checkpoint_id is set exactly for checkpoint moments")
        if self.checkpoint_id is not None and not self.checkpoint_id.startswith(f"{self.step_id}."):
            raise ValueError(
                f"{self.id}: {self.checkpoint_id} is not a checkpoint of {self.step_id}"
            )
        return self


class Moments(VersionedModel):
    """`moments.json`: the flagged moments, ranked (list order = rank)."""

    case_id: CaseId
    moments: list[Moment]

    @model_validator(mode="after")
    def _ids(self) -> Self:
        ids = [moment.id for moment in self.moments]
        _unique(ids, "moment")
        _in_case(ids, self.case_id, "moment")
        return self


# ── questions.json ────────────────────────────────────────────────────────────


class QuestionType(StrEnum):
    """What a question asks for (F1–F3)."""

    CUE = "cue"
    DECISION = "decision"
    REASON = "reason"
    ALTERNATIVES = "alternatives"
    CONFIRM_QUOTE = "confirm_quote"
    CHECKPOINT = "checkpoint"
    OPTIONS_HERE = "options_here"


VERDICTS = frozenset({"confirm", "edit", "reject"})
"""Built into every question (sent as `tap.verdict` to `/v1/answers/extract`), never tap options."""


class TapOption(ContractModel):
    """A one-tap answer. The verdicts confirm/edit/reject are built in, not tap options."""

    id: NonEmptyStr
    """Unique within its question; never `confirm`, `edit` or `reject`."""
    label: Bilingual

    @model_validator(mode="after")
    def _not_a_verdict(self) -> Self:
        if self.id in VERDICTS:
            raise ValueError(f"tap option id {self.id!r} is a built-in verdict")
        return self


class QuotedUtterance(ContractModel):
    """The narration a question asks the surgeon to confirm."""

    utterance_id: UtteranceId
    text: Bilingual


class Question(ContractModel):
    """A question about one moment."""

    id: QuestionId
    moment_id: MomentId
    type: QuestionType
    text: Bilingual
    ai_draft: Bilingual | None
    """The AI's draft answer for the surgeon to confirm, edit or reject."""
    tap_options: list[TapOption]
    est_seconds: PositiveSeconds
    """Estimated time to answer."""
    quote: QuotedUtterance | None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if not self.id.startswith(f"{self.moment_id}."):
            raise ValueError(f"question {self.id} is not about moment {self.moment_id}")
        _unique((option.id for option in self.tap_options), f"tap option (in {self.id})")
        if self.type is QuestionType.CONFIRM_QUOTE and self.quote is None:
            raise ValueError(f"{self.id}: a confirm_quote question needs a quote")
        return self


class OperatingQuestion(Question):
    """A question for the operating surgeon (`<case>.mNN.qN`)."""

    id: OperatingQuestionId


class ReviewerQuestion(Question):
    """A question for a reviewer (`<case>.mNN.rN`)."""

    id: ReviewerQuestionId


class Questions(VersionedModel):
    """`questions.json`: questions for the operating surgeon and for reviewers."""

    case_id: CaseId
    operating: list[OperatingQuestion]
    reviewer: list[ReviewerQuestion]

    @model_validator(mode="after")
    def _ids(self) -> Self:
        questions = [*self.operating, *self.reviewer]
        ids = [question.id for question in questions]
        _unique(ids, "question")
        _in_case(ids, self.case_id, "question")
        quoted = [q.quote.utterance_id for q in questions if q.quote is not None]
        _in_case(quoted, self.case_id, "quoted utterance")
        return self


# ── seed_records.json ─────────────────────────────────────────────────────────


class SeedRecords(VersionedModel):
    """`seed_records.json`: Decision Records that seed the knowledge base (🧪, 🎙️)."""

    case_id: CaseId
    records: list[DecisionRecord]

    @model_validator(mode="after")
    def _records_in_case(self) -> Self:
        _unique((str(record.id) for record in self.records), "record")
        for record in self.records:
            if record.case_id != self.case_id:
                raise ValueError(f"record {record.id} is from case {record.case_id}")
        return self


# ── metrics.json (GraSP cases) ────────────────────────────────────────────────


class StepMetrics(ContractModel):
    """AI step recognition against ground truth, for one step."""

    step_id: StepId
    precision: UnitInterval
    recall: UnitInterval


class Metrics(VersionedModel):
    """`metrics.json`: AI step accuracy against the dataset's ground truth (C7)."""

    case_id: CaseId
    frame_accuracy: UnitInterval
    segment_f1: UnitInterval
    per_step: list[StepMetrics]
    n_frames: Annotated[StrictInt, Field(gt=0)]
    model_info: GeneratedBy

    @model_validator(mode="after")
    def _unique_steps(self) -> Self:
        _unique((item.step_id for item in self.per_step), "per_step step")
        return self


# ── The package as files ──────────────────────────────────────────────────────

JSON_FILES: dict[str, type[VersionedModel]] = {
    "case.json": Case,
    "timeline.json": Timeline,
    "moments.json": Moments,
    "questions.json": Questions,
    "seed_records.json": SeedRecords,
    "metrics.json": Metrics,
}
"""Every JSON file of a Case Package and its model."""

REQUIRED_FILES: tuple[str, ...] = (
    "case.json",
    "video.mp4",
    "poster.jpg",
    "timeline.json",
    "moments.json",
    "questions.json",
    "clips/",
    "seed_records.json",
)
"""What a complete package must contain (`clips/` is a folder). `thumbs/` and `metrics.json`
(GraSP cases) are optional; `trainee.json` is a MINOR addition in Block 5."""
