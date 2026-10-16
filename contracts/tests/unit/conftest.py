"""Shared sample data for Dev1's contract unit tests (not the testers' folders)."""

import copy

import pytest
from scrubgpt_contracts.models.common import new_uuid7

ANSWER_ID = "01a1435a-f708-7ff0-b0be-4efc75ad6204"


def bi(en: str) -> dict:
    return {"ja": f"（{en}）", "en": en}


DRAFT = {
    "contract_version": "1.0",
    "id": None,
    "case_id": "case-fixture-01",
    "moment_id": "case-fixture-01.m02",
    "question_id": "case-fixture-01.m02.q1",
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


@pytest.fixture
def draft() -> dict:
    """A valid DecisionRecordDraft as JSON data."""
    return copy.deepcopy(DRAFT)


@pytest.fixture
def record() -> dict:
    """A valid DecisionRecord as JSON data."""
    return record_data()


@pytest.fixture
def change():
    """`change(data, a__b=1)`: a deep copy of `data` with `data["a"]["b"] = 1`."""
    return with_changes
