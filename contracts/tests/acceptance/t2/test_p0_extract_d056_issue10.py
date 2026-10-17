"""T2 acceptance: D-056 (Dev2 part, issue #5) and issue #10 (rule 5, rule 6 T2 part, Team Lead
ruling of 2026-10-17 criteria 7-10) on Dev2's contract files, re-test at 98293f2.

Sources (quoted per test):
- D-056 / issue #5 Team Lead reply: "No chip for a null field: missing_fields[] is the editable
  prompt for an unstated situation_cue.text / action.text"; "ExtractResponse rule (Dev2): a null
  draft.situation_cue.text / draft.action.text must be listed in missing_fields"; criteria 12b
  (amended), 12d, 12f, 12g.
- D-055: `scrubgpt-validate` exit 1 = the subject's content is defective.
- D-059 / issue #10 rule 5: "the fake Brain's /extract returns draft.question_id ==
  request.question.id"; rule 6: the brain_api fixtures' candidate records carry question_id.
- Issue #10 Team Lead ruling (2026-10-17 16:02), criteria 7-10: the answerer-role cross-check
  on ExtractRequest, ai/dataset/narrator rejected, 400 bad_request on the fake Brain (never
  503), and valid drafts with question_id and trust_label for every accepted combination.
- contracts/brain_api.md (/extract request and response tables, unstated cue/action paragraph,
  request fixtures paragraph).
- plan §4.3 (DecisionRecordDraft), §4.4 (Brain API), D-034, D-037.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
from typing import Any

import pytest
from pydantic import ValidationError

PATH = "/v1/answers/extract"
OPERATING = (
    "case-fixture-01.m01.q1",
    "case-fixture-01.m01.q2",
    "case-fixture-01.m02.q1",
    "case-fixture-01.m02.q2",
    "case-fixture-01.m03.q1",
    "case-fixture-01.m04.q1",
    "case-fixture-01.m05.q1",
    "case-fixture-01.m06.q1",
)
REVIEWER = (
    "case-fixture-01.m01.r1",
    "case-fixture-01.m01.r2",
    "case-fixture-01.m02.r1",
    "case-fixture-01.m04.r1",
)
QUESTIONS = OPERATING + REVIEWER
LANGS = ("ja", "en")
ALL_ROLES = ("ai", "dataset", "narrator", "operating_surgeon", "reviewer", "expert",
             "dev_team_simulated")  # fmt: skip
# Issue #10 ruling, criterion 7 and brain_api.md /extract answerer_role row.
TRUST_BY_ROLE = {
    "operating_surgeon": "operating_surgeon",
    "reviewer": "reviewer",
    "dev_team_simulated": "simulated",
    "expert": "expert_validated",
}
ANSWER = {
    "en": "I clipped the vessel and moved on.",
    "ja": "血管をクリップして先に進みました。",
}


def _allowed(question_id: str, role: str) -> bool:
    """#10 criterion 7 + 8: operating_surgeon answers `.qN`, reviewer `.rN`, dev_team_simulated
    and expert either; ai, dataset and narrator never."""
    if role in ("dev_team_simulated", "expert"):
        return True
    if role == "operating_surgeon":
        return question_id in OPERATING
    if role == "reviewer":
        return question_id in REVIEWER
    return False


ACCEPTED = [(q, r) for q in QUESTIONS for r in ALL_ROLES if _allowed(q, r)]
REJECTED = [(q, r) for q in QUESTIONS for r in ALL_ROLES if not _allowed(q, r)]


def _short(q: str) -> str:
    return q.removeprefix("case-fixture-01.")


def _ids(rows) -> list[str]:
    return [f"{_short(q)}-{r}" for q, r in rows]


def _request_model():
    from scrubgpt_contracts.models.brain_api import ExtractRequest

    return ExtractRequest


def _response_model():
    from scrubgpt_contracts.models.brain_api import ExtractResponse

    return ExtractResponse


# --- criteria 7 and 8: the answerer-role cross-check on ExtractRequest --------------------------


def test_c07_answerer_roles_are_the_four_named_in_brain_api_md():
    """brain_api.md /extract answerer_role: "operating_surgeon, reviewer, dev_team_simulated
    (role-play) or expert (ANSWERER_ROLES); ai, dataset and narrator don't answer questions"."""
    from scrubgpt_contracts.models.brain_api import ANSWERER_ROLES

    assert {str(getattr(r, "value", r)) for r in ANSWERER_ROLES} == set(TRUST_BY_ROLE)


