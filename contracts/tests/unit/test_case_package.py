"""Dev1's unit tests for models/case_package.py (plan §4.2, D-034)."""

import copy
import inspect

import pytest
from pydantic import BaseModel, ValidationError
from scrubgpt_contracts.models import case_package as cp

CASE_ID = "case-fixture-01"


def bi(en: str) -> dict:
    return {"ja": f"（{en}）", "en": en}


AI = {
    "trust_label": "ai_detected",
    "attributed_to": "ai",
    "generated_by": {"model_tier": "VISION_FAST", "model": "m", "prompt_version": "step.v1"},
    "confirmed_by": None,
    "confirmed_at": None,
}

CASE = {
    "contract_version": "1.0",
    "id": CASE_ID,
    "title": bi("Synthetic fixture case"),
    "source": "synthetic",
    "source_url": None,
    "language": "ja",
    "video_type": "full",
    "narrated": True,
    "synthetic_speech": True,
    "duration_s": 300.0,
    "default_step_track": "ai",
    "status": "complete",
    "data_note": bi("Synthetic test pattern; no patient data"),
}

TIMELINE = {
    "contract_version": "1.0",
    "case_id": CASE_ID,
    "steps": [
        {"t_start": 0.0, "t_end": 60.0, "confidence": 0.9, "provenance": AI,
         "id": f"{CASE_ID}.s001", "step_id": "rarp.p05.s01", "track": "ai"},
    ],
    "events": [
        {"t_start": 60.0, "t_end": 75.0, "confidence": 0.7, "provenance": AI,
         "id": f"{CASE_ID}.e001", "type": "bleeding", "signals": ["red_pixel_ratio"]},
    ],
    "instruments": [],
    "utterances": [
        {"t_start": 61.0, "t_end": 64.0, "confidence": 0.95, "provenance": AI,
         "id": f"{CASE_ID}.u0001", "speaker": None, "text": bi("Raise the pressure"),
         "original_lang": "ja", "class": "instruction"},
    ],
}  # fmt: skip

MOMENT_ID = f"{CASE_ID}.m01"
MOMENTS = {
    "contract_version": "1.0",
    "case_id": CASE_ID,
    "moments": [
        {
            "t_start": 55.0,
            "t_end": 75.0,
            "id": MOMENT_ID,
            "kind": "event",
            "step_id": "rarp.p05.s01",
            "title": bi("Bleeding during bladder neck dissection"),
            "why_flagged": [{"signal": "red_pixel_ratio", "detail": bi("Red area rose to 30%")}],
            "score": 0.8,
            "clip": f"clips/{MOMENT_ID}.mp4",
            "poster": f"clips/{MOMENT_ID}.jpg",
            "deep_look": None,
            "draft_obstacle": "bleeding.venous_plexus",
            "checkpoint_id": None,
            "provenance": AI,
        }
    ],
}

QUESTIONS = {
    "contract_version": "1.0",
    "case_id": CASE_ID,
    "operating": [
        {
            "id": f"{MOMENT_ID}.q1",
            "moment_id": MOMENT_ID,
            "type": "confirm_quote",
            "text": bi("You said to raise the pressure. Is that what you did?"),
            "ai_draft": None,
            "tap_options": [{"id": "pressure", "label": bi("Raised the pressure")}],
            "est_seconds": 10.0,
            "quote": {"utterance_id": f"{CASE_ID}.u0001", "text": bi("Raise the pressure")},
        }
    ],
    "reviewer": [
        {
            "id": f"{MOMENT_ID}.r1",
            "moment_id": MOMENT_ID,
            "type": "options_here",
            "text": bi("What would you have done here?"),
            "ai_draft": None,
            "tap_options": [],
            "est_seconds": 30.0,
            "quote": None,
        }
    ],
}

