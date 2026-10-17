"""T2 acceptance: fake Brain /v1/answers/transcribe (brief criterion 14).

Sources: D-037 and plan §4.5 (fixed JA or EN sentence; lang_hint=auto returns the JA one);
plan §4.4 (multipart audio, max 25 MB, else 413 payload_too_large); plan §4.1 ApiError;
brain_api.md /transcribe (MAX_AUDIO_BYTES = 26 214 400; empty audio -> 400; the Brain doesn't
trust the part's content type); issue #5 risk note (content type differs by OS).
"""

from __future__ import annotations

import re

import pytest

PATH = "/v1/answers/transcribe"
CJK = re.compile(r"[぀-ヿ㐀-鿿]")
MAX_AUDIO_BYTES = 25 * 1024 * 1024


@pytest.fixture
def transcribe(client, endpoints, audio_fixture, new_uuid7):
    def run(lang_hint: str, audio: bytes | None = None, content_type: str = "audio/webm"):
        data = audio_fixture.read_bytes() if audio is None else audio
        return client.post(
            PATH,
            data={"lang_hint": lang_hint, "answer_id": new_uuid7()},
            files={"audio": (audio_fixture.name, data, content_type)},
        )

    return run


def _ok(r, endpoints):
    assert r.status_code == 200, r.text[:500]
    body = r.json()
    endpoints["transcribe"].response.model_validate(body)
    assert body["contract_version"] == "1.0"
    return body


def test_c14_auto_returns_the_japanese_sentence(transcribe, endpoints):
    """D-037: /transcribe with lang_hint=auto returns the JA sentence (lang "ja")."""
    body = _ok(transcribe("auto"), endpoints)
    assert body["lang"] == "ja"
    assert body["text"] and CJK.search(body["text"])


def test_c14_ja_returns_the_japanese_sentence(transcribe, endpoints):
    """plan §4.5: a fixed JA sentence for ja; auto and ja give the same JA sentence."""
    ja = _ok(transcribe("ja"), endpoints)
    assert ja["lang"] == "ja"
    assert ja["text"] and CJK.search(ja["text"])
    assert ja["text"] == _ok(transcribe("auto"), endpoints)["text"]


def test_c14_en_returns_english(transcribe, endpoints):
    """plan §4.5: en returns the fixed EN sentence (lang "en")."""
    body = _ok(transcribe("en"), endpoints)
    assert body["lang"] == "en"
    assert body["text"] and not CJK.search(body["text"])
    assert re.search(r"[A-Za-z]{2,}", body["text"])


def test_c14_deterministic(transcribe, endpoints):
    """D-037: deterministic (a fixed sentence)."""
    assert _ok(transcribe("en"), endpoints) == _ok(transcribe("en"), endpoints)


def test_c14_audio_over_25_mb_is_413_payload_too_large(transcribe, assert_api_error):
    """plan §4.4 / §4.1: an audio part over 25 MB -> 413 payload_too_large ApiError."""
    r = transcribe("ja", audio=b"\0" * (MAX_AUDIO_BYTES + 1))
    body = assert_api_error(r, 413, "payload_too_large")
    assert body["error"]["retryable"] is False  # brain_api.md default


def test_c14_audio_of_exactly_25_mb_is_accepted(transcribe, endpoints):
    """brain_api.md: audio <= 25 MB (MAX_AUDIO_BYTES = 26 214 400 bytes) is accepted."""
    _ok(transcribe("ja", audio=b"\0" * MAX_AUDIO_BYTES), endpoints)


def test_c14_empty_audio_is_400(transcribe, assert_api_error):
    """brain_api.md /transcribe: empty audio -> 400 bad_request."""
    assert_api_error(transcribe("ja", audio=b""), 400, "bad_request")


@pytest.mark.parametrize(
    "content_type", ["application/octet-stream", "audio/mp4", "video/webm", "audio/x-m4a"]
)
def test_c14_any_content_type_is_accepted(transcribe, endpoints, content_type):
    """Issue #5 risk note / brain_api.md: the fake Brain accepts the audio whatever content type
    arrives."""
    _ok(transcribe("en", content_type=content_type), endpoints)


def test_c14_invalid_lang_hint_is_400(transcribe, assert_api_error):
    """plan §4.4: lang_hint is ja / en / auto; anything else is 400 bad_request (422 -> 400)."""
    assert_api_error(transcribe("fr"), 400, "bad_request")
