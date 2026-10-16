"""T2 acceptance: fake Brain /v1/translate (brief criterion 16).

Sources: plan §4.4 (texts[] {text, from_lang} -> items[]: Bilingual), §4.1 (both halves
non-empty); brain_api.md /translate (items[i] is texts[i]; its from_lang half is the input
verbatim, the other half the translation; at least 1 text).
"""

from __future__ import annotations

import pytest

PATH = "/v1/translate"


@pytest.fixture
def translate(client, endpoints):
    def run(texts):
        r = client.post(PATH, json={"texts": texts})
        assert r.status_code == 200, r.text[:500]
        body = r.json()
        endpoints["translate"].response.model_validate(body)
        assert body["contract_version"] == "1.0"
        return body["items"]

    return run


def _check(items, texts):
    assert len(items) == len(texts)
    for item, src in zip(items, texts, strict=True):
        assert set(item) >= {"ja", "en"}
        assert item[src["from_lang"]] == src["text"], (item, src)
        other = "en" if src["from_lang"] == "ja" else "ja"
        assert isinstance(item[other], str) and item[other].strip(), item
        assert item["ja"].strip() and item["en"].strip()


def test_c16_fixture_items_keep_input_verbatim(translate, request_fixture):
    """Brief c16: each item keeps the input verbatim in its from_lang half; both halves
    non-empty."""
    texts = request_fixture("translate")["texts"]
    _check(translate(texts), texts)


def test_c16_verbatim_is_not_normalised(translate):
    """Brief c16 "verbatim": no NFKC, case or punctuation changes in the from_lang half, and the
    order of items follows the order of texts."""
    texts = [
        {"text": "ＤＶＣ（サントリーニ）を１５ｍｍＨｇで…", "from_lang": "ja"},
        {"text": "Raised PNEUMO to 15 mmHg -- then WAITED!", "from_lang": "en"},
        {"text": "ｶﾞｰｾﾞで圧迫", "from_lang": "ja"},
        {"text": "a", "from_lang": "en"},
    ]
    _check(translate(texts), texts)


def test_c16_deterministic(translate, request_fixture):
    """D-037: deterministic."""
    texts = request_fixture("translate")["texts"]
    assert translate(texts) == translate(texts)


def test_c16_empty_texts_is_400(client, assert_api_error):
    """brain_api.md: texts[] at least 1 -> otherwise 400 bad_request."""
    assert_api_error(client.post(PATH, json={"texts": []}), 400, "bad_request")
