"""T2 acceptance: fake Brain /v1/ask (brief criterion 13).

Sources: D-037 and plan §4.5 (coverage full if 2 or more candidates score cosine >= 0.3, partial
if 1, none if 0; cites the top-ranked candidates it was sent); plan §4.4 (citations[record_id]);
brain_api.md /ask (record_id is one of the candidates; evidence_index points into its evidence;
coverage none exactly when citations is empty).

Candidates are fixture seed records whose every human-readable text is replaced, so a "match"
record says only the query's words and an "unrelated" record shares no word with it.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

QUERY_EN = "lens fogging cleaned with warm saline"
UNRELATED_EN = "zebra quartz vortex marmalade"
QUERY_JA = "レンズの曇りを温生食で拭いた"
UNRELATED_JA = "膀胱頸部温存吻合"  # shares no CJK bigram with QUERY_JA


def _rewrite(node: Any, text: str) -> Any:
    if isinstance(node, dict):
        if set(node) == {"ja", "en"}:
            return {"ja": text, "en": text}
        out = {}
        for k, v in node.items():
            if k in ("quote",):
                out[k] = text
            elif k == "cue_terms":
                out[k] = [text]
            else:
                out[k] = _rewrite(v, text)
        return out
    if isinstance(node, list):
        return [_rewrite(x, text) for x in node]
    return node


@pytest.fixture
def make_record(case_data, new_uuid7):
    from scrubgpt_contracts.models.decision_record import DecisionRecord

    def make(text: str) -> dict[str, Any]:
        record = copy.deepcopy(case_data["seeds"][0])
        record["id"] = new_uuid7()
        record["obstacle"] = None
        record["grounding"] = [g for g in record["grounding"] if g["field"] != "obstacle"]
        record["new_terms"] = []
        record = _rewrite(record, text)
        DecisionRecord.model_validate(record)
        return record

    return make


@pytest.fixture
def ask(client, endpoints):
    def run(query: str, lang: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        r = client.post("/v1/ask", json={"query": query, "lang": lang, "candidates": candidates})
        assert r.status_code == 200, r.text[:800]
        body = r.json()
        endpoints["ask"].response.model_validate(body)
        _check_citations(body, candidates)
        return body

    return run


def _check_citations(body: dict[str, Any], candidates: list[dict[str, Any]]) -> None:
    """brain_api.md: record_id is one of the candidates; evidence_index points into its
    evidence[] or is null; coverage none exactly when citations is empty."""
    by_id = {c["id"]: c for c in candidates}
    for c in body["citations"]:
        assert c["record_id"] in by_id, c
        idx = c["evidence_index"]
        if idx is not None:
            assert 0 <= idx < len(by_id[c["record_id"]]["evidence"]), c
    assert (body["coverage"] == "none") == (body["citations"] == [])


def _cited(body):
    return {c["record_id"] for c in body["citations"]}


def test_c13_no_matching_candidate_is_none_without_citations(ask, make_record):
    """D-037: coverage none if 0 candidates score cosine >= 0.3; none <=> no citations."""
    cands = [make_record(UNRELATED_EN) for _ in range(3)]
    body = ask(QUERY_EN, "en", cands)
    assert body["coverage"] == "none"
    assert body["citations"] == []


def test_c13_no_candidates_is_none(ask):
    """D-037 / brain_api.md: candidates may be empty -> coverage none, no citations."""
    body = ask(QUERY_EN, "en", [])
    assert body["coverage"] == "none"
    assert body["citations"] == []


def test_c13_one_match_is_partial_and_cites_it(ask, make_record):
    """D-037: partial if exactly 1 candidate scores >= 0.3; it cites the top-ranked candidate."""
    match = make_record(QUERY_EN)
    cands = [make_record(UNRELATED_EN), match, make_record(UNRELATED_EN)]
    body = ask(QUERY_EN, "en", cands)
    assert body["coverage"] == "partial"
    assert match["id"] in _cited(body)


def test_c13_two_matches_is_full(ask, make_record):
    """D-037: full if 2 or more candidates score >= 0.3."""
    m1, m2 = make_record(QUERY_EN), make_record(QUERY_EN)
    cands = [make_record(UNRELATED_EN), m1, m2]
    body = ask(QUERY_EN, "en", cands)
    assert body["coverage"] == "full"
    assert {m1["id"], m2["id"]} <= _cited(body)


def test_c13_many_matches_is_full_and_cites_at_most_three(ask, make_record):
    """D-037: full; brain_api.md: cites the top matches (at most 3)."""
    cands = [make_record(QUERY_EN) for _ in range(5)]
    body = ask(QUERY_EN, "en", cands)
    assert body["coverage"] == "full"
    assert 1 <= len(body["citations"]) <= 3


def test_c13_japanese_query_matches_japanese_records(ask, make_record):
    """D-037 "so Japanese queries work": a JA query against JA records follows the same rule."""
    m1, m2 = make_record(QUERY_JA), make_record(QUERY_JA)
    body = ask(QUERY_JA, "ja", [m1, make_record(UNRELATED_JA), m2])
    assert body["coverage"] == "full"
    assert {m1["id"], m2["id"]} <= _cited(body)
    body = ask(QUERY_JA, "ja", [m1, make_record(UNRELATED_JA)])
    assert body["coverage"] == "partial"
    body = ask(QUERY_JA, "ja", [make_record(UNRELATED_JA)])
    assert body["coverage"] == "none"


def test_c13_fixture_request_citations_reference_candidates(ask, request_fixture):
    """Brief c13: citations only reference candidate record ids; none <=> no citations (the
    ask.request.json fixture with the seed records)."""
    req = request_fixture("ask")
    ask(req["query"], req["lang"], req["candidates"])


def test_c13_deterministic(client, request_fixture):
    """D-037: deterministic: the same request gives the same body."""
    req = request_fixture("ask")
    assert client.post("/v1/ask", json=req).json() == client.post("/v1/ask", json=req).json()
