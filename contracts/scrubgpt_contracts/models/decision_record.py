"""The Decision Record, the core knowledge unit (plan §4.3; D-024, D-034).

- `DecisionRecord` is a confirmed (or seeded) record in the knowledge base.
- `DecisionRecordDraft` is what `/v1/answers/extract` returns: the same shape, with `id` and the
  confirmation fields (`provenance.confirmed_by`, `provenance.confirmed_at`) null. The app assigns
  the UUIDv7 `id` and fills the confirmation fields when the surgeon taps Confirm.

A field the surgeon did not state stays `null` (never invented). Every filled field points to the
words that support it through `grounding[]` (G5); `ungrounded_fields()` lists the ones that don't.
Several records may point to the same moment: they are different viewpoints, all kept.
"""

from enum import StrEnum
from typing import Any, Self

from pydantic import model_validator

from scrubgpt_contracts.models.common import (
    Bilingual,
    CaseId,
    Confidence,
    ContractModel,
    Evidence,
    FieldPath,
    Lang,
    MomentId,
    NonEmptyStr,
    ObstacleFamily,
    ObstacleLeafId,
    Provenance,
    RecordId,
    StepId,
    UtcDatetime,
    VersionedModel,
    get_at_path,
)


class RecordKind(StrEnum):
    """What kind of decision the record captures. Deliberate non-action is `action.type`."""

    RESCUE = "rescue"
    ANTICIPATORY = "anticipatory"
    CHECKPOINT = "checkpoint"
    BAIL_OUT = "bail_out"


class ObstacleCause(StrEnum):
    """What the obstacle is attributed to."""

    PATIENT = "patient"
    EVENT = "event"
    TECHNICAL = "technical"
    EQUIPMENT = "equipment"
    UNKNOWN = "unknown"


class ActionType(StrEnum):
    """Whether the surgeon acted, or deliberately chose not to act."""

    ACT = "act"
    DELIBERATE_NON_ACTION = "deliberate_non_action"


class Actor(StrEnum):
    """Who carried out the action."""

    SURGEON = "surgeon"
    ASSISTANT = "assistant"
    RESIDENT = "resident"
    BEDSIDE = "bedside"
    ANESTHESIA = "anesthesia"
    UNKNOWN = "unknown"


class OutcomeStatus(StrEnum):
    """Whether the delayed outcome is known yet."""

    PENDING = "pending"
    KNOWN = "known"
    NOT_APPLICABLE = "not_applicable"


class GroundingSource(StrEnum):
    """Where a grounding quote comes from (G5)."""

    ANSWER = "answer"
    EDIT = "edit"
    NARRATION = "narration"


class RecordContext(ContractModel):
    """What was known before the decision."""

    patient_factors: list[Bilingual]
    preop_plan: Bilingual | None


class SituationCue(ContractModel):
    """What the surgeon saw that triggered the decision."""

    text: Bilingual
    cue_terms: list[NonEmptyStr]
    """Short terms for retrieval, e.g. `venous oozing`, `静脈性出血`."""


class Obstacle(ContractModel):
    """The difficulty the decision dealt with, from the taxonomy in the Procedure Reference."""

    family: ObstacleFamily
    type: ObstacleLeafId | None
    """A taxonomy leaf of the same family, e.g. `anatomical_variation.median_lobe`."""
    cause: ObstacleCause

    @model_validator(mode="after")
    def _leaf_in_family(self) -> Self:
        if self.type is not None and not self.type.startswith(f"{self.family.value}."):
            raise ValueError(f"obstacle type {self.type} is not in family {self.family.value}")
        return self


class Action(ContractModel):
    """What was done (or deliberately not done)."""

    type: ActionType
    text: Bilingual
    actor: Actor


class Alternative(ContractModel):
    """An option the surgeon considered, and why it wasn't chosen."""

    option: Bilingual
    why_not: Bilingual | None


class DelayedOutcome(ContractModel):
    """The outcome known later (linked after the case)."""

    status: OutcomeStatus
    text: Bilingual | None
    source: NonEmptyStr | None
    """Where the outcome came from, e.g. a follow-up note."""


class Grounding(ContractModel):
    """The words that support one filled field (G5)."""

    field: FieldPath
    """The whole field it supports, e.g. `reason` or `alternatives[0].why_not`: an existing,
    non-null value; never one language of a Bilingual (`reason.en`), never an empty list (D-052)."""
    quote: NonEmptyStr
    """Verbatim, in the original language (not translated)."""
    source: GroundingSource


class NewTerm(ContractModel):
    """A term the vocabulary doesn't know yet (G4)."""

    term: NonEmptyStr
    lang: Lang


class DraftProvenance(Provenance):
    """Provenance of a draft: nobody has confirmed it yet."""

    confirmed_by: None
    confirmed_at: None


class DraftSituationCue(SituationCue):
    """The cue in a draft. `text` is `null` (and `cue_terms` empty) when the surgeon didn't state
    it; it is never filled from the moment (D-054)."""

    text: Bilingual | None

    @model_validator(mode="after")
    def _no_terms_without_text(self) -> Self:
        if self.text is None and self.cue_terms:
            raise ValueError("cue_terms must be empty while situation_cue.text is null")
        return self


class DraftAction(Action):
    """The action in a draft. `text` is `null` when the surgeon didn't state it (D-054); `type`
    and `actor` are always set (`act` / `unknown` when not said)."""

    text: Bilingual | None


