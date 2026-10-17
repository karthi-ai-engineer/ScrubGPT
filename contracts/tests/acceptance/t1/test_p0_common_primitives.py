"""AC5-AC9: shared primitives, timestamps, IDs, values and spans
(plan §4.1, D-034, D-035, #3, #4)."""

from __future__ import annotations

import copy
import json
import math
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
import uuid6
from pydantic import TypeAdapter, ValidationError
from scrubgpt_contracts.models import common
from scrubgpt_contracts.models.case_package import Case, Metrics, Moments, Questions, Timeline
from scrubgpt_contracts.models.common import (
    ERROR_HTTP_STATUS,
    ApiError,
    Bilingual,
    ErrorCode,
    Evidence,
    ObstacleFamily,
    Provenance,
    Role,
    TrustLabel,
)
from scrubgpt_contracts.models.decision_record import DecisionRecord
from scrubgpt_contracts.models.reference import ProcedureReference

CASE_ID = "case-fixture-01"
EVIDENCE = TypeAdapter(Evidence)

FAMILIES = (
    "bleeding",
    "anatomical_variation",
    "tissue_condition",
    "visibility",
    "technical_difficulty",
    "equipment",
    "patient_condition",
    "unexpected_finding",
)


def _set(doc: Any, path: tuple, value: Any) -> Any:
    doc = copy.deepcopy(doc)
    node = doc
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    return doc


def _provenance(**changes: Any) -> dict[str, Any]:
    base = {
        "trust_label": "operating_surgeon",
        "attributed_to": "operating_surgeon",
        "generated_by": {
            "model_tier": "TEXT_SMART",
            "model": "gpt-x",
            "prompt_version": "extract.v1",
        },
        "confirmed_by": "dr-a",
        "confirmed_at": "2026-10-21T09:30:00Z",
    }
    base.update(changes)
    return base


# --- AC5 Bilingual -----------------------------------------------------------------------


def test_ac5_bilingual_both_halves_accepted():
    """AC5: "`Bilingual`: `ja` and `en` are both required and non-empty" (plan §4.1)."""
    value = Bilingual.model_validate({"ja": "出血", "en": "Bleeding"})
    assert value.model_dump(mode="json") == {"ja": "出血", "en": "Bleeding"}


@pytest.mark.parametrize(
    "payload",
    [
        {"ja": "出血"},
        {"en": "Bleeding"},
        {},
        {"ja": "", "en": "Bleeding"},
        {"ja": "出血", "en": ""},
        {"ja": None, "en": "Bleeding"},
        {"ja": "出血", "en": None},
        {"ja": "   ", "en": "Bleeding"},
        {"ja": "出血", "en": " \t\n "},
        {"ja": "　", "en": "Bleeding"},
        {"ja": 1, "en": "Bleeding"},
        "Bleeding",
    ],
    ids=repr,
)
def test_ac5_bilingual_missing_empty_or_whitespace_half_is_rejected(payload):
    """AC5: "`ja` and `en` are both required and non-empty; whitespace-only is rejected"
    (plan §4.1, #3 point 7)."""
    with pytest.raises(ValidationError):
        Bilingual.model_validate(payload)


# --- AC6 Primitives -----------------------------------------------------------------------


def test_ac6_trust_label_has_exactly_the_seven_values():
    """AC6: "`TrustLabel` (7 values)" (plan §4.1)."""
    assert {t.value for t in TrustLabel} == {
        "ai_detected",
        "dataset_annotation",
        "narration_extracted",
        "operating_surgeon",
        "reviewer",
        "expert_validated",
        "simulated",
    }


def test_ac6_role_has_exactly_the_seven_values():
    """AC6: "`Role` (7 values)" (plan §4.1)."""
    assert {r.value for r in Role} == {
        "ai",
        "dataset",
        "narrator",
        "operating_surgeon",
        "reviewer",
        "expert",
        "dev_team_simulated",
    }


