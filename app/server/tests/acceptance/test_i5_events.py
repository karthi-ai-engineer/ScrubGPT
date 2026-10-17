"""I5 acceptance: live updates over Server-Sent Events, and "surgery ends" (`replay-ended`).

Sources: plan §2.9 I5 ("Live updates (SSE)"), §8.2 ("When the video ends, the app server raises a
'questions ready' event over SSE"), D-069 ("N questions ready" counts `questions.json`, never
fixed), app/server/CLAUDE.md rule 8, app/server/README.md "SSE events" and the API rows for
`GET /api/events` and `POST /api/cases/{case_id}/replay-ended`, the test brief (criteria 1 and 2).

The stream is read from a real uvicorn server on a free port (brief: the in-process TestClient
buffers a whole response), with a short heartbeat (`create_app(..., heartbeat_s=0.2)`).
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest
from scrubgpt_contracts.models.common import ApiError

CASE = "case-fixture-01"


def expected_payload(case_dir: Path, case_id: str) -> dict[str, object]:
    """Counted from the case's own `questions.json` (README "SSE events", D-069)."""
    questions = json.loads((case_dir / "questions.json").read_text(encoding="utf-8"))
    return {
        "case_id": case_id,
        "questions": {
            "operating": len(questions["operating"]),
            "reviewer": len(questions["reviewer"]),
        },
        "est_seconds": sum(q["est_seconds"] for q in questions["operating"]),
    }


