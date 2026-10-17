"""J3 / I2: the answer queue's `answered` and the methods allowed on stored records (Block 3
re-test, criterion 15).

Criterion 15 (brief, from T2 spec gaps 4-5): "The README states that the answer queue's
`answered` counts only answers given in the app (seed records don't mark a question answered),
and that other methods on stored records are refused with 400, with the behaviour matching."
app/server/README.md "Knowledge store (I2)": "The answer queue's `answered` counts only answers
given in the app; seed records are prior knowledge and don't mark a question answered. Stored
records can't be changed: any other method on them is refused (400)." Plan §4.1: HTTP 400 is
`ApiError` code `bad_request`; README "API": every error is an `ApiError` body.

Entry points: `GET /api/cases/{case_id}/answer-queue?role=…`, `GET|… /api/cases/{case_id}/records`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from scrubgpt_contracts.models.common import ApiError

CASE = "case-fixture-01"
README = Path(__file__).resolve().parents[4] / "app" / "server" / "README.md"


def _store_paragraph() -> str:
    text = README.read_text(encoding="utf-8")
    match = re.search(r"\*\*Knowledge store \(I2\)\.\*\*(.*?)(?:\n\s*\n|\Z)", text, re.S)
    assert match, "README has no 'Knowledge store (I2).' paragraph"
    return match.group(1)


# --- answered counts only answers given in the app ------------------------------------------


def test_c15_the_readme_says_answered_counts_only_app_answers():
    """Criterion 15: the README states that `answered` counts only answers given in the app and
    that seed records don't mark a question answered."""
    para = _store_paragraph()
    assert "answered" in para
    assert re.search(r"only answers given in the app", para), para
    assert re.search(r"seed records .*?(don't|do not) mark a question answered", para, re.S), para


@pytest.mark.parametrize("role", ["operating", "reviewer"])
def test_c15_questions_answered_by_seed_records_are_not_marked_answered(
    answer_app, data_dir, fixture_docs, role
):
    """Criterion 15 behaviour: the fixture's seed records answer questions (m01.q1, m01.r1,
    m02.q1, m04.q1), yet on a fresh store every question is `answered: false` and `est_seconds`
    is the sum over all of them."""
    seeded = {
        r["question_id"]
        for r in fixture_docs["seed_records"]["records"]  # type: ignore[index]
        if r["question_id"] is not None
    }
    questions = fixture_docs["questions"][role]  # type: ignore[index]
    seeded_here = seeded & {q["id"] for q in questions}
    assert seeded_here, "precondition: some seed record answers a question of this role"

    app = answer_app(data_dir)
    stored = app.client.get(f"/api/cases/{CASE}/records").json()["records"]
    assert {i["record"]["question_id"] for i in stored if i["source"] == "seed"} >= seeded_here

    queue = app.client.get(f"/api/cases/{CASE}/answer-queue", params={"role": role})
    assert queue.status_code == 200, queue.text
    body = queue.json()
    answered = {item["question"]["id"]: item["answered"] for item in body["questions"]}
    for qid in seeded_here:
        assert answered[qid] is False, qid
    assert not any(answered.values())
    assert body["est_seconds"] == pytest.approx(sum(q["est_seconds"] for q in questions))


# --- other methods on stored records → 400 ---------------------------------------------------


def test_c15_the_readme_says_other_methods_on_records_are_refused_with_400():
    """Criterion 15: the README states that other methods on stored records are refused (400)."""
    para = _store_paragraph()
    assert re.search(r"any other method on them is refused \(400\)", para), para


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_c15_other_methods_on_stored_records_are_400_bad_request(answer_app, data_dir, method):
    """Criterion 15 behaviour: any method but GET on `/api/cases/{case_id}/records` is refused with
    400 (`ApiError` `bad_request`, plan §4.1), and the stored records are unchanged."""
    app = answer_app(data_dir)
    before = app.client.get(f"/api/cases/{CASE}/records").json()
    record = before["records"][0]["record"]
    response = app.client.request(method, f"/api/cases/{CASE}/records", json={"record": record})
    assert response.status_code == 400, (method, response.status_code, response.text)
    error = ApiError.model_validate(response.json())
    assert error.error.code.value == "bad_request"
    assert app.client.get(f"/api/cases/{CASE}/records").json() == before
