"""T2 acceptance: unstated cue or action in a fake-Brain /extract draft (D-054, issue #5 12b-12d).

Sources:
- D-054 (Team Lead decision, issue #5): in DecisionRecordDraft only, situation_cue.text and
  action.text may be null (a null cue has cue_terms []); action.type / action.actor stay set
  (`act` / `unknown` when not said); each null one is listed in missing_fields[] and has an
  editable chip; confirm_draft() raises while either is null; neither the fake nor the real
  Brain ever fills them from the moment title; canned fake-Brain drafts only when answer.lang
  equals the seed record's language, else the generic draft.
- Issue #5, Team Lead reply, criteria 12b, 12c, 12d (quoted per test).
- Plan §4.3 / Team Lead reply: `language` is the language the answer was originally given in.
- D-052 / G5: every filled field has a grounding quote (`ungrounded_fields()`).
- brain_api.md /extract (updated for D-054): chip `value` equals the draft's value and is null
  only for an unstated situation_cue.text / action.text; REQUIRED_TO_CONFIRM; the canned table
  for case-fixture-01; the generic draft fills the one field the question asks about, every
  other field stays null (action.actor: unknown), a reject without text fills nothing;
  extract.request.json sends the seed answer's text.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

PATH = "/v1/answers/extract"
QUESTIONS = (
    "case-fixture-01.m01.q1",
    "case-fixture-01.m01.q2",
    "case-fixture-01.m02.q1",
    "case-fixture-01.m02.q2",
    "case-fixture-01.m03.q1",
    "case-fixture-01.m04.q1",
    "case-fixture-01.m05.q1",
    "case-fixture-01.m06.q1",
    "case-fixture-01.m01.r1",
    "case-fixture-01.m01.r2",
    "case-fixture-01.m02.r1",
    "case-fixture-01.m04.r1",
)
LANGS = ("ja", "en")
PROBE_TEXT = {
    "en": "I irrigated the field and waited for the view to clear.",
    "ja": "術野を洗浄して、視野が晴れるまで待ちました。",
}
# Probe answers: every answer mode and tap verdict of plan §4.4 / brain_api.md /extract.
PROBES = ("text", "voice", "tap_confirm", "tap_edit", "tap_reject", "tap_reject_with_words")
TEXT_PROBES = ("text", "voice", "tap_edit", "tap_reject_with_words")


# --- helpers -----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def probe(client, build_extract, case_data, endpoints):
    """POST one probe answer to the in-process fake Brain; cached per (question, lang, probe)."""
    cache: dict[tuple[str, str, str], tuple[dict[str, Any], dict[str, Any]]] = {}

    def run(question_id: str, lang: str, kind: str) -> tuple[dict[str, Any], dict[str, Any]]:
        key = (question_id, lang, kind)
        if key in cache:
            return copy.deepcopy(cache[key])
        options = [o["id"] for o in case_data["questions"][question_id]["tap_options"]]
        text = PROBE_TEXT[lang]
        if kind == "text":
            req = build_extract(question_id, mode="text", text=text, lang=lang)
        elif kind == "voice":
            req = build_extract(question_id, mode="voice", text=text, lang=lang)
            req["answer"]["audio_uri"] = f"answers/{req['answer']['answer_id']}.webm"
        elif kind == "tap_confirm":
            tap = {"verdict": "confirm", "choice_ids": options[:1]}
            req = build_extract(question_id, mode="tap", text=None, lang=lang, tap=tap)
        elif kind == "tap_edit":
            tap = {"verdict": "edit", "choice_ids": []}
            req = build_extract(question_id, mode="tap", text=text, lang=lang, tap=tap)
        elif kind == "tap_reject":
            tap = {"verdict": "reject", "choice_ids": []}
            req = build_extract(question_id, mode="tap", text=None, lang=lang, tap=tap)
        else:  # tap_reject_with_words
            tap = {"verdict": "reject", "choice_ids": []}
            req = build_extract(question_id, mode="tap", text=text, lang=lang, tap=tap)
        endpoints["extract"].request.model_validate(req)
        r = client.post(PATH, json=req)
        assert r.status_code == 200, (key, r.text[:800])
        out = r.json()
        endpoints["extract"].response.model_validate(out)
        cache[key] = (req, out)
        return copy.deepcopy((req, out))

    return run


def _is_canned(req, extract_spec) -> bool:
    return (req["moment"]["id"], req["answer"]["lang"]) in extract_spec["canned"]


def _ungrounded(draft: dict[str, Any]) -> list[str]:
    from scrubgpt_contracts.models.decision_record import DecisionRecordDraft, ungrounded_fields

    return ungrounded_fields(DecisionRecordDraft.model_validate(draft))


def _halves(value: Any) -> list[str]:
    return [] if value is None else [value["ja"], value["en"]]


def _answer_material(req: dict[str, Any]) -> list[str]:
    """Everything the generic draft may quote (brain_api.md: the answer text, tapped labels, or
    the confirmed AI draft or quote)."""
    answer, question = req["answer"], req["question"]
    material = [answer["text"]] if answer["text"] else []
    if answer["tap"] is not None:
        labels = {o["id"]: o["label"] for o in question["tap_options"]}
        for cid in answer["tap"]["choice_ids"]:
            material += _halves(labels[cid])
        if answer["tap"]["verdict"] == "confirm":
            material += _halves(question["ai_draft"])
            if question["quote"] is not None:
                material += _halves(question["quote"]["text"])
    return material


def _has_confirmable(req: dict[str, Any]) -> bool:
    """A tap confirm has something to fill only with a tapped label, an AI draft or a quote."""
    question = req["question"]
    return bool(req["answer"]["tap"]["choice_ids"] or question["ai_draft"] or question["quote"])


MATRIX = [(q, lang, kind) for q in QUESTIONS for lang in LANGS for kind in PROBES]
MATRIX_IDS = [f"{q.removeprefix('case-fixture-01.')}-{lang}-{kind}" for q, lang, kind in MATRIX]
# brain_api.md canned table (same as conftest's extract_spec["canned"], checked below):
# "m01 in ja and en, m02 and m03 in ja, m04 in en"; everything else is generic.
_CANNED_PREFIXES = {("m01", "ja"), ("m01", "en"), ("m02", "ja"), ("m03", "ja"), ("m04", "en")}
GENERIC = [
    (i, row)
    for i, row in enumerate(MATRIX)
    if (row[0].split(".")[1], row[1]) not in _CANNED_PREFIXES
]
GENERIC_MATRIX = [row for _, row in GENERIC]
GENERIC_IDS = [MATRIX_IDS[i] for i, _ in GENERIC]


# --- REQUIRED_TO_CONFIRM ------------------------------------------------------------------------


def test_d054_required_to_confirm_names_the_two_paths():
    """brain_api.md /extract (D-054): `REQUIRED_TO_CONFIRM` in brain_api.py lists the draft
    fields that may be null but must be filled before Confirm: situation_cue.text and
    action.text."""
    from scrubgpt_contracts.models.brain_api import REQUIRED_TO_CONFIRM

    assert set(REQUIRED_TO_CONFIRM) == {"situation_cue.text", "action.text"}
    assert len(REQUIRED_TO_CONFIRM) == 2


# --- 12b ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(("question_id", "lang", "kind"), MATRIX, ids=MATRIX_IDS)
def test_12b_every_draft_has_no_ungrounded_field(probe, question_id, lang, kind):
    """#5 12b: "The fake Brain's generic /extract draft has ungrounded_fields(draft) == [] for
    every request fixture and for the probe answers." Checked on every probe answer (generic and
    canned drafts; G5 holds for both, brain_api.md /extract)."""
    _, out = probe(question_id, lang, kind)
    assert _ungrounded(out["draft"]) == []


@pytest.mark.parametrize("role", ["operating_surgeon", "reviewer", "dev_team_simulated", "expert"])
def test_12b_request_fixture_draft_has_no_ungrounded_field(client, request_fixture, role):
    """#5 12b on the request fixture extract.request.json, for every answerer role."""
    req = request_fixture("extract")
    req["answerer_role"] = role
    r = client.post(PATH, json=req)
    assert r.status_code == 200, r.text[:800]
    assert _ungrounded(r.json()["draft"]) == []


