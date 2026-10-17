"""Issue #10: `question_id` on Decision Records (Team Lead answer, rules 1-4 and 6; Dev1's
ACCEPT analysis with the fixture values; logged as D-059). Also D-064 rule 3 (`question_id` is
metadata, never grounded) and D-023/D-034 (v1.0 fields are required keys, nullable where they
may be absent).

D-059: "`DecisionRecord` and `DecisionRecordDraft` carry `question_id: QuestionId | None`, a v1.0
required key ... non-null => `moment_id` is set and `question_id` starts with `moment_id + "."`;
an `operating_surgeon` record answers a `.qN` question, a `reviewer` record a `.rN` one, any
other label either; `null` for narration-mined or moment-less records; `validate case` errors
when a seed record's `question_id` isn't in `questions.json`."
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import uuid6
from pydantic import ValidationError
from scrubgpt_contracts.models.decision_record import (
    DecisionRecord,
    DecisionRecordDraft,
    confirm_draft,
)

CASE = "case-fixture-01"
M01 = f"{CASE}.m01"

MODELS = [
    pytest.param(DecisionRecord, id="DecisionRecord"),
    pytest.param(DecisionRecordDraft, id="DecisionRecordDraft"),
]

# A role each trust label can be attributed to without tripping other provenance rules
# (role-play, `dev_team_simulated`, is always `simulated`).
ROLE_FOR_LABEL = {
    "ai_detected": "ai",
    "dataset_annotation": "dataset",
    "narration_extracted": "narrator",
    "operating_surgeon": "operating_surgeon",
    "reviewer": "reviewer",
    "expert_validated": "expert",
    "simulated": "dev_team_simulated",
}


@pytest.fixture
def record(docs) -> dict[str, Any]:
    """Seed record 0 of the fixture: moment m01, answered in Japanese, `simulated`."""
    return copy.deepcopy(docs["seed_records.json"]["records"][0])


def _draft(record: dict[str, Any]) -> dict[str, Any]:
    draft = copy.deepcopy(record)
    draft["id"] = None
    draft["provenance"]["confirmed_by"] = None
    draft["provenance"]["confirmed_at"] = None
    return draft


def _as(model, doc: dict[str, Any]) -> dict[str, Any]:
    return _draft(doc) if model is DecisionRecordDraft else copy.deepcopy(doc)


def _set(doc: dict[str, Any], **fields: Any) -> dict[str, Any]:
    doc = copy.deepcopy(doc)
    doc.update(fields)
    return doc


def _labelled(doc: dict[str, Any], label: str) -> dict[str, Any]:
    doc = copy.deepcopy(doc)
    doc["provenance"]["trust_label"] = label
    doc["provenance"]["attributed_to"] = ROLE_FOR_LABEL[label]
    return doc


# --- Rule 1: a required key that may be null; only question ids ---------------------------------


@pytest.mark.parametrize("model", MODELS)
def test_10r1_question_id_key_is_present_in_the_dump(model, record):
    """#10 rule 1: "`question_id` is a required key" (D-059: "`DecisionRecord` and
    `DecisionRecordDraft` carry `question_id: QuestionId | None`")."""
    dumped = model.model_validate(_as(model, record)).model_dump(mode="json")
    assert "question_id" in dumped
    assert dumped["question_id"] == f"{M01}.q1"


@pytest.mark.parametrize("model", MODELS)
def test_10r1_missing_question_id_key_is_rejected(model, record):
    """#10 rule 1 + D-034: "v1.0 fields are required keys (nullable where they may be absent)";
    a record or draft without the `question_id` key fails."""
    doc = _as(model, record)
    del doc["question_id"]
    with pytest.raises(ValidationError):
        model.model_validate(doc)


