"""AC2-AC4: tolerant readers, required keys and `contract_version` (plan §4.1, D-023, D-034, #3)."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError
from scrubgpt_contracts.models import case_package, common, decision_record, reference
from scrubgpt_contracts.models.case_package import (
    Case,
    Metrics,
    Moments,
    Questions,
    SeedRecords,
    Timeline,
)
from scrubgpt_contracts.models.common import ApiError
from scrubgpt_contracts.models.decision_record import DecisionRecord, DecisionRecordDraft
from scrubgpt_contracts.models.reference import ProcedureReference

MODULES = (common, case_package, decision_record, reference)


def _all_models() -> list[type[BaseModel]]:
    found = []
    for module in MODULES:
        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseModel)
                and obj.__module__ == module.__name__
            ):
                found.append(obj)
    return found


ALL_MODELS = _all_models()


def _draft_from(record: dict[str, Any]) -> dict[str, Any]:
    draft = copy.deepcopy(record)
    draft["id"] = None
    draft["provenance"]["confirmed_by"] = None
    draft["provenance"]["confirmed_at"] = None
    return draft


def _top_level_docs(docs, metrics_doc, api_error_doc) -> list[tuple[str, type[BaseModel], Any]]:
    record = docs["seed_records.json"]["records"][0]
    return [
        ("case.json", Case, docs["case.json"]),
        ("timeline.json", Timeline, docs["timeline.json"]),
        ("moments.json", Moments, docs["moments.json"]),
        ("questions.json", Questions, docs["questions.json"]),
        ("seed_records.json", SeedRecords, docs["seed_records.json"]),
        ("metrics.json", Metrics, metrics_doc),
        ("rarp.json", ProcedureReference, docs["rarp.json"]),
        ("ApiError", ApiError, api_error_doc),
        ("DecisionRecord", DecisionRecord, record),
        ("DecisionRecordDraft", DecisionRecordDraft, _draft_from(record)),
    ]


def _sprinkle_unknown(node: Any) -> None:
    if isinstance(node, dict):
        for value in list(node.values()):
            _sprinkle_unknown(value)
        node["zz_future_field"] = {"anything": [1, 2, 3]}
    elif isinstance(node, list):
        for item in node:
            _sprinkle_unknown(item)


def _contains_key(node: Any, key: str) -> bool:
    if isinstance(node, dict):
        return key in node or any(_contains_key(v, key) for v in node.values())
    if isinstance(node, list):
        return any(_contains_key(v, key) for v in node)
    return False


# --- AC2 ---------------------------------------------------------------------------------


def test_ac2_every_contract_model_is_configured_extra_ignore():
    """AC2: "Tolerant readers: every contract model ignores unknown fields (D-023)."
    (plan §4.1: Pydantic `extra="ignore"`)"""
    assert ALL_MODELS, "no contract models found"
    wrong = [m.__name__ for m in ALL_MODELS if m.model_config.get("extra") != "ignore"]
    assert not wrong, f"models without extra='ignore': {wrong}"


def test_ac2_unknown_fields_everywhere_are_accepted_and_dropped(docs, metrics_doc, api_error_doc):
    """AC2: an unknown key at every level of every contract document is accepted and ignored
    (D-023: "an older reader therefore still accepts a newer MINOR version")."""
    for name, model, doc in _top_level_docs(docs, metrics_doc, api_error_doc):
        doc = copy.deepcopy(doc)
        _sprinkle_unknown(doc)
        parsed = model.model_validate(doc)
        dumped = parsed.model_dump(mode="json")
        assert not _contains_key(dumped, "zz_future_field"), name


# --- AC3 ---------------------------------------------------------------------------------


def test_ac3_no_v1_field_has_a_default():
    """AC3: "v1.0 fields are required keys ... no v1.0 field has a default" (D-034, plan §4.1)."""
    with_default = [
        f"{m.__name__}.{name}"
        for m in ALL_MODELS
        for name, info in m.model_fields.items()
        if not info.is_required()
    ]
    assert not with_default, f"fields with a default: {with_default}"


def _schema_objects(node: Any, where: str = "#"):
    if isinstance(node, dict):
        if "properties" in node:
            yield where, node
        for key, value in node.items():
            yield from _schema_objects(value, f"{where}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _schema_objects(value, f"{where}/{i}")


@pytest.mark.parametrize(
    "model",
    [
        Case,
        Timeline,
        Moments,
        Questions,
        SeedRecords,
        Metrics,
        ProcedureReference,
        DecisionRecord,
        DecisionRecordDraft,
        ApiError,
        common.Bilingual,
        common.Provenance,
    ],
    ids=lambda m: m.__name__,
)
def test_ac3_serialization_schema_lists_every_field_as_required(model):
    """AC3: "the JSON Schema (mode="serialization") lists every field as required" (plan §4.1
    Code generation, D-034)."""
    schema = model.model_json_schema(mode="serialization")
    problems = []
    for where, obj in _schema_objects(schema):
        missing = set(obj["properties"]) - set(obj.get("required", []))
        if missing:
            problems.append(f"{where}: not required {sorted(missing)}")
    assert not problems, "\n".join(problems)


def _drop(doc: Any, path: tuple) -> Any:
    doc = copy.deepcopy(doc)
    node = doc
    for step in path[:-1]:
        node = node[step]
    assert path[-1] in node, f"fixture has no {path}"
    del node[path[-1]]
    return doc


OMITTED_KEYS = [
    ("case.json", ("source_url",)),
    ("moments.json", ("moments", 0, "deep_look")),
    ("moments.json", ("moments", 0, "checkpoint_id")),
    ("moments.json", ("moments", 0, "draft_obstacle")),
    ("moments.json", ("moments", 0, "why_flagged")),
    ("questions.json", ("operating", 0, "quote")),
    ("questions.json", ("operating", 0, "ai_draft")),
    ("questions.json", ("operating", 0, "tap_options")),
    ("timeline.json", ("instruments",)),
    ("timeline.json", ("utterances", 0, "speaker")),
    ("timeline.json", ("steps", 0, "provenance", "generated_by")),
    ("timeline.json", ("steps", 0, "provenance", "confirmed_by")),
    ("timeline.json", ("steps", 0, "provenance", "confirmed_at")),
    ("timeline.json", ("steps", 0, "provenance", "generated_by", "prompt_version")),
    ("seed_records.json", ("records", 0, "moment_id")),
    ("seed_records.json", ("records", 0, "anticipation")),
    ("seed_records.json", ("records", 0, "reason")),
    ("seed_records.json", ("records", 0, "obstacle")),
    ("seed_records.json", ("records", 0, "obstacle", "type")),
    ("seed_records.json", ("records", 0, "context", "preop_plan")),
    ("seed_records.json", ("records", 0, "delayed_outcome", "text")),
    ("seed_records.json", ("records", 0, "delayed_outcome", "source")),
    ("seed_records.json", ("records", 0, "alternatives", 0, "why_not")),
    ("seed_records.json", ("records", 0, "new_terms")),
]

FILE_MODELS = {
    "case.json": Case,
    "timeline.json": Timeline,
    "moments.json": Moments,
    "questions.json": Questions,
    "seed_records.json": SeedRecords,
}


@pytest.mark.parametrize(
    ("name", "path"), OMITTED_KEYS, ids=[f"{n}:{'.'.join(map(str, p))}" for n, p in OMITTED_KEYS]
)
def test_ac3_omitting_a_nullable_or_list_key_is_rejected(docs, name, path):
    """AC3: "v1.0 fields are required keys. Omitting a nullable key is rejected" (D-034:
    "a value that may be absent is nullable (`T | None`, sent as `null`)")."""
    model = FILE_MODELS[name]
    model.model_validate(docs[name])  # control: the fixture itself is valid
    with pytest.raises(ValidationError):
        model.model_validate(_drop(docs[name], path))


# --- AC4 ---------------------------------------------------------------------------------


def test_ac4_contract_version_constant():
    """AC4 / #3 point 3: an exported `CONTRACT_VERSION = "1.0"` for producers."""
    assert common.CONTRACT_VERSION == "1.0"


