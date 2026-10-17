"""#5 criterion 12a: an unstated cue or action in a draft (Team Lead decision (c) on issue #5,
logged as D-054).

12a (verbatim): "`DecisionRecordDraft` accepts `situation_cue.text: null` (with `cue_terms: []`)
and `action.text: null`. `DecisionRecord` still rejects both. `confirm_draft()` raises
`ValueError` while either is null. `ungrounded_fields()` doesn't list a null field."

D-054: "In `DecisionRecordDraft` only, `situation_cue.text` and `action.text` are
`Bilingual | None` (draft-only submodels); a null `situation_cue.text` has `cue_terms: []`;
`action.type`/`action.actor` stay required (`act` / `unknown` when not said). `DecisionRecord` is
unchanged (both required). ... `confirm_draft()` raises while either is null, so the app's Confirm
stays disabled until the surgeon fills it (a chip edit -> `grounding[]` with `source: edit`, the
other half via `/v1/translate`). G5 checks these two paths only when filled."

Supporting rules: D-052 (grounding paths resolve to an existing, non-null value), D-023/D-034
(v1.0 fields are required keys, nullable where they may be absent), D-024 (Bilingual, both halves
non-empty). Only synthetic fixtures; anything modified is a deep copy or lives in `tmp_path`.
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
    ungrounded_fields,
)

CUE = "situation_cue.text"
ACTION = "action.text"
WHICH = {"cue": (CUE,), "action": (ACTION,), "both": (CUE, ACTION)}
SEED_INDEX = 0  # fixture seed record for m01 (rescue): cue, obstacle, action, alternative, reason


@pytest.fixture
def record(docs) -> dict[str, Any]:
    """A fully grounded fixture seed record (a confirmed DecisionRecord)."""
    return copy.deepcopy(docs["seed_records.json"]["records"][SEED_INDEX])


def _draft(record: dict[str, Any]) -> dict[str, Any]:
    """The same content as a draft (plan §4.3: `id` and the confirmation fields are null)."""
    draft = copy.deepcopy(record)
    draft["id"] = None
    draft["provenance"]["confirmed_by"] = None
    draft["provenance"]["confirmed_at"] = None
    return draft


def _covers(grounding_field: str, path: str) -> bool:
    return grounding_field == path or grounding_field.startswith((path + ".", path + "["))


def _unstate(doc: dict[str, Any], *paths: str) -> dict[str, Any]:
    """Set `situation_cue.text` / `action.text` to null the way D-054 describes an unstated cue
    or action: a null cue has `cue_terms: []`; the action keeps `type`/`actor` (`act` /
    `unknown` when not said). Groundings on the nulled field are dropped (D-052: a grounding
    path must resolve to a non-null value)."""
    doc = copy.deepcopy(doc)
    for path in paths:
        if path == CUE:
            doc["situation_cue"] = {"text": None, "cue_terms": []}
        elif path == ACTION:
            doc["action"] = {"type": "act", "text": None, "actor": "unknown"}
        else:  # pragma: no cover - test helper misuse
            raise AssertionError(path)
        doc["grounding"] = [g for g in doc["grounding"] if not _covers(g["field"], path)]
    return doc


def _confirm(draft: DecisionRecordDraft) -> DecisionRecord:
    return confirm_draft(
        draft,
        record_id=str(uuid6.uuid7()),
        confirmed_by="dr-fixture",
        confirmed_at=datetime(2026, 10, 21, 9, 30, tzinfo=UTC),
    )


# --- 12a: the draft accepts an unstated cue or action ------------------------------------------


def test_12a_draft_accepts_null_situation_cue_text_with_empty_cue_terms(record):
    """12a: "`DecisionRecordDraft` accepts `situation_cue.text: null` (with `cue_terms: []`)"."""
    draft = DecisionRecordDraft.model_validate(_unstate(_draft(record), CUE))
    dumped = draft.model_dump(mode="json")
    assert dumped["situation_cue"] == {"text": None, "cue_terms": []}
    assert dumped["action"]["text"] is not None


@pytest.mark.parametrize(
    ("action_type", "actor"),
    [("act", "unknown"), ("act", "surgeon"), ("deliberate_non_action", "assistant")],
)
def test_12a_draft_accepts_null_action_text(record, action_type, actor):
    """12a: "`DecisionRecordDraft` accepts ... `action.text: null`" - with `type`/`actor` still
    set (D-054: "`act` / `unknown` when not said", or what the answer did say)."""
    doc = _unstate(_draft(record), ACTION)
    doc["action"]["type"], doc["action"]["actor"] = action_type, actor
    dumped = DecisionRecordDraft.model_validate(doc).model_dump(mode="json")
    assert dumped["action"] == {"type": action_type, "text": None, "actor": actor}
    assert dumped["situation_cue"]["text"] is not None


def test_12a_draft_accepts_both_null_at_once(record):
    """12a: both fields unstated in the same draft."""
    dumped = DecisionRecordDraft.model_validate(_unstate(_draft(record), CUE, ACTION)).model_dump(
        mode="json"
    )
    assert dumped["situation_cue"]["text"] is None
    assert dumped["action"]["text"] is None


@pytest.mark.parametrize("which", list(WHICH))
def test_12a_draft_with_null_text_round_trips_through_json(record, which):
    """12a + D-023/D-034 ("v1.0 fields are required keys, nullable where they may be absent"):
    the null is serialised as an explicit `"text": null` key and the JSON validates again."""
    draft = DecisionRecordDraft.model_validate(_unstate(_draft(record), *WHICH[which]))
    wire = json.loads(draft.model_dump_json())
    for path in WHICH[which]:
        parent = path.split(".")[0]
        assert "text" in wire[parent] and wire[parent]["text"] is None, wire[parent]
    assert DecisionRecordDraft.model_validate(wire).model_dump(mode="json") == draft.model_dump(
        mode="json"
    )


# --- 12a: the confirmed record still rejects them ----------------------------------------------


@pytest.mark.parametrize("which", list(WHICH))
def test_12a_decision_record_still_rejects_null_text(record, which):
    """12a: "`DecisionRecord` still rejects both" (D-054: "`DecisionRecord` is unchanged (both
    required)"). The record is otherwise valid: the groundings on the nulled field are gone."""
    unstated = _unstate(record, *WHICH[which])
    # Control: the same document with only the text filled back in is a valid record, so the
    # rejection below comes from the null text alone (not from `cue_terms: []` or `unknown`).
    refilled = copy.deepcopy(unstated)
    for path in WHICH[which]:
        refilled[path.split(".")[0]]["text"] = {"ja": "にじみ", "en": "Oozing"}
        refilled["grounding"].append({"field": path, "quote": "にじみ", "source": "answer"})
    DecisionRecord.model_validate(refilled)
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(unstated)