class _DecisionRecordShape(VersionedModel):
    """Fields shared by `DecisionRecord` and `DecisionRecordDraft` (plan §4.3)."""

    id: RecordId | None
    case_id: CaseId
    moment_id: MomentId | None
    """`null` for a record that isn't tied to one flagged moment."""
    step_id: StepId
    """A step of the Procedure Reference."""
    language: Lang
    """The language the answer was originally given in."""
    kind: RecordKind
    context: RecordContext
    situation_cue: SituationCue
    obstacle: Obstacle | None
    anticipation: Bilingual | None
    """What the surgeon expected or planned."""
    action: Action
    alternatives: list[Alternative]
    reason: Bilingual | None
    immediate_result: Bilingual | None
    delayed_outcome: DelayedOutcome
    evidence: list[Evidence]
    grounding: list[Grounding]
    provenance: Provenance
    new_terms: list[NewTerm]
    confidence: Confidence

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        prefix = f"{self.case_id}."
        if self.moment_id is not None and not self.moment_id.startswith(prefix):
            raise ValueError(f"moment {self.moment_id} is not in case {self.case_id}")
        for i, item in enumerate(self.evidence):
            case_id = getattr(item, "case_id", None)
            if case_id is not None and case_id != self.case_id:
                raise ValueError(f"evidence[{i}] is from case {case_id}, not {self.case_id}")
        for i, item in enumerate(self.grounding):
            where = f"grounding[{i}].field {item.field!r}"
            try:
                value = get_at_path(self, item.field)
            except LookupError:
                raise ValueError(f"{where} doesn't exist") from None
            if value is None:
                raise ValueError(f"{where} is null")
            if isinstance(value, list) and not value:
                raise ValueError(f"{where} is an empty list")
            parent, _, last = item.field.rpartition(".")
            if last in ("ja", "en") and parent and isinstance(get_at_path(self, parent), Bilingual):
                raise ValueError(f"{where} names one language of a Bilingual; name the whole field")
        return self


class DecisionRecord(_DecisionRecordShape):
    """A Decision Record in the knowledge base (confirmed by a person, or seeded)."""

    id: RecordId
    """UUIDv7, assigned by the app."""


class DecisionRecordDraft(_DecisionRecordShape):
    """What `/v1/answers/extract` returns: `id` and the confirmation fields are null.

    Unlike a `DecisionRecord`, `situation_cue.text` and `action.text` may be null: the surgeon
    didn't state them. `/extract` then lists them in `missing_fields[]` with an editable chip, and
    the draft can't be confirmed until the surgeon fills them (D-054).
    """

    id: None
    situation_cue: DraftSituationCue
    action: DraftAction
    provenance: DraftProvenance


def confirm_draft(
    draft: DecisionRecordDraft, *, record_id: RecordId, confirmed_by: str, confirmed_at: UtcDatetime
) -> DecisionRecord:
    """The record the app stores when the surgeon taps Confirm on a draft.

    Raises `ValueError` while `situation_cue.text` or `action.text` is still null (D-054).
    """
    unstated = [
        path
        for path, value in [
            ("situation_cue.text", draft.situation_cue.text),
            ("action.text", draft.action.text),
        ]
        if value is None
    ]
    if unstated:
        raise ValueError(f"the surgeon must fill {unstated} before the draft can be confirmed")
    data: dict[str, Any] = draft.model_dump(mode="json")
    data["id"] = str(record_id)
    data["provenance"]["confirmed_by"] = confirmed_by
    data["provenance"]["confirmed_at"] = confirmed_at.isoformat()
    return DecisionRecord.model_validate(data)


def _groundable_paths(record: _DecisionRecordShape) -> list[str]:
    """Filled fields that state something about the decision and so need grounding (G5)."""
    paths = [f"context.patient_factors[{i}]" for i in range(len(record.context.patient_factors))]
    if record.context.preop_plan is not None:
        paths.append("context.preop_plan")
    if record.situation_cue.text is not None:
        paths.append("situation_cue.text")
    if record.obstacle is not None:
        paths.append("obstacle")
    if record.anticipation is not None:
        paths.append("anticipation")
    if record.action.text is not None:
        paths.append("action.text")
    for i, alternative in enumerate(record.alternatives):
        paths.append(f"alternatives[{i}].option")
        if alternative.why_not is not None:
            paths.append(f"alternatives[{i}].why_not")
    for name in ("reason", "immediate_result"):
        if getattr(record, name) is not None:
            paths.append(name)
    return paths


def _related(a: str, b: str) -> bool:
    """True if one path is the other, or contains it."""
    return a == b or a.startswith((f"{b}.", f"{b}[")) or b.startswith((f"{a}.", f"{a}["))


def ungrounded_fields(record: _DecisionRecordShape) -> list[str]:
    """Filled fields with no grounding quote (G5). A grounding on a parent or a child counts.

    `delayed_outcome` (linked later from its own `source`) and the classifications (`kind`,
    `action.type`, `action.actor`, `cue_terms`, `new_terms`) are not checked; null or empty fields
    aren't either (D-052, D-054).
    """
    grounded = [item.field for item in record.grounding]
    return [p for p in _groundable_paths(record) if not any(_related(p, g) for g in grounded)]
