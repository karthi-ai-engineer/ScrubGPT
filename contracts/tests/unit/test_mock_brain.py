"""Dev2's unit tests for the fake Brain (`mock_brain/`, D-037), in-process with FastAPI's client."""

import json
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from scrubgpt_contracts.mock_brain import logic
from scrubgpt_contracts.mock_brain.app import create_app
from scrubgpt_contracts.models.brain_api import ENDPOINTS, MAX_AUDIO_BYTES
from scrubgpt_contracts.models.common import ApiError
from scrubgpt_contracts.models.decision_record import DecisionRecordDraft

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "brain_api"
AUDIO = FIXTURES / "transcribe.request.audio.webm"
TRANSCRIBE = ENDPOINTS["transcribe"].path


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def request_body(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.request.json").read_text(encoding="utf-8"))


def post(client: TestClient, name: str, body: dict):
    return client.post(ENDPOINTS[name].path, json=body)


def transcribe(client: TestClient, **form: str):
    fields = {**request_body("transcribe"), **form}
    files = {"audio": (AUDIO.name, AUDIO.read_bytes(), "application/octet-stream")}
    return client.post(ENDPOINTS["transcribe"].path, data=fields, files=files)


def test_health_reports_mock(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["mode"] == "mock"
    assert body["contract_version"] == "1.0"


@pytest.mark.parametrize("name", [n for n in ENDPOINTS if n not in ("health", "transcribe")])
def test_every_fixture_gets_a_valid_response(client: TestClient, name: str) -> None:
    response = post(client, name, request_body(name))
    assert response.status_code == 200, response.text
    ENDPOINTS[name].response.model_validate(response.json())


@pytest.mark.parametrize("name", [n for n in ENDPOINTS if n != "health"])
def test_empty_request_is_400_bad_request(client: TestClient, name: str) -> None:
    response = client.post(
        ENDPOINTS[name].path, **({"data": {}} if name == "transcribe" else {"json": {}})
    )
    assert response.status_code == 400
    error = ApiError.model_validate(response.json())
    assert error.error.code.value == "bad_request"


def test_unknown_path_is_404_not_found(client: TestClient) -> None:
    response = client.get("/v1/nothing")
    assert response.status_code == 404
    assert ApiError.model_validate(response.json()).error.code.value == "not_found"


def test_transcribe_language_follows_the_hint(client: TestClient) -> None:
    assert transcribe(client, lang_hint="auto").json()["lang"] == "ja"
    assert transcribe(client, lang_hint="ja").json()["text"] == logic.TRANSCRIPTS[logic.Lang.JA]
    assert transcribe(client, lang_hint="en").json()["text"] == logic.TRANSCRIPTS[logic.Lang.EN]
    assert transcribe(client, lang_hint="fr").status_code == 400


def test_transcribe_accepts_any_content_type(client: TestClient) -> None:
    for content_type in ("audio/webm", "video/webm", "audio/mp4", "application/octet-stream"):
        files = {"audio": (AUDIO.name, AUDIO.read_bytes(), content_type)}
        response = client.post(
            ENDPOINTS["transcribe"].path, data=request_body("transcribe"), files=files
        )
        assert response.status_code == 200, content_type


def test_transcribe_too_large_is_413(client: TestClient) -> None:
    files = {"audio": ("big.webm", b"\0" * (MAX_AUDIO_BYTES + 1), "audio/webm")}
    response = client.post(
        ENDPOINTS["transcribe"].path, data=request_body("transcribe"), files=files
    )
    assert response.status_code == 413
    assert ApiError.model_validate(response.json()).error.code.value == "payload_too_large"


def test_embed_is_deterministic_normalised_and_handles_japanese() -> None:
    a = logic.embed_text("静脈性のにじみ")
    assert a == logic.embed_text("静脈性のにじみ")
    assert len(a) == logic.EMBED_DIM
    assert math.isclose(sum(x * x for x in a), 1.0)
    assert logic.tokens("ＡＢＣ Venous") == ["abc", "venous"]  # NFKC + lowercase
    assert logic.tokens("静脈性") == ["静脈", "脈性"]  # CJK bigrams
    assert logic.cosine(a, logic.embed_text("静脈性の出血")) > 0.3
    assert logic.embed_text("!!!") == [0.0] * logic.EMBED_DIM


def test_ask_coverage_rule(client: TestClient) -> None:
    body = request_body("ask")
    full = post(client, "ask", body).json()
    assert full["coverage"] == "full"
    candidate_ids = {r["id"] for r in body["candidates"]}
    assert {c["record_id"] for c in full["citations"]} <= candidate_ids

    partial = post(client, "ask", {**body, "query": "静脈性の出血"}).json()
    assert partial["coverage"] == "partial"
    assert len(partial["citations"]) == 1

    none = post(client, "ask", {**body, "query": "zzz"}).json()
    assert none["coverage"] == "none"
    assert none["citations"] == []

    empty = post(client, "ask", {**body, "candidates": []}).json()
    assert empty["coverage"] == "none"


def test_extract_canned_draft_for_fixture_question(client: TestClient) -> None:
    body = request_body("extract")
    result = post(client, "extract", body).json()
    draft = result["draft"]
    assert draft["id"] is None
    assert draft["moment_id"] == body["moment"]["id"]
    assert draft["provenance"]["trust_label"] == "operating_surgeon"
    assert draft["provenance"]["confirmed_by"] is None
    answer_ids = {e["answer_id"] for e in draft["evidence"] if "answer_id" in e}
    assert answer_ids == {body["answer"]["answer_id"]}
    assert "anticipation" in result["missing_fields"]


def _m05_request(body: dict, **question: object) -> dict:
    m05 = "case-fixture-01.m05"  # no fixture record for m05
    moment = dict(body["moment"], id=m05, clip=f"clips/{m05}.mp4", poster=f"clips/{m05}.jpg")
    asked = dict(body["question"], id=f"{m05}.q9", moment_id=m05, **question)
    return {**body, "moment": moment, "question": asked, "answerer_role": "reviewer"}


def test_extract_generic_draft_never_invents(client: TestClient) -> None:
    # D-054, D-056: the answer fills only the field the question asks about (a cue question
    # here); the action stays null, listed as missing with no chip, never taken from the moment.
    from scrubgpt_contracts.models.decision_record import ungrounded_fields

    body = request_body("extract")
    result = post(client, "extract", _m05_request(body)).json()
    draft = result["draft"]
    assert draft["provenance"]["trust_label"] == "reviewer"
    assert draft["situation_cue"]["text"]["ja"] == body["answer"]["text"]
    assert draft["action"]["text"] is None
    assert draft["action"]["actor"] == "unknown"
    assert draft["reason"] is None and draft["alternatives"] == []
    assert {"action.text", "reason", "alternatives", "obstacle"} <= set(result["missing_fields"])
    assert "action.text" not in {chip["field"] for chip in result["chips"]}
    assert draft["grounding"] == [
        {"field": "situation_cue.text", "quote": body["answer"]["text"], "source": "answer"}
    ]
    assert ungrounded_fields(DecisionRecordDraft.model_validate(draft)) == []


@pytest.mark.parametrize(
    ("question_type", "field"),
    [("reason", "reason"), ("alternatives", "alternatives[0].option"), ("decision", "action.text")],
)
def test_extract_generic_field_follows_the_question(
    client: TestClient, question_type: str, field: str
) -> None:
    body = request_body("extract")
    request = _m05_request(body, type=question_type, tap_options=[])
    draft = post(client, "extract", request).json()["draft"]
    assert [g["field"] for g in draft["grounding"]] == [field]


def test_extract_rejected_without_text_states_nothing(client: TestClient) -> None:
    body = request_body("extract")
    request = _m05_request(body)
    request["answer"] = dict(
        body["answer"], mode="tap", tap={"verdict": "reject", "choice_ids": []}, text=None
    )
    result = post(client, "extract", request).json()
    draft = result["draft"]
    assert draft["situation_cue"]["text"] is None and draft["action"]["text"] is None
    assert draft["grounding"] == []
    assert {"situation_cue.text", "action.text"} <= set(result["missing_fields"])
    assert result["chips"] == []
    assert result["readback"]["en"].startswith("(Mock)")


def test_translate_keeps_the_source_half_verbatim(client: TestClient) -> None:
    body = request_body("translate")
    items = post(client, "translate", body).json()["items"]
    for item, text in zip(items, body["texts"], strict=True):
        assert item[text["from_lang"]] == text["text"]


def test_briefing_cites_only_candidates(client: TestClient) -> None:
    body = request_body("briefing")
    sections = post(client, "briefing", body).json()["sections"]
    candidate_ids = {r["id"] for r in body["candidates"]}
    cited = {c["record_id"] for s in sections for c in s["citations"]}
    assert cited == candidate_ids
    assert "%" not in json.dumps(sections)


def _m02_request(lang: str) -> dict:
    case_dir = FIXTURES.parent / "cases" / "case-fixture-01"
    read = lambda name: json.loads((case_dir / name).read_text(encoding="utf-8"))  # noqa: E731
    question = next(q for q in read("questions.json")["operating"] if q["id"].endswith("m02.q1"))
    moment = next(m for m in read("moments.json")["moments"] if m["id"] == question["moment_id"])
    body = request_body("extract")
    reference = json.loads((FIXTURES.parent / "reference" / "rarp.json").read_text("utf-8"))
    step = next(s for p in reference["phases"] for s in p["steps"] if s["id"] == moment["step_id"])
    answer = dict(body["answer"], lang=lang, text="I lifted the lobe first.")
    context = dict(body["case_context"], step=step)
    return {
        **body,
        "question": question,
        "moment": moment,
        "case_context": context,
        "answer": answer,
    }


def test_extract_canned_only_in_the_answer_language(client: TestClient) -> None:
    # D-054: m02 has only a Japanese seed record.
    english = post(client, "extract", _m02_request("en")).json()["draft"]
    assert english["language"] == "en"
    assert english["kind"] == "anticipatory"
    assert english["grounding"][0]["quote"] == "I lifted the lobe first."
    japanese = post(client, "extract", _m02_request("ja")).json()["draft"]
    assert japanese["language"] == "ja"
    assert japanese["provenance"]["generated_by"]["prompt_version"] == "extract.mock.v1"
    assert japanese["reason"] is not None  # the canned seed record


def test_extract_fixture_quotes_come_from_the_request(client: TestClient) -> None:
    body = request_body("extract")
    draft = post(client, "extract", body).json()["draft"]
    assert draft["grounding"]
    for item in draft["grounding"]:
        assert item["quote"] in body["answer"]["text"]
