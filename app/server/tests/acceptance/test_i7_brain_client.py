"""I7 Brain client acceptance (brief criterion 4).

Sources: plan §2.9 I7 ("Switchable between the fake Brain (HTTP, MOCK_BRAIN_URL :8101, D-025)
and the real Brain API"), §4.1 `ApiError` (codes and HTTP statuses; "The app shows 'Brain
unavailable' for 503 and 504"), §4.4; contracts/brain_api.md "Errors" and "Endpoints";
app/server/CLAUDE.md rule 1 ("BRAIN_MODE=mock calls the fake Brain at MOCK_BRAIN_URL";
"BRAIN_MODE=real calls the real Brain API at BRAIN_URL"; "Handle ApiError … Map 503 and 504 to
'Brain unavailable'"); D-071 ("I7 is coded to the contract shapes, not the fake Brain's canned
behaviour; I7 real mode is chosen by BRAIN_MODE/BRAIN_URL only"); app/server/README.md "Brain
client (I7)" ("Requests and responses are validated against the contract models both ways. A
Brain error passes through as its ApiError (same code and status); an unreachable Brain is 503
unavailable, a slow one 504 timeout …; an off-contract answer is 502 upstream_error").

Entry points: `scrubgpt_app.brain_client.BrainClient` (`from_settings`, `transport=`, `http=`)
and the app server (`create_app(settings, brain=...)`).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import httpx
import pytest
from scrubgpt_contracts.models.brain_api import (
    ExtractRequest,
    ExtractResponse,
    HealthResponse,
    TranscribeForm,
    TranslateRequest,
    TranslateResponse,
)
from scrubgpt_contracts.models.common import ApiError
from uuid6 import uuid7

CASE = "case-fixture-01"
FIXTURE_REQUESTS = Path(__file__).resolve().parents[4] / "contracts" / "fixtures" / "brain_api"

# plan §4.1: code → HTTP status.
ERRORS = {
    "bad_request": 400,
    "not_found": 404,
    "payload_too_large": 413,
    "unavailable": 503,
    "upstream_error": 502,
    "refused": 502,
    "timeout": 504,
}


def _api_error(code: str) -> httpx.Response:
    return httpx.Response(
        ERRORS[code],
        json={
            "contract_version": "1.0",
            "error": {"code": code, "message": f"{code} from the Brain", "retryable": False},
        },
    )


def _extract_request() -> ExtractRequest:
    raw = json.loads((FIXTURE_REQUESTS / "extract.request.json").read_text(encoding="utf-8"))
    return ExtractRequest.model_validate(raw)


def _brain_error():
    from scrubgpt_app.brain_client import BrainError

    return BrainError


# --- mode → URL -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "expected_host"),
    [("mock", "mock-brain.test:9101"), ("real", "real-brain.test:9100")],
)
def test_c4_brain_mode_picks_the_url(make_settings, data_dir, mode, expected_host):
    """Criterion 4 (rule 1): "BRAIN_MODE=mock → MOCK_BRAIN_URL, real → BRAIN_URL"."""
    from scrubgpt_app.brain_client import BrainClient

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.url.host}:{request.url.port}{request.url.path}")
        return httpx.Response(
            200,
            json={
                "contract_version": "1.0",
                "status": "ok",
                "mode": mode,
                "model_tiers": {},
                "cache_mode": "off",
            },
        )

    settings = make_settings(
        data_dir,
        BRAIN_MODE=mode,
        MOCK_BRAIN_URL="http://mock-brain.test:9101",
        BRAIN_URL="http://real-brain.test:9100",
    )
    client = BrainClient.from_settings(settings, transport=httpx.MockTransport(handler))
    try:
        client.health()
    finally:
        client.close()
    assert seen == [f"{expected_host}/health"]


@pytest.mark.parametrize("mode", ["mock", "real"])
def test_c4_the_app_calls_the_url_of_its_brain_mode(make_settings, data_dir, mode):
    """Criterion 4 (rule 1, D-071 "real mode is chosen by BRAIN_MODE/BRAIN_URL only"): the app
    server built without `brain=` reaches the Brain of its mode; nothing listens on either port
    here, so `/api/brain/health` is 503 `unavailable` (never a call to the other URL)."""
    import socket

    from fastapi.testclient import TestClient
    from scrubgpt_app.api import create_app

    ports = []
    for _ in range(2):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            ports.append(sock.getsockname()[1])
    settings = make_settings(
        data_dir,
        BRAIN_MODE=mode,
        MOCK_BRAIN_URL=f"http://127.0.0.1:{ports[0]}",
        BRAIN_URL=f"http://127.0.0.1:{ports[1]}",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["brain_mode"] == mode
        response = client.get("/api/brain/health")
    assert response.status_code == 503
    body = ApiError.model_validate(response.json())
    assert body.error.code.value == "unavailable"


def test_c4_mock_mode_reaches_a_running_fake_brain(make_settings, data_dir, uvicorn_thread):
    """Criterion 4: with BRAIN_MODE=mock and MOCK_BRAIN_URL pointing at a running fake Brain, the
    app's `/api/brain/health` is the fake Brain's `/health` (`mode: mock`, plan §4.5)."""
    from fastapi.testclient import TestClient
    from scrubgpt_app.api import create_app
    from scrubgpt_contracts.mock_brain.app import create_app as create_brain

    brain = uvicorn_thread(create_brain())
    settings = make_settings(data_dir, BRAIN_MODE="mock", MOCK_BRAIN_URL=brain.base_url)
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/brain/health")
    assert response.status_code == 200, response.text
    health = HealthResponse.model_validate(response.json())
    assert health.mode.value == "mock"
    assert response.json()["contract_version"].startswith("1.")


# --- contract shapes both ways ----------------------------------------------------------------


def test_c4_extract_sends_the_contract_request_and_returns_a_validated_response(wire_brain):
    """Criterion 4: "Requests are the contract shapes; responses are validated against the
    contract models"."""
    brain, wire = wire_brain()
    request = _extract_request()
    response = brain.extract(request)
    assert isinstance(response, ExtractResponse)
    sent = wire.json_bodies("/v1/answers/extract")
    assert len(sent) == 1
    assert ExtractRequest.model_validate(sent[0]) == request
    # Every v1.0 key is sent (D-034), nothing renamed: the fixture request's keys all arrive.
    fixture = json.loads((FIXTURE_REQUESTS / "extract.request.json").read_text(encoding="utf-8"))
    assert set(fixture) <= set(sent[0])
    assert set(fixture["answer"]) <= set(sent[0]["answer"])
    assert set(fixture["case_context"]) <= set(sent[0]["case_context"])


