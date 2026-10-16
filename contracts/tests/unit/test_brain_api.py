"""Dev2's unit tests for `models/brain_api.py` (the Brain API models and `ENDPOINTS`)."""

import copy
import dataclasses
import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError
from scrubgpt_contracts.models.brain_api import (
    ENDPOINTS,
    Answer,
    AskResponse,
    EmbedResponse,
    ExtractRequest,
    ExtractResponse,
    TranscribeForm,
)
from scrubgpt_contracts.models.common import VersionedModel

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "brain_api"
ANSWER_ID = "01a1436a-d1c0-7a2b-9c3d-4e5f60718293"
RECORD_ID = "01a1436a-d1b8-7311-8fad-49edc656e70d"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.request.json").read_text(encoding="utf-8"))


def test_registry_names_paths_and_files() -> None:
    assert set(ENDPOINTS) == {
        "health",
        "transcribe",
        "extract",
        "translate",
        "embed",
        "ask",
        "briefing",
    }
    assert ENDPOINTS["health"].method == "GET"
    assert ENDPOINTS["health"].path == "/health"
    assert ENDPOINTS["health"].request is None
    assert ENDPOINTS["transcribe"].files == ("audio",)
    assert ENDPOINTS["transcribe"].request is TranscribeForm
    for name, endpoint in ENDPOINTS.items():
        if name != "health":
            assert endpoint.method == "POST"
            assert endpoint.path.startswith("/v1/")
        if name != "transcribe":
            assert endpoint.files == ()
        assert issubclass(endpoint.response, VersionedModel)
        assert endpoint.response.model_config["extra"] == "ignore"
        assert endpoint.timeout_s > 0


def test_registry_is_immutable() -> None:
    with pytest.raises(TypeError):
        ENDPOINTS["new"] = ENDPOINTS["health"]  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        ENDPOINTS["health"].path = "/other"  # type: ignore[misc]


@pytest.mark.parametrize("name", [n for n, e in ENDPOINTS.items() if e.request is not None])
def test_request_fixture_validates(name: str) -> None:
    model: type[BaseModel] = ENDPOINTS[name].request  # type: ignore[assignment]
    model.model_validate(fixture(name))


def test_audio_fixture_is_small_and_synthetic_format() -> None:
    files = sorted(FIXTURES.glob("transcribe.request.audio.*"))
    assert [f.suffix for f in files] == [".webm"]
    assert files[0].stat().st_size <= 100 * 1024
    assert files[0].read_bytes()[:4] == b"\x1a\x45\xdf\xa3"  # EBML (WebM) header


def test_extract_request_cross_checks() -> None:
    good = fixture("extract")
    ExtractRequest.model_validate(good)

    wrong_step = copy.deepcopy(good)
    wrong_step["moment"]["step_id"] = "rarp.p05.s01"
    with pytest.raises(ValidationError, match="moment's step"):
        ExtractRequest.model_validate(wrong_step)

    other_moment = copy.deepcopy(good)
    other_moment["question"]["moment_id"] = "case-fixture-01.m02"
    with pytest.raises(ValidationError):
        ExtractRequest.model_validate(other_moment)

    unknown_choice = copy.deepcopy(good)
    unknown_choice["answer"].update(
        mode="tap", tap={"verdict": "confirm", "choice_ids": ["nope"]}, text=None
    )
    with pytest.raises(ValidationError, match="not tap options"):
        ExtractRequest.model_validate(unknown_choice)


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        ({"mode": "tap", "tap": None, "text": None}, "tap is set exactly"),
        ({"mode": "text", "tap": None, "text": None}, "needs its text"),
        ({"mode": "voice", "tap": None, "text": None}, "needs its text"),
        (
            {"mode": "tap", "tap": {"verdict": "edit", "choice_ids": []}, "text": None},
            "edited text",
        ),
        ({"mode": "text", "tap": None, "text": "x", "audio_uri": "a.webm"}, "only for voice"),
    ],
)
def test_answer_rules(answer: dict, message: str) -> None:
    data = {"answer_id": ANSWER_ID, "lang": "ja", "audio_uri": None, **answer}
    with pytest.raises(ValidationError, match=message):
        Answer.model_validate(data)


