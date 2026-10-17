"""The answer loop on the server (J3 + I2 + I7), against the fake Brain in-process."""

import threading
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from scrubgpt_app.api import create_app
from scrubgpt_app.brain_client import BrainClient, BrainError
from scrubgpt_app.settings import REPO_ROOT, Settings
from scrubgpt_app.store import KnowledgeStore
from scrubgpt_contracts.mock_brain.app import create_app as create_fake_brain
from scrubgpt_contracts.models.common import ApiError
from scrubgpt_contracts.models.decision_record import DecisionRecord

FIXTURES = REPO_ROOT / "contracts" / "fixtures"
CASE_ID = "case-fixture-01"
Q1 = f"{CASE_ID}.m01.q1"
AUDIO = FIXTURES / "brain_api" / "transcribe.request.audio.webm"


def fake_brain() -> BrainClient:
    http = TestClient(create_fake_brain(), base_url="http://fake-brain")
    return BrainClient("http://fake-brain", http=http, mode="mock")


@pytest.fixture
def app_and_store(tmp_path: Path):
    environ = {"DATA_DIR": str(FIXTURES), "APP_DB_PATH": str(tmp_path / "store.sqlite")}
    settings = replace(Settings.load(environ, dotenv=False), web_dist=Path("/nonexistent"))
    store = KnowledgeStore(settings.db_path)
    app = create_app(settings, brain=fake_brain(), store=store)
    return TestClient(app), store, settings


def text_answer(text: str, lang: str = "ja") -> dict:
    return {"mode": "text", "tap": None, "text": text, "lang": lang, "audio_uri": None}


def draft(client: TestClient, answer: dict, question_id: str = Q1, role: str = "operating_surgeon"):
    body = {"case_id": CASE_ID, "question_id": question_id, "answerer_role": role, "answer": answer}
    return client.post("/api/answers/draft", json=body)


def test_seeds_are_in_the_store_at_start(app_and_store) -> None:
    client, store, _ = app_and_store
    stored = client.get(f"/api/cases/{CASE_ID}/records").json()["records"]
    assert stored and {item["source"] for item in stored} == {"seed"}
    assert len(stored) == len(store.for_case(CASE_ID))


def test_answer_queue_comes_from_questions_json(app_and_store) -> None:
    client, _, _ = app_and_store
    queue = client.get(f"/api/cases/{CASE_ID}/answer-queue?role=operating").json()
    ids = [item["question"]["id"] for item in queue["questions"]]
    assert ids and all(".q" in qid for qid in ids)
    assert queue["questions"][0]["clip"].startswith(f"/media/cases/{CASE_ID}/clips/")
    reviewer = client.get(f"/api/cases/{CASE_ID}/answer-queue?role=reviewer").json()
    assert all(".r" in item["question"]["id"] for item in reviewer["questions"])
    assert client.get(f"/api/cases/{CASE_ID}/answer-queue?role=x").status_code == 400


def test_draft_assigns_a_uuid7_answer_id(app_and_store) -> None:
    client, _, _ = app_and_store
    body = draft(client, text_answer("結紮部の近くからにじみが出ました")).json()
    assert body["answer_id"][14] == "7"  # UUID version 7
    extract = body["extract"]
    assert extract["draft"]["question_id"] == Q1
    assert extract["draft"]["provenance"]["trust_label"] == "operating_surgeon"


def test_a_reviewer_on_an_operating_question_is_400(app_and_store) -> None:
    client, _, _ = app_and_store
    response = draft(client, text_answer("x"), role="reviewer")
    assert response.status_code == 400
    assert ApiError.model_validate(response.json()).error.code.value == "bad_request"


def test_voice_answer_is_kept_and_transcribed(app_and_store) -> None:
    client, _, settings = app_and_store
    files = {"audio": ("a.webm", AUDIO.read_bytes(), "audio/webm")}
    body = client.post("/api/answers/audio", data={"lang_hint": "ja"}, files=files).json()
    assert body["lang"] == "ja" and body["text"]
    assert body["audio_uri"] == f"answers/{body['answer_id']}.webm"
    stored = settings.db_path.parent / body["audio_uri"]
    assert stored.read_bytes() == AUDIO.read_bytes()
    assert client.get(f"/media/{body['audio_uri']}").content == AUDIO.read_bytes()
    assert client.get("/media/answers/..%2Fstore.sqlite").status_code == 404


def confirm(client: TestClient, answer_id: str, draft_body: dict, edits=(), by="Dr Test"):
    body = {"answer_id": answer_id, "draft": draft_body, "edits": list(edits), "confirmed_by": by}
    return client.post("/api/answers/confirm", json=body)


