"""#7 AC3, AC4, AC5: which DecisionRecord fields need grounding (G5), what covers them, and which
grounding paths are valid (Team Lead answer on issue #7, logged as D-052; plan §4.1 field paths,
§4.3 `grounding[]`).

D-052: "G5 "filled fields": `context.patient_factors[i]`, `context.preop_plan`,
`situation_cue.text`, `obstacle`, `anticipation`, `action.text`, `alternatives[i].option`,
`alternatives[i].why_not`, `reason`, `immediate_result`, checked when non-null/non-empty; a
grounding covers a field when its path is the field, an ancestor or a descendant (never a
sibling). Not checked: `delayed_outcome`, `kind`, `action.type`, `action.actor`, `cue_terms`,
`new_terms`." - "Grounding paths must resolve to an existing, non-null value, never end at
`.ja`/`.en` inside a `Bilingual`, never point to an empty list (enforced by `DecisionRecord` and
`DecisionRecordDraft`)."

Errors are looked for in two places: `ungrounded_fields(record)` and `scrubgpt-validate case`
on a seed record (AC15, "an ungrounded filled field in a seed record").
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError
from scrubgpt_contracts.models.decision_record import (
    DecisionRecord,
    DecisionRecordDraft,
    ungrounded_fields,
)

SEED_INDEX = 2  # fixture seed record for m02 (anticipatory): the one with the most fields filled

G5_PATHS = [
    "context.patient_factors[0]",
    "context.patient_factors[1]",
    "context.preop_plan",
    "situation_cue.text",
    "obstacle",
    "anticipation",
    "action.text",
    "alternatives[0].option",
    "alternatives[0].why_not",
    "alternatives[1].option",
    "alternatives[1].why_not",
    "reason",
    "immediate_result",
]


def _bi(ja: str, en: str) -> dict[str, str]:
    return {"ja": ja, "en": en}


VERBATIM_QUOTE = "中葉がある"
"""Words that appear verbatim in the m02 record's `answer_text` evidence quote: since #9 AC7 (3e,
D-058) a `source: answer` grounding quote must be an exact substring of one of them."""


def _grounding(field: str) -> dict[str, str]:
    return {"field": field, "quote": VERBATIM_QUOTE, "source": "answer"}


@pytest.fixture
def full(docs) -> dict[str, Any]:
    """Seed record m02 with every G5 field filled (two patient factors, two alternatives,
    immediate_result) and exactly one grounding per G5 path - nothing else is grounded."""
    r = copy.deepcopy(docs["seed_records.json"]["records"][SEED_INDEX])
    r["context"]["patient_factors"] = [
        _bi("中葉あり", "Median lobe present"),
        _bi("BMI 32", "BMI 32"),
    ]
    r["context"]["preop_plan"] = _bi("中葉を確認する予定", "Planned to check the median lobe")
    r["anticipation"] = _bi("中葉を予想していた", "Expected a median lobe")
    r["reason"] = _bi("尿管口を守るため", "To protect the ureteral orifices")
    r["immediate_result"] = _bi("膀胱頸部を温存できた", "The bladder neck was preserved")
    r["alternatives"] = [
        {"option": _bi("後方から剥離", "Dissect from behind"), "why_not": _bi("出血", "Bleeding")},
        {"option": _bi("待つ", "Wait"), "why_not": _bi("時間がかかる", "Too slow")},
    ]
    assert r["obstacle"] is not None
    answers = [e["quote"] for e in r["evidence"] if e["kind"] == "answer_text"]
    assert any(VERBATIM_QUOTE in a for a in answers), answers
    r["grounding"] = [_grounding(f) for f in G5_PATHS]
    return r


def _draft(record: dict[str, Any]) -> dict[str, Any]:
    draft = copy.deepcopy(record)
    draft["id"] = None
    draft["provenance"]["confirmed_by"] = None
    draft["provenance"]["confirmed_at"] = None
    return draft


def _set_grounding(record: dict[str, Any], drop: str, add: list[str]) -> dict[str, Any]:
    doc = copy.deepcopy(record)
    doc["grounding"] = [g for g in doc["grounding"] if g["field"] != drop]
    doc["grounding"] += [_grounding(f) for f in add]
    return doc


def _ungrounded(doc: dict[str, Any]) -> list[str]:
    return list(ungrounded_fields(DecisionRecord.model_validate(doc)))


def _ungrounded_draft(doc: dict[str, Any]) -> list[str]:
    return list(ungrounded_fields(DecisionRecordDraft.model_validate(_draft(doc))))


def _run_case_with(data_dir, run_validate, doc: dict[str, Any]):
    seeds = data_dir.load("seed_records.json")
    seeds["records"][SEED_INDEX] = doc
    data_dir.save("seed_records.json", seeds)
    return run_validate("case", data_dir.case_dir)


def test_7ac3_fully_grounded_record_has_no_error(full, data_dir, run_validate):
    """#7 AC3 control: every G5 field covered by itself -> no error (function, draft, CLI)."""
    assert _ungrounded(full) == []
    assert _ungrounded_draft(full) == []
    result = _run_case_with(data_dir, run_validate, full)
    assert result.code == 0, result.output


