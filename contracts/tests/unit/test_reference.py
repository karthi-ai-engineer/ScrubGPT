"""Dev1's unit tests for models/reference.py (plan §4.2b, D-035)."""

import copy

import pytest
from pydantic import ValidationError
from scrubgpt_contracts.models.common import ObstacleFamily
from scrubgpt_contracts.models.reference import ProcedureReference


def bi(en: str) -> dict:
    return {"ja": f"（{en}）", "en": en}


DURATION = {"p25": 60.0, "p50": 120.0, "p75": 300.0}

REFERENCE = {
    "contract_version": "1.0",
    "id": "rarp",
    "name": bi("Robot-assisted radical prostatectomy"),
    "phases": [
        {
            "id": "rarp.p05",
            "name": bi("Anterior bladder neck dissection"),
            "order": 5,
            "typical_duration_s": DURATION,
            "steps": [
                {
                    "id": "rarp.p05.s01",
                    "name": bi("Identify the bladder neck"),
                    "order": 1,
                    "typical_duration_s": DURATION,
                    "checkpoints": [{"id": "rarp.p05.s01.c1", "text": bi("Bladder neck seen")}],
                }
            ],
        }
    ],
    "obstacle_taxonomy": [
        {"id": family.value, "name": bi(family.value), "leaves": []} for family in ObstacleFamily
    ],
}
REFERENCE["obstacle_taxonomy"][1]["leaves"] = [
    {"id": "anatomical_variation.median_lobe", "name": bi("Median lobe")}
]


def changed(mutate) -> dict:
    data = copy.deepcopy(REFERENCE)
    mutate(data)
    return data


def test_reference_validates_and_round_trips():
    reference = ProcedureReference.model_validate(REFERENCE)
    assert reference.model_dump(mode="json") == REFERENCE
    assert reference.step("rarp.p05.s01").name.en == "Identify the bladder neck"
    assert reference.step("rarp.p99.s01") is None
    assert reference.checkpoint_ids() == {"rarp.p05.s01.c1"}
    assert reference.leaf_ids() == {"anatomical_variation.median_lobe"}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["obstacle_taxonomy"].pop(),  # only 7 families
        lambda d: d["obstacle_taxonomy"].append(copy.deepcopy(d["obstacle_taxonomy"][0])),
        lambda d: d["obstacle_taxonomy"][0]["leaves"].append(
            {"id": "visibility.smoke", "name": bi("Smoke")}  # leaf in the wrong family
        ),
        lambda d: d["phases"][0].update(id="lap.p05"),  # phase outside the procedure
        lambda d: d["phases"][0]["steps"][0].update(id="rarp.p06.s01"),  # step outside the phase
        lambda d: d["phases"][0]["steps"][0]["checkpoints"][0].update(id="rarp.p05.s02.c1"),
        lambda d: d["phases"][0]["steps"].append(copy.deepcopy(d["phases"][0]["steps"][0])),
        lambda d: d["phases"][0].update(order=0),
        lambda d: d["phases"][0].update(order="5"),
        lambda d: d["phases"][0].update(typical_duration_s={"p25": 9, "p50": 5, "p75": 10}),
        lambda d: d["phases"][0]["steps"][0].pop("checkpoints"),  # keys are required (D-034)
        lambda d: d.update(name={"ja": "", "en": "x"}),
    ],
)
def test_invalid_references(mutate):
    with pytest.raises(ValidationError):
        ProcedureReference.model_validate(changed(mutate))


def test_duplicate_step_order_is_rejected():
    def mutate(data):
        second = copy.deepcopy(data["phases"][0]["steps"][0])
        second["id"] = "rarp.p05.s02"
        second["checkpoints"] = []
        data["phases"][0]["steps"].append(second)

    with pytest.raises(ValidationError):
        ProcedureReference.model_validate(changed(mutate))
