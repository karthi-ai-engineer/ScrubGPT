"""Issue #10 follow-up: Team Lead ruling of 2026-10-17 16:42, decisions 2-3, criteria 14-15.

Decision 2: "`DecisionRecord` and `DecisionRecordDraft`: `trust_label: narration_extracted` =>
`question_id` is `null`. Narration answers no question." (D-059 rule 1: "`null` for
narration-mined records".)

Criterion 14: "`DecisionRecord` and `DecisionRecordDraft` reject `trust_label:
narration_extracted` with a non-null `question_id` and accept it with `null`. `scrubgpt-validate
case` fails on a seed record that breaks this." Brief: it exits 1 with an error naming
`seed_records.json`; every other label's rule-3 behaviour is unchanged.

Decision 3 / criterion 15: the `DecisionRecordDraft` docstring no longer says a null cue/action
gets an editable chip (D-056: it is listed in `missing_fields` and gets no chip); "It must reach
the generated `schema/` and `ts/`". "Codegen output is fresh (CI)".
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from scrubgpt_contracts.models.decision_record import DecisionRecord, DecisionRecordDraft

CASE = "case-fixture-01"
M01 = f"{CASE}.m01"
M02 = f"{CASE}.m02"
NARRATION = 5  # seed record 5: m02, ja, narration_extracted, question_id null

MODELS = [
    pytest.param(DecisionRecord, id="DecisionRecord"),
    pytest.param(DecisionRecordDraft, id="DecisionRecordDraft"),
]

ROLE_FOR_LABEL = {
    "ai_detected": "ai",
    "dataset_annotation": "dataset",
    "narration_extracted": "narrator",
    "operating_surgeon": "operating_surgeon",
    "reviewer": "reviewer",
    "expert_validated": "expert",
    "simulated": "dev_team_simulated",
}


def _draft(record: dict[str, Any]) -> dict[str, Any]:
    draft = copy.deepcopy(record)
    draft["id"] = None
    draft["provenance"]["confirmed_by"] = None
    draft["provenance"]["confirmed_at"] = None
    return draft


def _as(model, doc: dict[str, Any]) -> dict[str, Any]:
    return _draft(doc) if model is DecisionRecordDraft else copy.deepcopy(doc)


def _with(doc: dict[str, Any], label: str, question_id: Any, **fields: Any) -> dict[str, Any]:
    doc = copy.deepcopy(doc)
    doc["provenance"]["trust_label"] = label
    doc["provenance"]["attributed_to"] = ROLE_FOR_LABEL[label]
    doc["question_id"] = question_id
    doc.update(fields)
    return doc


@pytest.fixture
def record(docs) -> dict[str, Any]:
    """Seed record 0: moment m01, `simulated`, answers `m01.q1`."""
    return copy.deepcopy(docs["seed_records.json"]["records"][0])


@pytest.fixture
def narration(docs) -> dict[str, Any]:
    """Seed record 5: the fixture's narration-mined record (moment m02, `question_id: null`)."""
    r = copy.deepcopy(docs["seed_records.json"]["records"][NARRATION])
    assert r["provenance"]["trust_label"] == "narration_extracted"
    return r


# --- Criterion 14: the models -------------------------------------------------------------------


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize(
    "value", [f"{M01}.q1", f"{M01}.q2", f"{M01}.q10", f"{M01}.r1", f"{M01}.r2", f"{M01}.r12"]
)
def test_14_narration_extracted_with_a_question_is_rejected(model, record, value):
    """Criterion 14: "`DecisionRecord` and `DecisionRecordDraft` reject `trust_label:
    narration_extracted` with a non-null `question_id`" (`.qN` or `.rN`; the id is otherwise
    valid: well-formed and about the record's own moment)."""
    with pytest.raises(ValidationError):
        model.model_validate(_with(_as(model, record), "narration_extracted", value))


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("value", [f"{M02}.q1", f"{M02}.q2", f"{M02}.r1"])
def test_14_fixture_narration_record_with_a_question_is_rejected(model, narration, value):
    """Criterion 14 on the fixture's own narration record (moment m02): giving it any question
    of its moment fails."""
    doc = _as(model, narration)
    doc["question_id"] = value
    with pytest.raises(ValidationError):
        model.model_validate(doc)


@pytest.mark.parametrize("model", MODELS)
def test_14_narration_extracted_with_a_question_is_rejected_from_json(model, record):
    """Criterion 14 through `model_validate_json` (how a reader loads a file or response)."""
    doc = _with(_as(model, record), "narration_extracted", f"{M01}.q1")
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(doc, ensure_ascii=False))


