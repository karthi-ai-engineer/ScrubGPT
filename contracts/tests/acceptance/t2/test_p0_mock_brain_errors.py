"""T2 acceptance: fake Brain error bodies (issue #5 criterion 9, plus the §4.1 error rules).

Sources: issue #5 Team Lead triage c9 and its risk note (the empty transcribe probe sends no
file part); plan §4.1 ApiError (422 -> 400 bad_request, 404 not_found, contract_version);
brain_api.md "Errors" (invalid JSON, a missing multipart part, cross-checks -> 400).
"""

from __future__ import annotations

import pytest

JSON_POST = ("extract", "translate", "embed", "ask", "briefing")


@pytest.mark.parametrize("name", JSON_POST)
def test_c09_empty_json_post_is_400_bad_request(client, endpoints, assert_api_error, name):
    """#5 c9: an empty POST ({}) to each POST endpoint returns HTTP 400 with an ApiError body:
    error.code == "bad_request", plus contract_version. It never returns 422."""
    r = client.post(endpoints[name].path, json={})
    assert r.status_code != 422
    assert_api_error(r, 400, "bad_request")


def test_c09_empty_transcribe_form_without_file_is_400(client, endpoints, assert_api_error):
    """#5 c9: an empty form with no file for transcribe returns 400 bad_request, never 422."""
    path = endpoints["transcribe"].path
    r = client.post(path, files={"lang_hint": (None, ""), "answer_id": (None, "")})
    assert r.status_code != 422
    assert_api_error(r, 400, "bad_request")
    r = client.post(path, data={})
    assert r.status_code != 422
    assert_api_error(r, 400, "bad_request")


def test_c09_transcribe_fields_but_no_audio_part_is_400(
    client, endpoints, request_fixture, assert_api_error
):
    """#5 risk note / brain_api.md: a missing multipart part (audio) -> 400 bad_request."""
    r = client.post(
        endpoints["transcribe"].path,
        files={k: (None, v) for k, v in request_fixture("transcribe").items()},
    )
    assert r.status_code != 422
    assert_api_error(r, 400, "bad_request")


def test_c09_transcribe_audio_but_no_form_fields_is_400(
    client, endpoints, audio_fixture, assert_api_error
):
    """brain_api.md: the body doesn't match the request model (lang_hint, answer_id missing)."""
    r = client.post(
        endpoints["transcribe"].path,
        files={"audio": (audio_fixture.name, audio_fixture.read_bytes(), "audio/webm")},
    )
    assert_api_error(r, 400, "bad_request")


@pytest.mark.parametrize("name", JSON_POST)
def test_c09_invalid_json_is_400(client, endpoints, assert_api_error, name):
    """brain_api.md Errors: invalid JSON -> 400 bad_request."""
    r = client.post(
        endpoints[name].path,
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )
    assert_api_error(r, 400, "bad_request")


@pytest.mark.parametrize("name", JSON_POST)
def test_c09_wrong_types_are_400(client, endpoints, request_fixture, assert_api_error, name):
    """plan §4.1: FastAPI's 422 validation error maps to 400; brain_api.md strict values."""
    body = request_fixture(name)
    key = next(iter(body))
    body[key] = 12345
    r = client.post(endpoints[name].path, json=body)
    assert_api_error(r, 400, "bad_request")


def test_unknown_path_is_404_not_found(client, assert_api_error):
    """plan §4.1 / brain_api.md: unknown path -> 404 not_found ApiError."""
    assert_api_error(client.get("/v1/does-not-exist"), 404, "not_found")
    assert_api_error(client.post("/v1/does-not-exist", json={}), 404, "not_found")


def test_extract_cross_check_question_moment_mismatch_is_400(
    client, endpoints, build_extract, case_data, assert_api_error
):
    """brain_api.md /extract cross-checks: question.moment_id == moment.id, else 400."""
    body = build_extract("case-fixture-01.m01.q1")
    body["moment"] = case_data["moments"]["case-fixture-01.m02"]
    body["case_context"]["step"] = case_data["steps"][body["moment"]["step_id"]]
    assert_api_error(client.post(endpoints["extract"].path, json=body), 400, "bad_request")


def test_extract_cross_check_step_mismatch_is_400(
    client, endpoints, build_extract, case_data, assert_api_error
):
    """brain_api.md /extract cross-checks: case_context.step.id == moment.step_id, else 400."""
    body = build_extract("case-fixture-01.m01.q1")
    other = next(s for sid, s in case_data["steps"].items() if sid != body["moment"]["step_id"])
    body["case_context"]["step"] = other
    assert_api_error(client.post(endpoints["extract"].path, json=body), 400, "bad_request")


def test_ask_duplicate_candidate_ids_is_400(client, endpoints, request_fixture, assert_api_error):
    """brain_api.md /ask: candidate ids unique (else 400)."""
    body = request_fixture("ask")
    body["candidates"] = [body["candidates"][0], body["candidates"][0]]
    assert_api_error(client.post(endpoints["ask"].path, json=body), 400, "bad_request")
