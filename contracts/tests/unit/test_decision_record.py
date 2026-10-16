"""Dev1's unit tests for models/decision_record.py (plan §4.3, D-034). Sample data: conftest.py."""

import inspect
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ValidationError
from scrubgpt_contracts.models import decision_record as dr
from scrubgpt_contracts.models.common import new_uuid7


def test_draft_validates_and_round_trips(draft):
    model = dr.DecisionRecordDraft.model_validate(draft)
    assert model.model_dump(mode="json") == draft
    assert dr.ungrounded_fields(model) == []


def test_draft_needs_null_id_and_unconfirmed_provenance(draft, change):
    with pytest.raises(ValidationError):
        dr.DecisionRecordDraft.model_validate(change(draft, id=str(new_uuid7())))
    with pytest.raises(ValidationError):
        dr.DecisionRecordDraft.model_validate(change(draft, provenance__confirmed_by="x"))


def test_record_needs_uuid7_id(record, change):
    assert dr.DecisionRecord.model_validate(record).id.version == 7
    with pytest.raises(ValidationError):
        dr.DecisionRecord.model_validate(change(record, id=None))


def test_record_may_stay_unconfirmed(record, change):
    """Narration-mined seed records have no confirming person."""
    data = change(record, provenance__confirmed_by=None, provenance__confirmed_at=None)
    assert dr.DecisionRecord.model_validate(data).provenance.confirmed_by is None


def test_confirm_draft(draft):
    model = dr.DecisionRecordDraft.model_validate(draft)
    record_id = new_uuid7()
    record = dr.confirm_draft(
        model,
        record_id=record_id,
        confirmed_by="surgeon-a",
        confirmed_at=datetime(2026, 10, 21, 9, 30, tzinfo=UTC),
    )
    assert record.id == record_id
    assert record.provenance.confirmed_by == "surgeon-a"
    assert record.model_dump(mode="json")["provenance"]["confirmed_at"] == "2026-10-21T09:30:00Z"
    assert record.action.model_dump() == model.action.model_dump()


@pytest.mark.parametrize(
    "changes",
    [
        {"moment_id": "case-fixture-02.m02"},  # moment from another case
        {"obstacle__type": "visibility.smoke"},  # leaf outside the family
        {"obstacle__family": "smoke"},  # not one of the 8 families
        {"kind": "deliberate_non_action"},  # that is action.type (D-034)
        {"language": "fr"},
        {"confidence": 1.2},
        {"step_id": "rarp.p5.s1"},
        {"situation_cue": None},  # required, not nullable
        {"reason": {"ja": "", "en": "x"}},  # bilingual halves must be non-empty
        {"grounding": [{"field": "anticipation", "quote": "q", "source": "answer"}]},  # null
        {"grounding": [{"field": "reasons", "quote": "q", "source": "answer"}]},  # no such field
        {"grounding": [{"field": "reason", "quote": "q", "source": "guess"}]},
        {"grounding": [{"field": "reason", "quote": " ", "source": "answer"}]},
        {"grounding": [{"field": "reason.en", "quote": "q", "source": "answer"}]},  # D-052
        {"grounding": [{"field": "action.text.ja", "quote": "q", "source": "answer"}]},
        {
            "alternatives": [],  # an empty list can't be grounded (D-052)
            "grounding": [{"field": "alternatives", "quote": "q", "source": "answer"}],
        },
        {"grounding": [{"field": "context.preop_plan", "quote": "q", "source": "answer"}]},  # null
    ],
)
def test_invalid_drafts(draft, change, changes):
    with pytest.raises(ValidationError):
        dr.DecisionRecordDraft.model_validate(change(draft, **changes))


def test_unstated_cue_and_action_in_drafts_only(draft, record, change):
    """D-054: a draft may leave situation_cue.text / action.text null; a record may not."""
    unstated = change(
        draft,
        situation_cue__text=None,
        situation_cue__cue_terms=[],
        action__text=None,
        grounding=[
            g for g in draft["grounding"] if g["field"] not in ("situation_cue.text", "action.text")
        ],
    )
    model = dr.DecisionRecordDraft.model_validate(unstated)
    assert dr.ungrounded_fields(model) == []  # null fields are not checked
    with pytest.raises(ValueError, match="before the draft can be confirmed"):
        dr.confirm_draft(
            model,
            record_id=new_uuid7(),
            confirmed_by="surgeon-a",
            confirmed_at=datetime(2026, 10, 21, 9, 30, tzinfo=UTC),
        )
    with pytest.raises(ValidationError):  # cue terms without a cue
        dr.DecisionRecordDraft.model_validate(change(unstated, situation_cue__cue_terms=["x"]))
    for changes in ({"situation_cue__text": None}, {"action__text": None}):
        with pytest.raises(ValidationError):
            dr.DecisionRecord.model_validate(change(record, **changes))