def test_ac6_provenance_shape():
    """AC6: "`Provenance` = { trust_label, attributed_to: Role, generated_by: { model_tier,
    model, prompt_version } | null, confirmed_by: str | null, confirmed_at: datetime | null }"
    (plan §4.1)."""
    dumped = Provenance.model_validate(_provenance()).model_dump(mode="json")
    assert set(dumped) == {
        "trust_label",
        "attributed_to",
        "generated_by",
        "confirmed_by",
        "confirmed_at",
    }
    assert set(dumped["generated_by"]) == {"model_tier", "model", "prompt_version"}
    # nullable parts (human-made items; STT has no prompt, #3 point 2)
    Provenance.model_validate(_provenance(generated_by=None, confirmed_by=None, confirmed_at=None))
    Provenance.model_validate(
        _provenance(
            generated_by={"model_tier": "STT", "model": "whisper-1", "prompt_version": None}
        )
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"trust_label": "verified"},
        {"attributed_to": "surgeon"},
        {"trust_label": None},
        {"attributed_to": None},
        {"generated_by": {"model_tier": "", "model": "gpt-x", "prompt_version": None}},
        {"generated_by": {"model_tier": "TEXT_SMART", "model": "", "prompt_version": None}},
        {"generated_by": {"model_tier": "TEXT_SMART", "model": None, "prompt_version": None}},
        {"generated_by": {"model_tier": "TEXT_SMART", "model": "gpt-x"}},
    ],
    ids=repr,
)
def test_ac6_provenance_rejects_bad_values(changes):
    """AC6 / #3 point 2: trust_label and attributed_to are the enums; `model_tier` and `model`
    are required non-empty strings; `prompt_version` is a required (nullable) key."""
    with pytest.raises(ValidationError):
        Provenance.model_validate(_provenance(**changes))


EVIDENCE_SAMPLES = {
    "media": {
        "kind": "media",
        "case_id": CASE_ID,
        "uri": "video.mp4#t=2280.0,2520.0",
        "t_start": 2280.0,
        "t_end": 2520.0,
    },
    "transcript": {
        "kind": "transcript",
        "case_id": CASE_ID,
        "utterance_id": f"{CASE_ID}.u0042",
        "quote": "少し出血しています",
    },
    "answer_audio": {
        "kind": "answer_audio",
        "answer_id": str(uuid6.uuid7()),
        "uri": "answers/0001.webm",
    },
    "answer_text": {
        "kind": "answer_text",
        "answer_id": str(uuid6.uuid7()),
        "quote": "Because the bleeding was venous",
    },
}


@pytest.mark.parametrize("kind", sorted(EVIDENCE_SAMPLES))
def test_ac6_evidence_four_kinds_with_their_fields(kind):
    """AC6: "`Evidence` tagged by `kind`, with 4 kinds and the fields in §4.1"."""
    parsed = EVIDENCE.validate_python(copy.deepcopy(EVIDENCE_SAMPLES[kind]))
    dumped = EVIDENCE.dump_python(parsed, mode="json")
    assert dumped["kind"] == kind
    assert set(dumped) == set(EVIDENCE_SAMPLES[kind])


@pytest.mark.parametrize("kind", sorted(EVIDENCE_SAMPLES))
def test_ac6_evidence_missing_field_is_rejected(kind):
    """AC6: each Evidence kind requires all its §4.1 fields."""
    for key in EVIDENCE_SAMPLES[kind]:
        if key == "kind":
            continue
        sample = copy.deepcopy(EVIDENCE_SAMPLES[kind])
        del sample[key]
        with pytest.raises(ValidationError):
            EVIDENCE.validate_python(sample)