def test_c07_role_matrix_covers_every_role_value():
    """Guard: the matrices below use every `Role` value of plan §4.1."""
    from scrubgpt_contracts.models.common import Role

    assert {r.value for r in Role} == set(ALL_ROLES)
    assert ACCEPTED and REJECTED


@pytest.mark.parametrize(("question_id", "role"), ACCEPTED, ids=_ids(ACCEPTED))
def test_c07_extract_request_accepts_allowed_role_and_question(build_extract, question_id, role):
    """#10 criterion 7: "ExtractRequest ... accepts operating_surgeon + .qN, reviewer + .rN, and
    dev_team_simulated / expert with either"."""
    _request_model().model_validate(build_extract(question_id, role=role))


@pytest.mark.parametrize(
    ("question_id", "role"),
    [(q, r) for q, r in REJECTED if r in ("operating_surgeon", "reviewer")],
    ids=_ids([(q, r) for q, r in REJECTED if r in ("operating_surgeon", "reviewer")]),
)
def test_c07_extract_request_rejects_role_on_the_other_question_kind(
    build_extract, question_id, role
):
    """#10 criterion 7: "ExtractRequest rejects answerer_role: operating_surgeon with a .rN
    question and reviewer with a .qN question"."""
    with pytest.raises(ValidationError):
        _request_model().model_validate(build_extract(question_id, role=role))


@pytest.mark.parametrize("role", ["ai", "dataset", "narrator"])
@pytest.mark.parametrize("question_id", QUESTIONS, ids=[_short(q) for q in QUESTIONS])
def test_c08_extract_request_rejects_non_answerer_roles(build_extract, question_id, role):
    """#10 criterion 8: "ExtractRequest rejects answerer_role ai, dataset and narrator" (on
    operating and reviewer questions alike)."""
    with pytest.raises(ValidationError):
        _request_model().model_validate(build_extract(question_id, role=role))


# --- criterion 9: the fake Brain answers them with 400 bad_request -----------------------------


@pytest.mark.parametrize(("question_id", "role"), REJECTED, ids=_ids(REJECTED))
@pytest.mark.parametrize("lang", LANGS)
def test_c09_fake_brain_rejects_with_400_bad_request(
    client, build_extract, assert_api_error, question_id, role, lang
):
    """#10 criterion 9: "The fake Brain answers each request rejected in 7-8 with HTTP 400 and
    an ApiError body with code: bad_request, never 503" (both languages, so canned and generic
    paths alike)."""
    req = build_extract(question_id, role=role, text=ANSWER[lang], lang=lang)
    r = client.post(PATH, json=req)
    assert r.status_code != 503, r.text[:500]
    body = assert_api_error(r, 400, "bad_request")
    assert body["error"]["retryable"] is False


@pytest.mark.parametrize(
    ("question_id", "role"),
    [
        ("case-fixture-01.m01.r1", "operating_surgeon"),
        ("case-fixture-01.m01.q1", "reviewer"),
        ("case-fixture-01.m02.q1", "narrator"),
    ],  # fmt: skip
    ids=["op-on-r1", "reviewer-on-q1", "narrator"],
)
def test_c09_fake_brain_process_rejects_with_400(
    mock_brain_url, build_extract, assert_api_error, question_id, role
):
    """#10 criterion 9 through `scrubgpt-mock-brain` as a process (the same 400, never 503)."""
    import httpx

    req = build_extract(question_id, role=role)
    r = httpx.post(f"{mock_brain_url}{PATH}", json=req, timeout=30)
    assert_api_error(r, 400, "bad_request")