@pytest.mark.parametrize(("question_id", "lang", "kind"), MATRIX, ids=MATRIX_IDS)
def test_12b_null_cue_or_action_is_missing_and_has_an_editable_null_chip(
    probe, extract_spec, question_id, lang, kind
):
    """#5 12b: "Every null situation_cue.text or action.text appears in missing_fields[] and as
    an editable chip." brain_api.md: the chip has `value: null`; D-054: a null cue has
    cue_terms []."""
    _, out = probe(question_id, lang, kind)
    draft = out["draft"]
    nulls = {
        "situation_cue.text": draft["situation_cue"]["text"] is None,
        "action.text": draft["action"]["text"] is None,
    }
    for path, is_null in nulls.items():
        if not is_null:
            continue
        assert path in out["missing_fields"], (path, out["missing_fields"])
        chips = [c for c in out["chips"] if c["field"] == path]
        assert chips, (path, out["chips"])
        assert any(c["editable"] is True for c in chips), (path, chips)
        assert all(c["value"] is None for c in chips), (path, chips)
    if nulls["situation_cue.text"]:
        assert draft["situation_cue"]["cue_terms"] == []


def test_generic_matrix_matches_the_canned_table(extract_spec):
    """The generic-only parametrisation below follows brain_api.md's canned table."""
    canned = {(f"case-fixture-01.{m}", lang) for m, lang in _CANNED_PREFIXES}
    assert canned == set(extract_spec["canned"])
    assert GENERIC_MATRIX and len(GENERIC_MATRIX) < len(MATRIX)