@pytest.mark.parametrize("kind", ["video", "", None, "MEDIA"])
def test_ac6_evidence_unknown_kind_is_rejected(kind):
    """AC6: Evidence is a tagged union over exactly 4 kinds (plan §4.1)."""
    sample = copy.deepcopy(EVIDENCE_SAMPLES["media"])
    sample["kind"] = kind
    with pytest.raises(ValidationError):
        EVIDENCE.validate_python(sample)
    del sample["kind"]
    with pytest.raises(ValidationError):
        EVIDENCE.validate_python(sample)


def test_ac6_api_error_shape_and_codes(api_error_doc):
    """AC6: "`ApiError` {contract_version, error {code, message, retryable}} with the 7 codes"
    (plan §4.1)."""
    assert {c.value for c in ErrorCode} == {
        "bad_request",
        "not_found",
        "payload_too_large",
        "unavailable",
        "upstream_error",
        "refused",
        "timeout",
    }
    dumped = ApiError.model_validate(api_error_doc).model_dump(mode="json")
    assert set(dumped) == {"contract_version", "error"}
    assert set(dumped["error"]) == {"code", "message", "retryable"}
    for code in ErrorCode:
        doc = copy.deepcopy(api_error_doc)
        doc["error"]["code"] = code.value
        ApiError.model_validate(doc)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("error", "code"), "validation_error"),
        (("error", "code"), None),
        (("error", "message"), None),
        (("error", "retryable"), None),
        (("error", "retryable"), "false"),
        (("error",), None),
    ],
    ids=repr,
)
def test_ac6_api_error_rejects_bad_values(api_error_doc, path, value):
    """AC6: ApiError `code` is one of the 7 codes; message and retryable are required."""
    with pytest.raises(ValidationError):
        ApiError.model_validate(_set(api_error_doc, path, value))


def test_ac6_api_error_http_mapping():
    """AC6: "HTTP mapping 400/404/413/503/502/502/504" (plan §4.1; #3 point 9
    `ERROR_HTTP_STATUS`)."""
    expected = {
        "bad_request": 400,
        "not_found": 404,
        "payload_too_large": 413,
        "unavailable": 503,
        "upstream_error": 502,
        "refused": 502,
        "timeout": 504,
    }
    assert {ErrorCode(k).value: v for k, v in ERROR_HTTP_STATUS.items()} == expected


# --- AC7 Timestamps -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "stamp",
    [
        "2026-10-21T09:30:00Z",
        "2026-10-21T09:30:00+00:00",
        "2026-10-21T09:30:00.000Z",
        "2026-10-21T09:30:00.123456Z",
        "2026-10-21T09:30:00.5+00:00",
        datetime(2026, 10, 21, 9, 30, tzinfo=UTC),
    ],
    ids=str,
)
def test_ac7_utc_timestamps_are_accepted_and_emitted_with_z(stamp):
    """AC7: "UTC only. `Z`, `+00:00` and fractional seconds are accepted ... output ends with
    `Z`" (plan §4.1, #3 point 4)."""
    parsed = Provenance.model_validate(_provenance(confirmed_at=stamp))
    out = parsed.model_dump(mode="json")["confirmed_at"]
    assert isinstance(out, str) and out.endswith("Z"), out
    assert parsed.confirmed_at.utcoffset() == timedelta(0)
    assert json.loads(parsed.model_dump_json())["confirmed_at"].endswith("Z")
    reparsed = datetime.fromisoformat(out.replace("Z", "+00:00"))
    assert reparsed == datetime.fromisoformat(
        stamp.replace("Z", "+00:00") if isinstance(stamp, str) else stamp.isoformat()
    )


@pytest.mark.parametrize(
    "stamp",
    [
        "2026-10-21T09:30:00",
        "2026-10-21T18:30:00+09:00",
        "2026-10-21T04:30:00-05:00",
        "2026-10-21T09:30:00.000+01:00",
        datetime(2026, 10, 21, 9, 30),
        datetime(2026, 10, 21, 18, 30, tzinfo=timezone(timedelta(hours=9))),
        "yesterday",
    ],
    ids=str,
)
def test_ac7_naive_and_non_utc_timestamps_are_rejected(stamp):
    """AC7: "naive values and non-UTC offsets are rejected" (#3 point 4)."""
    with pytest.raises(ValidationError):
        Provenance.model_validate(_provenance(confirmed_at=stamp))


