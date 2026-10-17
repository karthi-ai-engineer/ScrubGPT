"""I7: how Brain failures map to `ApiError` codes (Block 3 re-test, criterion 14).

Criterion 14 (brief, from T2 spec gaps 2-3): "Brain connect timeout and connection refused → 503
`unavailable` (retryable); a read timeout after connecting → 504 `timeout`; a 503 without an
`ApiError` body → 503 `unavailable`; other non-`ApiError` error bodies → 502 `upstream_error`. The
README states this."
Also plan §4.1 `ApiError` codes and HTTP statuses; contracts/brain_api.md "Errors"
(`unavailable` 503 retryable, `upstream_error` 502, `timeout` 504; "The app shows 'Brain
unavailable' for 503 and 504"); app/server/CLAUDE.md rule 1.

Entry points: `scrubgpt_app.brain_client.BrainClient` (`transport=`) and the app server
(`create_app(settings, brain=...)`, via the `answer_app` fixture), reached with
`POST /api/answers/draft` (which calls the Brain's `/extract`).
"""

from __future__ import annotations

import json
import re
import socket
from pathlib import Path

import httpx
import pytest
from scrubgpt_contracts.models.brain_api import ExtractRequest
from scrubgpt_contracts.models.common import ApiError

CASE = "case-fixture-01"
QUESTION = f"{CASE}.m05.q1"
REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_REQUESTS = REPO_ROOT / "contracts" / "fixtures" / "brain_api"
README = REPO_ROOT / "app" / "server" / "README.md"


def _extract_request() -> ExtractRequest:
    raw = json.loads((FIXTURE_REQUESTS / "extract.request.json").read_text(encoding="utf-8"))
    return ExtractRequest.model_validate(raw)


def _raise(exc: Exception):
    def override(request: httpx.Request):
        raise exc

    return override


def _respond(status: int, content: bytes, content_type: str):
    def override(request: httpx.Request):
        return httpx.Response(status, content=content, headers={"content-type": content_type})

    return override


def _through_app(answer_app, data_dir, draft_for, override) -> tuple[int, ApiError]:
    app = answer_app(data_dir, override=override)
    status, body = draft_for(app.client, QUESTION, "operating_surgeon", text="レンズが曇った")
    return status, ApiError.model_validate(body)


def _through_client(wire_brain, override):
    from scrubgpt_app.brain_client import BrainError

    brain, _ = wire_brain(override)
    with pytest.raises(BrainError) as caught:
        brain.extract(_extract_request())
    return caught.value


# --- connect timeout / connection refused → 503 unavailable, retryable ------------------------

UNREACHABLE = {
    "connect_timeout": httpx.ConnectTimeout("connect timed out"),
    "connection_refused": httpx.ConnectError("[WinError 10061] connection refused"),
}


@pytest.mark.parametrize("name", list(UNREACHABLE))
def test_c14_an_unreachable_brain_is_503_unavailable_retryable_in_the_client(wire_brain, name):
    """Criterion 14: "Brain connect timeout and connection refused → 503 `unavailable`
    (retryable)" (brain_api.md: `unavailable` is retryable)."""
    error = _through_client(wire_brain, _raise(UNREACHABLE[name]))
    assert error.code.value == "unavailable"
    assert error.retryable is True


@pytest.mark.parametrize("name", list(UNREACHABLE))
def test_c14_an_unreachable_brain_is_503_unavailable_retryable_through_the_app(
    answer_app, data_dir, draft_for, name
):
    """Criterion 14, as the web app sees it: 503 `ApiError` `unavailable`, `retryable: true`."""
    status, error = _through_app(answer_app, data_dir, draft_for, _raise(UNREACHABLE[name]))
    assert status == 503
    assert error.error.code.value == "unavailable"
    assert error.error.retryable is True


def test_c14_a_real_refused_connection_is_503_unavailable_retryable():
    """Criterion 14: connection refused over real HTTP (nothing listens on the port)."""
    from scrubgpt_app.brain_client import BrainClient, BrainError

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    client = BrainClient(f"http://127.0.0.1:{port}")
    try:
        with pytest.raises(BrainError) as caught:
            client.extract(_extract_request())
    finally:
        client.close()
    assert caught.value.code.value == "unavailable"
    assert caught.value.retryable is True