@pytest.mark.parametrize("which", ["cue", "action"])
def test_12a_validate_case_rejects_a_seed_record_with_null_text(
    data_dir, run_validate, record, which
):
    """12a: "`DecisionRecord` still rejects both" through `scrubgpt-validate case` (seed records
    are confirmed DecisionRecords, plan §4.2): exit 1 naming seed_records.json (AC15)."""
    seeds = data_dir.load("seed_records.json")
    seeds["records"][SEED_INDEX] = _unstate(record, *WHICH[which])
    data_dir.save("seed_records.json", seeds)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert "seed_records.json" in result.problems, result.output


# --- 12a: confirm_draft() ----------------------------------------------------------------------


@pytest.mark.parametrize("which", list(WHICH))
def test_12a_confirm_draft_raises_value_error_while_null(record, which):
    """12a: "`confirm_draft()` raises `ValueError` while either is null" (D-054: "the app's
    Confirm stays disabled until the surgeon fills it")."""
    draft = DecisionRecordDraft.model_validate(_unstate(_draft(record), *WHICH[which]))
    with pytest.raises(ValueError):
        _confirm(draft)


def test_12a_confirm_draft_control_both_filled_gives_a_decision_record(record):
    """12a control: with both fields filled, `confirm_draft()` returns a valid DecisionRecord
    with the id and confirmation filled (plan §4.3)."""
    confirmed = _confirm(DecisionRecordDraft.model_validate(_draft(record)))
    assert isinstance(confirmed, DecisionRecord)
    dumped = confirmed.model_dump(mode="json")
    assert dumped["id"] is not None
    assert dumped["provenance"]["confirmed_by"] == "dr-fixture"
    assert dumped["provenance"]["confirmed_at"] is not None
    assert dumped["situation_cue"] == record["situation_cue"]
    assert dumped["action"] == record["action"]
    DecisionRecord.model_validate(dumped)


