"""AC17: `scrubgpt-validate response <endpoint> <file>` and `live --base-url <url>` (plan §4.1,
§4.5; D-037; registry shape requested in #5).

These tests were written before Dev2's `models/brain_api.py` (the real `ENDPOINTS`) and fake
Brain existed. They use a stand-in registry (injected as `scrubgpt_contracts.models.brain_api`)
and a stand-in HTTP server on 127.0.0.1, both defined here, so they can simulate faulty Brains
and a missing registry. The real registry and fake Brain are tested in
test_p0_live_fake_brain.py and test_p0_d052_exit_codes.py. Nothing leaves the machine.
"""

from __future__ import annotations

import copy
import io
import json
import struct
import sys
import threading
import types
import wave
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import scrubgpt_contracts.models as models_pkg
import uuid6
from pydantic import BaseModel
from scrubgpt_contracts.models.common import (
    AnswerId,
    Bilingual,
    ContractModel,
    Lang,
    NonEmptyStr,
    VersionedModel,
)

MODULE = "scrubgpt_contracts.models.brain_api"


# --- stand-in registry (shape from #5) -----------------------------------------------------


@dataclass(frozen=True)
class Endpoint:
    method: str
    path: str
    request: type[BaseModel] | None
    response: type[BaseModel]
    files: tuple[str, ...]


class HealthResponse(VersionedModel):
    status: NonEmptyStr


class TranslateText(ContractModel):
    text: NonEmptyStr
    from_lang: Lang


class TranslateRequest(ContractModel):
    texts: list[TranslateText]


class TranslateResponse(VersionedModel):
    items: list[Bilingual]


class TranscribeForm(ContractModel):
    lang_hint: NonEmptyStr
    answer_id: AnswerId


class TranscribeResponse(VersionedModel):
    text: NonEmptyStr
    lang: Lang


STAND_IN_ENDPOINTS = {
    "health": Endpoint("GET", "/health", None, HealthResponse, ()),
    "translate": Endpoint("POST", "/v1/translate", TranslateRequest, TranslateResponse, ()),
    "transcribe": Endpoint(
        "POST", "/v1/answers/transcribe", TranscribeForm, TranscribeResponse, ("audio",)
    ),
}


def _install_registry(monkeypatch: pytest.MonkeyPatch, endpoints: Any, *, attr: bool = True):
    module = types.ModuleType(MODULE)
    if attr:
        module.ENDPOINTS = endpoints
    monkeypatch.setitem(sys.modules, MODULE, module)
    monkeypatch.setattr(models_pkg, "brain_api", module, raising=False)


def _remove_registry(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, MODULE, None)  # import of brain_api raises ImportError
    monkeypatch.delattr(models_pkg, "brain_api", raising=False)


@pytest.fixture
def registry(monkeypatch):
    _install_registry(monkeypatch, STAND_IN_ENDPOINTS)
    return STAND_IN_ENDPOINTS


TRANSLATE_REQUEST = {"texts": [{"text": "出血しています", "from_lang": "ja"}]}


def _tiny_wav() -> bytes:
    """0.1 s of a synthetic 440 Hz tone (D-036: synthetic media only)."""
    import math

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        frames = b"".join(
            struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / 16000)))
            for i in range(1600)
        )
        w.writeframes(frames)
    return buf.getvalue()


@pytest.fixture
def request_fixtures(tmp_path) -> Path:
    """Request fixtures laid out as in #5: `<name>.request.json` and
    `<name>.request.<file field>.<ext>`."""
    folder = tmp_path / "brain_api"
    folder.mkdir()
    (folder / "translate.request.json").write_text(
        json.dumps(TRANSLATE_REQUEST, ensure_ascii=False), encoding="utf-8"
    )
    (folder / "transcribe.request.json").write_text(
        json.dumps({"lang_hint": "ja", "answer_id": str(uuid6.uuid7())}), encoding="utf-8"
    )
    (folder / "transcribe.request.audio.wav").write_bytes(_tiny_wav())
    return folder


# --- stand-in server -----------------------------------------------------------------------

BAD_REQUEST = {
    "contract_version": "1.0",
    "error": {"code": "bad_request", "message": "request is empty", "retryable": False},
}
NOT_FOUND = {
    "contract_version": "1.0",
    "error": {"code": "not_found", "message": "no such endpoint", "retryable": False},
}


@dataclass
class Behaviour:
    health: tuple[int, Any] = (200, {"contract_version": "1.0", "status": "ok"})
    translate: tuple[int, Any] = (
        200,
        {"contract_version": "1.0", "items": [{"ja": "出血しています", "en": "It is bleeding"}]},
    )
    transcribe: tuple[int, Any] = (
        200,
        {"contract_version": "1.0", "text": "少し出血しています", "lang": "ja"},
    )
    empty: tuple[int, Any] = (400, BAD_REQUEST)
    log: list[tuple[str, str, bytes, str]] = field(default_factory=list)