@pytest.mark.parametrize(
    ("path", "text_key", "whole", "allowed"),
    [
        ("situation_cue", "situation_cue__text", "situation_cue", []),
        ("action", "action__text", "action", ["action.type", "action.actor"]),
    ],
)
def test_no_whole_field_grounding_for_unstated_text(
    draft, record, change, path, text_key, whole, allowed
):
    """D-056 rule 1 (12e): grounding the whole cue/action would claim its null text is grounded."""
    kept = [g for g in draft["grounding"] if g["field"] != f"{path}.text"]
    extra = {"situation_cue__cue_terms": []} if path == "situation_cue" else {}
    unstated = change(draft, **{text_key: None}, grounding=kept, **extra)
    assert dr.DecisionRecordDraft.model_validate(unstated)
    whole_grounding = {"field": whole, "quote": "まず気腹圧を上げました", "source": "answer"}
    with pytest.raises(ValidationError, match="is null"):
        dr.DecisionRecordDraft.model_validate(change(unstated, grounding=[*kept, whole_grounding]))
    for field in allowed:  # the type and actor are always set, so they may be grounded
        grounding = [*kept, {**whole_grounding, "field": field}]
        assert dr.DecisionRecordDraft.model_validate(change(unstated, grounding=grounding))
    # With the text filled, a whole-object grounding is fine (draft and record).
    filled = change(draft, grounding=[*draft["grounding"], whole_grounding])
    assert dr.DecisionRecordDraft.model_validate(filled)
    assert dr.DecisionRecord.model_validate(
        change(record, grounding=[*record["grounding"], whole_grounding])
    )


def test_unverbatim_groundings(draft, change):
    """Issue #9 (3e): answer quotes are in answer_text evidence, narration quotes in transcripts."""
    narration = {
        "kind": "transcript",
        "case_id": "case-fixture-01",
        "utterance_id": "case-fixture-01.u0003",
        "quote": "少し出血しています。気腹圧を上げてください。",
    }
    model = dr.DecisionRecordDraft.model_validate(
        change(
            draft,
            evidence=[*draft["evidence"], narration],
            grounding=[
                {"field": "action.text", "quote": "まず気腹圧を上げました", "source": "answer"},
                {"field": "action", "quote": "気腹圧を上げ", "source": "answer"},  # a substring
                {"field": "reason", "quote": "never said", "source": "answer"},
                {
                    "field": "situation_cue.text",
                    "quote": "少し出血しています",
                    "source": "narration",
                },
                {"field": "obstacle", "quote": "まず気腹圧を上げました", "source": "narration"},
                {"field": "alternatives[0]", "quote": "a chip the surgeon typed", "source": "edit"},
                # NFC on both sides: a decomposed げ (け + U+3099) matches the composed one.
                {"field": "context", "quote": "まず気腹圧を上げました", "source": "answer"},
            ],
        )
    )
    assert dr.unverbatim_groundings(model) == [2, 4]


def test_evidence_must_be_from_the_record_case(draft):
    draft["evidence"][0]["case_id"] = "grasp-01"
    with pytest.raises(ValidationError):
        dr.DecisionRecordDraft.model_validate(draft)


def test_every_v1_key_is_required(draft):
    del draft["anticipation"]  # nullable, but the key must be sent (D-034)
    with pytest.raises(ValidationError):
        dr.DecisionRecordDraft.model_validate(draft)


def test_ungrounded_fields(draft, change):
    model = dr.DecisionRecordDraft.model_validate(
        change(
            draft,
            grounding=[{"field": "action", "quote": "まず気腹圧を上げました", "source": "answer"}],
            immediate_result={"ja": "にじみは止まった", "en": "the oozing stopped"},
        )
    )
    assert dr.ungrounded_fields(model) == [
        "context.patient_factors[0]",
        "situation_cue.text",
        "obstacle",
        "alternatives[0].option",
        "reason",
        "immediate_result",
    ]


MODELS = [
    obj
    for obj in vars(dr).values()
    if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj.__module__ == dr.__name__
]


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_every_v1_field_is_required_and_tolerant(model):
    assert model.model_config.get("extra") == "ignore"
    assert all(field.is_required() for field in model.model_fields.values())
    schema = model.model_json_schema(mode="serialization")
    assert set(schema.get("required", [])) == set(model.model_fields)


def test_draft_and_record_have_the_same_shape():
    assert list(dr.DecisionRecord.model_fields) == list(dr.DecisionRecordDraft.model_fields)