@pytest.mark.parametrize("which", ["cue", "action"])
def test_12a_confirm_after_the_surgeon_fills_the_chip(record, which):
    """D-054 flow: the surgeon fills the missing field through a chip edit -> a `grounding[]`
    entry with `source: edit` (both halves present, the other from `/v1/translate`). The draft
    then confirms, and the record has no ungrounded field."""
    (path,) = WHICH[which]
    doc = _unstate(_draft(record), path)
    with pytest.raises(ValueError):
        _confirm(DecisionRecordDraft.model_validate(doc))
    parent = path.split(".")[0]
    doc[parent]["text"] = {"ja": "結紮部の近くからのにじみ", "en": "Oozing near the ligature"}
    if parent == "situation_cue":
        doc[parent]["cue_terms"] = ["にじみ", "oozing"]
    doc["grounding"].append({"field": path, "quote": "結紮部の近くからのにじみ", "source": "edit"})
    confirmed = _confirm(DecisionRecordDraft.model_validate(doc))
    assert ungrounded_fields(confirmed) == []
    DecisionRecord.model_validate(confirmed.model_dump(mode="json"))


# --- 12a: ungrounded_fields() --------------------------------------------------------------------


@pytest.mark.parametrize("which", list(WHICH))
def test_12a_ungrounded_fields_does_not_list_a_null_field(record, which):
    """12a: "`ungrounded_fields()` doesn't list a null field" (D-054: "G5 checks these two paths
    only when filled"). Everything else in the draft is grounded, so the list is empty."""
    assert ungrounded_fields(DecisionRecordDraft.model_validate(_draft(record))) == []  # control
    draft = DecisionRecordDraft.model_validate(_unstate(_draft(record), *WHICH[which]))
    listed = list(ungrounded_fields(draft))
    for path in WHICH[which]:
        assert path not in listed, listed
    assert listed == []


@pytest.mark.parametrize("path", [CUE, ACTION])
def test_12a_ungrounded_fields_still_lists_a_filled_field_without_a_quote(record, path):
    """D-054: "G5 checks these two paths only when filled" - in a draft, a filled cue or action
    with no covering grounding is still listed (D-052 G5 list)."""
    doc = _draft(record)
    doc["grounding"] = [g for g in doc["grounding"] if not _covers(g["field"], path)]
    assert path in list(ungrounded_fields(DecisionRecordDraft.model_validate(doc)))


# --- D-054 shape rules around 12a ---------------------------------------------------------------


@pytest.mark.parametrize("terms", [["にじみ"], ["oozing", "にじみ"]])
def test_d054_null_cue_text_has_empty_cue_terms(record, terms):
    """D-054: "a null `situation_cue.text` has `cue_terms: []`" - cue terms with no cue text
    are rejected (12a: "accepts `situation_cue.text: null` (with `cue_terms: []`)")."""
    doc = _unstate(_draft(record), CUE)
    doc["situation_cue"]["cue_terms"] = terms
    with pytest.raises(ValidationError):
        DecisionRecordDraft.model_validate(doc)


@pytest.mark.parametrize(
    ("field", "value"),
    [("type", None), ("actor", None), ("type", "unknown"), ("actor", "nobody")],
    ids=repr,
)
def test_d054_action_type_and_actor_stay_required_in_the_draft(record, field, value):
    """D-054: "`action.type`/`action.actor` stay required (`act` / `unknown` when not said)",
    also when `action.text` is null."""
    doc = _unstate(_draft(record), ACTION)
    doc["action"][field] = value
    with pytest.raises(ValidationError):
        DecisionRecordDraft.model_validate(doc)


@pytest.mark.parametrize("field", ["type", "actor"])
def test_d054_action_type_and_actor_keys_cannot_be_omitted(record, field):
    """D-054 + D-034: `type` and `actor` are required keys of the draft's action."""
    doc = _unstate(_draft(record), ACTION)
    del doc["action"][field]
    with pytest.raises(ValidationError):
        DecisionRecordDraft.model_validate(doc)


@pytest.mark.parametrize("parent", ["situation_cue", "action"])
def test_d054_only_the_text_is_nullable_not_the_object(record, parent):
    """D-054: only `situation_cue.text` and `action.text` become nullable; the `situation_cue` /
    `action` objects stay (an unstated cue is `{text: null, cue_terms: []}`)."""
    doc = _unstate(_draft(record), CUE, ACTION)
    doc[parent] = None
    with pytest.raises(ValidationError):
        DecisionRecordDraft.model_validate(doc)


