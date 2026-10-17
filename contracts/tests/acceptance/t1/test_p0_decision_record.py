"""AC10: DecisionRecord and DecisionRecordDraft (plan §4.3, D-034, #3 points 1 and 5)."""

from __future__ import annotations

import copy
from typing import Any

import pytest
import uuid6
from pydantic import ValidationError
from scrubgpt_contracts.models.decision_record import DecisionRecord, DecisionRecordDraft

RECORD_FIELDS = {
    "contract_version",
    "id",
    "case_id",
    "moment_id",
    "question_id",
    "step_id",
    "language",
    "kind",
    "context",
    "situation_cue",
    "obstacle",
    "anticipation",
    "action",
    "alternatives",
    "reason",
    "immediate_result",
    "delayed_outcome",
    "evidence",
    "grounding",
    "provenance",
    "new_terms",
    "confidence",
}


@pytest.fixture
def record(docs) -> dict[str, Any]:
    """Seed record 0 of the fixture: every main field filled (moment m01, rescue)."""
    return copy.deepcopy(docs["seed_records.json"]["records"][0])


def _draft(record: dict[str, Any]) -> dict[str, Any]:
    draft = copy.deepcopy(record)
    draft["id"] = None
    draft["provenance"]["confirmed_by"] = None
    draft["provenance"]["confirmed_at"] = None
    return draft


def _path_text(path: tuple) -> str:
    """("alternatives", 0, "why_not") -> "alternatives[0].why_not" (plan §4.1 field paths)."""
    text = ""
    for step in path:
        text += f"[{step}]" if isinstance(step, int) else (f".{step}" if text else step)
    return text


def _with(doc: dict[str, Any], path: tuple, value: Any) -> dict[str, Any]:
    doc = copy.deepcopy(doc)
    node = doc
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    return doc


def test_ac10_record_shape_matches_plan_4_3(record):
    """AC10: "`DecisionRecord` per §4.3" (top-level fields and nested shapes)."""
    dumped = DecisionRecord.model_validate(record).model_dump(mode="json")
    assert set(dumped) == RECORD_FIELDS
    assert set(dumped["context"]) == {"patient_factors", "preop_plan"}
    assert set(dumped["situation_cue"]) == {"text", "cue_terms"}
    assert set(dumped["obstacle"]) == {"family", "type", "cause"}
    assert set(dumped["action"]) == {"type", "text", "actor"}
    assert all(set(a) == {"option", "why_not"} for a in dumped["alternatives"])
    assert set(dumped["delayed_outcome"]) == {"status", "text", "source"}
    assert all(set(g) == {"field", "quote", "source"} for g in dumped["grounding"])
    assert all(set(t) == {"term", "lang"} for t in dumped["new_terms"])


def test_ac10_draft_has_same_shape_with_id_and_confirmation_null(record):
    """AC10: "`DecisionRecordDraft` has the same shape, with `id` null and
    `provenance.confirmed_by` / `confirmed_at` null" (plan §4.3)."""
    dumped = DecisionRecordDraft.model_validate(_draft(record)).model_dump(mode="json")
    assert set(dumped) == RECORD_FIELDS
    assert dumped["id"] is None
    assert dumped["provenance"]["confirmed_by"] is None
    assert dumped["provenance"]["confirmed_at"] is None


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("id",), str(uuid6.uuid7())),
        (("provenance", "confirmed_by"), "dr-a"),
        (("provenance", "confirmed_at"), "2026-10-21T09:30:00Z"),
    ],
    ids=repr,
)
def test_ac10_draft_rejects_id_or_confirmation(record, path, value):
    """AC10: in a draft, `id`, `confirmed_by` and `confirmed_at` are null (plan §4.3: "the
    app assigns the UUIDv7 id and fills the confirmation fields when the surgeon taps
    Confirm")."""
    with pytest.raises(ValidationError):
        DecisionRecordDraft.model_validate(_with(_draft(record), path, value))


def test_ac10_draft_still_requires_the_id_key(record):
    """AC10 + D-034: the draft's `id` is a required (null) key, like every v1.0 field."""
    draft = _draft(record)
    del draft["id"]
    with pytest.raises(ValidationError):
        DecisionRecordDraft.model_validate(draft)


def test_ac10_record_requires_a_uuid7_id(record):
    """AC10 / §4.3: a DecisionRecord `id` is a UUIDv7, not null."""
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(_with(record, ("id",), None))


@pytest.mark.parametrize("kind", ["rescue", "anticipatory", "checkpoint", "bail_out"])
def test_ac10_kind_values_accepted(record, kind):
    """AC10: "`kind` is one of rescue / anticipatory / checkpoint / bail_out (D-034)"."""
    DecisionRecord.model_validate(_with(record, ("kind",), kind))


@pytest.mark.parametrize("kind", ["deliberate_non_action", "rescued", "", None, "other"])
def test_ac10_other_kinds_rejected(record, kind):
    """AC10 / D-034: "`kind` loses `deliberate_non_action` (that is `action.type`)"."""
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(_with(record, ("kind",), kind))