@pytest.mark.parametrize("model", MODELS)
def test_14_narration_extracted_with_null_is_accepted(model, record, narration):
    """Criterion 14: "... and accept it with `null`" (with a moment, and with no moment)."""
    model.model_validate(_with(_as(model, record), "narration_extracted", None))
    model.model_validate(_with(_as(model, record), "narration_extracted", None, moment_id=None))
    model.model_validate(_as(model, narration))


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize(
    ("label", "value", "ok"),
    [
        ("operating_surgeon", None, True),
        ("operating_surgeon", f"{M01}.q1", True),
        ("operating_surgeon", f"{M01}.r1", False),
        ("reviewer", None, True),
        ("reviewer", f"{M01}.r1", True),
        ("reviewer", f"{M01}.q1", False),
        ("simulated", None, True),
        ("simulated", f"{M01}.q1", True),
        ("simulated", f"{M01}.r1", True),
        ("ai_detected", None, True),
        ("ai_detected", f"{M01}.q1", True),
        ("ai_detected", f"{M01}.r1", True),
        ("dataset_annotation", None, True),
        ("dataset_annotation", f"{M01}.q1", True),
        ("dataset_annotation", f"{M01}.r1", True),
        ("expert_validated", None, True),
        ("expert_validated", f"{M01}.q1", True),
        ("expert_validated", f"{M01}.r1", True),
        ("narration_extracted", None, True),
        ("narration_extracted", f"{M01}.q1", False),
        ("narration_extracted", f"{M01}.r1", False),
    ],
)
def test_14_full_label_by_question_matrix(model, record, label, value, ok):
    """Criterion 14 (brief): "Every other trust label's behaviour from rule 3 is unchanged
    (`operating_surgeon` -> null or `.qN`; `reviewer` -> null or `.rN`; `simulated`,
    `ai_detected`, `dataset_annotation`, `expert_validated` -> null, `.qN` or `.rN`)", and
    `narration_extracted` -> null only."""
    doc = _with(_as(model, record), label, value)
    if ok:
        model.model_validate(doc)
    else:
        with pytest.raises(ValidationError):
            model.model_validate(doc)


# --- Criterion 14: `scrubgpt-validate case` -----------------------------------------------------


def _assert_fails_naming_seeds(result) -> None:
    assert result.code == 1, result.output
    assert result.counts[0] >= 1, result.output
    assert any("seed_records.json" in ln for ln in result.error_lines), result.output


@pytest.mark.parametrize("value", [f"{M02}.q1", f"{M02}.q2", f"{M02}.r1"])
def test_14_validate_case_exits_1_on_narration_seed_with_a_question(data_dir, run_validate, value):
    """Criterion 14: "`scrubgpt-validate case` exits 1 with an error naming `seed_records.json`
    on a seed record that breaks this". The fixture's narration record gets an existing
    question of its own moment, so only the narration rule can fire."""
    seeds = data_dir.load("seed_records.json")
    assert seeds["records"][NARRATION]["provenance"]["trust_label"] == "narration_extracted"
    seeds["records"][NARRATION]["question_id"] = value
    data_dir.save("seed_records.json", seeds)
    _assert_fails_naming_seeds(run_validate("case", data_dir.case_dir))


def test_14_validate_case_exits_1_on_relabelled_seed_keeping_its_question(data_dir, run_validate):
    """Criterion 14: a seed record that answers `m01.q1`, relabelled `narration_extracted`
    (attributed to `narrator`) but keeping its `question_id`, fails naming
    `seed_records.json`."""
    seeds = data_dir.load("seed_records.json")
    r = seeds["records"][0]
    assert r["question_id"] == f"{M01}.q1"
    r["provenance"]["trust_label"] = "narration_extracted"
    r["provenance"]["attributed_to"] = "narrator"
    data_dir.save("seed_records.json", seeds)
    _assert_fails_naming_seeds(run_validate("case", data_dir.case_dir))


def test_14_validate_case_passes_on_relabelled_seed_with_null_question(data_dir, run_validate):
    """Criterion 14, positive side: the same relabelled seed record with `question_id: null`
    passes (exit 0, no warnings)."""
    seeds = data_dir.load("seed_records.json")
    r = seeds["records"][0]
    r["provenance"]["trust_label"] = "narration_extracted"
    r["provenance"]["attributed_to"] = "narrator"
    r["question_id"] = None
    data_dir.save("seed_records.json", seeds)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 0, result.output
    assert result.counts == (0, 0), result.output


def test_14_fixture_narration_seed_is_null_and_case_passes(docs, data_dir, run_validate):
    """Criterion 14 / decision 2: "The fixture's narration record is already null"; the
    unedited fixture still passes."""
    for r in docs["seed_records.json"]["records"]:
        if r["provenance"]["trust_label"] == "narration_extracted":
            assert r["question_id"] is None, r["id"]
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 0, result.output


