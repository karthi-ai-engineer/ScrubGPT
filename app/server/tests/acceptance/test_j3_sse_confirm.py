"""Confirmed answers update the graph through SSE (brief criterion 10, server side).

Sources: plan §8.3 ("Confirm → app server stores the record + provenance → SSE → graph and
library update live"), §2.9 I5 ("When an answer is confirmed, the graph and library update
instantly"); D-071 ("Confirm → answer.confirmed → record.created → graph.updated, one graph node
per record"); app/server/CLAUDE.md rule 8 (SSE events documented in the README); app/server/
README.md "SSE events" table:
- `answer.confirmed`: `case_id`, `question_id`, `record_id`, `answer_id`, first of three;
- `record.created`: `record` (the stored DecisionRecord), second, right after;
- `graph.updated`: `case_id`, `nodes: [{id, kind}]` (new only), `edges: [{src, dst, kind,
  record_id, trust_label}]`, third.

Runs the app server and the fake Brain under uvicorn on free ports (`BRAIN_MODE=mock`,
`MOCK_BRAIN_URL`), and reads `GET /api/events` over a real socket (the in-process TestClient
buffers an endless stream).
"""

from __future__ import annotations

import json

import httpx
import pytest
from scrubgpt_contracts.models.decision_record import DecisionRecord

CASE = "case-fixture-01"
NAMES = ("answer.confirmed", "record.created", "graph.updated")


@pytest.fixture
def running(make_settings, data_dir, uvicorn_thread, sse_connect):
    from scrubgpt_app.api import create_app
    from scrubgpt_contracts.mock_brain.app import create_app as create_brain

    brain = uvicorn_thread(create_brain())
    settings = make_settings(data_dir, BRAIN_MODE="mock", MOCK_BRAIN_URL=brain.base_url)
    server = uvicorn_thread(create_app(settings, heartbeat_s=0.2))
    stream = sse_connect(server)
    assert stream.status == 200
    return server, stream


def _answer(base: str, qid: str, role: str, text: str, lang: str = "ja") -> dict:
    draft = httpx.post(
        base + "/api/answers/draft",
        json={
            "case_id": CASE,
            "question_id": qid,
            "answerer_role": role,
            "answer": {"mode": "text", "tap": None, "text": text, "lang": lang, "audio_uri": None},
        },
        timeout=30,
    )
    assert draft.status_code == 200, draft.text
    body = draft.json()
    d = body["extract"]["draft"]
    edits = []
    if d["situation_cue"]["text"] is None:
        edits.append({"field": "situation_cue.text", "text": "出血が見えた", "lang": lang})
    if d["action"]["text"] is None:
        edits.append({"field": "action.text", "text": "圧迫して止血した", "lang": lang})
    confirm = httpx.post(
        base + "/api/answers/confirm",
        json={
            "answer_id": body["answer_id"],
            "draft": d,
            "edits": edits,
            "confirmed_by": "Dr Live",
        },
        timeout=30,
    )
    assert confirm.status_code == 201, confirm.text
    return {"answer_id": body["answer_id"], "record": confirm.json()["record"]}


def _next_three(stream) -> list[dict]:
    events = []
    while len(events) < 3:
        block = stream.next_event(deadline_s=15)
        if block.get("event") in NAMES:
            data = json.loads("\n".join(block["data"]))  # type: ignore[arg-type]
            events.append({"name": block["event"], "id": block.get("id"), "data": data})
    return events