@pytest.mark.parametrize("model", MODELS)
def test_10r1_null_question_id_is_accepted(model, record):
    """#10 rule 1: "It may be `null` (narration-mined records, or records with no moment)"; a
    record with a moment and a null `question_id` is valid too (nothing requires the reverse)."""
    model.model_validate(_set(_as(model, record), question_id=None))
    model.model_validate(_set(_as(model, record), question_id=None, moment_id=None))


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize(
    "value", [f"{M01}.q1", f"{M01}.q2", f"{M01}.r1", f"{M01}.r12", f"{M01}.q10"]
)
def test_10r1_well_formed_question_ids_are_accepted(model, record, value):
    """#10 rule 1 / D-034: question ids are `<case>.mNN.qN` (operating) or `.rN` (reviewer);
    the fixture record is `simulated`, which may answer either (rule 3)."""
    model.model_validate(_set(_as(model, record), question_id=value))


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize(
    "value",
    [
        "",
        " ",
        M01,  # a moment id, not a question id
        f"{M01}.q0",  # N starts at 1
        f"{M01}.r0",
        f"{M01}.q",
        f"{M01}.x1",
        f"{M01}.Q1",
        f"{M01}.q1 ",
        f" {M01}.q1",
        f"{M01}.q1.r1",
        f"{M01}.q01",
        "m01.q1",  # no case
        f"{CASE}.m1.q1",  # moment numbers have at least two digits
        f"{CASE}.u0003",  # an utterance id
        "Case-Fixture-01.m01.q1",
        "case_fixture_01.m01.q1",
        "rarp.p05.s01",  # a step id
        str(uuid6.uuid7()),
        1,
        ["case-fixture-01.m01.q1"],
        {"id": "case-fixture-01.m01.q1"},
    ],
    ids=repr,
)
def test_10r1_values_that_are_not_question_ids_are_rejected(model, record, value):
    """#10 rule 1: `question_id` is a `QuestionId` (`<case>.mNN.qN` / `.rN`, D-034); anything
    else fails."""
    with pytest.raises(ValidationError):
        model.model_validate(_set(_as(model, record), question_id=value))


def test_10r1_confirm_draft_keeps_the_question_id(record):
    """#10 rule 1 + plan §4.3 ("`DecisionRecordDraft` has the same shape"): confirming a draft
    keeps its `question_id` (Team Lead: "the link has to be in the record")."""
    for value in (f"{M01}.r1", None):
        draft = DecisionRecordDraft.model_validate(_set(_draft(record), question_id=value))
        confirmed = confirm_draft(
            draft,
            record_id=str(uuid6.uuid7()),
            confirmed_by="dr-a",
            confirmed_at=datetime(2026, 10, 21, 9, 30, tzinfo=UTC),
        )
        assert isinstance(confirmed, DecisionRecord)
        assert confirmed.question_id == value


# --- Rule 2: a question about the record's own moment ------------------------------------------


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("value", [f"{M01}.q1", f"{M01}.r1"])
def test_10r2_question_without_a_moment_is_rejected(model, record, value):
    """#10 rule 2: "If it is non-null, `moment_id` is non-null ... Otherwise validation
    fails"."""
    with pytest.raises(ValidationError):
        model.model_validate(_set(_as(model, record), moment_id=None, question_id=value))


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize(
    "value",
    [
        f"{CASE}.m02.q1",  # another moment of the same case
        f"{CASE}.m02.r1",
        f"{CASE}.m010.q1",  # starts with the moment id, but not with moment_id + "."
        f"{CASE}.m011.r1",
        "case-fixture-02.m01.q1",  # same moment number, another case
        "case-fixture-011.m01.q1",
    ],
)
def test_10r2_question_about_another_moment_is_rejected(model, record, value):
    """#10 rule 2: "`question_id` starts with `moment_id + "."`. Otherwise validation fails"
    (the record's moment is `case-fixture-01.m01`)."""
    with pytest.raises(ValidationError):
        model.model_validate(_set(_as(model, record), question_id=value))


@pytest.mark.parametrize("model", MODELS)
def test_10r2_question_about_its_own_moment_is_accepted(model, record):
    """#10 rule 2, positive side: moment `…m02` with question `…m02.q2` is valid."""
    model.model_validate(
        _set(_as(model, record), moment_id=f"{CASE}.m02", question_id=f"{CASE}.m02.q2")
    )