@pytest.mark.parametrize("role", ["operating_surgeon", "reviewer"])
def test_c09_fixture_request_with_the_wrong_role_is_400(
    client, request_fixture, assert_api_error, role
):
    """#10 criteria 7/9 on extract.request.json (an operating question, m01.q1): the fixture's
    own role is accepted, reviewer is a 400 bad_request."""
    req = request_fixture("extract")
    assert req["answerer_role"] == "operating_surgeon"
    req["answerer_role"] = role
    r = client.post(PATH, json=req)
    if role == "operating_surgeon":
        assert r.status_code == 200, r.text[:500]
    else:
        assert_api_error(r, 400, "bad_request")


# --- criteria 5 and 10: accepted combinations give a valid draft --------------------------------


@pytest.fixture(scope="module")
def extract_ok(client, endpoints):
    def run(req: dict[str, Any]) -> dict[str, Any]:
        r = client.post(PATH, json=req)
        assert r.status_code == 200, r.text[:800]
        out = r.json()
        endpoints["extract"].response.model_validate(out)
        return out

    return run


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize(("question_id", "role"), ACCEPTED, ids=_ids(ACCEPTED))
def test_c10_accepted_combination_gives_a_valid_draft(
    extract_ok, build_extract, question_id, role, lang
):
    """#10 criterion 10: "For each accepted combination in 7, the fake Brain returns a draft
    that validates as DecisionRecordDraft, with question_id == request.question.id and
    trust_label per brain_api.md" (operating_surgeon -> operating_surgeon, reviewer -> reviewer,
    dev_team_simulated -> simulated, expert -> expert_validated; attributed_to =
    answerer_role)."""
    from scrubgpt_contracts.models.decision_record import DecisionRecordDraft

    req = build_extract(question_id, role=role, text=ANSWER[lang], lang=lang)
    draft = extract_ok(req)["draft"]
    DecisionRecordDraft.model_validate(draft)
    assert draft["question_id"] == req["question"]["id"]
    assert draft["provenance"]["trust_label"] == TRUST_BY_ROLE[role]
    assert draft["provenance"]["attributed_to"] == role


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("question_id", QUESTIONS, ids=[_short(q) for q in QUESTIONS])
def test_c05_question_id_is_the_requests_for_canned_and_generic(
    extract_ok, build_extract, extract_spec, case_data, question_id, lang
):
    """#10 rule 5: "The fake Brain's /v1/answers/extract returns draft.question_id ==
    request.question.id, for canned and generic drafts" (canned per brain_api.md's table: m01
    in ja and en, m02 and m03 in ja, m04 in en)."""
    req = build_extract(question_id, text=ANSWER[lang], lang=lang)
    draft = extract_ok(req)["draft"]
    assert draft["question_id"] == question_id


def test_c05_both_canned_and_generic_are_covered(extract_spec):
    """Guard for the test above: the question x language matrix hits canned and generic drafts."""
    rows = {(q.rsplit(".", 1)[0], lang) for q in QUESTIONS for lang in LANGS}
    assert rows & set(extract_spec["canned"])
    assert rows - set(extract_spec["canned"])


@pytest.mark.parametrize(
    ("question_id", "lang", "seed_question"),
    [
        # the m01 en seed record answers m01.r1; an operating answer to m01.q1 in en is canned
        # from it but must name m01.q1
        ("case-fixture-01.m01.q1", "en", "case-fixture-01.m01.r1"),
        # the m01 ja seed record answers m01.q1; a reviewer answer to m01.r1 in ja is canned from
        # it but must name m01.r1
        ("case-fixture-01.m01.r1", "ja", "case-fixture-01.m01.q1"),
        ("case-fixture-01.m01.r2", "ja", "case-fixture-01.m01.q1"),
        ("case-fixture-01.m04.r1", "en", "case-fixture-01.m04.q1"),
    ],
)
def test_c05_canned_draft_names_the_request_question_not_the_seed(
    extract_ok, build_extract, seed_for, case_data, question_id, lang, seed_question
):
    """#10 rule 5 (brief: "a canned draft now carries the request's question_id, not the seed
    record's"); brain_api.md: the canned draft is the seed record "with id: null, the request's
    moment_id, question_id, answer_id and answerer provenance"."""
    moment_id = case_data["questions"][question_id]["moment_id"]
    seed = seed_for(moment_id, lang)
    assert seed is not None and seed["question_id"] == seed_question  # the premise
    answer = next(e["quote"] for e in seed["evidence"] if e["kind"] == "answer_text")
    req = build_extract(question_id, text=answer, lang=lang)
    draft = extract_ok(req)["draft"]
    assert draft["question_id"] == question_id
    assert draft["situation_cue"] == seed["situation_cue"]  # it is the canned draft


