"""T2 acceptance: fake Brain /v1/answers/extract (brief criterion 15).

Sources: plan §4.3 (DecisionRecordDraft: id and confirmation fields null; a field the surgeon
did not state is null; trust_label follows the answerer: operating_surgeon, reviewer, or
simulated for role-play); plan §4.4 (draft, readback, chips[], missing_fields[]); D-034
(answer_id assigned by the app and sent to /extract); brain_api.md /extract (chip field exists in
draft and is non-null, value is its current value; missing_fields each null or [] in the draft;
answer evidence uses the request's answer_id; attributed_to = answerer_role; the request's
moment_id; generic draft for a question with no fixture record).
"""

from __future__ import annotations

from typing import Any

import pytest

PATH = "/v1/answers/extract"
TRUST_BY_ROLE = {
    "operating_surgeon": "operating_surgeon",
    "reviewer": "reviewer",
    "dev_team_simulated": "simulated",
}
ALL_QUESTIONS = (
    "case-fixture-01.m01.q1",
    "case-fixture-01.m01.q2",
    "case-fixture-01.m02.q1",
    "case-fixture-01.m02.q2",
    "case-fixture-01.m03.q1",
    "case-fixture-01.m04.q1",
    "case-fixture-01.m05.q1",
    "case-fixture-01.m06.q1",
    "case-fixture-01.m01.r1",
    "case-fixture-01.m01.r2",
    "case-fixture-01.m02.r1",
    "case-fixture-01.m04.r1",
)
# Moments with no seed record for the moment or (moment-less records) its step: m05, m06.
NO_FIXTURE_RECORD = ("case-fixture-01.m05.q1", "case-fixture-01.m06.q1")


@pytest.fixture
def extract(client, endpoints):
    def run(body: dict[str, Any]) -> dict[str, Any]:
        r = client.post(PATH, json=body)
        assert r.status_code == 200, r.text[:800]
        out = r.json()
        endpoints["extract"].response.model_validate(out)
        assert out["contract_version"] == "1.0"
        return out

    return run


def _check_draft_basics(out, req, get_path, MISSING):  # noqa: N803
    from scrubgpt_contracts.models.decision_record import DecisionRecordDraft

    draft = out["draft"]
    DecisionRecordDraft.model_validate(draft)
    # §4.3: id and the confirmation fields are null
    assert draft["id"] is None
    assert draft["provenance"]["confirmed_by"] is None
    assert draft["provenance"]["confirmed_at"] is None
    # brain_api.md: the request's moment_id; case and step follow the request
    assert draft["moment_id"] == req["moment"]["id"]
    assert draft["case_id"] == req["case_context"]["case"]["id"]
    assert draft["step_id"] == req["moment"]["step_id"]
    # answer evidence carries the request's answer_id
    answer_ev = [e for e in draft["evidence"] if e["kind"] in ("answer_text", "answer_audio")]
    assert answer_ev, "draft has no answer evidence"
    for e in answer_ev:
        assert e["answer_id"] == req["answer"]["answer_id"], e
    # chips: field exists in the draft, is non-null, and value is its current value
    for chip in out["chips"]:
        value = get_path(draft, chip["field"])
        assert value is not MISSING, chip["field"]
        assert value is not None, chip["field"]
        assert chip["value"] == value, chip["field"]
    # missing_fields: each null or [] in the draft
    for path in out["missing_fields"]:
        value = get_path(draft, path)
        assert value is not MISSING, f"missing_fields path {path} doesn't exist in the draft"
        assert value is None or value == [], (path, value)
    return draft


@pytest.mark.parametrize("role", sorted(TRUST_BY_ROLE))
def test_c15_fixture_request_draft_shape_and_trust_label(
    extract,
    request_fixture,
    new_uuid7,
    get_path,
    MISSING,
    role,  # noqa: N803
):
    """Brief c15 on extract.request.json: draft validates as DecisionRecordDraft; id null;
    confirmed_by/confirmed_at null; trust_label follows answerer_role; answer evidence carries
    the request's answer_id (a fresh one, not the fixture's); chips and missing_fields hold."""
    req = request_fixture("extract")
    req["answerer_role"] = role
    req["answer"]["answer_id"] = new_uuid7()
    out = extract(req)
    draft = _check_draft_basics(out, req, get_path, MISSING)
    assert draft["provenance"]["trust_label"] == TRUST_BY_ROLE[role]
    assert draft["provenance"]["attributed_to"] == role