# --- AC3: no covering grounding -> error naming the path ------------------------------------


@pytest.mark.parametrize("field", G5_PATHS)
def test_7ac3_filled_field_without_grounding_is_named(full, field):
    """#7 AC3: "For each field in the G5 list: filled with no covering grounding -> error naming
    the path" (`ungrounded_fields`, record and draft)."""
    doc = _set_grounding(full, drop=field, add=[])
    assert _ungrounded(doc) == [field]
    assert _ungrounded_draft(doc) == [field]


@pytest.mark.parametrize("field", G5_PATHS)
def test_7ac3_filled_field_without_grounding_fails_validate_case(
    full, field, data_dir, run_validate
):
    """#7 AC3 + AC15: the same ungrounded seed record makes `scrubgpt-validate case` exit 1 with
    an error naming seed_records.json and the field path."""
    doc = _set_grounding(full, drop=field, add=[])
    result = _run_case_with(data_dir, run_validate, doc)
    assert result.code == 1, result.output
    lines = [ln for ln in result.problems.splitlines() if field in ln]
    assert lines, f"{field!r} not named:\n{result.output}"
    assert "seed_records.json" in result.problems, result.output


# --- AC3: ancestor / descendant covers, sibling does not -------------------------------------

ANCESTORS = [
    ("context.patient_factors[0]", "context.patient_factors"),
    ("context.patient_factors[0]", "context"),
    ("context.patient_factors[1]", "context.patient_factors"),
    ("context.preop_plan", "context"),
    ("situation_cue.text", "situation_cue"),
    ("action.text", "action"),
    ("alternatives[0].option", "alternatives[0]"),
    ("alternatives[0].option", "alternatives"),
    ("alternatives[0].why_not", "alternatives[0]"),
    ("alternatives[1].why_not", "alternatives[1]"),
    ("alternatives[1].option", "alternatives"),
]

DESCENDANTS = [
    ("obstacle", "obstacle.family"),
    ("obstacle", "obstacle.type"),
    ("obstacle", "obstacle.cause"),
]

SIBLINGS = [
    ("context.patient_factors[0]", "context.patient_factors[1]"),
    ("context.patient_factors[1]", "context.patient_factors[0]"),
    ("context.patient_factors[0]", "context.preop_plan"),
    ("context.preop_plan", "context.patient_factors"),
    ("context.preop_plan", "context.patient_factors[0]"),
    ("situation_cue.text", "situation_cue.cue_terms"),
    ("obstacle", "situation_cue"),
    ("obstacle", "anticipation"),
    ("anticipation", "reason"),
    ("anticipation", "obstacle"),
    ("action.text", "action.type"),
    ("action.text", "action.actor"),
    ("alternatives[0].option", "alternatives[0].why_not"),
    ("alternatives[0].option", "alternatives[1]"),
    ("alternatives[0].why_not", "alternatives[0].option"),
    ("alternatives[0].why_not", "alternatives[1].why_not"),
    ("alternatives[1].option", "alternatives[0]"),
    ("reason", "immediate_result"),
    ("reason", "anticipation"),
    ("immediate_result", "reason"),
]