def _is_empty_translate(body: bytes) -> bool:
    try:
        parsed = json.loads(body or b"{}")
    except ValueError:
        return True
    return not isinstance(parsed, dict) or "texts" not in parsed


def _handler_for(behaviour: Behaviour):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep test output quiet
            pass

        def _send(self, status: int, body: Any) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(length) if length else b""

        def do_GET(self):
            behaviour.log.append(("GET", self.path, b"", ""))
            if self.path == "/health":
                self._send(*behaviour.health)
            else:
                self._send(404, NOT_FOUND)

        def do_POST(self):
            body = self._body()
            ctype = self.headers.get("Content-Type", "")
            behaviour.log.append(("POST", self.path, body, ctype))
            if self.path == "/v1/translate":
                if _is_empty_translate(body):
                    self._send(*behaviour.empty)
                else:
                    self._send(*behaviour.translate)
            elif self.path == "/v1/answers/transcribe":
                if b'name="audio"' in body and b'name="answer_id"' in body:
                    self._send(*behaviour.transcribe)
                else:
                    self._send(*behaviour.empty)
            else:
                self._send(404, NOT_FOUND)

    return Handler


@pytest.fixture
def stand_in():
    """Start a stand-in Brain; yields (base_url, behaviour) - tests tweak `behaviour`."""
    behaviour = Behaviour()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(behaviour))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", behaviour
    finally:
        server.shutdown()
        server.server_close()


def _live(run_validate, url: str, fixtures: Path):
    return run_validate("live", "--base-url", url, "--fixtures", fixtures, "--timeout", "10")


# --- live ----------------------------------------------------------------------------------


def test_ac17_live_passes_against_a_conforming_brain(
    registry, request_fixtures, stand_in, run_validate
):
    """AC17: "`live --base-url <url>` (D-037) use[s] the ENDPOINTS registry with the shape in
    #5": every endpoint is called with its request fixture, every response validates, and the
    empty-request probes get 400 `bad_request` -> exit 0."""
    url, behaviour = stand_in
    result = _live(run_validate, url, request_fixtures)
    assert result.code == 0, result.output
    calls = [(m, p) for m, p, _, _ in behaviour.log]
    assert ("GET", "/health") in calls
    assert calls.count(("POST", "/v1/translate")) >= 2  # fixture + empty probe
    assert calls.count(("POST", "/v1/answers/transcribe")) >= 2
    sent = [json.loads(b) for m, p, b, _ in behaviour.log if p == "/v1/translate" and b.strip()]
    assert TRANSLATE_REQUEST in sent, "the translate request fixture was not sent as its body"
    multipart = [
        (b, c) for m, p, b, c in behaviour.log if p == "/v1/answers/transcribe" and b"audio" in b
    ]
    assert multipart, "transcribe was never sent the audio file"
    assert all("multipart/form-data" in c for _, c in multipart)


def test_ac17_live_fails_when_a_response_lacks_contract_version(
    registry, request_fixtures, stand_in, run_validate
):
    """AC17: "every response must carry `contract_version`" (plan §4.1, D-023)."""
    url, behaviour = stand_in
    behaviour.health = (200, {"status": "ok"})
    result = _live(run_validate, url, request_fixtures)
    assert result.code == 1, result.output
    assert "health" in result.problems, result.output


class LooseHealth(ContractModel):
    """A registry response model that forgot `contract_version` (not a VersionedModel)."""

    status: NonEmptyStr


def test_ac17_contract_version_required_even_if_the_model_forgets_it(
    monkeypatch, request_fixtures, stand_in, run_validate, tmp_path
):
    """AC17: "every response must carry `contract_version`" (plan §4.1: "every contract file
    and every API response carries contract_version") - checked by the tool itself, not only
    through the response model."""
    endpoints = dict(STAND_IN_ENDPOINTS)
    endpoints["health"] = Endpoint("GET", "/health", None, LooseHealth, ())
    _install_registry(monkeypatch, endpoints)
    url, behaviour = stand_in
    behaviour.health = (200, {"status": "ok"})
    result = _live(run_validate, url, request_fixtures)
    assert result.code == 1, result.output
    assert "health" in result.problems, result.output
    result = run_validate("response", "health", _write(tmp_path, {"status": "ok"}))
    assert result.code == 1, result.output


def test_ac17_live_fails_on_another_major_version(
    registry, request_fixtures, stand_in, run_validate
):
    """AC17 + AC4: a response with `contract_version` "2.0" does not validate."""
    url, behaviour = stand_in
    body = copy.deepcopy(behaviour.translate[1])
    body["contract_version"] = "2.0"
    behaviour.translate = (200, body)
    result = _live(run_validate, url, request_fixtures)
    assert result.code == 1, result.output
    assert "translate" in result.problems, result.output