# --- read timeout after connecting → 504 timeout --------------------------------------------


def test_c14_a_read_timeout_after_connecting_is_504_timeout(answer_app, data_dir, draft_for):
    """Criterion 14: "a read timeout after connecting → 504 `timeout`"."""
    status, error = _through_app(
        answer_app, data_dir, draft_for, _raise(httpx.ReadTimeout("read timed out"))
    )
    assert status == 504
    assert error.error.code.value == "timeout"


def test_c14_a_real_brain_that_connects_but_does_not_answer_is_504_timeout():
    """Criterion 14 over a real socket: the Brain accepts the connection but never answers, so the
    client's read times out → `timeout` (not `unavailable`)."""
    from scrubgpt_app.brain_client import BrainClient, BrainError

    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(4)  # accepts at the TCP level; never reads or answers
        port = server.getsockname()[1]
        http = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=httpx.Timeout(0.5))
        client = BrainClient(f"http://127.0.0.1:{port}", http=http)
        try:
            with pytest.raises(BrainError) as caught:
                client.health()
        finally:
            http.close()
    assert caught.value.code.value == "timeout"


# --- a 503 without an ApiError body → 503 unavailable ---------------------------------------

NON_API_ERROR_BODIES = {
    "text": (b"Service Unavailable", "text/plain"),
    "html": (b"<html><body><h1>503 Service Unavailable</h1></body></html>", "text/html"),
    "empty": (b"", "text/plain"),
    "other_json": (b'{"detail": "starting up"}', "application/json"),
}


@pytest.mark.parametrize("body", list(NON_API_ERROR_BODIES))
def test_c14_a_503_without_an_api_error_body_is_503_unavailable(
    answer_app, data_dir, draft_for, wire_brain, body
):
    """Criterion 14: "a 503 without an `ApiError` body → 503 `unavailable`"."""
    content, content_type = NON_API_ERROR_BODIES[body]
    override = _respond(503, content, content_type)
    assert _through_client(wire_brain, override).code.value == "unavailable"
    status, error = _through_app(answer_app, data_dir, draft_for, override)
    assert status == 503
    assert error.error.code.value == "unavailable"


# --- other non-ApiError error bodies → 502 upstream_error ------------------------------------


@pytest.mark.parametrize("status", [400, 404, 429, 500, 502, 504])
@pytest.mark.parametrize("body", list(NON_API_ERROR_BODIES))
def test_c14_other_non_api_error_bodies_are_502_upstream_error(
    answer_app, data_dir, draft_for, status, body
):
    """Criterion 14: "other non-`ApiError` error bodies → 502 `upstream_error`" (every status but
    503, including a proxy's 504 page)."""
    content, content_type = NON_API_ERROR_BODIES[body]
    got, error = _through_app(
        answer_app, data_dir, draft_for, _respond(status, content, content_type)
    )
    assert got == 502
    assert error.error.code.value == "upstream_error"


# --- the README states it ---------------------------------------------------------------------


def _brain_client_paragraph() -> str:
    text = README.read_text(encoding="utf-8")
    match = re.search(r"\*\*Brain client \(I7\)\.\*\*(.*?)(?:\n\s*\n|\Z)", text, re.S)
    assert match, "README has no 'Brain client (I7).' paragraph"
    return match.group(1)


def test_c14_the_readme_states_the_error_mapping():
    """Criterion 14: "The README states this" (app/server/README.md, "Brain client (I7)")."""
    para = _brain_client_paragraph()
    lowered = para.lower()
    assert "connection refused" in lowered
    assert "connect timeout" in lowered
    assert "503" in para and "`unavailable`" in para
    assert "504" in para and "`timeout`" in para
    assert re.search(r"503 without an `?ApiError`? body", para), para
    assert "502" in para and "`upstream_error`" in para
    # a read timeout after connecting is told apart from a connect timeout
    assert re.search(r"connects but|after connecting|read timeout", lowered), para