# --- AC8 IDs ------------------------------------------------------------------------------

ID_CASES: dict[str, tuple[list[str], list[str]]] = {
    "CaseId": (
        ["grasp-01", "yt-en-03", "yt-ja-02", "case-fixture-01", "c1"],
        ["Case-01", "case.01", "case_01", "-case", "case-", "case--01", "", "case 01"],
    ),
    "MomentId": (
        [f"{CASE_ID}.m01", f"{CASE_ID}.m07", f"{CASE_ID}.m100", "grasp-01.m12"],
        [f"{CASE_ID}.m1", f"{CASE_ID}.m", f"{CASE_ID}.M01", f"{CASE_ID}.m01a", "m01", "Bad.m01"],
    ),
    "OperatingQuestionId": (
        [f"{CASE_ID}.m01.q1", f"{CASE_ID}.m07.q12"],
        [f"{CASE_ID}.m01.q0", f"{CASE_ID}.m01.q01", f"{CASE_ID}.m1.q1", f"{CASE_ID}.m01.r1"],
    ),
    "ReviewerQuestionId": (
        [f"{CASE_ID}.m01.r1", f"{CASE_ID}.m07.r10"],
        [f"{CASE_ID}.m01.r0", f"{CASE_ID}.m01.r01", f"{CASE_ID}.m01.q1", f"{CASE_ID}.m01.r"],
    ),
    "EventId": (
        [f"{CASE_ID}.e012", f"{CASE_ID}.e001", f"{CASE_ID}.e1000"],
        [f"{CASE_ID}.e12", f"{CASE_ID}.e1", f"{CASE_ID}.E012", f"{CASE_ID}.e01a"],
    ),
    "UtteranceId": (
        [f"{CASE_ID}.u0042", f"{CASE_ID}.u12345"],
        [f"{CASE_ID}.u042", f"{CASE_ID}.u42", f"{CASE_ID}.U0042"],
    ),
    "SegmentId": (
        [f"{CASE_ID}.s001", f"{CASE_ID}.s1000"],
        [f"{CASE_ID}.s01", f"{CASE_ID}.s1", "rarp.p05.s01"],
    ),
    "InstrumentSpanId": (
        [f"{CASE_ID}.i001", f"{CASE_ID}.i1234"],
        [f"{CASE_ID}.i01", f"{CASE_ID}.i1"],
    ),
    "PhaseId": (
        ["rarp.p01", "rarp.p13", "rarp.p100"],
        ["rarp.p1", "rarp.P01", "rarp", "rarp.p01.s01", ".p01"],
    ),
    "StepId": (
        ["rarp.p05.s01", "rarp.p12.s02", "rarp.p05.s100"],
        ["rarp.p05.s1", "rarp.p5.s01", "rarp.p05", f"{CASE_ID}.s001"],
    ),
    "CheckpointId": (
        ["rarp.p06.s02.c1", "rarp.p06.s02.c12"],
        ["rarp.p06.s02.c0", "rarp.p06.s02.c01", "rarp.p06.s2.c1", "rarp.p06.s02"],
    ),
    "ObstacleLeafId": (
        [f"{family}.some_leaf" for family in FAMILIES]
        + ["anatomical_variation.median_lobe", "bleeding.dvc_santorini", "visibility.smoke2"],
        [
            "surgeon_error.slip",
            "bleeding",
            "bleeding.",
            "bleeding.Median",
            "bleeding.median-lobe",
            "bleeding.median__lobe",
            "bleeding._lobe",
            "bleeding.lobe_",
            "Bleeding.dvc",
            "anatomical_variation.median_lobe.x",
        ],
    ),
}