@pytest.mark.parametrize("version", ["1.0", "1.1", "1.9", "1.10", "1.123"])
def test_ac4_any_1x_contract_version_is_accepted(docs, metrics_doc, api_error_doc, version):
    """AC4: "`contract_version` is "MAJOR.MINOR": any 1.x is accepted" (#3 point 3, D-023
    tolerant reader)."""
    for name, model, doc in _top_level_docs(docs, metrics_doc, api_error_doc):
        doc = copy.deepcopy(doc)
        doc["contract_version"] = version
        parsed = model.model_validate(doc)
        assert parsed.model_dump(mode="json")["contract_version"] == version, name


@pytest.mark.parametrize(
    "version",
    [
        "1.01",
        "1.00",
        "2.0",
        "0.9",
        "1",
        "1.",
        ".1",
        "1.0.0",
        "v1.0",
        " 1.0",
        "1.0 ",
        "1.0\n",
        "",
        "1.a",
        1.0,
        1,
        None,
    ],
    ids=repr,
)
def test_ac4_other_majors_and_malformed_versions_are_rejected(
    docs, metrics_doc, api_error_doc, version
):
    """AC4: "other majors and malformed values are rejected" and "no leading zeros in MINOR"
    (#3 point 3: `^1\\.(0|[1-9][0-9]*)$`)."""
    accepted = []
    for name, model, doc in _top_level_docs(docs, metrics_doc, api_error_doc):
        doc = copy.deepcopy(doc)
        doc["contract_version"] = version
        try:
            model.model_validate(doc)
        except ValidationError:
            continue
        accepted.append(name)
    assert not accepted, f"contract_version {version!r} accepted by {accepted}"


def test_ac4_missing_contract_version_is_rejected(docs, metrics_doc, api_error_doc):
    """AC4 + plan §4.1: "every contract file and every API response carries
    contract_version" (required, no default, #3 point 3)."""
    accepted = []
    for name, model, doc in _top_level_docs(docs, metrics_doc, api_error_doc):
        doc = copy.deepcopy(doc)
        del doc["contract_version"]
        try:
            model.model_validate(doc)
        except ValidationError:
            continue
        accepted.append(name)
    assert not accepted, f"missing contract_version accepted by {accepted}"