# --- criterion 1 (12b amended), on every accepted role ------------------------------------------


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize(("question_id", "role"), ACCEPTED, ids=_ids(ACCEPTED))
def test_c01_no_ungrounded_field_and_no_chip_on_a_null_field(
    extract_ok, build_extract, get_path, question_id, role, lang
):
    """Brief criterion 1 (#5 12b amended by D-056): ungrounded_fields(draft) == []; every null
    situation_cue.text / action.text is in missing_fields[]; no chip names a null field (no
    `value: null` chip exists any more). Here for every accepted answerer role (the probe-answer
    matrix is in test_p0_mock_brain_extract_d054.py)."""
    from scrubgpt_contracts.models.decision_record import DecisionRecordDraft, ungrounded_fields

    out = extract_ok(build_extract(question_id, role=role, text=ANSWER[lang], lang=lang))
    draft = out["draft"]
    assert ungrounded_fields(DecisionRecordDraft.model_validate(draft)) == []
    for path in ("situation_cue.text", "action.text"):
        if get_path(draft, path) is None:
            assert path in out["missing_fields"], (path, out["missing_fields"])
    for chip in out["chips"]:
        assert chip["value"] is not None, chip
        assert get_path(draft, chip["field"]) is not None, chip


# --- criterion 3 (12f): ExtractResponse and scrubgpt-validate ----------------------------------


@pytest.fixture(scope="module")
def null_cue_response(client, build_extract) -> dict[str, Any]:
    """A generic fake-Brain response with null situation_cue.text and action.text, and a null
    `anticipation`: m02.q2 (a `reason` question) answered in English (no English m02 seed)."""
    req = build_extract("case-fixture-01.m02.q2", text=ANSWER["en"], lang="en")
    r = client.post(PATH, json=req)
    assert r.status_code == 200, r.text[:800]
    out = r.json()
    draft = out["draft"]
    assert draft["situation_cue"]["text"] is None and draft["action"]["text"] is None
    assert draft["anticipation"] is None and draft["reason"] is not None
    return out


def _validate_cli(body: dict[str, Any], tmp_path, name: str) -> tuple[int, str]:
    from scrubgpt_contracts.validate import main as validate_main

    saved = tmp_path / f"{name}.json"
    saved.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    lines: list[str] = []
    code = validate_main(["response", "extract", str(saved)], out=lines.append)
    return code, "\n".join(lines)


@pytest.mark.parametrize("path", ["situation_cue.text", "action.text"])
def test_c03_unlisted_null_cue_or_action_rejected_and_validate_exits_1(
    null_cue_response, tmp_path, path
):
    """#5 12f: "ExtractResponse rejects a body whose draft has a null situation_cue.text or
    action.text not listed in missing_fields ... scrubgpt-validate response extract <file> on
    such a body exits 1 (D-055)"."""
    body = copy.deepcopy(null_cue_response)
    body["missing_fields"] = [p for p in body["missing_fields"] if p != path]
    with pytest.raises(ValidationError):
        _response_model().model_validate(body)
    code, text = _validate_cli(body, tmp_path, "unlisted")
    assert code == 1, text


def test_c03_listed_null_cue_and_action_accepted_and_validate_exits_0(null_cue_response, tmp_path):
    """#5 12f: "... and accepts it when listed" (exit 0, D-052)."""
    body = copy.deepcopy(null_cue_response)
    assert {"situation_cue.text", "action.text"} <= set(body["missing_fields"])
    assert not [c for c in body["chips"] if c["field"] in ("situation_cue.text", "action.text")]
    _response_model().model_validate(body)
    code, text = _validate_cli(body, tmp_path, "listed")
    assert code == 0, text