@pytest.mark.parametrize("type_name", sorted(ID_CASES))
def test_ac8_id_formats(type_name):
    """AC8: IDs per §4.1/§4.2b "with minimum-width digits (#3 point 5, #4 point 2)": case,
    moment, operating/reviewer question, event, utterance, step segment, instrument span,
    phase, step, checkpoint and obstacle-leaf ids (8 fixed families, D-035)."""
    adapter = TypeAdapter(getattr(common, type_name))
    good, bad = ID_CASES[type_name]
    for value in good:
        assert adapter.validate_python(value) == value
    accepted = []
    for value in bad:
        try:
            adapter.validate_python(value)
        except ValidationError:
            continue
        accepted.append(value)
    assert not accepted, f"{type_name} accepted bad ids {accepted}"


def test_ac8_obstacle_family_is_the_eight_fixed_values():
    """AC8 / D-035: "8 fixed family IDs"."""
    assert {f.value for f in ObstacleFamily} == set(FAMILIES)


@pytest.mark.parametrize("type_name", ["RecordId", "AnswerId"])
def test_ac8_records_and_answers_are_uuid7(type_name):
    """AC8: "UUIDv7 for records and answers" (plan §4.1, D-034)."""
    adapter = TypeAdapter(getattr(common, type_name))
    good = uuid6.uuid7()
    assert str(adapter.validate_python(str(good))) == str(good)
    for bad in (str(uuid.uuid4()), str(uuid.uuid1()), "not-a-uuid", ""):
        with pytest.raises(ValidationError):
            adapter.validate_python(bad)


def test_ac8_record_and_answer_ids_in_models_reject_uuid4(docs):
    """AC8: DecisionRecord `id` and Evidence `answer_id` must be UUIDv7, not any UUID."""
    record = docs["seed_records.json"]["records"][0]
    DecisionRecord.model_validate(record)
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(_set(record, ("id",), str(uuid.uuid4())))
    sample = copy.deepcopy(EVIDENCE_SAMPLES["answer_text"])
    sample["answer_id"] = str(uuid.uuid4())
    with pytest.raises(ValidationError):
        EVIDENCE.validate_python(sample)


# --- AC9 Values and spans -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("uri", "t_start", "t_end"),
    [
        ("video.mp4#t=2280.0,2520.0", 2280.0, 2520.0),
        ("video.mp4#t=10,20", 10.0, 20.0),
        ("clips/case-fixture-01.m01.mp4#t=0,20", 58.0, 78.0),
        ("video.mp4#t=5.5,5.5", 5.5, 5.5),
    ],
)
def test_ac9_media_uri_relative_path_with_fragment_accepted(uri, t_start, t_end):
    """AC9: "a media evidence `uri` is `<relative path>#t=<start>,<end>`" (plan §4.1, #3 point
    6: integer or decimal seconds; clip-relative fragments may differ from t_start/t_end)."""
    sample = dict(EVIDENCE_SAMPLES["media"], uri=uri, t_start=t_start, t_end=t_end)
    EVIDENCE.validate_python(sample)


@pytest.mark.parametrize(
    "uri",
    [
        "video.mp4",
        "video.mp4#t=20,10",
        "video.mp4#t=10",
        "video.mp4#t=a,b",
        "video.mp4#t=-1,2",
        "video.mp4#t=1,2,3",
        "#t=1,2",
        "/video.mp4#t=1,2",
        "http://example.com/video.mp4#t=1,2",
        "file:///video.mp4#t=1,2",
        "../video.mp4#t=1,2",
        "clips/../video.mp4#t=1,2",
        "",
    ],
)
def test_ac9_media_uri_malformed_or_not_relative_is_rejected(uri):
    """AC9 / #3 point 6: "require start <= end, and require a relative POSIX path (no scheme,
    no leading `/`, no `..`)"."""
    sample = dict(EVIDENCE_SAMPLES["media"], uri=uri, t_start=1.0, t_end=2.0)
    with pytest.raises(ValidationError):
        EVIDENCE.validate_python(sample)