def wait_until(predicate, timeout: float = 8.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


# --- Criterion 1: the stream -----------------------------------------------------------------


def test_events_is_an_event_stream_with_no_cache(live_server, sse_connect, data_dir):
    """Criterion 1: "`GET /api/events` is a `text/event-stream` with `Cache-Control: no-cache`"
    (brief; README "SSE events")."""
    server = live_server(data_dir)
    client = sse_connect(server)
    assert client.status == 200
    assert client.headers["content-type"].split(";")[0].strip() == "text/event-stream"
    assert "no-cache" in [p.strip() for p in client.headers["cache-control"].split(",")]


def test_stream_starts_with_a_retry_line(live_server, sse_connect, data_dir):
    """Criterion 1: "it starts with a `retry:` line" (brief); README: `retry: 3000`."""
    client = sse_connect(live_server(data_dir))
    first = client.read_line()
    assert first.startswith("retry:"), first
    assert first.split(":", 1)[1].strip() == "3000"


def test_each_event_is_id_event_and_one_json_data_line(
    live_server, sse_connect, http_post, data_dir
):
    """Criterion 1: "each event is `id` / `event` / one JSON `data` line" (brief; README: "one
    `id` / `event` / `data` (JSON) block per event")."""
    server = live_server(data_dir)
    client = sse_connect(server)
    client.read_block()  # retry
    status, _ = http_post(server.base_url, f"/api/cases/{CASE}/replay-ended")
    assert status == 200
    event = client.next_event()
    assert event["fields"] == ["id", "event", "data"], event["lines"]
    assert event["event"] == "case.ended"
    assert str(event["id"]).strip() != ""
    assert len(event["data"]) == 1  # type: ignore[arg-type]
    json.loads(event["data"][0])  # type: ignore[index]


def test_heartbeat_comments_keep_an_idle_stream_alive(live_server, sse_connect, data_dir):
    """Criterion 1: "heartbeat comments keep idle streams alive" (brief); README: a `: ping`
    comment every heartbeat. With `heartbeat_s=0.2`, an idle stream gets several comment lines
    and stays open."""
    client = sse_connect(live_server(data_dir, heartbeat_s=0.2))
    client.read_block()  # retry (+ any greeting comment)
    comments = 0
    end = time.monotonic() + 3.0
    while comments < 3 and time.monotonic() < end:
        block = client.read_block()
        assert all(line.startswith(":") for line in block), block  # nothing but comments
        comments += 1
    assert comments >= 3
    assert not client.closed


def test_every_client_gets_every_event_in_order(
    live_server, sse_connect, http_post, data_dir, clone_case
):
    """Criterion 1: "every connected client gets every event, in order" (brief; README "Every
    connected tab gets every event")."""
    clone_case(data_dir / "cases", "case-fixture-02")
    server = live_server(data_dir)
    clients = [sse_connect(server) for _ in range(3)]
    for c in clients:
        c.read_block()  # subscribed once the retry line arrives
    order = [CASE, "case-fixture-02", CASE, CASE, "case-fixture-02"]
    for case_id in order:
        status, _ = http_post(server.base_url, f"/api/cases/{case_id}/replay-ended")
        assert status == 200
    seen = []
    for c in clients:
        events = [c.next_event() for _ in order]
        assert [e["event"] for e in events] == ["case.ended"] * len(order)
        assert [json.loads(e["data"][0])["case_id"] for e in events] == order  # type: ignore[index]
        ids = [int(str(e["id"])) for e in events]
        assert ids == sorted(ids) and len(set(ids)) == len(ids)
        seen.append(ids)
    assert seen[0] == seen[1] == seen[2]  # the same events, not per-client copies


def test_a_disconnected_client_is_cleaned_up(live_server, sse_connect, http_post, data_dir):
    """Criterion 1: "a disconnected client is cleaned up" (brief). Observed through the bus's
    subscriber count (`scrubgpt_app.events.EventBus.subscribers`, an entry point in the brief);
    the remaining client keeps receiving events."""
    server = live_server(data_dir, heartbeat_s=0.2)
    bus = server.app.state.events  # type: ignore[attr-defined]
    stay, leave = sse_connect(server), sse_connect(server)
    stay.read_block()
    leave.read_block()
    assert wait_until(lambda: bus.subscribers == 2)
    leave.close()
    assert wait_until(lambda: bus.subscribers == 1), f"still {bus.subscribers} subscribers"
    status, _ = http_post(server.base_url, f"/api/cases/{CASE}/replay-ended")
    assert status == 200
    assert stay.next_event()["event"] == "case.ended"


def test_a_client_that_falls_far_behind_is_dropped_and_its_stream_ends():
    """README "SSE events": "a tab that falls 100 events behind is dropped and reconnects".
    Through `scrubgpt_app.events.stream` (brief entry point): a subscriber that reads nothing
    while 150 events are published is unsubscribed and its stream ends (the browser reconnects
    on `retry`); one that is 50 behind still gets all 50, in order."""
    from scrubgpt_app.events import EventBus, stream

    async def connected() -> bool:
        return False

    async def fifty_behind_gets_everything() -> None:
        bus = EventBus()
        gen = stream(bus, connected, 5.0)
        assert (await gen.__anext__()).startswith("retry:")
        assert bus.subscribers == 1
        for i in range(50):
            bus.publish("case.ended", {"n": i})
        got = []
        for _ in range(50):
            chunk = await asyncio.wait_for(gen.__anext__(), 2)
            data = next(x for x in chunk.splitlines() if x.startswith("data:"))
            got.append(json.loads(data.split(":", 1)[1])["n"])
        assert got == list(range(50))
        assert bus.subscribers == 1
        await gen.aclose()
        assert bus.subscribers == 0

    async def far_behind_is_dropped() -> None:
        bus = EventBus()
        gen = stream(bus, connected, 5.0)
        assert (await gen.__anext__()).startswith("retry:")
        assert bus.subscribers == 1
        for i in range(150):
            bus.publish("case.ended", {"n": i})
        assert bus.subscribers == 0
        chunks = []
        with pytest.raises(StopAsyncIteration):
            while True:
                chunks.append(await asyncio.wait_for(gen.__anext__(), 2))
        assert len(chunks) < 150  # it never gets the whole backlog; the stream ends

    asyncio.run(fifty_behind_gets_everything())
    asyncio.run(far_behind_is_dropped())


# --- Criterion 2: replay-ended → case.ended ---------------------------------------------------


def test_replay_ended_returns_counts_from_questions_json(live_server, http_post, data_dir):
    """Criterion 2: `POST /api/cases/{id}/replay-ended` returns `{case_id, questions: {operating,
    reviewer}, est_seconds}` counted from that case's `questions.json` (operating questions'
    `est_seconds` summed). Fixture: 8 operating, 4 reviewer, 15+10+20+30+8+30+10+8 = 131 s."""
    server = live_server(data_dir)
    status, body = http_post(server.base_url, f"/api/cases/{CASE}/replay-ended")
    assert status == 200
    expected = expected_payload(data_dir / "cases" / CASE, CASE)
    assert expected == {
        "case_id": CASE,
        "questions": {"operating": 8, "reviewer": 4},
        "est_seconds": 131,
    }
    assert body == expected


def test_replay_ended_publishes_the_same_payload_as_case_ended(
    live_server, sse_connect, http_post, data_dir
):
    """Criterion 2: it "publishes `case.ended` with {…} … and returns the same payload"."""
    server = live_server(data_dir)
    client = sse_connect(server)
    client.read_block()
    status, body = http_post(server.base_url, f"/api/cases/{CASE}/replay-ended")
    assert status == 200
    event = client.next_event()
    assert event["event"] == "case.ended"
    assert (
        json.loads(event["data"][0])
        == body
        == expected_payload(  # type: ignore[index]
            data_dir / "cases" / CASE, CASE
        )
    )


def _fewer_questions(case_dir: Path) -> None:
    """Keeps only the questions the seed records answer (so the package stays valid, D-059)."""
    path = case_dir / "questions.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    keep = {f"{CASE}.m01.q1", f"{CASE}.m02.q1", f"{CASE}.m04.q1", f"{CASE}.m01.r1"}
    data["operating"] = [q for q in data["operating"] if q["id"] in keep]
    data["reviewer"] = [q for q in data["reviewer"] if q["id"] in keep]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_a_different_questions_json_gives_different_counts(
    live_server, sse_connect, http_post, data_dir
):
    """Criterion 2 / D-069: "N questions ready" counts `questions.json`, never fixed. A copy of
    the fixture with 3 operating (15 + 20 + 30 = 65 s) and 1 reviewer question."""
    _fewer_questions(data_dir / "cases" / CASE)
    server = live_server(data_dir)
    assert CASE in server.app.state.catalog.cases, "the reduced copy must still load"  # type: ignore[attr-defined]
    client = sse_connect(server)
    client.read_block()
    status, body = http_post(server.base_url, f"/api/cases/{CASE}/replay-ended")
    assert status == 200
    assert body == {
        "case_id": CASE,
        "questions": {"operating": 3, "reviewer": 1},
        "est_seconds": 65,
    }
    assert json.loads(client.next_event()["data"][0]) == body  # type: ignore[index]


def test_unknown_case_is_404_api_error_and_publishes_nothing(
    live_server, sse_connect, http_post, data_dir
):
    """Criterion 2: "an unknown case gives 404 with an `ApiError` (`not_found`) and publishes
    nothing" (brief; README API row; plan §4.1 ApiError)."""
    server = live_server(data_dir)
    client = sse_connect(server)
    client.read_block()
    status, body = http_post(server.base_url, "/api/cases/no-such-case/replay-ended")
    assert status == 404
    error = ApiError.model_validate(body)
    assert error.error.code.value == "not_found"
    # The next event on the stream is the known case's, so the 404 published nothing.
    status, _ = http_post(server.base_url, f"/api/cases/{CASE}/replay-ended")
    assert status == 200
    event = client.next_event()
    assert json.loads(event["data"][0])["case_id"] == CASE  # type: ignore[index]


def test_cli_served_stream_carries_case_ended(start_serve, data_dir, http_post):
    """Criteria 1–2 end to end: `scrubgpt-app serve --port <free>` (brief entry point) serves the
    stream (retry line first, `text/event-stream`) and publishes `case.ended` from
    `replay-ended`, counted from `questions.json`."""
    import http.client

    base, port = start_serve(data_dir)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    try:
        conn.request("GET", "/api/events")
        resp = conn.getresponse()
        assert resp.status == 200
        assert resp.getheader("content-type", "").startswith("text/event-stream")
        assert resp.readline().decode().startswith("retry:")
        # read the rest of the greeting block
        while resp.readline().strip():
            pass
        status, body = http_post(base, f"/api/cases/{CASE}/replay-ended")
        assert status == 200
        lines: list[str] = []
        while True:
            line = resp.readline().decode("utf-8").rstrip("\r\n")
            if line == "" and any(x.startswith("event:") for x in lines):
                break
            if line and not line.startswith(":"):
                lines.append(line)
        assert lines[1] == "event: case.ended"
        assert json.loads(lines[2].split(":", 1)[1]) == body
        assert body == expected_payload(data_dir / "cases" / CASE, CASE)
    finally:
        conn.close()