@pytest.mark.parametrize(("field", "cover"), ANCESTORS + DESCENDANTS, ids=repr)
def test_7ac3_covered_by_ancestor_or_descendant_is_no_error(
    full, field, cover, data_dir, run_validate
):
    """#7 AC3: "Covered by itself, an ancestor or a descendant -> no error" (#7 point 2:
    "`alternatives[0]` covers `alternatives[0].option`; `obstacle.type` covers `obstacle`")."""
    doc = _set_grounding(full, drop=field, add=[cover])
    DecisionRecord.model_validate(doc)  # the cover is itself a valid grounding path (AC5)
    assert _ungrounded(doc) == []
    assert _ungrounded_draft(doc) == []
    result = _run_case_with(data_dir, run_validate, doc)
    assert result.code == 0, result.output


@pytest.mark.parametrize(("field", "sibling"), SIBLINGS, ids=repr)
def test_7ac3_covered_only_by_a_sibling_is_an_error(full, field, sibling, data_dir, run_validate):
    """#7 AC3: "Covered only by a sibling -> error" (#7 point 2: "A sibling never covers it:
    `alternatives[0].why_not` does not cover `alternatives[0].option`")."""
    doc = _set_grounding(full, drop=field, add=[sibling])
    DecisionRecord.model_validate(doc)  # the sibling is a valid grounding path (AC5)
    assert field in _ungrounded(doc)
    assert field in _ungrounded_draft(doc)
    result = _run_case_with(data_dir, run_validate, doc)
    assert result.code == 1, result.output
    assert any(field in ln for ln in result.problems.splitlines()), result.output


def test_7ac3_index_prefix_is_not_an_ancestor(full):
    """#7 AC3 (field paths are `a.b[0].c`, plan §4.1): `alternatives[1]` is a sibling of
    `alternatives[11]`, not its ancestor, and `context.patient_factors[1]` does not cover
    `context.patient_factors[10]` - the paths only share a text prefix."""
    doc = copy.deepcopy(full)
    doc["alternatives"] = [
        {"option": _bi(f"選択肢{i}", f"Option {i}"), "why_not": _bi(f"理由{i}", f"Reason {i}")}
        for i in range(12)
    ]
    doc["context"]["patient_factors"] = [_bi(f"因子{i}", f"Factor {i}") for i in range(11)]
    keep = [
        g
        for g in doc["grounding"]
        if not g["field"].startswith(("alternatives", "context.patient_factors"))
    ]
    doc["grounding"] = keep + [_grounding(f"alternatives[{i}]") for i in range(11)]
    doc["grounding"] += [_grounding(f"context.patient_factors[{i}]") for i in range(10)]
    assert sorted(_ungrounded(doc)) == sorted(
        ["alternatives[11].option", "alternatives[11].why_not", "context.patient_factors[10]"]
    )


# --- only filled fields are checked ----------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "empty"),
    [
        (("context", "patient_factors"), []),
        (("context", "preop_plan"), None),
        (("obstacle",), None),
        (("anticipation",), None),
        (("alternatives",), []),
        (("reason",), None),
        (("immediate_result",), None),
    ],
    ids=repr,
)
def test_7ac3_null_or_empty_fields_need_no_grounding(full, path, empty, data_dir, run_validate):
    """#7 point 2: "A field is checked only when it is non-null or non-empty": a null or empty
    G5 field with no grounding is no error."""
    doc = copy.deepcopy(full)
    node = doc
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = empty
    text = ".".join(path)
    doc["grounding"] = [
        g for g in doc["grounding"] if not (g["field"] == text or g["field"].startswith(text))
    ]
    assert _ungrounded(doc) == []
    result = _run_case_with(data_dir, run_validate, doc)
    assert result.code == 0, result.output