METRICS = {
    "contract_version": "1.0",
    "case_id": "grasp-01",
    "frame_accuracy": 0.71,
    "segment_f1": 0.64,
    "per_step": [{"step_id": "rarp.p05.s01", "precision": 0.8, "recall": 0.6}],
    "n_frames": 3600,
    "model_info": {"model_tier": "VISION_FAST", "model": "m", "prompt_version": "step.v1"},
}

SEED_RECORDS = {"contract_version": "1.0", "case_id": CASE_ID, "records": []}

DOCUMENTS = [
    (cp.Case, CASE),
    (cp.Timeline, TIMELINE),
    (cp.Moments, MOMENTS),
    (cp.Questions, QUESTIONS),
    (cp.Metrics, METRICS),
    (cp.SeedRecords, SEED_RECORDS),
]


@pytest.mark.parametrize(("model", "data"), DOCUMENTS, ids=lambda x: getattr(x, "__name__", ""))
def test_documents_validate_and_round_trip(model, data):
    assert model.model_validate(data).model_dump(mode="json") == data


INSTRUMENT = {
    "t_start": 0.0,
    "t_end": 30.0,
    "confidence": 0.6,
    "provenance": AI,
    "id": f"{CASE_ID}.i001",
    "key": "needle_driver",
    "name": bi("Needle driver"),
}


def test_instruments_and_checkpoint_moments():
    timeline = changed(TIMELINE, lambda d: d["instruments"].append(INSTRUMENT))
    assert cp.Timeline.model_validate(timeline).instruments[0].key == "needle_driver"
    moments = changed(
        MOMENTS,
        lambda d: d["moments"][0].update(kind="checkpoint", checkpoint_id="rarp.p05.s01.c1"),
    )
    assert cp.Moments.model_validate(moments).moments[0].checkpoint_id == "rarp.p05.s01.c1"


def test_utterance_class_is_class_on_the_wire():
    timeline = cp.Timeline.model_validate(TIMELINE)
    assert timeline.utterances[0].class_ is cp.UtteranceClass.INSTRUCTION
    assert "class" in timeline.model_dump()["utterances"][0]
    schema = cp.Utterance.model_json_schema(mode="serialization")
    assert "class" in schema["properties"] and "class" in schema["required"]
    # The Python name is never accepted as a key: one spelling on the wire.
    renamed = copy.deepcopy(TIMELINE)
    renamed["utterances"][0]["class_"] = renamed["utterances"][0].pop("class")
    with pytest.raises(ValidationError):
        cp.Timeline.model_validate(renamed)


def changed(data: dict, mutate) -> dict:
    data = copy.deepcopy(data)
    mutate(data)
    return data