def test_answer_id_must_be_uuid7() -> None:
    with pytest.raises(ValidationError):
        TranscribeForm.model_validate(
            {"lang_hint": "auto", "answer_id": "123e4567-e89b-42d3-a456-426614174000"}
        )


def test_ask_coverage_matches_citations() -> None:
    answer = {"ja": "回答", "en": "answer"}
    citation = {"record_id": RECORD_ID, "evidence_index": None}
    base = {"contract_version": "1.0", "answer": answer}
    AskResponse.model_validate({**base, "citations": [], "coverage": "none"})
    AskResponse.model_validate({**base, "citations": [citation], "coverage": "partial"})
    with pytest.raises(ValidationError):
        AskResponse.model_validate({**base, "citations": [citation], "coverage": "none"})
    with pytest.raises(ValidationError):
        AskResponse.model_validate({**base, "citations": [], "coverage": "full"})


def test_embed_dimension_is_checked() -> None:
    body = {"contract_version": "1.0", "vectors": [[0.0, 1.0]], "dim": 2, "model": "m"}
    EmbedResponse.model_validate(body)
    with pytest.raises(ValidationError, match="components"):
        EmbedResponse.model_validate({**body, "dim": 3})


def test_extract_response_paths_must_match_the_draft() -> None:
    from scrubgpt_contracts.mock_brain.logic import extract

    response = extract(ExtractRequest.model_validate(fixture("extract")))
    data = response.model_dump(mode="json")
    ExtractResponse.model_validate(data)

    bad_chip = copy.deepcopy(data)
    bad_chip["chips"].append({"field": "anticipation", "value": answer_text(), "editable": True})
    with pytest.raises(ValidationError, match="not the draft's"):
        ExtractResponse.model_validate(bad_chip)

    null_chip = copy.deepcopy(data)
    null_chip["chips"].append({"field": "anticipation", "value": None, "editable": True})
    with pytest.raises(ValidationError, match="is null in the draft"):
        ExtractResponse.model_validate(null_chip)

    bad_missing = copy.deepcopy(data)
    bad_missing["missing_fields"].append("action.text")
    with pytest.raises(ValidationError, match="is filled"):
        ExtractResponse.model_validate(bad_missing)


def answer_text() -> dict:
    return {"ja": "テキスト", "en": "text"}


def test_tolerant_reader_ignores_unknown_fields() -> None:
    body = {"contract_version": "1.1", "vectors": [[1.0]], "dim": 1, "model": "m", "extra": 1}
    EmbedResponse.model_validate(body)


def test_unstated_cue_must_be_missing_with_an_editable_chip() -> None:
    # D-054: a null situation_cue.text / action.text is listed and gets an editable chip.
    from scrubgpt_contracts.mock_brain.logic import extract

    data = extract(ExtractRequest.model_validate(fixture("extract"))).model_dump(mode="json")
    data["draft"]["situation_cue"] = {"text": None, "cue_terms": []}
    data["draft"]["grounding"] = [
        g for g in data["draft"]["grounding"] if g["field"] != "situation_cue.text"
    ]
    for chip in data["chips"]:
        if chip["field"] == "situation_cue.text":
            chip["value"] = None
    with pytest.raises(ValidationError, match="list it in missing_fields"):
        ExtractResponse.model_validate(data)
    data["missing_fields"].append("situation_cue.text")
    ExtractResponse.model_validate(data)
    for chip in data["chips"]:
        chip["editable"] = False
    with pytest.raises(ValidationError, match="editable chip"):
        ExtractResponse.model_validate(data)
