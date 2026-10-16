"""Dev1's unit tests for models/common.py (plan §4.1; Team Lead answer on issue #3)."""

import inspect
import json
import math
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError
from scrubgpt_contracts.models import common as c


def ok(type_, value):
    return TypeAdapter(type_).validate_python(value)


def bad(type_, value):
    with pytest.raises(ValidationError):
        TypeAdapter(type_).validate_python(value)


# ── Bilingual and strings ─────────────────────────────────────────────────────


def test_bilingual_needs_both_halves_non_empty():
    assert c.Bilingual(ja="出血", en="bleeding").en == "bleeding"
    for value in [{"ja": "", "en": "x"}, {"ja": "x", "en": "   "}, {"ja": "x"}, {"en": "x"}]:
        bad(c.Bilingual, value)


def test_unknown_fields_are_ignored():
    value = c.Bilingual.model_validate({"ja": "a", "en": "b", "added_in_1_1": 5})
    assert value.model_dump() == {"ja": "a", "en": "b"}


def test_numbers_and_booleans_are_strict():
    assert ok(c.Seconds, 3) == 3.0
    for value in ["1.5", True, -0.1, math.nan, math.inf]:
        bad(c.Seconds, value)
    for value in [-0.01, 1.01, "0.5"]:
        bad(c.UnitInterval, value)
    bad(c.ApiErrorDetail, {"code": "timeout", "message": "m", "retryable": "true"})


# ── Versions and timestamps ───────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["1.0", "1.1", "1.12"])
def test_contract_version_accepts_any_v1(value):
    assert ok(c.ContractVersion, value) == value


@pytest.mark.parametrize("value", ["1.01", "2.0", "1", "1.0.0", "", "v1.0"])
def test_contract_version_rejects_others(value):
    bad(c.ContractVersion, value)


@pytest.mark.parametrize(
    "value", ["2026-10-21T09:30:00Z", "2026-10-21T09:30:00+00:00", "2026-10-21T09:30:00.000Z"]
)
def test_timestamps_accept_any_utc_form_and_emit_z(value):
    parsed = ok(c.UtcDatetime, value)
    assert parsed == datetime(2026, 10, 21, 9, 30, tzinfo=UTC)
    dumped = TypeAdapter(c.UtcDatetime).dump_json(parsed).decode()
    assert dumped.startswith('"2026-10-21T09:30:00') and dumped.endswith('Z"')


@pytest.mark.parametrize("value", ["2026-10-21T09:30:00", "2026-10-21T18:30:00+09:00"])
def test_timestamps_reject_naive_and_non_utc(value):
    bad(c.UtcDatetime, value)


# ── IDs ───────────────────────────────────────────────────────────────────────

VALID_IDS = {
    c.CaseId: ["grasp-01", "yt-en-03", "yt-ja-02", "case-fixture-01", "psi-ava-01"],
    c.MomentId: ["case-fixture-01.m07", "grasp-01.m01", "grasp-01.m100"],
    c.QuestionId: ["case-fixture-01.m07.q1", "case-fixture-01.m07.r1", "grasp-01.m01.q12"],
    c.OperatingQuestionId: ["case-fixture-01.m07.q1"],
    c.ReviewerQuestionId: ["case-fixture-01.m07.r2"],
    c.EventId: ["case-fixture-01.e012", "grasp-01.e1000"],
    c.UtteranceId: ["case-fixture-01.u0042", "grasp-01.u12345"],
    c.SegmentId: ["case-fixture-01.s001", "grasp-01.s1000"],
    c.InstrumentSpanId: ["case-fixture-01.i002"],
    c.ProcedureId: ["rarp"],
    c.PhaseId: ["rarp.p01", "rarp.p13"],
    c.StepId: ["rarp.p05.s01"],
    c.CheckpointId: ["rarp.p06.s02.c1"],
    c.ObstacleLeafId: ["anatomical_variation.median_lobe", "bleeding.venous_plexus"],
}
INVALID_IDS = {
    c.CaseId: ["Grasp-01", "grasp_01", "grasp.01", "-grasp", ""],
    c.MomentId: ["case-fixture-01.m7", "case-fixture-01.M07", "case-fixture-01.07"],
    c.QuestionId: ["case-fixture-01.m07.q0", "case-fixture-01.m07.q01", "case-fixture-01.m07.x1"],
    c.OperatingQuestionId: ["case-fixture-01.m07.r1"],
    c.ReviewerQuestionId: ["case-fixture-01.m07.q1"],
    c.EventId: ["case-fixture-01.e12"],
    c.UtteranceId: ["case-fixture-01.u042"],
    c.SegmentId: ["case-fixture-01.s01", "rarp.p05.s01"],
    c.InstrumentSpanId: ["case-fixture-01.i02"],
    c.ProcedureId: ["RARP", "1rarp"],
    c.PhaseId: ["rarp.p1", "rarp.05"],
    c.StepId: ["rarp.p05.s1", "rarp.p05"],
    c.CheckpointId: ["rarp.p06.s02.c0", "rarp.p06.s02"],
    c.ObstacleLeafId: ["bleeding", "smoke.thick", "bleeding.Venous", "bleeding.venous-plexus"],
}