def test_7ac3_alternative_with_null_why_not_needs_no_grounding_for_it(full):
    """#7 point 2: `alternatives[i].why_not` is checked only when non-null."""
    doc = copy.deepcopy(full)
    doc["alternatives"][1]["why_not"] = None
    doc["grounding"] = [g for g in doc["grounding"] if g["field"] != "alternatives[1].why_not"]
    assert _ungrounded(doc) == []


# --- AC4: fields that are never checked --------------------------------------------------------


@pytest.fixture
def with_unchecked_filled(full) -> dict[str, Any]:
    """`full` with every unchecked field filled: delayed_outcome known with text and source,
    cue_terms and new_terms non-empty; no grounding names them or one of their ancestors."""
    doc = copy.deepcopy(full)
    doc["delayed_outcome"] = {
        "status": "known",
        "text": _bi("術後3か月で尿禁制が戻った", "Continence returned at 3 months"),
        "source": "follow-up clinic note",
    }
    doc["situation_cue"]["cue_terms"] = ["中葉", "median lobe"]
    doc["new_terms"] = [{"term": "中葉", "lang": "ja"}]
    doc["action"]["type"] = "deliberate_non_action"
    doc["action"]["actor"] = "assistant"
    doc["kind"] = "anticipatory"
    fields = {g["field"] for g in doc["grounding"]}
    covering = {"delayed_outcome", "situation_cue", "action", "kind", "new_terms"}
    covering |= {"situation_cue.cue_terms", "action.type", "action.actor"}
    assert not fields & covering
    assert not [f for f in fields if f.startswith(("delayed_outcome", "new_terms", "kind"))]
    assert not [f for f in fields if f.startswith(("situation_cue.cue", "action.type"))]
    assert not [f for f in fields if f.startswith("action.actor")]
    return doc


@pytest.mark.parametrize(
    "unchecked",
    [
        "delayed_outcome.text",
        "kind",
        "action.type",
        "action.actor",
        "situation_cue.cue_terms",
        "new_terms",
    ],
)
def test_7ac4_unchecked_fields_need_no_grounding(with_unchecked_filled, unchecked):
    """#7 AC4: "Ungrounded `delayed_outcome.text`, `kind`, `action.type`, `action.actor`,
    `cue_terms` or `new_terms` -> no G5 error"."""
    found = _ungrounded(with_unchecked_filled) + _ungrounded_draft(with_unchecked_filled)
    assert not [f for f in found if f.startswith(unchecked) or f.startswith("delayed_outcome")]
    assert found == []


def test_7ac4_unchecked_fields_pass_validate_case(with_unchecked_filled, data_dir, run_validate):
    """#7 AC4 through `scrubgpt-validate case`: exit 0."""
    result = _run_case_with(data_dir, run_validate, with_unchecked_filled)
    assert result.code == 0, result.output


# --- AC5: what a grounding path may point to --------------------------------------------------

MODELS = [
    pytest.param(DecisionRecord, id="DecisionRecord"),
    pytest.param(DecisionRecordDraft, id="DecisionRecordDraft"),
]


def _as(model, doc: dict[str, Any]) -> dict[str, Any]:
    return _draft(doc) if model is DecisionRecordDraft else copy.deepcopy(doc)


def _with_extra_grounding(doc: dict[str, Any], field: str) -> dict[str, Any]:
    doc = copy.deepcopy(doc)
    doc["grounding"].append(_grounding(field))
    return doc