def test_c4_translate_and_transcribe_use_the_contract_shapes(wire_brain):
    """Criterion 4: `/v1/translate` (JSON) and `/v1/answers/transcribe` (multipart: `audio`,
    `lang_hint`, `answer_id`; brain_api.md) in the contract shapes."""
    brain, wire = wire_brain()
    out = brain.translate(
        TranslateRequest.model_validate({"texts": [{"text": "出血", "from_lang": "ja"}]})
    )
    assert isinstance(out, TranslateResponse)
    assert out.items[0].ja == "出血"
    TranslateRequest.model_validate(wire.json_bodies("/v1/translate")[0])

    audio = (FIXTURE_REQUESTS / "transcribe.request.audio.webm").read_bytes()
    answer_id = str(uuid7())
    form = TranscribeForm.model_validate({"lang_hint": "auto", "answer_id": answer_id})
    heard = brain.transcribe(form, audio, "answer.webm", "audio/webm")
    assert heard.lang.value == "ja"  # plan §4.5: `lang_hint=auto` returns the JA sentence
    [(_, _, headers, body)] = [c for c in wire.calls if c[1] == "/v1/answers/transcribe"]
    assert headers["content-type"].startswith("multipart/form-data")
    assert audio in body
    assert b'name="lang_hint"' in body and b'name="answer_id"' in body
    assert answer_id.encode() in body
    assert b'name="audio"' in body


@pytest.mark.parametrize(
    "broken",
    [
        "empty_object",
        "missing_contract_version",
        "wrong_type",
        "chip_on_null_field",
        "not_json",
    ],
)
def test_c4_an_off_contract_response_is_502_upstream_error(wire_brain, broken):
    """Criterion 4: "an off-contract response → 502 upstream_error" (README: responses are
    validated against the contract models)."""
    brain_ok, _ = wire_brain()
    good = brain_ok.extract(_extract_request()).model_dump(mode="json")

    bad = copy.deepcopy(good)
    if broken == "empty_object":
        bad = {}
    elif broken == "missing_contract_version":
        del bad["contract_version"]
    elif broken == "wrong_type":
        bad["readback"] = "only one language"
    elif broken == "chip_on_null_field":
        bad["draft"]["action"]["text"] = None
        if "action.text" not in bad["missing_fields"]:
            bad["missing_fields"].append("action.text")
        bad["chips"].append(
            {"field": "action.text", "value": {"ja": "作り話", "en": "Made up"}, "editable": True}
        )

    def respond(request: httpx.Request):
        if broken == "not_json":
            return httpx.Response(
                200, content=b"<html>oops</html>", headers={"content-type": "text/html"}
            )
        return httpx.Response(200, json=bad)

    brain, _ = wire_brain(respond)
    BrainError = _brain_error()
    with pytest.raises(BrainError) as caught:
        brain.extract(_extract_request())
    assert caught.value.code.value == "upstream_error"


