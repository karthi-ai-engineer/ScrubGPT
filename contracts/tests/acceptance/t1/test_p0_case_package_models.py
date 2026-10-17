"""AC11: Case Package models (plan §4.2, D-034, Team Lead answers on #4)."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from pydantic import ValidationError
from scrubgpt_contracts.models.case_package import (
    Case,
    Metrics,
    Moments,
    Questions,
    SeedRecords,
    Timeline,
)

CASE_ID = "case-fixture-01"
OTHER = "case-fixture-02"


def _with(doc: Any, path: tuple, value: Any) -> Any:
    doc = copy.deepcopy(doc)
    node = doc
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    return doc


def _without(doc: Any, path: tuple) -> Any:
    doc = copy.deepcopy(doc)
    node = doc
    for step in path[:-1]:
        node = node[step]
    del node[path[-1]]
    return doc


def _props(model) -> set[str]:
    return set(model.model_json_schema(mode="serialization")["properties"])


def _item_props(model, list_field: str) -> set[str]:
    schema = model.model_json_schema(mode="serialization")
    ref = schema["properties"][list_field]["items"]["$ref"].split("/")[-1]
    return set(schema["$defs"][ref]["properties"])


# --- case.json ----------------------------------------------------------------------------


def test_ac11_case_json_fields(docs):
    """AC11: case.json per §4.2 (`id`, `title`, `source`, `source_url`, `language`,
    `video_type`, `narrated`, `synthetic_speech`, `duration_s`, `default_step_track`, `status`,
    `data_note`) + `contract_version`."""
    Case.model_validate(docs["case.json"])
    assert _props(Case) == {
        "contract_version",
        "id",
        "title",
        "source",
        "source_url",
        "language",
        "video_type",
        "narrated",
        "synthetic_speech",
        "duration_s",
        "default_step_track",
        "status",
        "data_note",
    }


@pytest.mark.parametrize(
    ("field", "good", "bad"),
    [
        ("source", ["grasp", "psi-ava", "youtube", "synthetic"], ["vimeo", "GraSP"]),
        ("language", ["ja", "en"], ["fr", "auto"]),
        ("video_type", ["full", "edited"], ["partial"]),
        ("default_step_track", ["ai", "dataset"], ["both", "human"]),
        ("status", ["complete", "partial"], ["done"]),
        ("source_url", [None, "https://www.youtube.com/watch?v=x"], ["", "  "]),
        ("duration_s", [0.1, 300, 300.0], [0, 0.0, -1.0]),
        ("title", [{"ja": "症例", "en": "Case"}], ["Case", {"en": "Case"}]),
        ("data_note", [{"ja": "注", "en": "Note"}], [{"ja": "", "en": "Note"}]),
    ],
    ids=lambda x: str(x),
)
def test_ac11_case_json_values(docs, field, good, bad):
    """AC11: case.json enumerations and values (plan §4.2; #4 point 9: `duration_s` > 0,
    `source_url` non-empty string or null)."""
    for value in good:
        Case.model_validate(_with(docs["case.json"], (field,), value))
    for value in bad:
        with pytest.raises(ValidationError):
            Case.model_validate(_with(docs["case.json"], (field,), value))


def test_ac11_case_language_none_requires_no_speech(docs):
    """#4 point 9: "`language: none` requires `narrated: false` and `synthetic_speech:
    false`"."""
    base = _with(docs["case.json"], ("language",), "none")
    Case.model_validate(_with(_with(base, ("narrated",), False), ("synthetic_speech",), False))
    with pytest.raises(ValidationError):
        Case.model_validate(_with(_with(base, ("narrated",), True), ("synthetic_speech",), False))
    with pytest.raises(ValidationError):
        Case.model_validate(_with(_with(base, ("narrated",), False), ("synthetic_speech",), True))


# --- case_id in every file + item prefixes -------------------------------------------------


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("timeline.json", Timeline),
        ("moments.json", Moments),
        ("questions.json", Questions),
        ("seed_records.json", SeedRecords),
    ],
)
def test_ac11_case_id_required_in_every_case_file(docs, name, model):
    """AC11 / #4 point 1: "`case_id` in timeline, moments, questions, seed_records and
    metrics"."""
    assert "case_id" in _props(model)
    with pytest.raises(ValidationError):
        model.model_validate(_without(docs[name], ("case_id",)))
    with pytest.raises(ValidationError):
        model.model_validate(_with(docs[name], ("case_id",), "Not A Case"))


def test_ac11_metrics_shape_and_case_id(metrics_doc):
    """AC11 + plan §4.2: metrics.json = {contract_version, case_id, frame_accuracy, segment_f1,
    per_step[] {step_id, precision, recall}, n_frames, model_info}; #4 point 8."""
    Metrics.model_validate(metrics_doc)
    assert _props(Metrics) == {
        "contract_version",
        "case_id",
        "frame_accuracy",
        "segment_f1",
        "per_step",
        "n_frames",
        "model_info",
    }
    assert _item_props(Metrics, "per_step") == {"step_id", "precision", "recall"}
    with pytest.raises(ValidationError):
        Metrics.model_validate(_without(metrics_doc, ("case_id",)))
    with pytest.raises(ValidationError):  # D-034: nullable keys are still required keys
        Metrics.model_validate(_without(metrics_doc, ("model_info", "prompt_version")))
    for path, bad in (
        (("n_frames",), 0),
        (("n_frames",), 1.5),
        (("frame_accuracy",), 1.2),
        (("segment_f1",), -0.1),
        (("per_step", 0, "precision"), 1.01),
        (("per_step", 1, "step_id"), "rarp.p03.s01"),  # duplicate step_id
        (("model_info",), {"model_tier": "", "model": "x", "prompt_version": None}),
    ):
        with pytest.raises(ValidationError):
            Metrics.model_validate(_with(metrics_doc, path, bad))


@pytest.mark.parametrize(
    ("name", "model", "path", "value"),
    [
        ("timeline.json", Timeline, ("steps", 0, "id"), f"{OTHER}.s001"),
        ("timeline.json", Timeline, ("events", 0, "id"), f"{OTHER}.e001"),
        ("timeline.json", Timeline, ("instruments", 0, "id"), f"{OTHER}.i001"),
        ("timeline.json", Timeline, ("utterances", 0, "id"), f"{OTHER}.u0001"),
    ],
    ids=lambda x: str(x),
)
def test_ac11_item_ids_carry_the_case_prefix(docs, name, model, path, value):
    """AC11 / #4 decision (a): "item ids start with" the file's `case_id`."""
    with pytest.raises(ValidationError):
        model.model_validate(_with(docs[name], path, value))


def test_ac11_moment_and_question_ids_carry_the_case_prefix(docs):
    """AC11 / #4 decision (a): moment and question ids start with `<case_id>.`."""
    moments = copy.deepcopy(docs["moments.json"])
    m = moments["moments"][0]
    m["id"] = f"{OTHER}.m01"
    m["clip"] = f"clips/{OTHER}.m01.mp4"
    m["poster"] = f"clips/{OTHER}.m01.jpg"
    with pytest.raises(ValidationError):
        Moments.model_validate(moments)
    questions = copy.deepcopy(docs["questions.json"])
    q = questions["operating"][0]
    q["id"] = f"{OTHER}.m01.q1"
    q["moment_id"] = f"{OTHER}.m01"
    with pytest.raises(ValidationError):
        Questions.model_validate(questions)


def test_ac11_timeline_ids_unique(docs):
    """#4 point 2: one numbering for the whole timeline; ids unique."""
    tl = _with(docs["timeline.json"], ("steps", 1, "id"), docs["timeline.json"]["steps"][0]["id"])
    with pytest.raises(ValidationError):
        Timeline.model_validate(tl)


# --- timeline items -----------------------------------------------------------------------


def test_ac11_timeline_item_fields(docs):
    """AC11 / §4.2: every timeline item has `id`, `t_start`, `t_end`, `confidence`,
    `provenance`; steps add `step_id`, `track`; events `type`, `signals`; instruments `key`,
    `name` (#4 point 4); utterances `speaker`, `text`, `original_lang`, `class` (#4 point 5)."""
    Timeline.model_validate(docs["timeline.json"])
    common_fields = {"id", "t_start", "t_end", "confidence", "provenance"}
    assert _props(Timeline) == {
        "contract_version",
        "case_id",
        "steps",
        "events",
        "instruments",
        "utterances",
    }
    assert _item_props(Timeline, "steps") == common_fields | {"step_id", "track"}
    assert _item_props(Timeline, "events") == common_fields | {"type", "signals"}
    assert _item_props(Timeline, "instruments") == common_fields | {"key", "name"}
    assert _item_props(Timeline, "utterances") == common_fields | {
        "speaker",
        "text",
        "original_lang",
        "class",
    }


@pytest.mark.parametrize(
    ("path", "good", "bad"),
    [
        (("steps", 0, "track"), ["ai", "dataset"], ["human", None]),
        (("steps", 0, "step_id"), ["rarp.p03.s01"], ["rarp.p03", "p03.s01", None]),
        (
            ("events", 0, "type"),
            ["bleeding", "smoke", "out_of_body", "idle", "suction", "other"],
            ["fire", None],
        ),
        (("events", 0, "signals"), [[], ["red_pixel_ratio"], ["x", "y"]], [[""], ["  "], None]),
        (
            ("utterances", 0, "class"),
            [
                "instruction",
                "concern",
                "explanation",
                "decision",
                "bookmark",
                "teaching",
                "irrelevant",
            ],
            ["question", None],
        ),
        (("utterances", 0, "speaker"), [None, "speaker_1"], ["", "  "]),
        (("utterances", 0, "original_lang"), ["ja", "en"], ["none", "auto"]),
        (("utterances", 0, "text"), [{"ja": "あ", "en": "a"}], ["a", {"ja": "あ"}]),
        (
            ("instruments", 0, "key"),
            ["needle_driver", "bipolar_forceps", "scissors2"],
            ["Needle Driver", "needle-driver", "NeedleDriver", "", "_x", "x_", None],
        ),
        (("instruments", 0, "name"), [{"ja": "鉗子", "en": "Forceps"}], ["Forceps", None]),
    ],
    ids=lambda x: str(x),
)
def test_ac11_timeline_item_values(docs, path, good, bad):
    """AC11: timeline enumerations per §4.2; utterances use `class` on the wire; instruments
    carry a snake_case `key` and a Bilingual `name` (#4 points 3-5)."""
    for value in good:
        Timeline.model_validate(_with(docs["timeline.json"], path, value))
    for value in bad:
        with pytest.raises(ValidationError):
            Timeline.model_validate(_with(docs["timeline.json"], path, value))


def test_ac11_utterance_class_on_the_wire(docs):
    """AC11 / #4 point 5: "utterances use `class` on the wire": `model_dump()`,
    `model_dump_json()` and the generated schema write `class`, never `class_`."""
    tl = Timeline.model_validate(docs["timeline.json"])
    dumped = tl.model_dump()
    assert "class" in dumped["utterances"][0] and "class_" not in dumped["utterances"][0]
    dumped_json = json.loads(tl.model_dump_json())
    assert "class" in dumped_json["utterances"][0]
    assert "class_" not in dumped_json["utterances"][0]
    assert dumped_json["utterances"][0]["class"] == docs["timeline.json"]["utterances"][0]["class"]
    schema_text = json.dumps(Timeline.model_json_schema(mode="serialization"))
    assert '"class_"' not in schema_text
    assert '"class"' in schema_text


def test_ac11_instruments_key_required_list_may_be_empty(docs):
    """#4 point 4: `instruments` is a required key and may be `[]` until C4 (Block 5); each
    span carries `key`."""
    Timeline.model_validate(_with(docs["timeline.json"], ("instruments",), []))
    with pytest.raises(ValidationError):
        Timeline.model_validate(_without(docs["timeline.json"], ("instruments", 0, "key")))


# --- moments.json -------------------------------------------------------------------------


def test_ac11_moment_fields(docs):
    """AC11 / §4.2 moments[]: `id`, `kind`, `step_id`, `t_start`, `t_end`, `title`,
    `why_flagged[] {signal, detail}`, `score`, `clip`, `poster`, `deep_look`, `draft_obstacle`,
    `checkpoint_id`, `provenance`."""
    Moments.model_validate(docs["moments.json"])
    assert _props(Moments) == {"contract_version", "case_id", "moments"}
    assert _item_props(Moments, "moments") == {
        "id",
        "kind",
        "step_id",
        "t_start",
        "t_end",
        "title",
        "why_flagged",
        "score",
        "clip",
        "poster",
        "deep_look",
        "draft_obstacle",
        "checkpoint_id",
        "provenance",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("clip", "clips/case-fixture-01.m02.mp4"),
        ("clip", "clips/m01.mp4"),
        ("clip", "case-fixture-01.m01.mp4"),
        ("clip", "clips/case-fixture-01.m01.webm"),
        ("poster", "clips/case-fixture-01.m01.png"),
        ("poster", "clips/case-fixture-01.m02.jpg"),
        ("poster", "poster.jpg"),
        ("clip", None),
    ],
)
def test_ac11_clip_and_poster_paths(docs, field, value):
    """AC11 / #4 point 6: "`clip` = `clips/<moment_id>.mp4` and `poster` =
    `clips/<moment_id>.jpg`"."""
    with pytest.raises(ValidationError):
        Moments.model_validate(_with(docs["moments.json"], ("moments", 0, field), value))


def _moment_index(docs, kind: str) -> int:
    return next(i for i, m in enumerate(docs["moments.json"]["moments"]) if m["kind"] == kind)


def test_ac11_checkpoint_moment_needs_a_checkpoint_id(docs):
    """AC11 / #4 point 6: "`kind: checkpoint` <=> `checkpoint_id` is not null"."""
    i = _moment_index(docs, "checkpoint")
    with pytest.raises(ValidationError):
        Moments.model_validate(_with(docs["moments.json"], ("moments", i, "checkpoint_id"), None))


def test_ac11_non_checkpoint_moment_has_no_checkpoint_id(docs):
    """AC11 / #4 point 6: a moment that is not `kind: checkpoint` has `checkpoint_id: null`."""
    i = _moment_index(docs, "event")
    step = docs["moments.json"]["moments"][i]["step_id"]
    with pytest.raises(ValidationError):
        Moments.model_validate(
            _with(docs["moments.json"], ("moments", i, "checkpoint_id"), f"{step}.c1")
        )


def test_ac11_checkpoint_id_belongs_to_the_moments_own_step(docs):
    """AC11 / #4 point 6: "a `checkpoint_id` starts with `<step_id>.`" (checkpoints belong to
    steps, §4.2b)."""
    i = _moment_index(docs, "checkpoint")
    with pytest.raises(ValidationError):
        Moments.model_validate(
            _with(docs["moments.json"], ("moments", i, "checkpoint_id"), "rarp.p99.s01.c1")
        )


@pytest.mark.parametrize(
    ("path", "good", "bad"),
    [
        (("kind",), ["deviation", "event", "speech"], ["anomaly", None]),
        (("deep_look",), [None, {"ja": "所見", "en": "Finding"}], ["Finding", {"en": "x"}]),
        (
            ("draft_obstacle",),
            [None, "visibility.smoke"],
            ["smoke", "weather.rain", "bleeding.Big"],
        ),
        (("why_flagged",), [[]], [None]),
        (("why_flagged", 0, "signal"), ["anything_new"], ["", None]),
        (("why_flagged", 0, "detail"), [{"ja": "詳細", "en": "Detail"}], ["Detail"]),
        (("title",), [{"ja": "題", "en": "Title"}], ["Title", {"ja": " ", "en": "T"}]),
    ],
    ids=lambda x: str(x),
)
def test_ac11_moment_values(docs, path, good, bad):
    """AC11 / §4.2: moment kinds, Bilingual title/detail/deep_look, draft_obstacle is a
    taxonomy leaf id or null, why_flagged signal is a free non-empty string (#4 point 3)."""
    i = _moment_index(docs, "event")
    for value in good:
        Moments.model_validate(_with(docs["moments.json"], ("moments", i) + path, value))
    for value in bad:
        with pytest.raises(ValidationError):
            Moments.model_validate(_with(docs["moments.json"], ("moments", i) + path, value))


# --- questions.json -----------------------------------------------------------------------


def test_ac11_question_fields(docs):
    """AC11 / §4.2 questions: `operating[]`, `reviewer[]`, each `id`, `moment_id`, `type`,
    `text`, `ai_draft`, `tap_options[] {id, label}`, `est_seconds`, `quote`."""
    Questions.model_validate(docs["questions.json"])
    assert _props(Questions) == {"contract_version", "case_id", "operating", "reviewer"}
    expected = {
        "id",
        "moment_id",
        "type",
        "text",
        "ai_draft",
        "tap_options",
        "est_seconds",
        "quote",
    }
    assert _item_props(Questions, "operating") == expected
    assert _item_props(Questions, "reviewer") == expected


def test_ac11_operating_ids_are_q_and_reviewer_ids_are_r(docs):
    """AC11: "operating question ids are `.qN` and reviewer ids `.rN`" (D-034, #4 point 7)."""
    q = docs["questions.json"]
    with pytest.raises(ValidationError):
        Questions.model_validate(_with(q, ("operating", 0, "id"), f"{CASE_ID}.m01.r9"))
    with pytest.raises(ValidationError):
        Questions.model_validate(_with(q, ("reviewer", 0, "id"), f"{CASE_ID}.m01.q9"))


def test_ac11_question_id_starts_with_its_moment_id(docs):
    """#4 point 7: question ids start with `<moment_id>.`."""
    q = docs["questions.json"]
    with pytest.raises(ValidationError):
        Questions.model_validate(_with(q, ("operating", 0, "id"), f"{CASE_ID}.m05.q7"))


def test_ac11_question_ids_unique(docs):
    """#4 point 7: question ids unique in the file."""
    q = copy.deepcopy(docs["questions.json"])
    q["operating"].append(copy.deepcopy(q["operating"][0]))
    with pytest.raises(ValidationError):
        Questions.model_validate(q)


@pytest.mark.parametrize("verdict", ["confirm", "edit", "reject"])
def test_ac11_tap_option_ids_are_never_verdicts(docs, verdict):
    """AC11: "tap option ids are never confirm / edit / reject" (§4.2: the verdicts are built
    in, not tap options; #4 point 7)."""
    q = docs["questions.json"]
    i = next(i for i, x in enumerate(q["operating"]) if x["tap_options"])
    with pytest.raises(ValidationError):
        Questions.model_validate(_with(q, ("operating", i, "tap_options", 0, "id"), verdict))


def test_ac11_tap_option_ids_unique_and_labels_bilingual(docs):
    """#4 point 7: `tap_options[].id` non-empty and unique within the question; `label` is
    Bilingual (§4.2)."""
    q = docs["questions.json"]
    i = next(i for i, x in enumerate(q["operating"]) if len(x["tap_options"]) >= 2)
    first = q["operating"][i]["tap_options"][0]["id"]
    for path, value in (
        (("operating", i, "tap_options", 1, "id"), first),
        (("operating", i, "tap_options", 0, "id"), ""),
        (("operating", i, "tap_options", 0, "label"), "Label"),
    ):
        with pytest.raises(ValidationError):
            Questions.model_validate(_with(q, path, value))


def test_ac11_confirm_quote_needs_a_quote(docs):
    """AC11: "`confirm_quote` needs a quote" (#4 point 7)."""
    q = docs["questions.json"]
    i = next(i for i, x in enumerate(q["operating"]) if x["type"] == "confirm_quote")
    with pytest.raises(ValidationError):
        Questions.model_validate(_with(q, ("operating", i, "quote"), None))


@pytest.mark.parametrize(
    ("path", "good", "bad"),
    [
        (
            ("type",),
            ["cue", "decision", "reason", "alternatives", "checkpoint", "options_here"],
            ["prevention", "avoidable", None],
        ),
        (("est_seconds",), [0.5, 15, 15.0], [0, -1, None]),
        (("ai_draft",), [None, {"ja": "下書き", "en": "Draft"}], ["Draft"]),
        (("text",), [{"ja": "質問", "en": "Question"}], ["Question", {"ja": "質問"}]),
    ],
    ids=lambda x: str(x),
)
def test_ac11_question_values(docs, path, good, bad):
    """AC11 / §4.2: question types (no "prevention" type, D-027), `est_seconds` > 0 (#4
    point 7), Bilingual text and ai_draft."""
    q = docs["questions.json"]
    i = next(i for i, x in enumerate(q["operating"]) if x["type"] != "confirm_quote")
    for value in good:
        Questions.model_validate(_with(q, ("operating", i) + path, value))
    for value in bad:
        with pytest.raises(ValidationError):
            Questions.model_validate(_with(q, ("operating", i) + path, value))


def test_ac11_quote_shape_and_utterance_prefix(docs):
    """§4.2: `quote` = `{utterance_id, text: Bilingual}` or null; #4 point 7: `quote.utterance_id`
    starts with `<case_id>.`."""
    q = docs["questions.json"]
    i = next(i for i, x in enumerate(q["operating"]) if x["type"] == "confirm_quote")
    assert set(q["operating"][i]["quote"]) == {"utterance_id", "text"}
    for path, bad in (
        (("operating", i, "quote", "utterance_id"), f"{OTHER}.u0003"),
        (("operating", i, "quote", "text"), "plain"),
    ):
        with pytest.raises(ValidationError):
            Questions.model_validate(_with(q, path, bad))


# --- seed_records.json --------------------------------------------------------------------


def test_ac11_seed_records_shape(docs):
    """AC11 / §4.2: seed_records.json = `{contract_version, case_id, records[]}` of Decision
    Records."""
    SeedRecords.model_validate(docs["seed_records.json"])
    assert _props(SeedRecords) == {"contract_version", "case_id", "records"}
    bad = _with(docs["seed_records.json"], ("records", 0, "kind"), "deliberate_non_action")
    with pytest.raises(ValidationError):
        SeedRecords.model_validate(bad)
