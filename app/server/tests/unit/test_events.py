"""Live updates (I5): the event bus, the SSE wire format and `case.ended` at the end of a replay."""

import asyncio
import json
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from scrubgpt_app.api import create_app
from scrubgpt_app.events import Event, EventBus, stream
from scrubgpt_app.settings import REPO_ROOT, Settings
from scrubgpt_contracts.models.common import ApiError

FIXTURES = REPO_ROOT / "contracts" / "fixtures"
CASE_ID = "case-fixture-01"


def test_event_wire_format_is_one_json_line() -> None:
    event = Event(7, "case.ended", {"case_id": CASE_ID, "title": "症例\nA"})
    text = event.encode()
    assert text.startswith("id: 7\nevent: case.ended\ndata: ")
    assert text.endswith("\n\n")
    data_line = text.splitlines()[2]
    assert json.loads(data_line.removeprefix("data: ")) == event.data  # newline stays escaped


def test_every_subscriber_gets_every_event_in_order() -> None:
    async def scenario() -> list[list[int]]:
        bus = EventBus()
        async with bus.subscribe() as first, bus.subscribe() as second:
            assert bus.subscribers == 2
            bus.publish("a", {})
            bus.publish("b", {})
            got = [[(await q.get()).id for _ in range(2)] for q in (first, second)]
        assert bus.subscribers == 0
        return got

    assert asyncio.run(scenario()) == [[1, 2], [1, 2]]


def test_a_full_subscriber_is_dropped_not_the_others() -> None:
    async def scenario() -> tuple[object, int]:
        bus = EventBus(queue_size=2)
        async with bus.subscribe() as slow, bus.subscribe() as fast:
            for name in ("a", "b", "c"):
                bus.publish(name, {})
                await fast.get()
            last = None
            while not slow.empty():
                last = slow.get_nowait()
            return last, bus.subscribers

    last, subscribers = asyncio.run(scenario())
    assert last is None and subscribers == 1  # the slow one got the end marker and left


def test_stream_sends_retry_heartbeats_and_events_until_disconnect() -> None:
    async def scenario() -> list[str]:
        bus = EventBus()
        calls = 0

        async def is_disconnected() -> bool:
            nonlocal calls
            calls += 1
            return calls > 3

        chunks = []
        body = stream(bus, is_disconnected, heartbeat_s=0.01)
        chunks.append(await anext(body))
        chunks.append(await anext(body))  # nothing published yet: a heartbeat
        bus.publish("case.ended", {"case_id": CASE_ID})
        chunks += [chunk async for chunk in body]
        return chunks

    chunks = asyncio.run(scenario())
    assert chunks[0].startswith("retry: ")
    assert chunks[1] == ": ping\n\n"
    assert any(chunk.startswith("id: 1\nevent: case.ended\n") for chunk in chunks)


@pytest.fixture(scope="module")
def client() -> TestClient:
    settings = Settings.load({"DATA_DIR": str(FIXTURES)}, dotenv=False)
    app = create_app(replace(settings, web_dist=Path("/nonexistent")), heartbeat_s=0.05)
    return TestClient(app)


def test_replay_ended_counts_the_case_questions(client: TestClient) -> None:
    questions = json.loads(
        (FIXTURES / "cases" / CASE_ID / "questions.json").read_text(encoding="utf-8")
    )
    body = client.post(f"/api/cases/{CASE_ID}/replay-ended").json()
    assert body == {
        "case_id": CASE_ID,
        "questions": {
            "operating": len(questions["operating"]),
            "reviewer": len(questions["reviewer"]),
        },
        "est_seconds": sum(q["est_seconds"] for q in questions["operating"]),
    }


def test_replay_ended_for_an_unknown_case_is_404(client: TestClient) -> None:
    response = client.post("/api/cases/case-nope/replay-ended")
    assert response.status_code == 404
    assert ApiError.model_validate(response.json()).error.code.value == "not_found"


@pytest.fixture
def live_server() -> Iterator[str]:
    """The app on a free local port in a background thread: a real HTTP stream (the in-process
    TestClient waits for a response to end, and an event stream never ends)."""
    settings = Settings.load({"DATA_DIR": str(FIXTURES)}, dotenv=False)
    app = create_app(replace(settings, web_dist=Path("/nonexistent")), heartbeat_s=0.05)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the app server did not start"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(10)


def test_events_stream_delivers_case_ended(live_server: str) -> None:
    with httpx.Client(base_url=live_server, timeout=10) as http:
        with http.stream("GET", "/api/events") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert response.headers["cache-control"] == "no-cache"
            lines = response.iter_lines()
            assert next(lines).startswith("retry: ")
            http.post(f"/api/cases/{CASE_ID}/replay-ended").raise_for_status()
            names, data = [], None
            for line in lines:
                if line.startswith("event: "):
                    names.append(line.removeprefix("event: "))
                if line.startswith("data: "):
                    data = json.loads(line.removeprefix("data: "))
                    break
    assert names == ["case.ended"]
    assert data is not None and data["case_id"] == CASE_ID