@pytest.mark.parametrize(("question_id", "lang", "kind"), GENERIC_MATRIX, ids=GENERIC_IDS)
def test_12b_cue_and_action_never_come_from_the_moment_title(
    probe, extract_spec, question_id, lang, kind
):
    """#5 12b / D-054: "Neither the fake nor the real Brain ever fills them from the moment
    title (a title is not a grounding source)." On a generic draft, neither half of
    situation_cue.text / action.text contains a title half unless the answer itself (text,
    tapped label, confirmed AI draft or quote) contains it."""
    req, out = probe(question_id, lang, kind)
    assert not _is_canned(req, extract_spec)
    title = req["moment"]["title"]
    material = _answer_material(req)
    for path, value in (
        ("situation_cue.text", out["draft"]["situation_cue"]["text"]),
        ("action.text", out["draft"]["action"]["text"]),
    ):
        for half in _halves(value):
            for t in (title["ja"], title["en"]):
                if t in half:
                    assert any(t in m for m in material), (path, value, title)


@pytest.mark.parametrize(("question_id", "lang", "kind"), GENERIC_MATRIX, ids=GENERIC_IDS)
def test_12b_generic_draft_fills_only_the_asked_field_verbatim(
    probe, extract_spec, case_data, get_path, question_id, lang, kind
):
    """brain_api.md /extract generic draft (D-054): the answer, verbatim and grounded, fills the
    one field the question asks about; everything else stays null (action.actor: unknown); a
    reject without text fills nothing. D-054: action.type / action.actor are set (`act` /
    `unknown` when not said)."""
    req, out = probe(question_id, lang, kind)
    assert not _is_canned(req, extract_spec)  # canned drafts: see the 12c tests
    draft = out["draft"]
    asked = extract_spec["generic_target"](case_data["questions"][question_id]["type"])
    assert draft["action"]["actor"] == "unknown"
    for path in extract_spec["required_to_confirm"]:
        if path != asked:
            assert get_path(draft, path) is None, (path, get_path(draft, path))
    if draft["action"]["text"] is None:
        assert draft["action"]["type"] == "act"
    if kind == "tap_reject":
        assert draft["grounding"] == [], draft["grounding"]
        assert get_path(draft, asked) is None
        return
    value = get_path(draft, asked)
    if kind == "tap_confirm" and not _has_confirmable(req):
        # nothing was tapped or confirmed: nothing verbatim to fill (never invent, §4.3)
        assert value is None, (asked, value)
        assert draft["grounding"] == [], draft["grounding"]
        return
    assert value is not None, (asked, draft)
    for g in draft["grounding"]:
        assert any(g["quote"] in m for m in _answer_material(req)), g
    if kind in TEXT_PROBES:
        assert value[lang] == req["answer"]["text"], (asked, value)
        for g in draft["grounding"]:
            assert g["quote"] in req["answer"]["text"], g


@pytest.mark.parametrize(("question_id", "lang", "kind"), MATRIX, ids=MATRIX_IDS)
def test_12b_draft_language_is_the_answer_language(probe, question_id, lang, kind):
    """Team Lead reply #5 (decision 2) / plan §4.3: `language` means the language the answer
    was originally given in, so every draft has draft.language == answer.lang."""
    req, out = probe(question_id, lang, kind)
    assert out["draft"]["language"] == req["answer"]["lang"]