@pytest.mark.parametrize(
    ("model", "data", "mutate"),
    [
        (cp.Case, CASE, lambda d: d.update(language="none")),  # but narrated
        (cp.Case, CASE, lambda d: d.update(duration_s=0)),
        (cp.Case, CASE, lambda d: d.update(source="vimeo")),
        (cp.Case, CASE, lambda d: d.update(narrated="yes")),
        (cp.Case, CASE, lambda d: d.update(contract_version="2.0")),
        (cp.Case, CASE, lambda d: d.pop("source_url")),  # nullable, but a required key
        (cp.Timeline, TIMELINE, lambda d: d["steps"][0].update(id="grasp-01.s001")),
        (cp.Timeline, TIMELINE, lambda d: d["steps"][0].update(track="human")),
        (cp.Timeline, TIMELINE, lambda d: d["events"][0].update(type="fire")),
        (cp.Timeline, TIMELINE, lambda d: d["events"].append(copy.deepcopy(d["events"][0]))),
        (cp.Timeline, TIMELINE, lambda d: d["utterances"][0].update(t_end=60.0)),  # before start
        (cp.Timeline, TIMELINE, lambda d: d["utterances"][0].update({"class": "joke"})),
        (cp.Timeline, TIMELINE, lambda d: d.pop("instruments")),
        (cp.Moments, MOMENTS, lambda d: d["moments"][0].update(clip="clips/other.mp4")),
        (cp.Moments, MOMENTS, lambda d: d["moments"][0].update(poster=f"{MOMENT_ID}.jpg")),
        (cp.Moments, MOMENTS, lambda d: d["moments"][0].update(score=1.5)),
        (cp.Moments, MOMENTS, lambda d: d["moments"][0].update(draft_obstacle="bleeding")),
        (cp.Moments, MOMENTS, lambda d: d.update(case_id="grasp-01")),
        (cp.Questions, QUESTIONS, lambda d: d["operating"][0].update(id=f"{MOMENT_ID}.r1")),
        (cp.Questions, QUESTIONS, lambda d: d["reviewer"][0].update(id=f"{MOMENT_ID}.q1")),
        (cp.Questions, QUESTIONS, lambda d: d["operating"][0].update(moment_id=f"{CASE_ID}.m02")),
        (cp.Questions, QUESTIONS, lambda d: d["operating"][0].update(quote=None)),
        (cp.Questions, QUESTIONS, lambda d: d["operating"][0].update(est_seconds=0)),
        (cp.Questions, QUESTIONS, lambda d: d["operating"][0].update(type="avoidable")),
        (
            cp.Questions,
            QUESTIONS,
            lambda d: d["operating"][0]["tap_options"].append(
                copy.deepcopy(d["operating"][0]["tap_options"][0])
            ),
        ),
        (cp.Timeline, TIMELINE, lambda d: d["instruments"].append(dict(INSTRUMENT, key="Needle"))),
        (cp.Moments, MOMENTS, lambda d: d["moments"][0].update(kind="checkpoint")),  # no id
        (cp.Moments, MOMENTS, lambda d: d["moments"][0].update(checkpoint_id="rarp.p05.s01.c1")),
        (
            cp.Moments,
            MOMENTS,
            lambda d: d["moments"][0].update(kind="checkpoint", checkpoint_id="rarp.p06.s01.c1"),
        ),
        (
            cp.Questions,
            QUESTIONS,
            lambda d: d["operating"][0]["tap_options"].append({"id": "confirm", "label": bi("OK")}),
        ),
        (
            cp.Questions,
            QUESTIONS,
            lambda d: d["operating"][0]["quote"].update(utterance_id="grasp-01.u0001"),
        ),
        (cp.Metrics, METRICS, lambda d: d.update(n_frames=0)),
        (cp.Metrics, METRICS, lambda d: d.update(n_frames=3600.0)),
        (cp.Metrics, METRICS, lambda d: d.update(segment_f1=1.1)),
        (cp.Metrics, METRICS, lambda d: d["per_step"].append(copy.deepcopy(d["per_step"][0]))),
    ],
)
def test_invalid_documents(model, data, mutate):
    with pytest.raises(ValidationError):
        model.model_validate(changed(data, mutate))


def test_seed_records_must_be_from_the_case(record):
    assert cp.SeedRecords.model_validate({**SEED_RECORDS, "records": [record]})
    with pytest.raises(ValidationError):
        cp.SeedRecords.model_validate({**SEED_RECORDS, "case_id": "grasp-01", "records": [record]})
    with pytest.raises(ValidationError):
        cp.SeedRecords.model_validate({**SEED_RECORDS, "records": [record, record]})


def test_file_tables():
    assert set(cp.JSON_FILES) <= {*cp.REQUIRED_FILES, "metrics.json"}
    assert "metrics.json" not in cp.REQUIRED_FILES


MODELS = [
    obj
    for obj in vars(cp).values()
    if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj.__module__ == cp.__name__
]


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_every_v1_field_is_required_and_tolerant(model):
    assert model.model_config.get("extra") == "ignore"
    assert all(field.is_required() for field in model.model_fields.values())
    schema = model.model_json_schema(mode="serialization")
    assert len(schema.get("required", [])) == len(model.model_fields)