# --- Rule 3: the question style follows the trust label -----------------------------------------


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize(
    ("label", "value", "ok"),
    [
        ("operating_surgeon", None, True),
        ("operating_surgeon", f"{M01}.q1", True),
        ("operating_surgeon", f"{M01}.q2", True),
        ("operating_surgeon", f"{M01}.r1", False),
        ("operating_surgeon", f"{M01}.r2", False),
        ("reviewer", None, True),
        ("reviewer", f"{M01}.r1", True),
        ("reviewer", f"{M01}.r2", True),
        ("reviewer", f"{M01}.q1", False),
        ("reviewer", f"{M01}.q2", False),
    ],
)
def test_10r3_operating_answers_q_and_reviewer_answers_r(model, record, label, value, ok):
    """#10 rule 3: "If `trust_label` is `operating_surgeon`, `question_id` is `null` or `.qN`.
    If `trust_label` is `reviewer`, it is `null` or `.rN`." """
    doc = _set(_labelled(_as(model, record), label), question_id=value)
    if ok:
        model.model_validate(doc)
    else:
        with pytest.raises(ValidationError):
            model.model_validate(doc)


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize(
    "label",
    ["simulated", "ai_detected", "dataset_annotation", "expert_validated"],
)
@pytest.mark.parametrize("value", [None, f"{M01}.q1", f"{M01}.r1"])
def test_10r3_other_labels_may_answer_either(model, record, label, value):
    """#10 rule 3: "`simulated` may use either" (brief: "any other label (e.g. `simulated`) may
    have either"; D-059: "any other label either"). `narration_extracted` is no longer one of
    them: Team Lead ruling on #10 of 2026-10-17, decision 2 ("`trust_label:
    narration_extracted` => `question_id` is `null`"), tested in
    `test_p0_i10_narration_question_id.py`."""
    model.model_validate(_set(_labelled(_as(model, record), label), question_id=value))


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("value", [None, f"{M01}.q1", f"{M01}.r1"])
def test_10r3_narration_extracted_answers_no_question(model, record, value):
    """#10 rule 3 as amended by the Team Lead ruling of 2026-10-17 (decision 2, criterion 14):
    `narration_extracted` takes only `question_id: null` (D-059 rule 1: "`null` for
    narration-mined records")."""
    doc = _set(_labelled(_as(model, record), "narration_extracted"), question_id=value)
    if value is None:
        model.model_validate(doc)
    else:
        with pytest.raises(ValidationError):
            model.model_validate(doc)


# --- Rule 4: the fixture seed records -----------------------------------------------------------


def _seeds(docs) -> list[dict[str, Any]]:
    return docs["seed_records.json"]["records"]


def _one(records: list[dict[str, Any]], **match: Any) -> dict[str, Any]:
    def _get(r: dict[str, Any], key: str) -> Any:
        return r["provenance"]["trust_label"] if key == "trust_label" else r[key]

    found = [r for r in records if all(_get(r, k) == v for k, v in match.items())]
    assert len(found) == 1, f"expected exactly one seed record with {match}, got {len(found)}"
    return found[0]


def test_10r4_every_seed_record_has_the_question_id_key(docs):
    """#10 rule 4 + rule 1: every seed record carries the required `question_id` key."""
    for i, r in enumerate(_seeds(docs)):
        assert "question_id" in r, f"seed record {i} has no question_id key"


def test_10r4_m01_ja_record_answers_q1(docs):
    """#10 rule 4 / Dev1's analysis: "the m01 ja record -> `case-fixture-01.m01.q1`"."""
    assert _one(_seeds(docs), moment_id=M01, language="ja")["question_id"] == f"{M01}.q1"


def test_10r4_m01_en_record_answers_r1_with_reviewer_view(docs):
    """#10 rule 4 / Dev1's analysis: "the m01 en record -> `case-fixture-01.m01.r1`. I reword
    its `action.text` to "Would put a figure-of-eight stitch on the DVC straight away" /
    「すぐにDVCへ8の字縫合をかけるだろう」"."""
    r = _one(_seeds(docs), moment_id=M01, language="en")
    assert r["question_id"] == f"{M01}.r1"
    assert r["action"]["text"] == {
        "ja": "すぐにDVCへ8の字縫合をかけるだろう",
        "en": "Would put a figure-of-eight stitch on the DVC straight away",
    }


def test_10r4_m02_simulated_record_answers_q1(docs):
    """#10 rule 4 / Dev1's analysis: "the m02 record -> `.m02.q1`" (the `simulated` one)."""
    r = _one(_seeds(docs), moment_id=f"{CASE}.m02", trust_label="simulated")
    assert r["question_id"] == f"{CASE}.m02.q1"


def test_10r4_m04_record_answers_q1(docs):
    """#10 rule 4 / Dev1's analysis: "the m04 record -> `.m04.q1`"."""
    assert _one(_seeds(docs), moment_id=f"{CASE}.m04")["question_id"] == f"{CASE}.m04.q1"


def test_10r4_moment_less_and_narration_records_are_null(docs):
    """#10 rule 4 / Dev1's analysis: "the record with no moment, and the new narration record
    -> `null`" (rule 1: "`null` (narration-mined records, or records with no moment)")."""
    seeds = _seeds(docs)
    no_moment = [r for r in seeds if r["moment_id"] is None]
    narration = [r for r in seeds if r["provenance"]["trust_label"] == "narration_extracted"]
    assert no_moment, "the fixture has no record without a moment"
    assert narration, "the fixture has no narration_extracted record"
    for r in no_moment + narration:
        assert r["question_id"] is None, (r["moment_id"], r["question_id"])