# --- 12c ---------------------------------------------------------------------------------------


def _assert_canned_from(out, req, seed):
    """brain_api.md: the canned draft "is that record, with id: null, the request's moment_id,
    answer_id and answerer provenance"."""
    draft = out["draft"]
    assert draft["id"] is None
    assert draft["moment_id"] == req["moment"]["id"]
    for key in seed:
        if key in ("id", "moment_id", "provenance", "evidence"):
            continue
        assert draft[key] == seed[key], key
    seed_ev = [
        {**e, "answer_id": req["answer"]["answer_id"]} if "answer_id" in e else e
        for e in seed["evidence"]
    ]
    assert draft["evidence"] == seed_ev


@pytest.mark.parametrize("mode", ["text", "voice"])
def test_12c_m02_q1_in_english_gets_the_generic_english_draft(
    probe, client, build_extract, seed_for, mode
):
    """#5 12c: "For m02.q1 with answer.lang: en, where only a Japanese seed exists, the fake
    Brain returns the generic draft with draft.language == "en"." Generic (brain_api.md):
    m02.q1 is a `decision` question, so the answer fills action.text; situation_cue.text stays
    null (never the title); no quote comes from the Japanese seed record."""
    qid = "case-fixture-01.m02.q1"
    assert seed_for("case-fixture-01.m02", "en") is None  # the premise: only a JA seed
    ja_seed = seed_for("case-fixture-01.m02", "ja")
    assert ja_seed is not None
    answer = "I checked the bladder-neck midline first and then kept cutting."
    req = build_extract(qid, mode=mode, text=answer, lang="en")
    r = client.post(PATH, json=req)
    assert r.status_code == 200, r.text[:800]
    out = r.json()
    draft = out["draft"]
    assert draft["language"] == "en"
    assert draft["action"]["text"]["en"] == answer
    assert draft["situation_cue"]["text"] is None
    assert draft["reason"] is None and draft["alternatives"] == []
    seed_quotes = {g["quote"] for g in ja_seed["grounding"]}
    for g in draft["grounding"]:
        assert g["quote"] in answer, g
        assert g["quote"] not in seed_quotes, g
    assert draft["situation_cue"] != ja_seed["situation_cue"]


def test_12c_m02_q1_in_japanese_gets_the_canned_draft(client, build_extract, seed_for):
    """#5 12c: "With answer.lang: ja, it returns the canned draft." (the m02 seed record,
    brain_api.md /extract)."""
    qid = "case-fixture-01.m02.q1"
    seed = seed_for("case-fixture-01.m02", "ja")
    answer_quote = next(e["quote"] for e in seed["evidence"] if e["kind"] == "answer_text")
    req = build_extract(qid, text=answer_quote, lang="ja")
    r = client.post(PATH, json=req)
    assert r.status_code == 200, r.text[:800]
    out = r.json()
    assert out["draft"]["language"] == "ja"
    _assert_canned_from(out, req, seed)


@pytest.mark.parametrize(("question_id", "lang"), [(q, lang) for q in QUESTIONS for lang in LANGS])
def test_12c_canned_only_in_the_seed_language(
    client, build_extract, seed_for, extract_spec, case_data, question_id, lang
):
    """D-054 / brain_api.md: canned drafts are used only when answer.lang equals the seed
    record's language ("m01 in ja and en, m02 and m03 in ja, m04 in en; any other language or
    moment gets the generic draft")."""
    moment_id = case_data["questions"][question_id]["moment_id"]
    seed = seed_for(moment_id, lang)
    canned = (moment_id, lang) in extract_spec["canned"]
    assert (seed is not None) == canned, "fixture seeds disagree with brain_api.md's table"
    req = build_extract(question_id, text=PROBE_TEXT[lang], lang=lang)
    r = client.post(PATH, json=req)
    assert r.status_code == 200, r.text[:800]
    out = r.json()
    assert out["draft"]["language"] == lang
    if canned:
        _assert_canned_from(out, req, seed)
    else:
        # generic: every quote is the request's own words, never another seed's
        for g in out["draft"]["grounding"]:
            assert g["quote"] in PROBE_TEXT[lang], g


# --- 12d ---------------------------------------------------------------------------------------