@pytest.mark.parametrize(
    ("id_type", "value"), [(t, v) for t, values in VALID_IDS.items() for v in values]
)
def test_valid_ids(id_type, value):
    assert ok(id_type, value) == value


@pytest.mark.parametrize(
    ("id_type", "value"), [(t, v) for t, values in INVALID_IDS.items() for v in values]
)
def test_invalid_ids(id_type, value):
    bad(id_type, value)


def test_obstacle_families_are_the_fixed_eight():
    assert [f.value for f in c.ObstacleFamily] == [
        "bleeding",
        "anatomical_variation",
        "tissue_condition",
        "visibility",
        "technical_difficulty",
        "equipment",
        "patient_condition",
        "unexpected_finding",
    ]


def test_id_helpers():
    assert c.moment_id("grasp-01", 7) == "grasp-01.m07"
    assert c.question_id("grasp-01.m07", 1) == "grasp-01.m07.q1"
    assert c.question_id("grasp-01.m07", 2, reviewer=True) == "grasp-01.m07.r2"
    assert c.event_id("grasp-01", 12) == "grasp-01.e012"
    assert c.utterance_id("grasp-01", 42) == "grasp-01.u0042"
    assert c.segment_id("grasp-01", 4) == "grasp-01.s004"
    assert c.instrument_span_id("grasp-01", 2) == "grasp-01.i002"
    with pytest.raises(ValueError):
        c.moment_id("Bad Case", 1)
    with pytest.raises(ValueError):
        c.question_id("grasp-01.m07", 0)


def test_uuid7_ids():
    new = c.new_uuid7()
    assert new.version == 7
    assert ok(c.RecordId, str(new)) == new
    bad(c.AnswerId, "0b0e6f0e-4d3c-4f6e-9a3b-2c1d0e9f8a7b")  # a UUIDv4


# ── Field paths ───────────────────────────────────────────────────────────────


def test_field_paths():
    assert c.parse_field_path("action.text") == ("action", "text")
    assert c.parse_field_path("alternatives[0].why_not") == ("alternatives", 0, "why_not")
    for value in ["action.", ".text", "a..b", "a[x]", "Action", "a[0]b"]:
        bad(c.FieldPath, value)
        with pytest.raises(ValueError):
            c.parse_field_path(value)


def test_get_at_path_in_json_and_models():
    data = {"alternatives": [{"option": {"ja": "a", "en": "b"}, "why_not": None}]}
    assert c.get_at_path(data, "alternatives[0].option.en") == "b"
    assert c.get_at_path(data, "alternatives[0].why_not") is None
    model = c.ApiError.model_validate(
        {"contract_version": "1.0", "error": {"code": "timeout", "message": "m", "retryable": True}}
    )
    assert c.get_at_path(model, "error.code") == c.ErrorCode.TIMEOUT
    for path in ["alternatives[1].option", "alternatives[0].nope", "alternatives[0].option.en.x"]:
        with pytest.raises(LookupError):
            c.get_at_path(data, path)
    with pytest.raises(LookupError):
        c.get_at_path(model, "error.nope")


# ── Spans, provenance, evidence ───────────────────────────────────────────────


def test_time_span():
    assert c.TimeSpan(t_start=5, t_end=5).t_end == 5.0
    bad(c.TimeSpan, {"t_start": 6, "t_end": 5})
    bad(c.TimeSpan, {"t_start": -1, "t_end": 5})


def test_provenance():
    human = c.Provenance.model_validate(
        {
            "trust_label": "operating_surgeon",
            "attributed_to": "operating_surgeon",
            "generated_by": None,
            "confirmed_by": "surgeon-a",
            "confirmed_at": "2026-10-21T09:30:00Z",
        }
    )
    assert human.trust_label is c.TrustLabel.OPERATING_SURGEON
    stt = c.GeneratedBy(model_tier="STT", model="whisper-1", prompt_version=None)
    assert stt.prompt_version is None
    bad(c.GeneratedBy, {"model_tier": "STT", "model": "whisper-1"})  # key is required (D-034)
    bad(c.Provenance, {**human.model_dump(), "trust_label": "doctor"})
    assert set(c.TRUST_LABEL_EMOJI) == set(c.TrustLabel)