@pytest.mark.parametrize(
    ("path", "good", "bad"),
    [
        (("action", "type"), ["act", "deliberate_non_action"], ["non_action", "none"]),
        (
            ("action", "actor"),
            ["surgeon", "assistant", "resident", "bedside", "anesthesia", "unknown"],
            ["nurse", "ai"],
        ),
        (
            ("obstacle", "cause"),
            ["patient", "event", "technical", "equipment", "unknown"],
            ["surgeon", "other"],
        ),
        (("delayed_outcome", "status"), ["pending", "known", "not_applicable"], ["unknown"]),
        (("language",), ["ja", "en"], ["none", "fr", "JA"]),
        (("grounding", 0, "source"), ["answer", "edit", "narration"], ["ai", "transcript"]),
        (("new_terms", 0, "lang"), ["ja", "en"], ["fr", "none"]),
    ],
    ids=lambda x: str(x),
)
def test_ac10_enumerations(record, path, good, bad):
    """AC10: the §4.3 enumerations (action.type, actor, obstacle.cause, delayed_outcome.status,
    language ja|en, grounding `source` answer|edit|narration)."""
    for value in good:
        DecisionRecord.model_validate(_with(record, path, value))
    for value in bad:
        with pytest.raises(ValidationError):
            DecisionRecord.model_validate(_with(record, path, value))


def test_ac10_nullable_fields_accept_null(record):
    """AC10 / §4.3: moment_id, obstacle, obstacle.type, anticipation, reason, immediate_result,
    preop_plan, why_not, delayed_outcome text/source may be null ("a field the surgeon did not
    state is null"). Grounding entries pointing at them are removed first.

    Updated for #10 / D-059: `question_id` may be null too, and a null `moment_id` needs a null
    `question_id` (rule 2), so it is cleared along with `moment_id`."""
    nulls = [
        ("moment_id",),
        ("question_id",),
        ("obstacle",),
        ("anticipation",),
        ("reason",),
        ("immediate_result",),
        ("context", "preop_plan"),
        ("alternatives", 0, "why_not"),
        ("delayed_outcome", "text"),
        ("delayed_outcome", "source"),
    ]
    for path in nulls:
        doc = _with(record, path, None)
        if path == ("moment_id",):
            doc["question_id"] = None
        text = _path_text(path)
        doc["grounding"] = [
            g
            for g in doc["grounding"]
            if not (g["field"] == text or g["field"].startswith((text + ".", text + "[")))
        ]
        DecisionRecord.model_validate(doc)
    doc = _with(record, ("obstacle", "type"), None)
    DecisionRecord.model_validate(doc)


@pytest.mark.parametrize(
    "field",
    ["action.text", "alternatives[0].why_not", "alternatives[0].option", "situation_cue.text"],
)
def test_ac10_grounding_path_to_existing_non_null_field_accepted(record, field):
    """AC10: "Grounding field paths (`a.b[0].c`) must point to existing, non-null fields"."""
    doc = copy.deepcopy(record)
    doc["grounding"].append({"field": field, "quote": "圧で止まりそうだった", "source": "answer"})
    DecisionRecord.model_validate(doc)


@pytest.mark.parametrize(
    "field",
    [
        "anticipation",  # null in this record
        "context.preop_plan",  # null in this record
        "delayed_outcome.text",  # null in this record
        "alternatives[1].option",  # index out of range
        "alternatives[0].nonexistent",
        "nonexistent",
        "reason.foo",
        "action..text",
        "action.text.",
        "Action.text",
        "alternatives.0.option",
        "alternatives[x].option",
        "",
    ],
)
def test_ac10_grounding_path_to_missing_null_or_malformed_field_rejected(record, field):
    """AC10: grounding field paths must use the `a.b[0].c` syntax and "point to existing,
    non-null fields"."""
    doc = copy.deepcopy(record)
    doc["grounding"].append({"field": field, "quote": "静脈性なので", "source": "answer"})
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(doc)


def test_ac10_grounding_quote_is_a_verbatim_string_not_bilingual(record):
    """AC10: "Quotes are verbatim strings, not Bilingual (#3)" (grounding, transcript and
    answer_text evidence); whitespace-only quotes are rejected too (#3 point 1)."""
    bilingual = {"ja": "静脈性なので", "en": "Because it was venous"}
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(_with(record, ("grounding", 0, "quote"), bilingual))
    for empty in ("", "   "):
        with pytest.raises(ValidationError):
            DecisionRecord.model_validate(_with(record, ("grounding", 0, "quote"), empty))
    answer_text = next(i for i, e in enumerate(record["evidence"]) if e["kind"] == "answer_text")
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(_with(record, ("evidence", answer_text, "quote"), bilingual))
    transcript = {
        "kind": "transcript",
        "case_id": "case-fixture-01",
        "utterance_id": "case-fixture-01.u0003",
        "quote": bilingual,
    }
    doc = copy.deepcopy(record)
    doc["evidence"].append(transcript)
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(doc)
    doc["evidence"][-1]["quote"] = "気腹圧を上げてください"
    DecisionRecord.model_validate(doc)


def test_ac10_human_readable_fields_are_bilingual(record):
    """AC10 + D-024 ("The DecisionRecord is fully bilingual"): a plain string where §4.3 says
    Bilingual is rejected."""
    for path in (
        ("situation_cue", "text"),
        ("action", "text"),
        ("reason",),
        ("immediate_result",),
        ("alternatives", 0, "option"),
    ):
        with pytest.raises(ValidationError):
            DecisionRecord.model_validate(_with(record, path, "plain English only"))


def test_ac10_obstacle_leaf_must_belong_to_its_family(record, data_dir, run_validate):
    """#3 point 5: "a leaf prefix equals `obstacle.family`" is checked in decision_record.py
    or validate.py. A seed record with family `bleeding` and type `visibility.smoke` must not
    pass `scrubgpt-validate case`."""
    seeds = data_dir.load("seed_records.json")
    seeds["records"][0]["obstacle"]["family"] = "bleeding"
    seeds["records"][0]["obstacle"]["type"] = "visibility.smoke"
    data_dir.save("seed_records.json", seeds)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert "seed_records.json" in result.problems, result.output