def test_ac17_live_fails_when_a_response_does_not_match_its_model(
    registry, request_fixtures, stand_in, run_validate
):
    """AC17: "`live` validates every response against its model"."""
    url, behaviour = stand_in
    behaviour.translate = (200, {"contract_version": "1.0", "items": ["It is bleeding"]})
    result = _live(run_validate, url, request_fixtures)
    assert result.code == 1, result.output
    assert "translate" in result.problems, result.output


def test_ac17_live_fails_when_a_valid_request_gets_an_error(
    registry, request_fixtures, stand_in, run_validate
):
    """AC17: a request fixture answered with an error instead of its response is a failure."""
    url, behaviour = stand_in
    behaviour.transcribe = (
        503,
        {
            "contract_version": "1.0",
            "error": {"code": "unavailable", "message": "down", "retryable": True},
        },
    )
    result = _live(run_validate, url, request_fixtures)
    assert result.code == 1, result.output
    assert "transcribe" in result.problems, result.output


@pytest.mark.parametrize(
    "empty",
    [
        (422, {"detail": [{"loc": ["body"], "msg": "Field required", "type": "missing"}]}),
        (400, NOT_FOUND),
        (400, {"error": BAD_REQUEST["error"]}),  # ApiError without contract_version
        (400, {"detail": "bad request"}),
        (200, {"contract_version": "1.0", "items": []}),
        (500, BAD_REQUEST),
    ],
    ids=["422-fastapi", "400-wrong-code", "400-no-version", "400-not-apierror", "200", "500"],
)
def test_ac17_empty_post_must_be_400_bad_request(
    registry, request_fixtures, stand_in, run_validate, empty
):
    """AC17: "Each POST endpoint sent an empty request must return HTTP 400 with an `ApiError`
    of code `bad_request` (§4.1)" (FastAPI's 422 is mapped to 400)."""
    url, behaviour = stand_in
    behaviour.empty = empty
    result = _live(run_validate, url, request_fixtures)
    assert result.code == 1, result.output


@pytest.mark.parametrize("how", ["no-module", "no-attribute", "empty-dict"])
def test_ac17_live_exit_2_without_a_registry(
    monkeypatch, request_fixtures, stand_in, run_validate, how
):
    """AC17: "Exit 2 when there is no registry yet"."""
    if how == "no-module":
        _remove_registry(monkeypatch)
    elif how == "no-attribute":
        _install_registry(monkeypatch, None, attr=False)
    else:
        _install_registry(monkeypatch, {})
    url, _ = stand_in
    result = _live(run_validate, url, request_fixtures)
    assert result.code == 2, result.output


# --- response ------------------------------------------------------------------------------


def _write(tmp_path: Path, body: Any) -> Path:
    path = tmp_path / "saved.response.json"
    path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return path


def test_ac17_response_valid_file_exits_0(registry, tmp_path, run_validate):
    """AC17: `response <endpoint> <file>` validates a saved response with the registry's
    response model -> exit 0 when valid."""
    body = {"contract_version": "1.0", "items": [{"ja": "出血", "en": "Bleeding"}]}
    result = run_validate("response", "translate", _write(tmp_path, body))
    assert result.code == 0, result.output


@pytest.mark.parametrize(
    "body",
    [
        {"items": [{"ja": "出血", "en": "Bleeding"}]},
        {"contract_version": "2.0", "items": [{"ja": "出血", "en": "Bleeding"}]},
        {"contract_version": "1.0", "items": [{"ja": "出血", "en": ""}]},
        {"contract_version": "1.0", "items": "Bleeding"},
    ],
    ids=["no-version", "major-2", "half-bilingual", "wrong-shape"],
)
def test_ac17_response_invalid_file_exits_1(registry, tmp_path, run_validate, body):
    """AC17: an invalid saved response (incl. one without `contract_version`) -> exit 1."""
    result = run_validate("response", "translate", _write(tmp_path, body))
    assert result.code == 1, result.output


def test_ac17_response_broken_json_exits_1(registry, tmp_path, run_validate):
    """AC17: a saved response that isn't JSON is invalid -> exit 1."""
    path = tmp_path / "saved.json"
    path.write_text("{ nope", encoding="utf-8")
    result = run_validate("response", "translate", path)
    assert result.code == 1, result.output


def test_ac17_response_unknown_endpoint_is_not_a_pass(registry, tmp_path, run_validate):
    """AC17: an endpoint that isn't in the registry is never exit 0."""
    body = {"contract_version": "1.0", "status": "ok"}
    result = run_validate("response", "no_such_endpoint", _write(tmp_path, body))
    assert result.code != 0, result.output


def test_ac17_response_exit_2_without_a_registry(monkeypatch, tmp_path, run_validate):
    """AC17: "Exit 2 when there is no registry yet" (`response` needs it too)."""
    _remove_registry(monkeypatch)
    body = {"contract_version": "1.0", "status": "ok"}
    result = run_validate("response", "health", _write(tmp_path, body))
    assert result.code == 2, result.output
