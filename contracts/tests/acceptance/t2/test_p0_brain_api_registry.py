"""T2 acceptance: the ENDPOINTS registry and the Brain API models (issue #5 criteria 1-4, 11).

Sources: issue #5 Team Lead triage; plan §4.1 (contract_version, tolerant readers, D-023), §4.4
(endpoint paths, multipart transcribe); contracts/brain_api.md ("ENDPOINTS[name] is a frozen
Endpoint"; "Tolerant readers: requests and responses").
"""

from __future__ import annotations

import dataclasses
import importlib.metadata
import subprocess
from collections.abc import Mapping

import pytest
from pydantic import BaseModel, ValidationError

EXPECTED_PATHS = {
    "health": ("GET", "/health"),
    "transcribe": ("POST", "/v1/answers/transcribe"),
    "extract": ("POST", "/v1/answers/extract"),
    "translate": ("POST", "/v1/translate"),
    "embed": ("POST", "/v1/embed"),
    "ask": ("POST", "/v1/ask"),
    "briefing": ("POST", "/v1/briefing"),
}


def test_c01_endpoints_is_mapping_with_exactly_the_seven_names(endpoints):
    """#5 c1: `from scrubgpt_contracts.models.brain_api import ENDPOINTS` gives a mapping with
    exactly the keys health, transcribe, extract, translate, embed, ask, briefing."""
    assert isinstance(endpoints, Mapping)
    assert set(endpoints.keys()) == set(EXPECTED_PATHS)
    assert len(endpoints) == 7


@pytest.mark.parametrize("name", sorted(EXPECTED_PATHS))
def test_c02_endpoint_has_attributes_and_is_immutable(endpoints, name):
    """#5 c2: each value has method ("GET"/"POST"), path, request, response and files, and is
    immutable (a frozen dataclass or NamedTuple)."""
    ep = endpoints[name]
    for attr in ("method", "path", "request", "response", "files"):
        assert hasattr(ep, attr), f"{name} lacks {attr}"
    assert ep.method in ("GET", "POST")
    is_frozen_dataclass = dataclasses.is_dataclass(ep) and ep.__dataclass_params__.frozen
    is_namedtuple = isinstance(ep, tuple) and hasattr(type(ep), "_fields")
    assert is_frozen_dataclass or is_namedtuple, f"{name}: {type(ep)} is not frozen"
    for attr in ("method", "path", "request", "response", "files"):
        with pytest.raises(AttributeError):
            setattr(ep, attr, None)


@pytest.mark.parametrize("name", sorted(EXPECTED_PATHS))
def test_c02_method_and_path_follow_plan_4_4(endpoints, name):
    """#5 c2: health is GET /health with request None; every other endpoint is POST on the plan
    §4.4 path."""
    ep = endpoints[name]
    assert (ep.method, ep.path) == EXPECTED_PATHS[name]
    if name == "health":
        assert ep.request is None
    else:
        assert isinstance(ep.request, type) and issubclass(ep.request, BaseModel)


@pytest.mark.parametrize("name", sorted(EXPECTED_PATHS))
def test_c03_files_attribute(endpoints, name):
    """#5 c3: files == ("audio",) for transcribe and () for all the others."""
    expected = ("audio",) if name == "transcribe" else ()
    assert endpoints[name].files == expected
    assert isinstance(endpoints[name].files, tuple)


def test_c03_transcribe_request_is_the_form_field_model(endpoints, new_uuid7):
    """#5 c3: transcribe.request is the form-field model (lang_hint in ja|en|auto, answer_id)."""
    form = endpoints["transcribe"].request
    assert set(form.model_fields) == {"lang_hint", "answer_id"}
    answer_id = new_uuid7()
    for hint in ("ja", "en", "auto"):
        form.model_validate({"lang_hint": hint, "answer_id": answer_id})
    with pytest.raises(ValidationError):
        form.model_validate({"lang_hint": "fr", "answer_id": answer_id})
    with pytest.raises(ValidationError):
        form.model_validate({"lang_hint": "ja"})
    with pytest.raises(ValidationError):
        form.model_validate({"answer_id": answer_id})


def test_c03_transcribe_answer_id_must_be_uuid7(endpoints):
    """brain_api.md: answer_id is a UUIDv7 ("UUIDs are UUIDv7"); plan §4.1 records and answers are
    UUIDv7."""
    form = endpoints["transcribe"].request
    with pytest.raises(ValidationError):
        form.model_validate(
            {"lang_hint": "ja", "answer_id": "1b4e28ba-2fa1-41d2-883f-0016d3cca427"}  # v4
        )
    with pytest.raises(ValidationError):
        form.model_validate({"lang_hint": "ja", "answer_id": "not-a-uuid"})


@pytest.mark.parametrize("name", sorted(EXPECTED_PATHS))
def test_c04_response_models_are_versioned_tolerant_readers(endpoints, name):
    """#5 c4: every response model is a Pydantic model with a contract_version field and is a
    tolerant reader (extra="ignore", D-023)."""
    from scrubgpt_contracts.models.common import VersionedModel

    response = endpoints[name].response
    assert isinstance(response, type) and issubclass(response, BaseModel)
    assert "contract_version" in response.model_fields
    assert issubclass(response, VersionedModel)
    assert response.model_config.get("extra") == "ignore"


@pytest.mark.parametrize("name", sorted(n for n in EXPECTED_PATHS if n != "health"))
def test_c04_request_models_are_tolerant_readers(endpoints, request_fixture, name):
    """brain_api.md "Tolerant readers: every model ignores unknown fields: requests and
    responses"; D-023. An unknown key at the top level is accepted and dropped."""
    model = endpoints[name].request
    assert model.model_config.get("extra") == "ignore"
    body = request_fixture(name)
    body["x_future_field"] = {"anything": 1}
    parsed = model.model_validate(body)
    assert "x_future_field" not in parsed.model_dump()


def test_c04_response_reader_ignores_unknown_nested_fields(endpoints, client, request_fixture):
    """D-023 / plan §4.1: an older reader still accepts a newer MINOR version: unknown fields are
    ignored at every level, and contract_version 1.x is accepted."""
    body = client.post("/v1/ask", json=request_fixture("ask")).json()
    body["x_new"] = 1
    body["contract_version"] = "1.7"
    body["answer"]["x_new"] = "extra"
    for c in body["citations"]:
        c["x_new"] = True
    endpoints["ask"].response.model_validate(body)


def test_c11_main_entry_points_are_callable():
    """#5 c11: scrubgpt_contracts.mock_brain and scrubgpt_contracts.codegen each expose a callable
    main()."""
    import scrubgpt_contracts.codegen as codegen
    import scrubgpt_contracts.mock_brain as mock_brain

    assert callable(mock_brain.main)
    assert callable(codegen.main)


@pytest.mark.parametrize(
    ("script", "target"),
    [
        ("scrubgpt-mock-brain", "scrubgpt_contracts.mock_brain:main"),
        ("scrubgpt-codegen", "scrubgpt_contracts.codegen:main"),
    ],
)
def test_c11_console_scripts_resolve(console_script, script, target):
    """#5 c11: the scrubgpt-mock-brain and scrubgpt-codegen console scripts resolve."""
    eps = {ep.name: ep for ep in importlib.metadata.entry_points(group="console_scripts")}
    assert script in eps
    assert eps[script].value == target
    assert callable(eps[script].load())
    done = subprocess.run(
        [str(console_script(script)), "--help"], capture_output=True, text=True, timeout=60
    )
    assert done.returncode == 0, done.stderr
    assert "usage" in done.stdout.lower()