BILINGUAL_HALVES = [
    "situation_cue.text.ja",
    "situation_cue.text.en",
    "action.text.en",
    "reason.ja",
    "immediate_result.en",
    "anticipation.ja",
    "context.preop_plan.en",
    "context.patient_factors[0].ja",
    "context.patient_factors[1].en",
    "alternatives[0].option.en",
    "alternatives[1].why_not.ja",
    "delayed_outcome.text.en",
]


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("field", BILINGUAL_HALVES)
def test_7ac5_path_ending_in_ja_or_en_is_rejected(with_unchecked_filled, model, field):
    """#7 AC5: "A grounding path ending in `.ja` or `.en` ... -> `DecisionRecord` and
    `DecisionRecordDraft` validation fails" (the half exists and is non-null)."""
    doc = _as(model, with_unchecked_filled)
    model.model_validate(doc)
    with pytest.raises(ValidationError):
        model.model_validate(_with_extra_grounding(doc, field))


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize(
    "path", ["context.patient_factors", "alternatives", "situation_cue.cue_terms", "new_terms"]
)
def test_7ac5_path_to_an_empty_list_is_rejected(full, model, path):
    """#7 AC5: "... pointing to an empty list ... -> validation fails"."""
    doc = _as(model, full)
    node = doc
    parts = path.split(".")
    for step in parts[:-1]:
        node = node[step]
    node[parts[-1]] = []
    doc["grounding"] = [g for g in doc["grounding"] if not g["field"].startswith(path)]
    model.model_validate(doc)
    with pytest.raises(ValidationError):
        model.model_validate(_with_extra_grounding(doc, path))


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize(
    "field",
    [
        "alternatives[2]",
        "alternatives[2].option",
        "context.patient_factors[5]",
        "situation_cue.cue_terms[9]",
        "obstacle.nonexistent",
        "action.reason",
        "nonexistent",
        "reason.de",
    ],
)
def test_7ac5_path_to_a_missing_value_is_rejected(full, model, field):
    """#7 AC5: "... pointing to a missing path ... -> validation fails"."""
    doc = _as(model, full)
    with pytest.raises(ValidationError):
        model.model_validate(_with_extra_grounding(doc, field))


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize(
    ("set_null", "field"),
    [
        (("anticipation",), "anticipation"),
        (("obstacle",), "obstacle"),
        (("obstacle",), "obstacle.type"),
        (("obstacle", "type"), "obstacle.type"),
        (("context", "preop_plan"), "context.preop_plan"),
        (("alternatives", 0, "why_not"), "alternatives[0].why_not"),
        (("reason",), "reason"),
        (("immediate_result",), "immediate_result"),
        (("moment_id",), "moment_id"),
        (None, "delayed_outcome.text"),
        (None, "delayed_outcome.source"),
    ],
    ids=repr,
)
def test_7ac5_path_to_a_null_value_is_rejected(full, model, set_null, field):
    """#7 AC5: "... pointing to a null value -> validation fails" (`delayed_outcome.text` and
    `.source` are null in the fixture record)."""
    doc = _as(model, full)
    if set_null is not None:
        node = doc
        for step in set_null[:-1]:
            node = node[step]
        node[set_null[-1]] = None
        text = field.split(".")[0] if set_null == ("obstacle",) else field
        doc["grounding"] = [g for g in doc["grounding"] if not g["field"].startswith(text)]
        model.model_validate(doc)
    with pytest.raises(ValidationError):
        model.model_validate(_with_extra_grounding(doc, field))


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize(
    "field",
    [
        "obstacle",
        "alternatives[0]",
        "alternatives[1]",
        "alternatives",
        "context",
        "context.patient_factors",
        "context.patient_factors[1]",
        "situation_cue",
        "situation_cue.cue_terms",
        "action",
        "obstacle.type",
        "obstacle.family",
        "delayed_outcome",
        "reason",
        "alternatives[1].why_not",
    ],
)
def test_7ac5_paths_to_whole_fields_objects_and_items_are_valid(
    with_unchecked_filled, model, field
):
    """#7 AC5: "`obstacle` and `alternatives[0]` are valid paths" (#7 point 3: "Paths to whole
    objects or list items stay valid"; also non-empty lists and whole Bilingual fields)."""
    model.model_validate(_with_extra_grounding(_as(model, with_unchecked_filled), field))
