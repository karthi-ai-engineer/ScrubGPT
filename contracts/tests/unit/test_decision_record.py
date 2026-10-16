"""Dev1's unit tests for models/decision_record.py (plan §4.3, D-034)."""

import copy
import inspect
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ValidationError
from scrubgpt_contracts.models import decision_record as dr
from scrubgpt_contracts.models.common import new_uuid7

ANSWER_ID = "01a1435a-f708-7ff0-b0be-4efc75ad6204"


def bi(en: str) -> dict:
    return {"ja": f"（{en}）", "en": en}


DRAFT = {
    "contract_version": "1.0",
    "id": None,
    "case_id": "case-fixture-01",
    "moment_id": "case-fixture-01.m02",
    "step_id": "rarp.p05.s01",
    "language": "ja",
    "kind": "rescue",
    "context": {"patient_factors": [bi("large prostate")], "preop_plan": None},
    "situation_cue": {"text": bi("venous oozing at the plexus"), "cue_terms": ["venous oozing"]},
    "obstacle": {"family": "bleeding", "type": "bleeding.venous_plexus", "cause": "patient"},
    "anticipation": None,
    "action": {"type": "act", "text": bi("raised the pneumoperitoneum"), "actor": "surgeon"},
    "alternatives": [{"option": bi("suture ligation"), "why_not": None}],
    "reason": bi("pressure first, sutures if it continues"),
    "immediate_result": None,
    "delayed_outcome": {"status": "pending", "text": None, "source": None},
    "evidence": [
        {
            "kind": "media",
            "case_id": "case-fixture-01",
            "uri": "video.mp4#t=60.0,80.0",
            "t_start": 60.0,
            "t_end": 80.0,
        },
        {"kind": "answer_text", "answer_id": ANSWER_ID, "quote": "まず気腹圧を上げました"},
    ],
    "grounding": [
        {"field": "context.patient_factors[0]", "quote": "大きい前立腺", "source": "answer"},
        {"field": "situation_cue.text", "quote": "静脈叢からのにじみ", "source": "answer"},
        {"field": "obstacle.type", "quote": "静脈叢", "source": "answer"},
        {"field": "action.text", "quote": "まず気腹圧を上げました", "source": "answer"},
        {"field": "alternatives[0]", "quote": "縫合も考えました", "source": "answer"},
        {"field": "reason", "quote": "まず圧で", "source": "answer"},
    ],
    "provenance": {
        "trust_label": "operating_surgeon",
        "attributed_to": "operating_surgeon",
        "generated_by": {"model_tier": "TEXT_SMART", "model": "m", "prompt_version": "extract.v1"},
        "confirmed_by": None,
        "confirmed_at": None,
    },
    "new_terms": [{"term": "にじみ", "lang": "ja"}],
    "confidence": 0.8,
}


def with_changes(base: dict, **changes) -> dict:
    data = copy.deepcopy(base)
    for path, value in changes.items():
        target = data
        *parents, last = path.split("__")
        for key in parents:
            target = target[key]
        target[last] = value
    return data


def record_data() -> dict:
    return with_changes(
        DRAFT,
        id=str(new_uuid7()),
        provenance__confirmed_by="surgeon-a",
        provenance__confirmed_at="2026-10-21T09:30:00Z",
    )


def test_draft_validates_and_round_trips():
    draft = dr.DecisionRecordDraft.model_validate(DRAFT)
    assert draft.model_dump(mode="json") == DRAFT
    assert dr.ungrounded_fields(draft) == []


def test_draft_needs_null_id_and_unconfirmed_provenance():
    with pytest.raises(ValidationError):
        dr.DecisionRecordDraft.model_validate(with_changes(DRAFT, id=str(new_uuid7())))
    with pytest.raises(ValidationError):
        dr.DecisionRecordDraft.model_validate(with_changes(DRAFT, provenance__confirmed_by="x"))


def test_record_needs_uuid7_id():
    record = dr.DecisionRecord.model_validate(record_data())
    assert record.id.version == 7
    with pytest.raises(ValidationError):
        dr.DecisionRecord.model_validate(with_changes(record_data(), id=None))


def test_record_may_stay_unconfirmed():
    """Narration-mined seed records have no confirming person."""
    data = with_changes(record_data(), provenance__confirmed_by=None)
    data["provenance"]["confirmed_at"] = None
    assert dr.DecisionRecord.model_validate(data).provenance.confirmed_by is None


def test_confirm_draft():
    draft = dr.DecisionRecordDraft.model_validate(DRAFT)
    record_id = new_uuid7()
    record = dr.confirm_draft(
        draft,
        record_id=record_id,
        confirmed_by="surgeon-a",
        confirmed_at=datetime(2026, 10, 21, 9, 30, tzinfo=UTC),
    )
    assert record.id == record_id
    assert record.provenance.confirmed_by == "surgeon-a"
    assert record.model_dump(mode="json")["provenance"]["confirmed_at"] == "2026-10-21T09:30:00Z"
    assert record.action == draft.action


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
    ],
)
def test_invalid_drafts(changes):
    with pytest.raises(ValidationError):
        dr.DecisionRecordDraft.model_validate(with_changes(DRAFT, **changes))


def test_evidence_must_be_from_the_record_case():
    data = copy.deepcopy(DRAFT)
    data["evidence"][0]["case_id"] = "grasp-01"
    with pytest.raises(ValidationError):
        dr.DecisionRecordDraft.model_validate(data)


def test_every_v1_key_is_required():
    data = copy.deepcopy(DRAFT)
    del data["anticipation"]  # nullable, but the key must be sent (D-034)
    with pytest.raises(ValidationError):
        dr.DecisionRecordDraft.model_validate(data)


def test_ungrounded_fields():
    draft = dr.DecisionRecordDraft.model_validate(
        with_changes(
            DRAFT,
            grounding=[{"field": "action", "quote": "まず気腹圧を上げました", "source": "answer"}],
            immediate_result=bi("oozing stopped"),
        )
    )
    assert dr.ungrounded_fields(draft) == [
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