EVIDENCE = [
    {"kind": "media", "case_id": "grasp-01", "uri": "video.mp4#t=2280.0,2520.0",
     "t_start": 2280.0, "t_end": 2520.0},
    {"kind": "media", "case_id": "grasp-01", "uri": "clips/grasp-01.m07.mp4#t=0,20",
     "t_start": 2280.0, "t_end": 2300.0},
    {"kind": "transcript", "case_id": "grasp-01", "utterance_id": "grasp-01.u0042",
     "quote": "ここで止血します"},
    {"kind": "answer_audio", "answer_id": "01a1435a-f708-7ff0-b0be-4efc75ad6204",
     "uri": "answers/01a1435a-f708-7ff0-b0be-4efc75ad6204.webm"},
    {"kind": "answer_text", "answer_id": "01a1435a-f708-7ff0-b0be-4efc75ad6204",
     "quote": "I clipped the vessel first."},
]  # fmt: skip


@pytest.mark.parametrize("value", EVIDENCE)
def test_evidence_kinds_round_trip(value):
    parsed = ok(c.Evidence, value)
    assert type(parsed).__name__.lower().startswith(value["kind"].replace("_", ""))
    dumped = json.loads(TypeAdapter(c.Evidence).dump_json(parsed))
    assert dumped == {**value, **{k: float(dumped[k]) for k in ("t_start", "t_end") if k in value}}


@pytest.mark.parametrize(
    "uri",
    [
        "video.mp4",
        "video.mp4#t=20,10",
        "https://example.com/video.mp4#t=0,1",
        "/data/video.mp4#t=0,1",
        "../other/video.mp4#t=0,1",
        "clips\\a.mp4#t=0,1",
        "video.mp4#t=-1,2",
    ],
)
def test_media_evidence_uri_rules(uri):
    bad(c.Evidence, {**EVIDENCE[0], "uri": uri})


def test_evidence_rejects_unknown_kind_and_foreign_utterance():
    bad(c.Evidence, {**EVIDENCE[2], "kind": "photo"})
    bad(c.Evidence, {**EVIDENCE[2], "utterance_id": "grasp-02.u0042"})


def test_media_fragment_helper():
    assert c.media_fragment("video.mp4", 2280, 2520) == "video.mp4#t=2280.0,2520.0"
    assert c.media_fragment("video.mp4", 0.04, 1.25) == "video.mp4#t=0.04,1.25"
    for args in [("video.mp4", 5, 4), ("/abs/video.mp4", 0, 1), ("video.mp4", -1, 1)]:
        with pytest.raises(ValueError):
            c.media_fragment(*args)


# ── API errors ────────────────────────────────────────────────────────────────


def test_api_error():
    assert c.ERROR_HTTP_STATUS == {
        c.ErrorCode.BAD_REQUEST: 400,
        c.ErrorCode.NOT_FOUND: 404,
        c.ErrorCode.PAYLOAD_TOO_LARGE: 413,
        c.ErrorCode.UNAVAILABLE: 503,
        c.ErrorCode.UPSTREAM_ERROR: 502,
        c.ErrorCode.REFUSED: 502,
        c.ErrorCode.TIMEOUT: 504,
    }
    body = c.api_error(c.ErrorCode.TIMEOUT, "OpenAI timed out").model_dump(mode="json")
    assert body == {
        "contract_version": "1.0",
        "error": {"code": "timeout", "message": "OpenAI timed out", "retryable": True},
    }
    assert c.api_error(c.ErrorCode.REFUSED, "no").error.retryable is False
    assert c.api_error(c.ErrorCode.REFUSED, "no", retryable=True).error.retryable is True


# ── Contract rules for every model in common.py ───────────────────────────────

MODELS = [
    obj
    for obj in vars(c).values()
    if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj.__module__ == c.__name__
]


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_every_v1_field_is_required_and_tolerant(model):
    assert model.model_config.get("extra") == "ignore"
    assert all(field.is_required() for field in model.model_fields.values())


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_json_schema_generates(model):
    schema = model.model_json_schema(mode="serialization")
    assert set(schema.get("required", [])) == set(model.model_fields)
