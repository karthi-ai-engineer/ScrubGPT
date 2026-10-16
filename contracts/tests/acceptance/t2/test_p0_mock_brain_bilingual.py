"""T2 acceptance: every human-readable text in every fake Brain response is Bilingual with both
halves non-empty (brief criterion 17), plus counts-not-percentages in /briefing.

Sources: plan §4.1 ("Bilingual = {ja, en}, both halves non-empty. Every human-readable field
uses it", except verbatim quotes, D-048); brain_api.md "Bilingual" rule (verbatim quotes and the
transcript stay in the original language); CLAUDE.md guardrail and brain_api.md /briefing
("counts, not percentages, when n < 20").
"""

from __future__ import annotations

from typing import Any

import pytest

# String leaves that are not human-readable prose: ids, enums, paths, URIs, versions, model
# names, timestamps, verbatim quotes and terms (D-048), and the ApiError developer message.
NON_PROSE_KEYS = {
    "contract_version",
    "id",
    "case_id",
    "moment_id",
    "step_id",
    "record_id",
    "answer_id",
    "utterance_id",
    "language",
    "lang",
    "kind",
    "type",
    "family",
    "cause",
    "actor",
    "status",
    "source",
    "uri",
    "quote",
    "field",
    "trust_label",
    "attributed_to",
    "model_tier",
    "model",
    "prompt_version",
    "confirmed_by",
    "confirmed_at",
    "coverage",
    "mode",
    "cache_mode",
    "term",
    "cue_terms",
    "missing_fields",
    "model_tiers",
}


def _walk(node: Any, path: tuple, problems: list[str], *, transcript_ok: bool) -> None:
    if isinstance(node, dict):
        if "ja" in node and "en" in node:
            for half in ("ja", "en"):
                v = node[half]
                if not (isinstance(v, str) and v.strip()):
                    problems.append(f"{'.'.join(map(str, path))}.{half} empty: {v!r}")
            return
        for k, v in node.items():
            _walk(v, (*path, k), problems, transcript_ok=transcript_ok)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk(v, (*path, i), problems, transcript_ok=transcript_ok)
    elif isinstance(node, str):
        keys = [p for p in path if isinstance(p, str)]
        key = keys[-1] if keys else ""
        if key in NON_PROSE_KEYS:
            return
        if transcript_ok and path == ("text",):
            return  # the verbatim transcript (brain_api.md)
        if key.startswith("cue_terms") or (len(keys) >= 2 and keys[-2] == "model_tiers"):
            return
        problems.append(f"plain string at {'.'.join(map(str, path))}: {node[:60]!r}")


@pytest.fixture(scope="module")
def all_responses(client, request_fixture, audio_fixture, build_extract, case_data, new_uuid7):
    out: list[tuple[str, dict[str, Any]]] = []

    def keep(name, r):
        assert r.status_code == 200, (name, r.text[:500])
        out.append((name, r.json()))

    keep("health", client.get("/health"))
    for hint in ("ja", "en", "auto"):
        keep(
            "transcribe",
            client.post(
                "/v1/answers/transcribe",
                data={"lang_hint": hint, "answer_id": new_uuid7()},
                files={"audio": (audio_fixture.name, audio_fixture.read_bytes(), "audio/webm")},
            ),
        )
    keep("extract", client.post("/v1/answers/extract", json=request_fixture("extract")))
    for qid in case_data["questions"]:
        for lang, text in (("en", "I waited and watched."), ("ja", "様子を見ました。")):
            keep(
                "extract",
                client.post("/v1/answers/extract", json=build_extract(qid, text=text, lang=lang)),
            )
    keep("translate", client.post("/v1/translate", json=request_fixture("translate")))
    keep("embed", client.post("/v1/embed", json=request_fixture("embed")))
    keep("ask", client.post("/v1/ask", json=request_fixture("ask")))
    ask_ja = request_fixture("ask") | {"query": "静脈性出血", "lang": "ja"}
    keep("ask", client.post("/v1/ask", json=ask_ja))
    keep("ask", client.post("/v1/ask", json=request_fixture("ask") | {"candidates": []}))
    keep("briefing", client.post("/v1/briefing", json=request_fixture("briefing")))
    factors = [{"ja": "肥満", "en": "Obesity"}]
    for lang in ("ja", "en"):
        brief = request_fixture("briefing") | {"case_factors": factors, "lang": lang}
        keep("briefing", client.post("/v1/briefing", json=brief))
    keep(
        "briefing",
        client.post("/v1/briefing", json={"case_factors": [], "lang": "en", "candidates": []}),
    )
    return out


def test_c17_every_response_validates(all_responses, endpoints):
    """§4.4 / D-025: every fake Brain response matches the endpoint's response model."""
    for name, body in all_responses:
        endpoints[name].response.model_validate(body)


def test_c17_every_human_readable_text_is_bilingual_non_empty(all_responses):
    """Brief c17 / plan §4.1: every human-readable text in every fake Brain response is
    Bilingual with both halves non-empty."""
    problems: list[str] = []
    for name, body in all_responses:
        found: list[str] = []
        _walk(body, (), found, transcript_ok=(name == "transcribe"))
        problems += [f"{name}: {p}" for p in found]
    assert not problems, "\n".join(problems[:40])


def test_briefing_counts_not_percentages(all_responses):
    """CLAUDE.md guardrail / brain_api.md /briefing: counts, not percentages, when n < 20 (the
    fixtures send 5 records)."""
    for name, body in all_responses:
        if name != "briefing":
            continue
        for s in body["sections"]:
            for part in (s["title"], s["body"]):
                for half in ("ja", "en"):
                    assert "%" not in part[half] and "％" not in part[half], part[half]
