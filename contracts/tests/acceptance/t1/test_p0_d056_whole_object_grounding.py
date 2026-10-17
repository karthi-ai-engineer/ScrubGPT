"""#5 criterion 12e: no grounding on the whole `situation_cue` / `action` while its text is null
(Team Lead reply on issue #5, 2026-10-16 08:18, logged as D-056 rule 1; refines D-054).

12e (verbatim): "`DecisionRecordDraft` rejects a grounding with `field: "situation_cue"` while
`situation_cue.text` is null, and one with `field: "action"` while `action.text` is null. It accepts
`action.type` and `action.actor` groundings while `action.text` is null. Both whole-object
groundings are still accepted when the text is filled."

D-056: "in `DecisionRecordDraft`, a `grounding[].field` of exactly `situation_cue` while
`situation_cue.text` is null, or exactly `action` while `action.text` is null, is a validation error
(`action.type` / `action.actor` groundings stay allowed). `DecisionRecord` is unchanged." The Team
Lead's reply adds: "'A path inside them' needs no new rule ... D-052 already rejects those paths."
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from typing import Any

import pytest
import uuid6
from pydantic import ValidationError
from scrubgpt_contracts.models.decision_record import (
    DecisionRecord,
    DecisionRecordDraft,
    confirm_draft,
)

SEED_INDEX = 0  # fixture seed record for m01 (rescue), fully grounded
SOURCES = ["answer", "edit", "narration"]


@pytest.fixture
def record(docs) -> dict[str, Any]:
    return copy.deepcopy(docs["seed_records.json"]["records"][SEED_INDEX])


def _draft(record: dict[str, Any]) -> dict[str, Any]:
    draft = copy.deepcopy(record)
    draft["id"] = None
    draft["provenance"]["confirmed_by"] = None
    draft["provenance"]["confirmed_at"] = None
    return draft


def _covers(field: str, path: str) -> bool:
    return field == path or field.startswith((path + ".", path + "["))


def _unstate(doc: dict[str, Any], *which: str) -> dict[str, Any]:
    """An unstated cue (`text: null`, `cue_terms: []`) or action (`text: null`, `type`/`actor`
    kept: `act` / `unknown`), per D-054; groundings on the nulled text are dropped (D-052)."""
    doc = copy.deepcopy(doc)
    for part in which:
        if part == "situation_cue":
            doc["situation_cue"] = {"text": None, "cue_terms": []}
            doc["grounding"] = [g for g in doc["grounding"] if not _covers(g["field"], part)]
        elif part == "action":
            doc["action"] = {"type": "act", "text": None, "actor": "unknown"}
            doc["grounding"] = [
                g
                for g in doc["grounding"]
                if g["field"] != "action" and not _covers(g["field"], "action.text")
            ]
        else:  # pragma: no cover - helper misuse
            raise AssertionError(part)
    return doc


def _with(doc: dict[str, Any], field: str, source: str = "answer") -> dict[str, Any]:
    doc = copy.deepcopy(doc)
    doc["grounding"].append({"field": field, "quote": "静脈性のにじみ", "source": source})
    return doc


def _rejects(doc: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        DecisionRecordDraft.model_validate(doc)
    with pytest.raises(ValidationError):
        DecisionRecordDraft.model_validate_json(json.dumps(doc, ensure_ascii=False))


def _accepts(doc: dict[str, Any]) -> DecisionRecordDraft:
    DecisionRecordDraft.model_validate_json(json.dumps(doc, ensure_ascii=False))
    return DecisionRecordDraft.model_validate(doc)


@pytest.mark.parametrize("source", SOURCES)
def test_12e_draft_rejects_whole_situation_cue_grounding_while_text_null(record, source):
    """12e: "`DecisionRecordDraft` rejects a grounding with `field: "situation_cue"` while
    `situation_cue.text` is null" (whatever its `source`)."""
    doc = _unstate(_draft(record), "situation_cue")
    _accepts(doc)  # control: the draft without that grounding is valid
    _rejects(_with(doc, "situation_cue", source))


@pytest.mark.parametrize("source", SOURCES)
def test_12e_draft_rejects_whole_action_grounding_while_text_null(record, source):
    """12e: "... and one with `field: "action"` while `action.text` is null"."""
    doc = _unstate(_draft(record), "action")
    _accepts(doc)
    _rejects(_with(doc, "action", source))