# --- Criterion 15: codegen is fresh; no "editable chip" in the draft description -----------------


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


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _draft_schema_descriptions(schema_dir: Path) -> list[tuple[str, str]]:
    """The description of every `DecisionRecordDraft` node in the schema files."""
    found: list[tuple[str, str]] = []
    for f in sorted(schema_dir.glob("*.schema.json")):
        schema = json.loads(_text(f))
        if f.name == "DecisionRecordDraft.schema.json":
            found.append((f.name, schema.get("description", "")))
        node = schema.get("$defs", {}).get("DecisionRecordDraft")
        if node is not None:
            found.append((f"{f.name}#/$defs/DecisionRecordDraft", node.get("description", "")))
    return found


def _check_draft_schema_description(schema_dir: Path) -> None:
    found = _draft_schema_descriptions(schema_dir)
    names = {n for n, _ in found}
    assert "DecisionRecordDraft.schema.json" in names, names
    assert "ExtractResponse.schema.json#/$defs/DecisionRecordDraft" in names, names
    for name, desc in found:
        assert desc, f"{name}: no description"
        assert "editable chip" not in desc.lower(), f"{name}: {desc}"
        assert "missing_fields" in desc, f"{name}: doesn't mention missing_fields: {desc}"


def _ts_doc_comment(text: str, name: str) -> str:
    match = re.search(rf"/\*\*((?:(?!\*/).)*?)\*/\nexport interface {name} \{{", text, re.S)
    assert match, f"no doc comment right before `export interface {name}`"
    return match.group(1)


def _check_draft_ts_description(ts_file: Path) -> None:
    doc = _ts_doc_comment(_text(ts_file), "DecisionRecordDraft")
    flat = " ".join(ln.strip().lstrip("*").strip() for ln in doc.splitlines())
    assert "editable chip" not in flat.lower(), flat
    assert "missing_fields" in flat, flat


def test_15_committed_schema_draft_description_has_no_editable_chip(paths):
    """Criterion 15: "the `DecisionRecordDraft` description in `schema/` ... no longer
    mentions an editable chip for a null cue/action" (D-056: listed in `missing_fields`, no
    chip). Checked in `DecisionRecordDraft.schema.json` and wherever it is embedded."""
    _check_draft_schema_description(paths["repo"] / "contracts" / "schema")


def test_15_committed_ts_draft_description_has_no_editable_chip(paths):
    """Criterion 15: the same for the doc comment on `export interface DecisionRecordDraft` in
    the committed `ts/contracts.ts`."""
    _check_draft_ts_description(paths["repo"] / "contracts" / "ts" / "contracts.ts")


def test_15_python_draft_docstring_has_no_editable_chip():
    """Decision 3: the source of the generated text, the `DecisionRecordDraft` docstring,
    no longer promises an editable chip and points at `missing_fields`."""
    doc = DecisionRecordDraft.__doc__ or ""
    assert "editable chip" not in doc.lower(), doc
    assert "missing_fields" in doc, doc


def test_15_generated_schema_matches_committed_and_has_no_editable_chip(tmp_path, paths):
    """Criterion 15: "Codegen output is fresh" for `schema/`: `scrubgpt-codegen --out <tmp>`
    produces exactly the committed file set, byte for byte (line endings aside), and the
    generated draft description has no editable chip."""
    _codegen(tmp_path, "--schema-only")
    generated = tmp_path / "schema"
    committed = paths["repo"] / "contracts" / "schema"
    mine = sorted(p.name for p in generated.glob("*.schema.json"))
    theirs = sorted(p.name for p in committed.glob("*.schema.json"))
    assert mine == theirs
    stale = [n for n in mine if _text(generated / n) != _text(committed / n)]
    assert not stale, f"committed schema/ is stale: {stale}"
    _check_draft_schema_description(generated)


def test_15_generated_ts_matches_committed_and_has_no_editable_chip(tmp_path, paths):
    """Criterion 15: "Codegen output is fresh" for `ts/` (needs Node's `npx`), and the
    generated `DecisionRecordDraft` doc comment has no editable chip."""
    if not shutil.which("npx"):
        pytest.skip("npx not on PATH: TypeScript generation not checked")
    _codegen(tmp_path)
    generated = tmp_path / "ts"
    committed = paths["repo"] / "contracts" / "ts"
    mine = sorted(p.name for p in generated.iterdir() if p.is_file() and not p.name.startswith("."))
    theirs = sorted(
        p.name for p in committed.iterdir() if p.is_file() and not p.name.startswith(".")
    )
    assert mine == theirs
    stale = [n for n in mine if _text(generated / n) != _text(committed / n)]
    assert not stale, f"committed ts/ is stale: {stale}"
    _check_draft_ts_description(generated / "contracts.ts")
    # The full run regenerates schema/ too; it must match as well.
    schema_stale = [
        p.name
        for p in (tmp_path / "schema").glob("*.schema.json")
        if _text(p) != _text(paths["repo"] / "contracts" / "schema" / p.name)
    ]
    assert not schema_stale, schema_stale