# --- ApiError pass-through, unreachable, slow -------------------------------------------------


@pytest.mark.parametrize("code", list(ERRORS))
def test_c4_the_brains_api_error_passes_through_the_client(wire_brain, code):
    """Criterion 4: "the Brain's ApiError passes through with its code and status"."""
    brain, _ = wire_brain(lambda request: _api_error(code))
    BrainError = _brain_error()
    with pytest.raises(BrainError) as caught:
        brain.extract(_extract_request())
    assert caught.value.code.value == code


@pytest.mark.parametrize("code", list(ERRORS))
def test_c4_the_brains_api_error_passes_through_the_app_server(
    answer_app, data_dir, draft_for, code
):
    """Criterion 4 through the app: `POST /api/answers/draft` answers with the Brain's ApiError,
    same code and HTTP status (plan §4.1)."""

    def override(request: httpx.Request):
        return _api_error(code) if request.url.path == "/v1/answers/extract" else None

    app = answer_app(data_dir, override=override)
    status, body = draft_for(app.client, f"{CASE}.m05.q1")
    assert status == ERRORS[code]
    error = ApiError.model_validate(body)
    assert error.error.code.value == code
    assert body["contract_version"].startswith("1.")


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("connection refused"),
    ],
    ids=["connect_error"],
)
def test_c4_an_unreachable_brain_is_503_unavailable(answer_app, data_dir, draft_for, exc):
    """Criterion 4: "an unreachable Brain → 503 unavailable" (and the UI shows "Brain unavailable",
    rule 1)."""

    def override(request: httpx.Request):
        raise exc

    app = answer_app(data_dir, override=override)
    status, body = draft_for(app.client, f"{CASE}.m05.q1")
    assert status == 503, body
    assert ApiError.model_validate(body).error.code.value == "unavailable"


def test_c4_a_closed_port_is_503_unavailable():
    """Criterion 4: an unreachable Brain over real HTTP (nothing listens on the port)."""
    import socket

    from scrubgpt_app.brain_client import BrainClient

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    client = BrainClient(f"http://127.0.0.1:{port}")
    BrainError = _brain_error()
    try:
        with pytest.raises(BrainError) as caught:
            client.health()
    finally:
        client.close()
    assert caught.value.code.value == "unavailable"


@pytest.mark.parametrize(
    "exc",
    [httpx.ReadTimeout("read timed out"), httpx.WriteTimeout("write timed out")],
    ids=["read_timeout", "write_timeout"],
)
def test_c4_a_slow_brain_is_504_timeout(answer_app, data_dir, draft_for, exc):
    """Criterion 4: "a slow one → 504 timeout"."""

    def override(request: httpx.Request):
        raise exc

    app = answer_app(data_dir, override=override)
    status, body = draft_for(app.client, f"{CASE}.m05.q1")
    assert status == 504, body
    assert ApiError.model_validate(body).error.code.value == "timeout"


@pytest.mark.parametrize("status", [500, 502, 404])
def test_c4_a_non_contract_error_body_is_upstream_error(wire_brain, status):
    """Criterion 4: an error response that isn't an `ApiError` is off-contract → `upstream_error`
    (README: "an off-contract answer is 502 upstream_error")."""
    brain, _ = wire_brain(
        lambda request: httpx.Response(
            status, content=b"Internal Server Error", headers={"content-type": "text/plain"}
        )
    )
    BrainError = _brain_error()
    with pytest.raises(BrainError) as caught:
        brain.extract(_extract_request())
    assert caught.value.code.value == "upstream_error"


def test_c4_translate_through_the_app_is_the_contract_response(answer_app, data_dir):
    """Criterion 4 / rule 1: `/api/translate` goes through the Brain client and returns a
    `TranslateResponse`; rule 10: both `ja` and `en` pass through."""
    app = answer_app(data_dir)
    response = app.client.post(
        "/api/translate", json={"texts": [{"text": "Clip the vessel", "from_lang": "en"}]}
    )
    assert response.status_code == 200, response.text
    parsed = TranslateResponse.model_validate(response.json())
    assert parsed.items[0].en == "Clip the vessel"
    assert parsed.items[0].ja.strip()
    assert app.wire.json_bodies("/v1/translate") == [
        {"texts": [{"text": "Clip the vessel", "from_lang": "en"}]}
    ]