def test_ac9_answer_audio_uri_needs_no_fragment():
    """#3 point 6: "The pattern applies to `kind: media` only (`answer_audio.uri` is an app URI
    with no fragment)"."""
    EVIDENCE.validate_python(EVIDENCE_SAMPLES["answer_audio"])


SPAN_CARRIERS = [
    ("evidence-media", None),
    ("timeline.json", ("steps", 0)),
    ("timeline.json", ("events", 0)),
    ("timeline.json", ("instruments", 0)),
    ("timeline.json", ("utterances", 0)),
    ("moments.json", ("moments", 0)),
]


def _span_doc(docs, carrier, base, t_start, t_end):
    if carrier == "evidence-media":
        # A clip's fragment is relative to the clip and is not compared with t_start/t_end (#9
        # AC4 as clarified in Dev1's accepted analysis; `MediaFragmentUri` docstring), so only the
        # span rule can accept or reject this sample.
        return EVIDENCE.validate_python, dict(
            EVIDENCE_SAMPLES["media"],
            uri=f"clips/{CASE_ID}.m01.mp4#t=0,1",
            t_start=t_start,
            t_end=t_end,
        )
    model = {"timeline.json": Timeline, "moments.json": Moments}[carrier]
    doc = _set(docs[carrier], base + ("t_start",), t_start)
    doc = _set(doc, base + ("t_end",), t_end)
    return model.model_validate, doc


@pytest.mark.parametrize(("carrier", "base"), SPAN_CARRIERS, ids=lambda x: str(x))
def test_ac9_spans_start_non_negative_and_end_not_before_start(docs, carrier, base):
    """AC9: "`t_start` >= 0 and `t_end` >= `t_start`" (plan §4.1; #3 point 8: zero-length
    spans allowed)."""
    validate, doc = _span_doc(docs, carrier, base, 10.0, 10.0)
    validate(doc)  # zero-length span is fine
    validate, doc = _span_doc(docs, carrier, base, 0.0, 12.5)
    validate(doc)
    if carrier == "evidence-media":
        # the same spans on the normalised video, whose fragment must equal t_start/t_end (#9 AC4)
        for t_start, t_end in ((10.0, 10.0), (0.0, 12.5)):
            sample = dict(EVIDENCE_SAMPLES["media"], t_start=t_start, t_end=t_end)
            EVIDENCE.validate_python(dict(sample, uri=f"video.mp4#t={t_start},{t_end}"))
    for t_start, t_end in ((-0.1, 5.0), (12.0, 11.9), (-5.0, -1.0)):
        validate, doc = _span_doc(docs, carrier, base, t_start, t_end)
        with pytest.raises(ValidationError):
            validate(doc)


UNIT_INTERVAL_FIELDS = [
    ("timeline.json", ("steps", 0, "confidence")),
    ("timeline.json", ("events", 0, "confidence")),
    ("timeline.json", ("utterances", 0, "confidence")),
    ("timeline.json", ("instruments", 0, "confidence")),
    ("moments.json", ("moments", 0, "score")),
    ("seed_records.json", ("records", 0, "confidence")),
]


def _model_for(name):
    from scrubgpt_contracts.models.case_package import SeedRecords

    return {
        "timeline.json": Timeline,
        "moments.json": Moments,
        "seed_records.json": SeedRecords,
        "case.json": Case,
        "questions.json": Questions,
        "rarp.json": ProcedureReference,
    }[name]