def test_c15_expert_answerer_is_expert_validated(extract, build_extract, get_path, MISSING):  # noqa: N803
    """brain_api.md /extract: expert -> expert_validated; attributed_to = answerer_role."""
    req = build_extract("case-fixture-01.m02.q2", role="expert")
    draft = _check_draft_basics(extract(req), req, get_path, MISSING)
    assert draft["provenance"]["trust_label"] == "expert_validated"
    assert draft["provenance"]["attributed_to"] == "expert"


@pytest.mark.parametrize("role", sorted(TRUST_BY_ROLE))
@pytest.mark.parametrize("question_id", ALL_QUESTIONS)
def test_c15_every_fixture_question(
    extract,
    build_extract,
    get_path,
    MISSING,
    question_id,
    role,  # noqa: N803
):
    """Brief c15 for every fixture question (canned and generic), each answerer role."""
    req = build_extract(question_id, role=role)
    draft = _check_draft_basics(extract(req), req, get_path, MISSING)
    assert draft["provenance"]["trust_label"] == TRUST_BY_ROLE[role]
    assert draft["provenance"]["attributed_to"] == role


def _assert_unstated_fields_null(draft):
    """§4.3 / guardrail "never invent reasoning": what the answer didn't state stays null
    (or [])."""
    for key in ("anticipation", "reason", "immediate_result", "obstacle"):
        assert draft[key] is None, (key, draft[key])
    assert draft["context"]["preop_plan"] is None
    assert draft["context"]["patient_factors"] == []
    assert draft["alternatives"] == []
    assert draft["delayed_outcome"]["text"] is None


@pytest.mark.parametrize("question_id", NO_FIXTURE_RECORD)
def test_c15_no_fixture_record_text_answer_keeps_unstated_fields_null(
    extract,
    build_extract,
    get_path,
    MISSING,
    question_id,  # noqa: N803
):
    """Brief c15: for a question with no fixture record, fields the answer did not state stay
    null; brain_api.md generic draft: the answer becomes action.text, grounded verbatim, and the
    unstated fields are listed in missing_fields."""
    answer = "I wiped the lens with warm saline and carried on."
    req = build_extract(question_id, text=answer, lang="en")
    out = extract(req)
    draft = _check_draft_basics(out, req, get_path, MISSING)
    _assert_unstated_fields_null(draft)
    assert draft["action"]["text"]["en"] == answer
    groundings = [g for g in draft["grounding"] if g["field"] == "action.text"]
    assert groundings and all(g["quote"] in answer for g in groundings)
    for path in ("anticipation", "reason", "immediate_result"):
        assert path in out["missing_fields"], (path, out["missing_fields"])


def test_c15_no_fixture_record_tap_answer_keeps_unstated_fields_null(
    extract,
    build_extract,
    case_data,
    get_path,
    MISSING,  # noqa: N803
):
    """Brief c15 with a tap answer on case-fixture-01.m05.q1 (no fixture record)."""
    qid = "case-fixture-01.m05.q1"
    option = case_data["questions"][qid]["tap_options"][0]["id"]
    req = build_extract(
        qid, mode="tap", text=None, lang="ja", tap={"verdict": "confirm", "choice_ids": [option]}
    )
    draft = _check_draft_basics(extract(req), req, get_path, MISSING)
    _assert_unstated_fields_null(draft)


def test_c15_grounding_points_at_filled_fields(extract, request_fixture, get_path, MISSING):  # noqa: N803
    """brain_api.md / G5: every grounding entry points at a filled field of the draft, with a
    non-empty verbatim quote and source answer|edit|narration."""
    out = extract(request_fixture("extract"))
    for g in out["draft"]["grounding"]:
        value = get_path(out["draft"], g["field"])
        assert value is not MISSING and value is not None, g
        assert g["quote"]
        assert g["source"] in ("answer", "edit", "narration")


def test_c15_deterministic(client, request_fixture):
    """D-037: deterministic: the same request gives the same body."""
    req = request_fixture("extract")
    assert client.post(PATH, json=req).json() == client.post(PATH, json=req).json()