def test_12d_extract_fixture_validates_and_quotes_appear_in_its_answer(
    client, request_fixture, endpoints
):
    """#5 12d: "extract.request.json validates, and every grounding[].quote in its response
    appears in the request's answer.text"."""
    req = request_fixture("extract")
    endpoints["extract"].request.model_validate(req)
    assert isinstance(req["answer"]["text"], str) and req["answer"]["text"]
    r = client.post(PATH, json=req)
    assert r.status_code == 200, r.text[:800]
    out = r.json()
    endpoints["extract"].response.model_validate(out)
    assert out["draft"]["grounding"], "the fixture's draft has no grounding at all"
    for g in out["draft"]["grounding"]:
        assert g["quote"] in req["answer"]["text"], g


def test_12d_extract_fixture_sends_the_seed_answer_text(request_fixture, seed_for):
    """Team Lead reply #5 (3) / brain_api.md: "extract.request.json should send the seed
    answer's text, so the canned quotes appear in the request" (it answers m01.q1)."""
    req = request_fixture("extract")
    assert req["question"]["id"] == "case-fixture-01.m01.q1"
    seed = seed_for(req["moment"]["id"], req["answer"]["lang"])
    assert seed is not None, "no seed record in the fixture answer's language"
    quotes = [e["quote"] for e in seed["evidence"] if e["kind"] == "answer_text"]
    assert req["answer"]["text"] in quotes


# --- D-054: confirm_draft and action.type / action.actor ----------------------------------------


def _confirm(draft: dict[str, Any], new_uuid7):
    from scrubgpt_contracts.models.decision_record import DecisionRecordDraft, confirm_draft

    return confirm_draft(
        DecisionRecordDraft.model_validate(draft),
        record_id=new_uuid7(),
        confirmed_by="t2-tester",
        confirmed_at=datetime.now(UTC),
    )


@pytest.mark.parametrize(("question_id", "lang", "kind"), MATRIX, ids=MATRIX_IDS)
def test_d054_confirm_draft_raises_while_cue_or_action_is_null(
    probe, new_uuid7, question_id, lang, kind
):
    """D-054 [T2]: "a draft returned by the fake Brain whose situation_cue.text or action.text
    is null makes confirm_draft() raise ValueError; action.type/action.actor are always set."
    A draft with both filled confirms into a DecisionRecord (brain_api.md "On Confirm")."""
    from scrubgpt_contracts.models.decision_record import DecisionRecord

    _, out = probe(question_id, lang, kind)
    draft = out["draft"]
    assert draft["action"]["type"] in ("act", "deliberate_non_action")
    assert isinstance(draft["action"]["actor"], str) and draft["action"]["actor"]
    if draft["situation_cue"]["text"] is None or draft["action"]["text"] is None:
        with pytest.raises(ValueError):
            _confirm(draft, new_uuid7)
    else:
        record = _confirm(draft, new_uuid7)
        assert isinstance(record, DecisionRecord)
        assert record.situation_cue.text is not None and record.action.text is not None


def test_d054_some_probe_drafts_leave_cue_or_action_null(probe):
    """Guard for the D-054 tests above: the probe answers do produce drafts with a null
    situation_cue.text and with a null action.text (else those checks would be vacuous)."""
    drafts = [probe(q, lang, kind)[1]["draft"] for q, lang, kind in MATRIX]
    assert any(d["situation_cue"]["text"] is None for d in drafts)
    assert any(d["action"]["text"] is None for d in drafts)
    assert any(
        d["situation_cue"]["text"] is not None and d["action"]["text"] is not None for d in drafts
    )


# --- ExtractResponse model ----------------------------------------------------------------------


@pytest.fixture
def both_null_response(probe):
    """A generic fake-Brain response with situation_cue.text and action.text both null: a
    `reason` question (m02.q2) answered in English (no English seed for m02)."""
    _, out = probe("case-fixture-01.m02.q2", "en", "text")
    assert out["draft"]["situation_cue"]["text"] is None
    assert out["draft"]["action"]["text"] is None
    assert out["draft"]["reason"] is not None
    return out


def _model():
    from scrubgpt_contracts.models.brain_api import ExtractResponse

    return ExtractResponse


def test_model_accepts_the_fake_brain_response(both_null_response):
    """Control: the unmodified response is valid."""
    _model().model_validate(both_null_response)