@pytest.mark.parametrize(("name", "path"), UNIT_INTERVAL_FIELDS, ids=lambda x: str(x))
def test_ac9_confidence_and_score_in_unit_interval(docs, name, path):
    """AC9: "`confidence` and `score` are in [0, 1]" (plan §4.2, §4.3)."""
    model = _model_for(name)
    for ok in (0, 0.0, 0.5, 1, 1.0):
        model.model_validate(_set(docs[name], path, ok))
    for bad in (-0.01, 1.01, 2, -1):
        with pytest.raises(ValidationError):
            model.model_validate(_set(docs[name], path, bad))


FLOAT_FIELDS = [
    ("timeline.json", ("steps", 0, "t_start")),
    ("timeline.json", ("steps", 0, "t_end")),
    ("timeline.json", ("steps", 0, "confidence")),
    ("moments.json", ("moments", 0, "score")),
    ("moments.json", ("moments", 0, "t_end")),
    ("case.json", ("duration_s",)),
    ("questions.json", ("operating", 0, "est_seconds")),
    ("seed_records.json", ("records", 0, "confidence")),
    ("seed_records.json", ("records", 0, "evidence", 0, "t_end")),
    ("rarp.json", ("phases", 0, "typical_duration_s", "p50")),
    ("rarp.json", ("phases", 0, "steps", 0, "typical_duration_s", "p75")),
]


@pytest.mark.parametrize(("name", "path"), FLOAT_FIELDS, ids=lambda x: str(x))
def test_ac9_nan_and_infinity_are_rejected(docs, name, path):
    """AC9: "NaN and infinity are rejected" (#3 point 8: on every contract model)."""
    model = _model_for(name)
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValidationError):
            model.model_validate(_set(docs[name], path, bad))
        text = json.dumps(_set(docs[name], path, bad), ensure_ascii=False)
        with pytest.raises(ValidationError):
            model.model_validate_json(text)


def test_ac9_nan_rejected_in_metrics(metrics_doc):
    """AC9: NaN/infinity rejected in metrics.json scores too."""
    for path in (("frame_accuracy",), ("per_step", 0, "recall")):
        for bad in (math.nan, math.inf):
            with pytest.raises(ValidationError):
                Metrics.model_validate(_set(metrics_doc, path, bad))


STRINGLY = [
    ("timeline.json", ("steps", 0, "t_start"), "0.0"),
    ("timeline.json", ("steps", 0, "confidence"), "0.9"),
    ("moments.json", ("moments", 0, "score"), "0.92"),
    ("moments.json", ("moments", 0, "t_end"), "78"),
    ("case.json", ("duration_s",), "300"),
    ("case.json", ("narrated",), "true"),
    ("case.json", ("synthetic_speech",), "false"),
    ("questions.json", ("operating", 0, "est_seconds"), "15"),
    ("seed_records.json", ("records", 0, "confidence"), "0.84"),
    ("seed_records.json", ("records", 0, "evidence", 0, "t_start"), "58.0"),
    ("rarp.json", ("phases", 0, "order"), "1"),
    ("rarp.json", ("phases", 0, "typical_duration_s", "p50"), "600"),
]


@pytest.mark.parametrize(("name", "path", "value"), STRINGLY, ids=lambda x: str(x))
def test_ac9_numbers_and_booleans_sent_as_strings_are_rejected(docs, name, path, value):
    """AC9: "numbers or booleans sent as strings" are rejected."""
    model = _model_for(name)
    with pytest.raises(ValidationError):
        model.model_validate(_set(docs[name], path, value))
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(_set(docs[name], path, value), ensure_ascii=False))


def test_ac9_stringly_values_rejected_in_metrics_and_api_error(metrics_doc, api_error_doc):
    """AC9: numbers/booleans as strings rejected in metrics.json and ApiError too."""
    for path, value in ((("n_frames",), "1500"), (("frame_accuracy",), "0.7")):
        with pytest.raises(ValidationError):
            Metrics.model_validate(_set(metrics_doc, path, value))
    with pytest.raises(ValidationError):
        ApiError.model_validate(_set(api_error_doc, ("error", "retryable"), "false"))