def _check_triplet(events: list[dict], answered: dict, qid: str) -> dict:
    record = answered["record"]
    assert [e["name"] for e in events] == list(NAMES)

    confirmed = events[0]["data"]
    assert confirmed == {
        "case_id": CASE,
        "question_id": qid,
        "record_id": record["id"],
        "answer_id": answered["answer_id"],
    }

    created = events[1]["data"]
    assert set(created) == {"record"}
    DecisionRecord.model_validate(created["record"])
    assert created["record"] == record

    graph = events[2]["data"]
    assert graph["case_id"] == CASE
    assert isinstance(graph["nodes"], list) and isinstance(graph["edges"], list)
    for node in graph["nodes"]:
        assert set(node) >= {"id", "kind"}
    record_nodes = [n for n in graph["nodes"] if n["kind"] == "record"]
    assert len(record_nodes) == 1, graph["nodes"]
    assert record["id"] in record_nodes[0]["id"]
    assert graph["edges"], "the record is linked into the graph"
    for edge in graph["edges"]:
        assert set(edge) >= {"src", "dst", "kind", "record_id", "trust_label"}
        assert edge["record_id"] == record["id"]
        assert edge["trust_label"] == record["provenance"]["trust_label"]
    assert any(record_nodes[0]["id"] in (e["src"], e["dst"]) for e in graph["edges"])

    ids = [e["id"] for e in events]
    if all(i is not None for i in ids):
        numbers = [int(i) for i in ids]  # type: ignore[arg-type]
        assert numbers == sorted(numbers) and len(set(numbers)) == 3
    return graph


def test_c10_confirm_emits_the_three_events_in_order_with_their_payloads(running):
    """Criterion 10 (D-071; README "SSE events"): "Confirm emits answer.confirmed →
    record.created → graph.updated, in that order, with the documented payloads"."""
    server, stream = running
    qid = f"{CASE}.m05.q1"
    answered = _answer(server.base_url, qid, "operating_surgeon", "レンズが曇った")
    graph = _check_triplet(_next_three(stream), answered, qid)
    assert all(e["trust_label"] == "operating_surgeon" for e in graph["edges"])


def test_c10_two_answers_on_one_moment_are_two_record_nodes(running):
    """Criterion 10 (D-071 "one graph node per record"; rule 4 keep every viewpoint): two answers
    on one moment each add their own record node; the second adds no new moment node ("nodes …
    (new only)")."""
    server, stream = running
    first_q = f"{CASE}.m05.q1"
    first = _answer(server.base_url, first_q, "operating_surgeon", "レンズが曇った")
    g1 = _check_triplet(_next_three(stream), first, first_q)

    second = _answer(server.base_url, first_q, "dev_team_simulated", "曇りで見えなかった")
    g2 = _check_triplet(_next_three(stream), second, first_q)

    r1 = next(n["id"] for n in g1["nodes"] if n["kind"] == "record")
    r2 = next(n["id"] for n in g2["nodes"] if n["kind"] == "record")
    assert r1 != r2
    assert not [n for n in g2["nodes"] if n["kind"] != "record"], (
        "the case, step and moment already exist: graph.updated lists new nodes only"
    )
    assert all(e["trust_label"] == "simulated" for e in g2["edges"])

    stored = httpx.get(server.base_url + f"/api/cases/{CASE}/records", timeout=10).json()
    on_m05 = [
        r["record"]["id"] for r in stored["records"] if r["record"]["moment_id"] == f"{CASE}.m05"
    ]
    assert sorted(on_m05) == sorted([first["record"]["id"], second["record"]["id"]])


def test_c10_a_refused_confirm_emits_nothing(running):
    """Criterion 10 with criterion 2/7: a Confirm the server refuses (cue or action still null)
    stores nothing and emits none of the three events; the next valid Confirm's events come next."""
    server, stream = running
    qid = f"{CASE}.m05.q1"
    draft = httpx.post(
        server.base_url + "/api/answers/draft",
        json={
            "case_id": CASE,
            "question_id": qid,
            "answerer_role": "operating_surgeon",
            "answer": {
                "mode": "text",
                "tap": None,
                "text": "曇り",
                "lang": "ja",
                "audio_uri": None,
            },
        },
        timeout=30,
    ).json()
    refused = httpx.post(
        server.base_url + "/api/answers/confirm",
        json={
            "answer_id": draft["answer_id"],
            "draft": draft["extract"]["draft"],
            "edits": [],
            "confirmed_by": "Dr Live",
        },
        timeout=30,
    )
    assert refused.status_code == 400
    answered = _answer(server.base_url, qid, "operating_surgeon", "レンズが曇った")
    events = _next_three(stream)
    # The first events after the refusal belong to the valid answer.
    _check_triplet(events, answered, qid)