@pytest.mark.parametrize("path", ["situation_cue.text", "action.text"])
def test_model_rejects_null_required_field_not_in_missing_fields(both_null_response, path):
    """ExtractResponse [T2] / brain_api.md (D-054): a null situation_cue.text / action.text must
    be in missing_fields[], else the response is invalid."""
    body = copy.deepcopy(both_null_response)
    body["missing_fields"] = [p for p in body["missing_fields"] if p != path]
    with pytest.raises(ValidationError):
        _model().model_validate(body)


@pytest.mark.parametrize("path", ["situation_cue.text", "action.text"])
def test_model_rejects_null_required_field_without_a_chip(both_null_response, path):
    """ExtractResponse [T2] / brain_api.md (D-054): a null situation_cue.text / action.text must
    have an editable chip, else the response is invalid (no chip at all)."""
    body = copy.deepcopy(both_null_response)
    body["chips"] = [c for c in body["chips"] if c["field"] != path]
    with pytest.raises(ValidationError):
        _model().model_validate(body)


@pytest.mark.parametrize("path", ["situation_cue.text", "action.text"])
def test_model_rejects_null_required_field_with_only_a_read_only_chip(both_null_response, path):
    """ExtractResponse [T2] / brain_api.md (D-054): the chip must be **editable**."""
    body = copy.deepcopy(both_null_response)
    for chip in body["chips"]:
        if chip["field"] == path:
            chip["editable"] = False
    assert any(c["field"] == path for c in body["chips"])
    with pytest.raises(ValidationError):
        _model().model_validate(body)


def test_model_rejects_a_chip_whose_value_differs_from_the_draft(both_null_response):
    """ExtractResponse [T2] / brain_api.md: a chip's `value` equals the draft's value at its
    path; a different Bilingual on a filled field is rejected."""
    body = copy.deepcopy(both_null_response)
    body["chips"] = [c for c in body["chips"] if c["field"] != "reason"] + [
        {
            "field": "reason",
            "value": {"ja": "別の理由", "en": "A different reason"},
            "editable": True,
        }
    ]
    with pytest.raises(ValidationError):
        _model().model_validate(body)


def test_model_rejects_a_null_chip_on_a_filled_field(both_null_response):
    """ExtractResponse [T2] / brain_api.md: `value: null` differs from a filled field's value
    (null is allowed only for an unstated situation_cue.text / action.text)."""
    body = copy.deepcopy(both_null_response)
    body["chips"] = [c for c in body["chips"] if c["field"] != "reason"] + [
        {"field": "reason", "value": None, "editable": True}
    ]
    with pytest.raises(ValidationError):
        _model().model_validate(body)


@pytest.mark.parametrize("path", ["situation_cue.text", "action.text"])
def test_model_rejects_a_filled_chip_on_a_null_required_field(both_null_response, path):
    """ExtractResponse [T2] / brain_api.md: the chip of an unstated situation_cue.text /
    action.text has `value: null`, the draft's value; any other value differs."""
    body = copy.deepcopy(both_null_response)
    for chip in body["chips"]:
        if chip["field"] == path:
            chip["value"] = {"ja": "モーメントの題名", "en": "The moment title"}
    with pytest.raises(ValidationError):
        _model().model_validate(body)


def test_model_rejects_a_chip_value_that_differs_on_a_canned_draft(probe):
    """ExtractResponse [T2] on a canned draft (m01.q1 in Japanese): changing a filled chip's
    value away from the draft's value is rejected."""
    _, out = probe("case-fixture-01.m01.q1", "ja", "text")
    assert out["chips"], "canned draft has no chip"
    body = copy.deepcopy(out)
    chip = body["chips"][0]
    assert chip["value"] is not None
    chip["value"] = {"ja": chip["value"]["ja"] + "（改）", "en": chip["value"]["en"] + " (changed)"}
    with pytest.raises(ValidationError):
        _model().model_validate(body)


def test_model_rejects_a_chip_on_a_path_not_in_the_draft(both_null_response):
    """ExtractResponse [T2] / brain_api.md chips: "field exists in draft and value equals its
    value there". A chip on a path the draft doesn't have has no equal value."""
    body = copy.deepcopy(both_null_response)
    body["chips"].append(
        {
            "field": "alternatives[3].option",
            "value": {"ja": "代案", "en": "An option"},
            "editable": True,
        }
    )
    with pytest.raises(ValidationError):
        _model().model_validate(body)