@pytest.mark.parametrize("field", ["situation_cue", "action"])
def test_12e_draft_rejects_the_grounding_with_both_texts_null(record, field):
    """12e with both texts unstated: either whole-object grounding is rejected."""
    doc = _unstate(_draft(record), "situation_cue", "action")
    _accepts(doc)
    _rejects(_with(doc, field))


def test_12e_draft_rejects_it_among_other_valid_groundings(record):
    """12e: the bad grounding is rejected wherever it sits in `grounding[]` (first or last)."""
    doc = _unstate(_draft(record), "action")
    first = copy.deepcopy(doc)
    first["grounding"].insert(0, {"field": "action", "quote": "x", "source": "edit"})
    _rejects(first)
    _rejects(_with(doc, "action", "edit"))


@pytest.mark.parametrize(
    "fields",
    [["action.type"], ["action.actor"], ["action.type", "action.actor"]],
    ids=lambda f: "+".join(f),
)
@pytest.mark.parametrize("also_cue_null", [False, True], ids=["cue-filled", "cue-null"])
def test_12e_draft_accepts_action_type_and_actor_groundings_while_text_null(
    record, fields, also_cue_null
):
    """12e: "It accepts `action.type` and `action.actor` groundings while `action.text` is null"
    (D-056: "`action.type` / `action.actor` groundings stay allowed")."""
    doc = _unstate(_draft(record), "action", *(["situation_cue"] if also_cue_null else []))
    for field in fields:
        doc = _with(doc, field)
    draft = _accepts(doc)
    assert draft.action.text is None
    assert {g.field for g in draft.grounding} >= set(fields)


def test_12e_draft_accepts_both_whole_object_groundings_when_text_filled(record):
    """12e: "Both whole-object groundings are still accepted when the text is filled"."""
    doc = _with(_with(_draft(record), "situation_cue"), "action", "edit")
    draft = _accepts(doc)
    assert draft.situation_cue.text is not None and draft.action.text is not None


@pytest.mark.parametrize(
    ("unstated", "grounded"),
    [("situation_cue", "action"), ("action", "situation_cue")],
)
def test_12e_the_rule_is_per_object(record, unstated, grounded):
    """12e: only the object whose text is null is affected: with the cue unstated, a grounding on
    the filled `action` is fine, and the other way round."""
    _accepts(_with(_unstate(_draft(record), unstated), grounded))


def test_12e_decision_record_is_unchanged(record):
    """D-056: "`DecisionRecord` is unchanged": whole-object groundings stay valid there (its
    texts are always filled)."""
    DecisionRecord.model_validate(_with(_with(record, "situation_cue"), "action"))


@pytest.mark.parametrize(
    ("unstated", "field"),
    [
        ("situation_cue", "situation_cue.text"),
        ("situation_cue", "situation_cue.cue_terms"),
        ("action", "action.text"),
    ],
)
def test_12e_paths_inside_the_unstated_object_stay_rejected(record, unstated, field):
    """Team Lead reply (12e): "'A path inside them' needs no new rule. With the text null,
    `situation_cue.text` and `action.text` are null and `cue_terms` is `[]`, and D-052 already
    rejects those paths"."""
    doc = _unstate(_draft(record), unstated)
    _rejects(_with(doc, field))


@pytest.mark.parametrize("which", ["situation_cue", "action"])
def test_12e_after_the_surgeon_fills_the_text_the_grounding_is_accepted_and_confirms(record, which):
    """12e "still accepted when the text is filled", end to end: the surgeon fills the unstated
    text with a chip edit (D-056: "the surgeon's text becomes a `grounding[]` entry with `source:
    edit`"); a whole-object grounding is then valid and the draft confirms."""
    doc = _unstate(_draft(record), which)
    _rejects(_with(doc, which, "edit"))
    filled = copy.deepcopy(doc)
    filled[which]["text"] = copy.deepcopy(record[which]["text"])
    filled = _with(filled, which, "edit")
    draft = _accepts(filled)
    confirmed = confirm_draft(
        draft,
        record_id=str(uuid6.uuid7()),
        confirmed_by="dr-fixture",
        confirmed_at=datetime(2026, 10, 21, 9, 30, tzinfo=UTC),
    )
    assert which in {g.field for g in confirmed.grounding}