def test_10r4_seed_question_ids_exist_in_questions_json(docs):
    """#10 rule 4: "The fixture seed records set `question_id` to an existing id in
    `questions.json`"."""
    questions = docs["questions.json"]
    known = {q["id"] for kind in ("operating", "reviewer") for q in questions[kind]}
    for r in _seeds(docs):
        if r["question_id"] is not None:
            assert r["question_id"] in known, r["question_id"]


def test_10r4_seed_records_validate_as_decision_records(docs):
    """#10 rule 4 + rules 1-3: every seed record validates as a `DecisionRecord`."""
    for r in _seeds(docs):
        DecisionRecord.model_validate(r)


def test_10r4_validate_case_passes_on_the_fixture(data_dir, run_validate):
    """#10 rule 4: "`scrubgpt-validate case` passes on the fixture" (exit 0)."""
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 0, result.output
    assert result.counts[0] == 0, result.output


def _break_seed(data_dir, index_match: dict[str, Any], **fields: Any) -> None:
    seeds = data_dir.load("seed_records.json")
    target = _one(seeds["records"], **index_match)
    target.update(fields)
    data_dir.save("seed_records.json", seeds)


@pytest.mark.parametrize(
    ("match", "value"),
    [
        ({"moment_id": M01, "language": "ja"}, f"{M01}.q9"),
        ({"moment_id": M01, "language": "en"}, f"{M01}.r7"),
        ({"moment_id": f"{CASE}.m04"}, f"{CASE}.m04.r2"),
    ],
    ids=repr,
)
def test_10r4_validate_case_exits_1_on_unknown_question(data_dir, run_validate, match, value):
    """#10 rule 4 / D-059: "`validate case` errors when a seed record's `question_id` isn't in
    `questions.json`" (brief: "**exits 1** with an error"). The ids are well-formed and about
    the record's own moment, so only the cross-file check can catch them."""
    _break_seed(data_dir, match, question_id=value)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert result.counts[0] >= 1, result.output
    hits = [ln for ln in result.error_lines if value in ln]
    assert hits, f"no ERROR line names {value}:\n{result.output}"
    assert any("seed_records.json" in ln for ln in hits), result.output


def test_10r4_validate_case_accepts_another_existing_question(data_dir, run_validate):
    """#10 rule 4, positive side: a seed `question_id` that exists in `questions.json` (here
    `m02.r1` on the `simulated` m02 record) passes."""
    _break_seed(
        data_dir,
        {"moment_id": f"{CASE}.m02", "trust_label": "simulated"},
        question_id=f"{CASE}.m02.r1",
    )
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 0, result.output


def test_10r4_validate_case_exits_1_on_missing_question_id_key(data_dir, run_validate):
    """#10 rule 1 via `validate case`: a seed record without the required `question_id` key is
    an error (exit 1, D-034)."""
    seeds = data_dir.load("seed_records.json")
    del seeds["records"][0]["question_id"]
    data_dir.save("seed_records.json", seeds)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert any("seed_records.json" in ln for ln in result.error_lines), result.output


def test_10r4_validate_case_exits_1_on_question_about_another_moment(data_dir, run_validate):
    """#10 rule 2 via `validate case`: an existing question about a different moment (`m02.q1`
    on the m01 ja record) fails (exit 1)."""
    _break_seed(data_dir, {"moment_id": M01, "language": "ja"}, question_id=f"{CASE}.m02.q1")
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert any("seed_records.json" in ln for ln in result.error_lines), result.output


# --- Rule 6: generated JSON Schema and TypeScript ----------------------------------------------

SCHEMAS_WITH_RECORD = {
    "DecisionRecord": "DecisionRecord",
    "DecisionRecordDraft": "DecisionRecordDraft",
    "SeedRecords": "DecisionRecord",
    "ExtractResponse": "DecisionRecordDraft",
    "AskRequest": "DecisionRecord",
    "BriefingRequest": "DecisionRecord",
}