def test_c03_validate_console_script_exits_1_on_unlisted_null_cue(
    null_cue_response, tmp_path, console_script
):
    """#5 12f through the real `scrubgpt-validate` console script: exit 1 (D-055)."""
    body = copy.deepcopy(null_cue_response)
    body["missing_fields"] = [p for p in body["missing_fields"] if p != "situation_cue.text"]
    saved = tmp_path / "unlisted.json"
    saved.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    done = subprocess.run(
        [str(console_script("scrubgpt-validate")), "response", "extract", str(saved)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert done.returncode == 1, done.stdout + done.stderr


@pytest.mark.parametrize(
    "path", ["situation_cue.text", "action.text", "anticipation", "immediate_result", "obstacle"]
)
def test_c03_chip_on_any_null_field_rejected_and_validate_exits_1(
    null_cue_response, tmp_path, path
):
    """#5 12f / D-056: "ExtractResponse also rejects any chip on a field that is null in the
    draft" (brain_api.md chips row: "a chip on a null field is invalid")."""
    body = copy.deepcopy(null_cue_response)
    assert body["draft"][path.split(".")[0]] is None or path.endswith(".text")
    body["chips"].append(
        {"field": path, "value": {"ja": "推測", "en": "A guess"}, "editable": True}
    )
    with pytest.raises(ValidationError):
        _response_model().model_validate(body)
    code, text = _validate_cli(body, tmp_path, "chip_on_null")
    assert code == 1, text


@pytest.mark.parametrize("path", ["reason", "situation_cue.text"])
def test_c03_chip_with_null_value_rejected_and_validate_exits_1(null_cue_response, tmp_path, path):
    """#5 12f / D-056: "... and a chip with value: null" (on a filled field and on a null one)."""
    body = copy.deepcopy(null_cue_response)
    body["chips"] = [c for c in body["chips"] if c["field"] != path] + [
        {"field": path, "value": None, "editable": True}
    ]
    with pytest.raises(ValidationError):
        _response_model().model_validate(body)
    code, text = _validate_cli(body, tmp_path, "null_chip")
    assert code == 1, text


def test_c03_chip_model_value_is_a_non_null_bilingual():
    """D-056: "the Chip shape stays (chips only for filled fields)": Chip.value is a Bilingual,
    never null."""
    from scrubgpt_contracts.models.brain_api import Chip

    Chip.model_validate(
        {"field": "reason", "value": {"ja": "理由", "en": "Reason"}, "editable": True}
    )
    with pytest.raises(ValidationError):
        Chip.model_validate({"field": "reason", "value": None, "editable": True})


# --- criterion 4 (12g): never from the moment title ---------------------------------------------


GENERIC_NON_CUE = [
    (q, lang)
    for q in QUESTIONS
    for lang in LANGS
    if q not in ("case-fixture-01.m01.q1", "case-fixture-01.m05.q1")  # the two `cue` questions
    and (q.rsplit(".", 1)[0], lang)
    not in {
        ("case-fixture-01.m01", "ja"),
        ("case-fixture-01.m01", "en"),
        ("case-fixture-01.m02", "ja"),
        ("case-fixture-01.m03", "ja"),
        ("case-fixture-01.m04", "en"),
    }
]


@pytest.mark.parametrize(
    ("question_id", "lang"), GENERIC_NON_CUE, ids=[f"{_short(q)}-{lg}" for q, lg in GENERIC_NON_CUE]
)
def test_c04_action_only_answer_leaves_the_cue_null(
    extract_ok, build_extract, case_data, extract_spec, question_id, lang
):
    """#5 12g: "The generic draft never takes situation_cue.text from the moment title: a request
    whose answer states only an action gives situation_cue.text: null" (and, per D-056, it is in
    missing_fields with no chip)."""
    assert extract_spec["generic_target"](case_data["questions"][question_id]["type"]) != (
        "situation_cue.text"
    )
    req = build_extract(question_id, text=ANSWER[lang], lang=lang)
    out = extract_ok(req)
    draft = out["draft"]
    assert draft["situation_cue"]["text"] is None, draft["situation_cue"]
    assert draft["situation_cue"]["cue_terms"] == []
    assert "situation_cue.text" in out["missing_fields"]
    assert not [c for c in out["chips"] if c["field"] == "situation_cue.text"]
    title = req["moment"]["title"]
    for g in draft["grounding"]:
        assert g["quote"] not in (title["ja"], title["en"]), g


def test_c04_matrix_is_not_empty():
    """Guard: 12g is checked on operating and reviewer questions."""
    qs = {q for q, _ in GENERIC_NON_CUE}
    assert qs & set(OPERATING) and qs & set(REVIEWER)


# --- criterion 6: ask/briefing candidates carry question_id -------------------------------------


@pytest.mark.parametrize("name", ["ask", "briefing"])
def test_c06_candidates_carry_the_seed_question_id_and_validate(
    request_fixture, endpoints, case_data, name
):
    """#10 rule 6 (T2 part): "Every candidate record in fixtures/brain_api/ask.request.json and
    briefing.request.json carries question_id, equal to the same record's value in the fixture
    case's seed_records.json; both fixtures validate"."""
    from scrubgpt_contracts.models.decision_record import DecisionRecord

    req = request_fixture(name)
    endpoints[name].request.model_validate(req)
    seeds = {r["id"]: r for r in case_data["seeds"]}
    assert req["candidates"], "no candidates"
    for cand in req["candidates"]:
        assert "question_id" in cand, cand["id"]
        assert cand["id"] in seeds, f"candidate {cand['id']} is not a seed record"
        assert cand["question_id"] == seeds[cand["id"]]["question_id"], cand["id"]
        DecisionRecord.model_validate(cand)
    assert any(c["question_id"] is not None for c in req["candidates"])


@pytest.mark.parametrize("name", ["ask", "briefing"])
def test_c06_candidates_are_copies_of_seed_records(request_fixture, case_data, name):
    """brain_api.md request fixtures: "ask and briefing send five of the seed records (m01 ja and
    en, m02, m04 and the checkpoint record without a moment), exactly as in seed_records.json"."""
    req = request_fixture(name)
    seeds = {r["id"]: r for r in case_data["seeds"]}
    assert len(req["candidates"]) == 5
    for cand in req["candidates"]:
        assert cand == seeds[cand["id"]], cand["id"]


# --- criterion 2 (12d) on the fixture: question_id too ------------------------------------------


def test_c02_extract_fixture_draft_names_its_question(extract_ok, request_fixture, endpoints):
    """#5 12d + #10 rule 5 on extract.request.json: it validates, its response quotes appear in
    answer.text, and the draft names m01.q1."""
    req = request_fixture("extract")
    endpoints["extract"].request.model_validate(req)
    out = extract_ok(req)
    assert out["draft"]["question_id"] == req["question"]["id"] == "case-fixture-01.m01.q1"
    assert out["draft"]["grounding"]
    for g in out["draft"]["grounding"]:
        assert g["quote"] in req["answer"]["text"], g


# --- criterion 11: brain_api.md states them -----------------------------------------------------


@pytest.fixture(scope="module")
def brain_api_md(paths) -> str:
    text = (paths["contracts"] / "brain_api.md").read_text(encoding="utf-8")
    start = text.index("### `POST /v1/answers/extract`")
    end = text.index("### `POST /v1/translate`")
    return text[start:end]


def _row(section: str, first_cell: str) -> str:
    rows = [line for line in section.splitlines() if line.startswith(f"| {first_cell} |")]
    assert len(rows) == 1, (first_cell, rows)
    return rows[0]


def test_c11_chips_row_forbids_a_chip_on_a_null_field(brain_api_md):
    """Brief criterion 11 (states 1/3): the chips row says chips are only for filled fields and
    that a chip on a null field is invalid (D-056); value is a Bilingual."""
    row = _row(brain_api_md, "`chips[]`")
    assert "value: Bilingual" in row
    assert re.search(r"chip on a null field is invalid", row), row
    assert "D-056" in row


def test_c11_missing_fields_row_is_the_fill_in_prompt(brain_api_md):
    """Brief criterion 11 (states 1/3): missing_fields[] is the missing-field prompt (D-056) and a
    null cue/action must be listed, else the response is invalid."""
    row = _row(brain_api_md, "`missing_fields[]`")
    assert "missing-field prompt" in row and "fill-in" in row, row
    para = brain_api_md[brain_api_md.index("**Unstated cue or action") :]
    para = para.split("\n\n", 1)[0]
    assert "must" in para and "missing_fields[]" in para and "invalid" in para, para
    assert "no chip" in para, para
    assert "Neither the fake nor the real Brain ever fills them from the moment" in para, para


def test_c11_draft_row_states_question_id_and_trust_labels(brain_api_md):
    """Brief criterion 11 (states 5 and 10): the draft row says question_id is question.id and
    maps each answerer_role to its trust_label."""
    row = _row(brain_api_md, "`draft`")
    assert "`question_id` is `question.id`" in row, row
    for role, label in TRUST_BY_ROLE.items():
        assert f"`{role}` → `{label}`" in row, (role, label)


def test_c11_answerer_role_cross_check_is_listed(brain_api_md):
    """Brief criterion 11 (states 7-9): the answerer_role row names the four roles and says ai,
    dataset and narrator don't answer; the cross-checks list the role/question rule with 400
    bad_request on both Brains."""
    row = _row(brain_api_md, "`answerer_role`")
    for role in ("operating_surgeon", "reviewer", "dev_team_simulated", "expert"):
        assert f"`{role}`" in row, role
    for role in ("ai", "dataset", "narrator"):
        assert f"`{role}`" in row, role
    assert "don't answer" in row, row
    checks = next(line for line in brain_api_md.splitlines() if line.startswith("Cross-checks"))
    assert "400 `bad_request`" in checks and "both Brains" in checks, checks
    assert "ANSWER_ROLES" in checks or "ANSWERER_ROLES" in checks, checks
    assert re.search(r"`operating_surgeon` answers an operating question \(`…qN`\)", checks)
    assert re.search(r"`reviewer` a reviewer question \(`…rN`\)", checks)
    assert re.search(r"`dev_team_simulated` and `expert` may answer either", checks)


# --- criterion 12: generated Chip.value is a non-null Bilingual ---------------------------------


def _accepts_null(schema: dict[str, Any]) -> bool:
    if schema.get("type") == "null":
        return True
    if isinstance(schema.get("type"), list) and "null" in schema["type"]:
        return True
    return any(_accepts_null(s) for key in ("anyOf", "oneOf") for s in schema.get(key, []))


def test_c12_fresh_schema_chip_value_is_a_non_null_bilingual(tmp_path, paths):
    """Brief criterion 12: in a fresh `scrubgpt-codegen --out <tmp> --schema-only` run (and in the
    committed file), ExtractResponse's Chip.value is a required, non-null Bilingual. (Freshness
    of all of schema/ + ts/ byte for byte: test_p0_codegen_output.py c18.)"""
    from scrubgpt_contracts.codegen import main

    assert main(["--out", str(tmp_path), "--schema-only"]) == 0
    fresh = (tmp_path / "schema" / "ExtractResponse.schema.json").read_bytes()
    committed = (paths["contracts"] / "schema" / "ExtractResponse.schema.json").read_bytes()
    assert fresh == committed
    chip = json.loads(fresh)["$defs"]["Chip"]
    assert "value" in chip["required"]
    value = chip["properties"]["value"]
    assert not _accepts_null(value), value
    refs = [value.get("$ref")] + [s.get("$ref") for s in value.get("allOf", [])]
    assert "#/$defs/Bilingual" in refs, value


def test_c12_typescript_chip_value_is_bilingual(paths):
    """Brief criterion 12: ts/contracts.ts has `value: Bilingual;` in `interface Chip`, without
    `| null` (the committed file equals a fresh run: c18)."""
    ts = (paths["contracts"] / "ts" / "contracts.ts").read_text(encoding="utf-8")
    blocks = re.findall(r"export interface Chip \{(.*?)\n\}", ts, flags=re.S)
    assert blocks, "no interface Chip"
    for block in blocks:
        assert re.search(r"^\s*value: Bilingual;$", block, flags=re.M), block
        assert "null" not in re.search(r"^\s*value:.*$", block, flags=re.M).group(0)
