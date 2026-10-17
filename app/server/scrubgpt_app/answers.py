"""The answer loop on the server (J3 + I2 + I7; plan §8.3).

The web app sends what the surgeon did; the server builds the contract requests from the loaded
case (full question, moment, `case.json` and the Reference step: the Brain is stateless, §4.4),
assigns the UUIDv7 `answer_id`, keeps voice recordings locally, and on Confirm turns the draft
into a stored Decision Record with `confirm_draft()`.

Edits: the surgeon's text for a field becomes that field's value in both languages (the other
half from `/v1/translate`, H5) and replaces the field's groundings with one `source: edit`
grounding quoting their words (D-054, D-056). A field the surgeon didn't state stays null unless
they fill it; nothing is filled for them.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from scrubgpt_contracts.models.brain_api import (
    Answer,
    CaseContext,
    ExtractRequest,
    ExtractResponse,
    TranslateRequest,
    TranslateText,
)
from scrubgpt_contracts.models.case_package import Question
from scrubgpt_contracts.models.common import Lang, Role, get_at_path
from scrubgpt_contracts.models.decision_record import (
    DecisionRecord,
    DecisionRecordDraft,
    confirm_draft,
)
from uuid6 import uuid7

from scrubgpt_app.brain_client import BrainClient
from scrubgpt_app.catalog import Catalog, LoadedCase

EDITABLE = re.compile(
    r"^(context\.preop_plan|context\.patient_factors\[\d+\]|situation_cue\.text|anticipation"
    r"|action\.text|reason|immediate_result|alternatives\[\d+\]\.(option|why_not))$"
)
"""The Bilingual fields a surgeon can fill or correct (chips and `missing_fields`, D-056)."""

AUDIO_SUFFIX = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "video/mp4": ".m4a",
}


class AnswerError(ValueError):
    """A request the server can't turn into a valid contract request (400 `bad_request`)."""


class AnswerIn(BaseModel):
    """What the web app sends for one answer; the server adds `answer_id` when it is missing."""

    model_config = ConfigDict(extra="forbid")

    answer_id: str | None = None
    mode: str
    tap: dict[str, Any] | None = None
    text: str | None = None
    lang: Lang
    audio_uri: str | None = None


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    question_id: str
    answerer_role: Role
    answer: AnswerIn


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    text: str = Field(min_length=1)
    lang: Lang


class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_id: str
    draft: dict[str, Any]
    edits: list[Edit] = []
    confirmed_by: str = Field(min_length=1)


@dataclass(frozen=True)
class Answering:
    catalog: Catalog
    brain: BrainClient
    audio_dir: Path

    def case(self, case_id: str) -> LoadedCase:
        loaded = self.catalog.cases.get(case_id)
        if loaded is None:
            raise LookupError(f"no loaded case {case_id!r}")
        return loaded

    def question(self, loaded: LoadedCase, question_id: str) -> Question:
        for question in [*loaded.questions.operating, *loaded.questions.reviewer]:
            if question.id == question_id:
                return question
        raise LookupError(f"case {loaded.id} has no question {question_id!r}")

    # ── voice ─────────────────────────────────────────────────────────────────

    def save_audio(self, audio: bytes, content_type: str) -> tuple[str, str]:
        """Keep a recording locally under a new `answer_id`; returns (answer_id, audio_uri)."""
        answer_id = str(uuid7())
        suffix = AUDIO_SUFFIX.get(content_type.split(";")[0].strip().lower(), ".webm")
        name = f"{answer_id}{suffix}"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        (self.audio_dir / name).write_bytes(audio)
        return answer_id, f"answers/{name}"

    # ── draft ─────────────────────────────────────────────────────────────────

    def extract_request(self, body: DraftIn) -> ExtractRequest:
        loaded = self.case(body.case_id)
        question = self.question(loaded, body.question_id)
        moment = next(m for m in loaded.moments.moments if m.id == question.moment_id)
        reference = self.catalog.references.get(moment.step_id.split(".", 1)[0])
        step = None if reference is None else _find_step(reference, moment.step_id)
        if step is None:
            raise AnswerError(f"no Procedure Reference step {moment.step_id} is loaded")
        answer = body.answer.model_dump()
        answer["answer_id"] = answer["answer_id"] or str(uuid7())
        return ExtractRequest.model_validate(
            {
                "question": question.model_dump(mode="json", by_alias=True),
                "moment": moment.model_dump(mode="json", by_alias=True),
                "case_context": CaseContext(case=loaded.case, step=step).model_dump(
                    mode="json", by_alias=True
                ),
                "answer": Answer.model_validate(answer).model_dump(mode="json"),
                "answerer_role": body.answerer_role.value,
            }
        )

    def draft(self, body: DraftIn) -> tuple[str, ExtractResponse]:
        request = self.extract_request(body)
        return str(request.answer.answer_id), self.brain.extract(request)

    # ── confirm ───────────────────────────────────────────────────────────────

    def apply_edits(self, draft: DecisionRecordDraft, edits: list[Edit]) -> DecisionRecordDraft:
        if not edits:
            return draft
        for edit in edits:
            if not EDITABLE.match(edit.field):
                raise AnswerError(f"{edit.field!r} is not a field the surgeon can edit")
            try:
                get_at_path(draft, edit.field)
            except LookupError:
                raise AnswerError(f"{edit.field!r} doesn't exist in the draft") from None
        texts = [TranslateText(text=edit.text, from_lang=edit.lang) for edit in edits]
        items = self.brain.translate(TranslateRequest(texts=texts)).items
        data = draft.model_dump(mode="json", by_alias=True)
        for edit, bilingual in zip(edits, items, strict=True):
            _set_at_path(data, edit.field, bilingual.model_dump())
            data["grounding"] = [
                g for g in data["grounding"] if not _covers(g["field"], edit.field)
            ] + [{"field": edit.field, "quote": edit.text, "source": "edit"}]
        return DecisionRecordDraft.model_validate(data)

    def confirm(self, body: ConfirmIn) -> DecisionRecord:
        draft = DecisionRecordDraft.model_validate(body.draft)
        self.case(draft.case_id)
        evidence_ids = {str(getattr(item, "answer_id", "")) for item in draft.evidence} - {""}
        if evidence_ids and evidence_ids != {body.answer_id}:
            raise AnswerError("the draft's answer evidence belongs to another answer")
        draft = self.apply_edits(draft, body.edits)
        try:
            return confirm_draft(
                draft,
                record_id=str(uuid7()),
                confirmed_by=body.confirmed_by,
                confirmed_at=datetime.now(UTC),
            )
        except ValueError as exc:  # e.g. the cue or the action is still unstated (D-054)
            raise AnswerError(str(exc)) from None


def _find_step(reference: Any, step_id: str) -> Any:
    for phase in reference.phases:
        for step in phase.steps:
            if step.id == step_id:
                return step
    return None


_PART = re.compile(r"([A-Za-z_]+)(?:\[(\d+)\])?")


def _set_at_path(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    target: Any = data
    for i, part in enumerate(parts):
        match = _PART.fullmatch(part)
        assert match is not None
        key, index = match.group(1), match.group(2)
        last = i == len(parts) - 1
        if index is None:
            if last:
                target[key] = value
            else:
                target = target[key]
        else:
            if last:
                target[key][int(index)] = value
            else:
                target = target[key][int(index)]


def _covers(grounded: str, edited: str) -> bool:
    """A grounding on the edited field or inside it. A grounding on a whole object (e.g.
    `alternatives[0]`) stays: it still supports the object's other fields (G5)."""
    return grounded == edited or grounded.startswith((edited + ".", edited + "["))
