"""AC12: the ProcedureReference model (plan §4.2b, D-035, #4 point 10)."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError
from scrubgpt_contracts.models.reference import ProcedureReference

FAMILIES = [
    "bleeding",
    "anatomical_variation",
    "tissue_condition",
    "visibility",
    "technical_difficulty",
    "equipment",
    "patient_condition",
    "unexpected_finding",
]


@pytest.fixture
def ref(docs) -> dict[str, Any]:
    return copy.deepcopy(docs["rarp.json"])


def _with(doc: Any, path: tuple, value: Any) -> Any:
    doc = copy.deepcopy(doc)
    node = doc
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    return doc


def _first_step_with_checkpoint(ref) -> tuple[int, int]:
    for p, phase in enumerate(ref["phases"]):
        for s, step in enumerate(phase["steps"]):
            if step["checkpoints"]:
                return p, s
    raise AssertionError("fixture reference has no checkpoint")


def test_ac12_shape(ref):
    """AC12 / §4.2b + #4 point 10: `{contract_version, id, name, phases[], obstacle_taxonomy[]}`;
    phases `{id, name, order, typical_duration_s {p25,p50,p75}, steps[]}`; steps `{id, name,
    order, typical_duration_s, checkpoints[] {id, text}}`; families `{id, name, leaves[] {id,
    name}}`."""
    dumped = ProcedureReference.model_validate(ref).model_dump(mode="json")
    assert set(dumped) == {"contract_version", "id", "name", "phases", "obstacle_taxonomy"}
    phase = dumped["phases"][0]
    assert set(phase) == {"id", "name", "order", "typical_duration_s", "steps"}
    assert set(phase["typical_duration_s"]) == {"p25", "p50", "p75"}
    assert set(phase["steps"][0]) == {"id", "name", "order", "typical_duration_s", "checkpoints"}
    p, s = _first_step_with_checkpoint(dumped)
    assert set(dumped["phases"][p]["steps"][s]["checkpoints"][0]) == {"id", "text"}
    family = dumped["obstacle_taxonomy"][0]
    assert set(family) == {"id", "name", "leaves"}
    assert set(family["leaves"][0]) == {"id", "name"}


def test_ac12_exactly_the_eight_families_missing_one_rejected(ref):
    """AC12: "exactly the 8 families" (D-035; #4 point 10) - a missing family is rejected."""
    for i in range(len(ref["obstacle_taxonomy"])):
        doc = copy.deepcopy(ref)
        del doc["obstacle_taxonomy"][i]
        with pytest.raises(ValidationError):
            ProcedureReference.model_validate(doc)


def test_ac12_duplicate_or_unknown_family_rejected(ref):
    """AC12: each of the 8 families exactly once; an unknown family id is rejected."""
    doc = copy.deepcopy(ref)
    doc["obstacle_taxonomy"].append(copy.deepcopy(doc["obstacle_taxonomy"][0]))
    with pytest.raises(ValidationError):
        ProcedureReference.model_validate(doc)
    doc = copy.deepcopy(ref)
    extra = copy.deepcopy(doc["obstacle_taxonomy"][0])
    extra["id"] = "surgeon_error"
    extra["leaves"] = []
    doc["obstacle_taxonomy"].append(extra)
    with pytest.raises(ValidationError):
        ProcedureReference.model_validate(doc)


def test_ac12_family_may_have_no_leaves(ref):
    """#4 point 10 (Team Lead): "Leaves may be empty"."""
    ProcedureReference.model_validate(_with(ref, ("obstacle_taxonomy", 0, "leaves"), []))


def test_ac12_ids_nested_by_prefix(ref):
    """AC12: "ids nested by prefix": phase ids start with `<id>.`, step ids with their phase id,
    checkpoint ids with their step id, leaf ids with their family id (#4 point 10)."""
    p, s = _first_step_with_checkpoint(ref)
    other_phase = "rarp.p02" if ref["phases"][0]["id"] != "rarp.p02" else "rarp.p03"
    bad = [
        (("id",), "lap"),  # phases no longer start with <id>.
        (("phases", 0, "id"), "other.p01"),
        (("phases", 0, "steps", 0, "id"), f"{other_phase}.s07"),
        (("phases", p, "steps", s, "checkpoints", 0, "id"), "rarp.p99.s99.c1"),
    ]
    family = next(f for f in ref["obstacle_taxonomy"] if f["id"] == "bleeding")
    fi = ref["obstacle_taxonomy"].index(family)
    bad.append((("obstacle_taxonomy", fi, "leaves", 0, "id"), "visibility.smoke_x"))
    for path, value in bad:
        with pytest.raises(ValidationError):
            ProcedureReference.model_validate(_with(ref, path, value))


def test_ac12_ids_unique(ref):
    """#4 point 10: "Ids are unique across the whole file"."""
    dup_phase = copy.deepcopy(ref)
    dup_phase["phases"][1]["id"] = dup_phase["phases"][0]["id"]
    dup_step = copy.deepcopy(ref)
    phase = next(p for p in dup_step["phases"] if len(p["steps"]) >= 2)
    phase["steps"][1]["id"] = phase["steps"][0]["id"]
    dup_leaf = copy.deepcopy(ref)
    fam = next(f for f in dup_leaf["obstacle_taxonomy"] if len(f["leaves"]) >= 2)
    fam["leaves"][1]["id"] = fam["leaves"][0]["id"]
    for doc in (dup_phase, dup_step, dup_leaf):
        with pytest.raises(ValidationError):
            ProcedureReference.model_validate(doc)


def test_ac12_order_unique_within_its_list(ref):
    """#4 point 10: "`order` unique within its list"."""
    doc = _with(ref, ("phases", 1, "order"), ref["phases"][0]["order"])
    with pytest.raises(ValidationError):
        ProcedureReference.model_validate(doc)
    doc = copy.deepcopy(ref)
    phase = next(p for p in doc["phases"] if len(p["steps"]) >= 2)
    phase["steps"][1]["order"] = phase["steps"][0]["order"]
    with pytest.raises(ValidationError):
        ProcedureReference.model_validate(doc)


@pytest.mark.parametrize(
    "durations",
    [
        {"p25": 500.0, "p50": 400.0, "p75": 900.0},
        {"p25": 100.0, "p50": 950.0, "p75": 900.0},
        {"p25": 100.0, "p50": 50.0, "p75": 10.0},
        {"p25": -1.0, "p50": 50.0, "p75": 100.0},
        {"p25": 100.0, "p50": 200.0},
    ],
    ids=str,
)
def test_ac12_typical_durations_ordered(ref, durations):
    """AC12: "p25 <= p50 <= p75" for phases and steps (§4.2b, #4 point 10)."""
    with pytest.raises(ValidationError):
        ProcedureReference.model_validate(
            _with(ref, ("phases", 0, "typical_duration_s"), durations)
        )
    with pytest.raises(ValidationError):
        ProcedureReference.model_validate(
            _with(ref, ("phases", 0, "steps", 0, "typical_duration_s"), durations)
        )


def test_ac12_typical_durations_equal_quartiles_allowed(ref):
    """AC12: equal quartiles satisfy p25 <= p50 <= p75."""
    flat = {"p25": 300.0, "p50": 300.0, "p75": 300.0}
    ProcedureReference.model_validate(_with(ref, ("phases", 0, "typical_duration_s"), flat))


def test_ac12_names_are_bilingual(ref):
    """§4.2b: phase, step, checkpoint, family and leaf names are Bilingual."""
    p, s = _first_step_with_checkpoint(ref)
    for path in (
        ("name",),
        ("phases", 0, "name"),
        ("phases", 0, "steps", 0, "name"),
        ("phases", p, "steps", s, "checkpoints", 0, "text"),
        ("obstacle_taxonomy", 0, "name"),
        ("obstacle_taxonomy", 0, "leaves", 0, "name"),
    ):
        with pytest.raises(ValidationError):
            ProcedureReference.model_validate(_with(ref, path, "English only"))
        with pytest.raises(ValidationError):
            ProcedureReference.model_validate(_with(ref, path, {"ja": "名", "en": ""}))
