"""T2 acceptance: fake Brain /v1/embed (brief criterion 12).

Sources: D-037 and plan §4.5 (NFKC + lowercase; Latin word tokens + CJK character bigrams;
blake2b -> 256 buckets; L2-normalised; "so Japanese queries work"); plan §4.4 (vectors, dim,
model); brain_api.md /embed ("text without tokens -> the zero vector").
"""

from __future__ import annotations

import math

import pytest


@pytest.fixture
def embed(client, endpoints):
    def run(*texts: str) -> list[list[float]]:
        r = client.post("/v1/embed", json={"texts": list(texts)})
        assert r.status_code == 200, r.text[:500]
        body = r.json()
        endpoints["embed"].response.model_validate(body)
        assert len(body["vectors"]) == len(texts)
        return body["vectors"]

    return run


def test_c12_dim_256_and_vectors_match_texts(client, request_fixture):
    """D-037: 256 dims; plan §4.4: every vector has `dim` components, vectors[i] embeds
    texts[i]."""
    req = request_fixture("embed")
    body = client.post("/v1/embed", json=req).json()
    assert body["dim"] == 256
    assert isinstance(body["model"], str) and body["model"]
    assert len(body["vectors"]) == len(req["texts"])
    for v in body["vectors"]:
        assert len(v) == 256
        assert all(isinstance(x, float | int) and math.isfinite(x) for x in v)


@pytest.mark.parametrize(
    "text", ["静脈性のにじみ", "venous oozing near the ligature", "DVC 静脈 bleeding 2"]
)
def test_c12_vectors_are_l2_normalised(embed, text):
    """D-037: L2-normalised."""
    (v,) = embed(text)
    assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-6)


def test_c12_deterministic_across_calls_and_instances(embed, request_fixture):
    """D-037: the fake Brain is deterministic: the same text gives the same vector on every call
    and in a fresh app instance."""
    from fastapi.testclient import TestClient
    from scrubgpt_contracts.mock_brain.app import create_app

    texts = request_fixture("embed")["texts"]
    first = embed(*texts)
    assert embed(*texts) == first
    with TestClient(create_app()) as other:
        assert other.post("/v1/embed", json={"texts": texts}).json()["vectors"] == first
    # a text's vector doesn't depend on its batch neighbours
    assert embed(texts[1])[0] == first[1]


def test_c12_nfkc_and_lowercase(embed):
    """D-037: NFKC + lowercase: full-width Latin, upper case and half-width katakana embed the
    same as their normalised forms."""
    a, b = embed("ＶＥＮＯＵＳ Oozing", "venous oozing")
    assert a == b
    a, b = embed("ｶﾞｰｾﾞ", "ガーゼ")
    assert a == b
    a, b = embed("１５ mmHg", "15 mmhg")
    assert a == b


def test_c12_latin_word_tokens(embed, cosine):
    """D-037: Latin *word* tokens: word order and punctuation don't matter, but the same letters
    in a different word share nothing."""
    a, b = embed("venous oozing", "Oozing, venous!")
    assert a == b
    a, b = embed("oozing", "gnizoo")
    assert cosine(a, b) < 0.5
    a, b = embed("needle driver", "needledriver")
    assert cosine(a, b) < 0.5


def test_c12_cjk_character_bigrams(embed, cosine):
    """D-037: CJK character *bigrams*: the same characters in another order (no shared bigram)
    are not similar, while texts sharing a bigram are."""
    a, b = embed("静脈性", "脈静性")  # same characters; bigrams 静脈,脈性 vs 脈静,静性
    assert cosine(a, b) < 0.5, "looks like character unigrams, not bigrams"
    a, b = embed("静脈性", "脈性")  # shares the bigram 脈性
    assert cosine(a, b) > 0.3


def test_c12_japanese_query_scores_higher_than_unrelated_text(embed, cosine):
    """Brief c12 / D-037 "so Japanese queries work": a Japanese query and a Japanese text sharing
    words score higher than unrelated text."""
    query, related, unrelated_ja, unrelated_en = embed(
        "静脈性出血への対応",
        "結紮部の近くで静脈性出血があり気腹圧を上げた",
        "膀胱頸部を温存して吻合を行った",
        "the camera lens fogged up",
    )
    assert cosine(query, related) > cosine(query, unrelated_ja)
    assert cosine(query, related) > cosine(query, unrelated_en)
    assert cosine(query, related) > 0


def test_c12_text_without_tokens_gives_zero_vector(embed):
    """brain_api.md /embed: text without tokens -> the zero vector (still 256 components)."""
    (v,) = embed("、。！？ …")
    assert len(v) == 256
    assert all(x == 0 for x in v)


def test_c12_empty_texts_rejected(client, assert_api_error):
    """brain_api.md /embed: texts at least 1, non-empty -> otherwise 400 bad_request."""
    assert_api_error(client.post("/v1/embed", json={"texts": []}), 400, "bad_request")
    assert_api_error(client.post("/v1/embed", json={"texts": [""]}), 400, "bad_request")