def test_confirm_stores_a_new_record_and_never_merges(app_and_store) -> None:
    client, store, _ = app_and_store
    before = len(store.for_moment(f"{CASE_ID}.m01"))
    body = draft(client, text_answer("結紮部の近くから静脈性のにじみが出てきました。")).json()
    response = confirm(client, body["answer_id"], body["extract"]["draft"])
    assert response.status_code == 201, response.text
    record = DecisionRecord.model_validate(response.json()["record"])
    assert record.provenance.confirmed_by == "Dr Test"
    assert record.question_id == Q1
    assert len(store.for_moment(f"{CASE_ID}.m01")) == before + 1
    assert store.get(str(record.id)).source == "answer"


def test_an_unstated_cue_must_be_filled_before_confirm(app_and_store) -> None:
    client, _, _ = app_and_store
    # m05.q1 has no seed record: the generic draft fills only the asked field.
    answer = {"mode": "tap", "tap": {"verdict": "reject", "choice_ids": []}, "text": None,
              "lang": "en", "audio_uri": None}  # fmt: skip
    body = draft(client, answer, question_id=f"{CASE_ID}.m05.q1").json()
    missing = body["extract"]["missing_fields"]
    assert "situation_cue.text" in missing and "action.text" in missing
    refused = confirm(client, body["answer_id"], body["extract"]["draft"])
    assert refused.status_code == 400
    edits = [
        {"field": "situation_cue.text", "text": "Oozing near the ligature", "lang": "en"},
        {"field": "action.text", "text": "Raised the pressure", "lang": "en"},
    ]
    record = confirm(client, body["answer_id"], body["extract"]["draft"], edits).json()["record"]
    assert record["situation_cue"]["text"]["en"] == "Oozing near the ligature"
    assert record["situation_cue"]["text"]["ja"]  # the other half from /translate
    groundings = {g["field"]: g for g in record["grounding"]}
    assert groundings["action.text"] == {
        "field": "action.text",
        "quote": "Raised the pressure",
        "source": "edit",
    }


def test_edits_only_on_surgeon_fields(app_and_store) -> None:
    client, _, _ = app_and_store
    body = draft(client, text_answer("にじみ")).json()
    edits = [{"field": "provenance.trust_label", "text": "expert", "lang": "en"}]
    response = confirm(client, body["answer_id"], body["extract"]["draft"], edits)
    assert response.status_code == 400


def test_confirm_publishes_three_events_in_order(app_and_store) -> None:
    client, _, _ = app_and_store
    app = client.app
    seen: list[str] = []
    ready = threading.Event()

    async def listen() -> None:
        async with app.state.events.subscribe() as queue:
            ready.set()
            for _ in range(3):
                seen.append((await queue.get()).name)

    with client:  # runs the app's event loop in the portal thread
        future = client.portal.start_task_soon(listen)
        ready.wait(5)
        body = draft(client, text_answer("にじみが出ました")).json()
        confirm(client, body["answer_id"], body["extract"]["draft"])
        future.result(5)
    assert seen == ["answer.confirmed", "record.created", "graph.updated"]


def test_brain_down_is_503_unavailable(tmp_path: Path) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    brain = BrainClient("http://nowhere", transport=httpx.MockTransport(refuse))
    environ = {"DATA_DIR": str(FIXTURES), "APP_DB_PATH": str(tmp_path / "s.sqlite")}
    settings = replace(Settings.load(environ, dotenv=False), web_dist=Path("/nonexistent"))
    client = TestClient(create_app(settings, brain=brain))
    response = draft(client, text_answer("にじみ"))
    assert response.status_code == 503
    error = ApiError.model_validate(response.json()).error
    assert error.code.value == "unavailable" and error.retryable


def test_off_contract_brain_answer_is_an_upstream_error() -> None:
    brain = BrainClient(
        "http://x", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": 1}))
    )
    with pytest.raises(BrainError) as info:
        brain.health()
    assert info.value.code.value == "upstream_error"


def test_brain_error_body_is_passed_through() -> None:
    body = {
        "contract_version": "1.0",
        "error": {"code": "timeout", "message": "slow", "retryable": True},
    }
    brain = BrainClient(
        "http://x", transport=httpx.MockTransport(lambda r: httpx.Response(504, json=body))
    )
    with pytest.raises(BrainError) as info:
        brain.health()
    assert info.value.code.value == "timeout" and info.value.unavailable