@pytest.mark.parametrize("which", ["cue", "action"])
def test_d054_text_key_is_still_a_required_key_in_the_draft(record, which):
    """D-023/D-034: "v1.0 fields are required keys (nullable where they may be absent)" - the
    draft's `text` may be null but the key may not be left out."""
    (path,) = WHICH[which]
    doc = _unstate(_draft(record), path)
    del doc[path.split(".")[0]]["text"]
    with pytest.raises(ValidationError):
        DecisionRecordDraft.model_validate(doc)


@pytest.mark.parametrize("which", ["cue", "action"])
@pytest.mark.parametrize("source", ["answer", "edit", "narration"])
def test_d054_grounding_cannot_point_at_a_null_text(record, which, source):
    """D-052 ("grounding paths must resolve to an existing, non-null value ... enforced by
    `DecisionRecord` and `DecisionRecordDraft`") + D-054 ("never fill these fields from the
    moment title"): a draft that grounds a null cue/action text is rejected."""
    (path,) = WHICH[which]
    doc = _unstate(_draft(record), path)
    doc["grounding"].append({"field": path, "quote": "結紮部の近くから", "source": source})
    with pytest.raises(ValidationError):
        DecisionRecordDraft.model_validate(doc)


@pytest.mark.parametrize("which", ["cue", "action"])
@pytest.mark.parametrize(
    "value",
    [
        "plain English only",
        {"ja": "にじみ", "en": ""},
        {"ja": " ", "en": "Oozing"},
        {"ja": "にじみ"},
    ],
    ids=["plain-string", "empty-en", "blank-ja", "no-en"],
)
def test_d054_filled_text_in_the_draft_is_still_bilingual(record, which, value):
    """D-054: the draft fields are `Bilingual | None` - when filled, still a Bilingual with both
    halves non-empty (plan §4.1, D-024)."""
    (path,) = WHICH[which]
    doc = _draft(record)
    doc[path.split(".")[0]]["text"] = value
    with pytest.raises(ValidationError):
        DecisionRecordDraft.model_validate(doc)


# --- D-054: the regenerated contract schema ----------------------------------------------------


def _schema(paths, name: str) -> dict[str, Any]:
    return json.loads(
        (paths["repo"] / "contracts" / "schema" / f"{name}.schema.json").read_text("utf-8")
    )


def _resolve(root: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        ref = node["$ref"]
        assert ref.startswith("#/$defs/"), ref
        node = root["$defs"][ref.removeprefix("#/$defs/")]
    return node


def _allows_null(root: dict[str, Any], node: dict[str, Any]) -> bool:
    node = _resolve(root, node)
    if node.get("type") == "null" or (
        isinstance(node.get("type"), list) and "null" in node["type"]
    ):
        return True
    return any(_allows_null(root, alt) for alt in node.get("anyOf", []) + node.get("oneOf", []))


def _text_of(root: dict[str, Any], record_node: dict[str, Any], parent: str):
    record_node = _resolve(root, record_node)
    obj = _resolve(root, record_node["properties"][parent])
    return obj, obj["properties"]["text"]


@pytest.mark.parametrize("parent", ["situation_cue", "action"])
def test_d054_committed_schema_draft_nullable_record_not(paths, parent):
    """D-054 / #5 decision (c): "Dev1 changes `decision_record.py` and regenerates `schema/` and
    `ts/`". The committed JSON Schema says: in DecisionRecordDraft (and in the `draft` of
    ExtractResponse) `<parent>.text` is a required, nullable key; in DecisionRecord it is
    required and not nullable."""
    draft_schema = _schema(paths, "DecisionRecordDraft")
    obj, text = _text_of(draft_schema, draft_schema, parent)
    assert "text" in obj.get("required", []), obj
    assert _allows_null(draft_schema, text), text

    record_schema = _schema(paths, "DecisionRecord")
    obj, text = _text_of(record_schema, record_schema, parent)
    assert "text" in obj.get("required", []), obj
    assert not _allows_null(record_schema, text), text

    extract = _schema(paths, "ExtractResponse")
    obj, text = _text_of(extract, extract["properties"]["draft"], parent)
    assert "text" in obj.get("required", []), obj
    assert _allows_null(extract, text), text