def _codegen(out: Path, *extra: str) -> None:
    exe = shutil.which("scrubgpt-codegen")
    assert exe, "scrubgpt-codegen is not installed in the uv environment"
    proc = subprocess.run(
        [exe, "--out", str(out), *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def _record_def(schema: dict[str, Any], name: str, model: str) -> dict[str, Any]:
    if name == model:
        return schema
    defs = schema.get("$defs", {})
    assert model in defs, f"{name}.schema.json doesn't define {model}"
    return defs[model]


def _check_question_id_schema(schema_dir: Path) -> None:
    for name, model in SCHEMAS_WITH_RECORD.items():
        schema = json.loads((schema_dir / f"{name}.schema.json").read_text(encoding="utf-8"))
        node = _record_def(schema, name, model)
        assert "question_id" in node.get("properties", {}), f"{name}: {model} has no question_id"
        assert "question_id" in node.get("required", []), f"{name}: {model}.question_id optional"
        prop = node["properties"]["question_id"]
        variants = prop.get("anyOf", prop.get("oneOf", [prop]))
        types = {v.get("type") for v in variants}
        assert "null" in types, f"{name}: {model}.question_id isn't nullable: {prop}"
        strings = [v for v in variants if v.get("type") == "string"]
        assert strings, f"{name}: {model}.question_id has no string form: {prop}"
        pattern = strings[0].get("pattern")
        assert pattern, f"{name}: {model}.question_id string has no pattern: {prop}"
        assert re.search(pattern, f"{M01}.q1") and re.search(pattern, f"{M01}.r2")
        assert not re.search(pattern, M01) and not re.search(pattern, f"{CASE}.u0003")


def test_10r6_committed_schemas_list_question_id_required_and_nullable(paths):
    """#10 rule 6: "`schema/` and `ts/` are regenerated and the generated `question_id` field
    shows up there" (brief: required and nullable in `DecisionRecord`, `DecisionRecordDraft`
    and the schemas embedding them)."""
    _check_question_id_schema(paths["repo"] / "contracts" / "schema")


def test_10r6_generated_schemas_list_question_id_and_match_committed(tmp_path, paths):
    """#10 rule 6: `scrubgpt-codegen --out <tmp>` produces the same field, and the committed
    schema files for these models match it byte for byte (CI)."""
    _codegen(tmp_path, "--schema-only")
    _check_question_id_schema(tmp_path / "schema")
    committed = paths["repo"] / "contracts" / "schema"
    for name in SCHEMAS_WITH_RECORD:
        mine = (tmp_path / "schema" / f"{name}.schema.json").read_text(encoding="utf-8")
        theirs = (committed / f"{name}.schema.json").read_text(encoding="utf-8")
        assert mine.replace("\r\n", "\n") == theirs.replace("\r\n", "\n"), name


def _ts_interface(text: str, name: str) -> str:
    match = re.search(rf"^export interface {name} \{{\n(.*?)^\}}", text, re.M | re.S)
    assert match, f"no `export interface {name}` in contracts.ts"
    return match.group(1)


def _check_question_id_ts(ts_file: Path) -> None:
    text = ts_file.read_text(encoding="utf-8").replace("\r\n", "\n")
    for name in ("DecisionRecord", "DecisionRecordDraft"):
        body = _ts_interface(text, name)
        lines = [ln.strip() for ln in body.splitlines() if ln.strip().startswith("question_id")]
        assert lines == ["question_id: string | null;"], (name, lines)


def test_10r6_committed_ts_has_required_nullable_question_id(paths):
    """#10 rule 6: the committed `ts/contracts.ts` has `question_id: string | null` (required,
    not `question_id?:`) on `DecisionRecord` and `DecisionRecordDraft`."""
    _check_question_id_ts(paths["repo"] / "contracts" / "ts" / "contracts.ts")


def test_10r6_generated_ts_matches_committed(tmp_path, paths):
    """#10 rule 6: `scrubgpt-codegen --out <tmp>` output matches the committed `ts/` (needs
    Node's `npx`)."""
    if not shutil.which("npx"):
        pytest.skip("npx not on PATH: TypeScript generation not checked")
    _codegen(tmp_path)
    _check_question_id_ts(tmp_path / "ts" / "contracts.ts")
    mine = (tmp_path / "ts" / "contracts.ts").read_text(encoding="utf-8")
    theirs = (paths["repo"] / "contracts" / "ts" / "contracts.ts").read_text(encoding="utf-8")
    assert mine.replace("\r\n", "\n") == theirs.replace("\r\n", "\n")


# --- D-064 rule 3: `question_id` is metadata, never grounded ------------------------------------


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("value", [f"{M01}.q1", f"{M01}.r1", None])
@pytest.mark.parametrize("source", ["answer", "edit", "narration"])
def test_d064r3_grounding_on_question_id_is_rejected(model, record, value, source):
    """D-064 rule 3: "a `grounding[].field` must start at `context`, `situation_cue`, ... ;
    metadata (`id`, `case_id`, `moment_id`, `question_id`, ...) is a model error"."""
    doc = _set(_as(model, record), question_id=value)
    model.model_validate(doc)  # valid before the grounding is added
    doc["grounding"].append({"field": "question_id", "quote": "静脈性なので", "source": source})
    with pytest.raises(ValidationError):
        model.model_validate(doc)
