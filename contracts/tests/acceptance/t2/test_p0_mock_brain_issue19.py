"""T2 acceptance: fake-Brain behaviour fixes of contract change issue #19 (criteria 1-10).

Sources:
- Issue #19 (proposal), the Team Lead's triage with decisions (a) and (b) and acceptance criteria
  1-10 (quoted per test).
- contracts/brain_api.md, the fake-Brain rows for /extract and /briefing.
- D-037 (fake Brain), D-054 / D-056 (unstated fields, missing_fields is the fill-in prompt),
  D-064 rule 1 (a clip URI names its own case's moment), D-068 (the 5 canned pairs of
  case-fixture-01), root CLAUDE.md guardrail "Never invent reasoning".

Offline: the fake Brain in-process through its ASGI app. Two test hooks inside the fake Brain's
own module (in-process, monkeypatched for one test each): `logic.reference` (a trimmed obstacle
taxonomy, named in the test brief, because every `ObstacleFamily` value is named in the fixture
reference) and `logic.seed_records` (a seed record whose alternatives have a null `why_not`,
because no fixture seed has one).
"""

from __future__ import annotations

import copy
import re
import subprocess
from typing import Any

import pytest

PATH = "/v1/answers/extract"
BRIEFING = "/v1/briefing"
LANGS = ("ja", "en")
PROBE_TEXT = {
    "en": "I irrigated the field and waited for the view to clear.",
    "ja": "術野を洗浄して、視野が晴れるまで待ちました。",
}
# D-068 rule 1 / issue #19 criterion 3: the 5 canned (question, answer language) pairs.
CANNED = (
    ("case-fixture-01.m01.q1", "ja"),
    ("case-fixture-01.m01.r1", "en"),
    ("case-fixture-01.m02.q1", "ja"),
    ("case-fixture-01.m04.q1", "en"),
    ("case-fixture-01.m03.q1", "ja"),
)
CANNED_IDS = [f"{q.split('.', 1)[1]}-{lang}" for q, lang in CANNED]
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
# Every answer shape of plan §4.4 Answer. "Says something" (criterion 3) = text set, not an edit.
KINDS = (
    "text",
    "voice_audio",
    "voice_no_audio",
    "tap_confirm",
    "tap_confirm_choices",
    "tap_reject",
    "tap_reject_choices",
    "tap_confirm_text",
    "tap_reject_text",
    "tap_edit_text",
    "tap_edit_text_choices",
)
SAYS_SOMETHING = {"text", "voice_audio", "voice_no_audio", "tap_confirm_text", "tap_reject_text"}
TEXTLESS_TAPS = ("tap_confirm", "tap_confirm_choices", "tap_reject", "tap_reject_choices")
# Decision-content fields the generic draft may fill (brain_api.md: only the one asked about).
CONTENT_PATHS = (
    "situation_cue.text",
    "obstacle",
    "anticipation",
    "action.text",
    "reason",
    "immediate_result",
)


# --- helpers -------------------------------------------------------------------------------------


def _req(build_extract, case_data, question_id: str, lang: str, kind: str) -> dict[str, Any]:
    options = [o["id"] for o in case_data["questions"][question_id]["tap_options"]]
    text = PROBE_TEXT[lang]
    tap = None
    mode = "tap"
    if kind == "text":
        mode = "text"
    elif kind.startswith("voice"):
        mode = "voice"
    else:
        verdict = kind.split("_")[1]
        choices = options[:1] if kind.endswith("choices") else []
        tap = {"verdict": verdict, "choice_ids": choices}
        if not kind.endswith("text") and not kind.endswith("text_choices"):
            text = None
    req = build_extract(question_id, mode=mode, text=text, lang=lang, tap=tap)
    if kind == "voice_audio":
        req["answer"]["audio_uri"] = f"answers/{req['answer']['answer_id']}.webm"
    return req


@pytest.fixture(scope="module")
def ask(client, endpoints):
    """POST an /extract request; the request and the response both validate (criterion 8)."""

    def run(req: dict[str, Any]) -> dict[str, Any]:
        endpoints["extract"].request.model_validate(req)
        r = client.post(PATH, json=req)
        assert r.status_code == 200, r.text[:800]
        out = r.json()
        endpoints["extract"].response.model_validate(out)
        return out

    return run


@pytest.fixture(scope="module")
def matrix(ask, build_extract, case_data):
    """Every fixture question x language x answer shape, answered once (cached)."""
    cache: dict[tuple[str, str, str], tuple[dict[str, Any], dict[str, Any]]] = {}

    def get(question_id: str, lang: str, kind: str):
        key = (question_id, lang, kind)
        if key not in cache:
            req = _req(build_extract, case_data, question_id, lang, kind)
            cache[key] = (req, ask(req))
        return copy.deepcopy(cache[key])

    return get


def _seed_quotes(case_data) -> set[str]:
    quotes = set()
    for s in case_data["seeds"]:
        quotes |= {g["quote"] for g in s["grounding"]}
        quotes |= {e["quote"] for e in s["evidence"] if "quote" in e}
    return quotes


def _seed_answer_ids_and_uris(case_data) -> tuple[set[str], set[str]]:
    ids, uris = set(), set()
    for s in case_data["seeds"]:
        for e in s["evidence"]:
            if "answer_id" in e:
                ids.add(e["answer_id"])
            if e["kind"] == "answer_audio":
                uris.add(e["uri"])
    return ids, uris


def _halves(value: Any) -> list[str]:
    return [] if value is None else [value["ja"], value["en"]]


def _material(req: dict[str, Any]) -> list[str]:
    """What a generic draft may quote (brain_api.md: the answer text, tapped labels, or the
    confirmed AI draft or quote)."""
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


def _target(question_type: str) -> str:
    """brain_api.md generic draft: the one field the question asks about."""
    return {
        "cue": "situation_cue.text",
        "reason": "reason",
        "alternatives": "alternatives[0].option",
    }.get(question_type, "action.text")


def _filled(draft: dict[str, Any], get_path, MISSING) -> set[str]:  # noqa: N803
    filled = {p for p in CONTENT_PATHS if get_path(draft, p) not in (None, MISSING)}
    if draft["alternatives"]:
        filled.add("alternatives[0].option")
    return filled


def _assert_generic(req, out, case_data, get_path, MISSING):  # noqa: N803
    """The generic draft (brain_api.md): no seed record's words, only the asked field filled,
    every quote from the answer itself."""
    draft = out["draft"]
    seed_quotes = _seed_quotes(case_data)
    for g in draft["grounding"]:
        assert g["quote"] not in seed_quotes, g
        assert any(g["quote"] in m for m in _material(req)), (g, _material(req))
    for e in draft["evidence"]:
        if "quote" in e:
            assert e["quote"] not in seed_quotes, e
    for s in case_data["seeds"]:
        for key in ("situation_cue", "action", "reason", "alternatives", "immediate_result"):
            if s[key] not in (None, []):
                assert draft[key] != s[key], (key, s["id"])
    filled = _filled(draft, get_path, MISSING)
    assert filled <= {_target(req["question"]["type"])}, filled
    if not _material(req):
        assert filled == set(), "nothing was said, yet a field was filled"
    ids, uris = _seed_answer_ids_and_uris(case_data)
    for e in draft["evidence"]:
        assert e.get("answer_id") not in ids, e
        assert e.get("uri") not in uris, e


def _assert_canned_content(out, seed):
    """The canned draft is the seed record's decision content (brain_api.md /extract)."""
    draft = out["draft"]
    for key in (
        "kind",
        "situation_cue",
        "obstacle",
        "anticipation",
        "action",
        "alternatives",
        "reason",
        "immediate_result",
        "grounding",
    ):
        assert draft[key] == seed[key], key


_WHY_NOT = re.compile(r"alternatives\[([0-9]+)\]\.why_not")


def _assert_why_not_listed(out):
    """Criterion 6 on one response."""
    draft, missing = out["draft"], out["missing_fields"]
    chips = {c["field"] for c in out["chips"]}
    assert not set(missing) & chips, set(missing) & chips
    for i, alt in enumerate(draft["alternatives"]):
        path = f"alternatives[{i}].why_not"
        if alt["why_not"] is None:
            assert path in missing, (path, missing)
        else:
            assert path not in missing, (path, missing)
    listed = [p for p in missing if _WHY_NOT.fullmatch(p)]
    assert len(listed) == len(set(listed)), missing
    # "after its option": alternatives in their own order. Where the why_not entries sit among
    # the other missing_fields entries is a spec gap (reported), so it is not asserted here.
    assert listed == sorted(listed, key=lambda p: int(_WHY_NOT.fullmatch(p).group(1))), missing


# --- criterion 1 ---------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", TEXTLESS_TAPS)
@pytest.mark.parametrize(("question_id", "lang"), CANNED, ids=CANNED_IDS)
def test_c1_textless_tap_on_a_canned_question_gets_the_generic_draft(
    matrix,
    case_data,
    get_path,
    MISSING,
    question_id,
    lang,
    kind,  # noqa: N803
):
    """#19 criterion 1: "A `tap` answer with `text: null` (`confirm`, `reject` or `choice_ids`)
    never gets a canned draft, even on a question that has one under D-068 (e.g. `m01.q1` ja).
    It gets the generic draft." (guardrail "Never invent reasoning")."""
    req, out = matrix(question_id, lang, kind)
    assert req["answer"]["text"] is None
    _assert_generic(req, out, case_data, get_path, MISSING)
    assert out["draft"]["question_id"] == question_id
    assert out["draft"]["language"] == lang


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("question_id", QUESTIONS)
def test_c1_reject_without_text_fills_nothing(matrix, get_path, MISSING, question_id, lang):  # noqa: N803
    """#19 criterion 1 / D-054: "`reject` without text fills no field and has no `answer_text`
    evidence or grounding"."""
    _, out = matrix(question_id, lang, "tap_reject")
    draft = out["draft"]
    assert _filled(draft, get_path, MISSING) == set()
    assert draft["alternatives"] == []
    assert draft["grounding"] == []
    assert [e for e in draft["evidence"] if e["kind"] == "answer_text"] == []


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("question_id", QUESTIONS)
def test_c1_confirm_without_text_fills_only_the_asked_field_from_ai_draft_or_quote(
    matrix,
    case_data,
    get_path,
    MISSING,  # noqa: N803
    question_id,
    lang,
):
    """#19 criterion 1 / D-054: "`confirm` fills only the asked field, from `ai_draft` or the
    quote". With neither, nothing was said, so nothing is filled ("Never invent reasoning")."""
    req, out = matrix(question_id, lang, "tap_confirm")
    question = case_data["questions"][question_id]
    draft = out["draft"]
    target = _target(question["type"])
    filled = _filled(draft, get_path, MISSING)
    assert filled <= {target}, filled
    source = question["ai_draft"] or (question["quote"] or {}).get("text")
    if source is None:
        assert filled == set(), filled
        assert draft["grounding"] == []
        return
    assert filled == {target}, (filled, target)
    value = get_path(draft, target)
    assert value[lang] == source[lang], (value, source)
    assert draft["grounding"], "a filled field needs its grounding (G5)"
    for g in draft["grounding"]:
        assert g["quote"] in _halves(source) or any(g["quote"] in h for h in _halves(source)), g
    _assert_generic(req, out, case_data, get_path, MISSING)


# --- criterion 2 ---------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["tap_edit_text", "tap_edit_text_choices"])
@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("question_id", QUESTIONS)
def test_c2_edit_with_text_gets_the_generic_draft_grounded_as_edit(
    matrix,
    case_data,
    get_path,
    MISSING,  # noqa: N803
    question_id,
    lang,
    kind,
):
    """#19 criterion 2 / decision (a): "An `edit` tap, with or without text, always gets the
    generic draft. When it has text, the grounding is `source: edit`." Covers the 5 canned pairs
    and every other question x language."""
    if kind.endswith("choices") and not case_data["questions"][question_id]["tap_options"]:
        pytest.skip("question has no tap options")
    req, out = matrix(question_id, lang, kind)
    _assert_generic(req, out, case_data, get_path, MISSING)
    draft = out["draft"]
    target = _target(req["question"]["type"])
    assert _filled(draft, get_path, MISSING) == {target}
    assert get_path(draft, target)[lang] == req["answer"]["text"]
    assert draft["grounding"], "the edited text is grounded"
    for g in draft["grounding"]:
        assert g["source"] == "edit", g
        assert g["quote"] in req["answer"]["text"], g


def test_c2_edit_without_text_cannot_be_sent(client, build_extract, assert_api_error):
    """#19 criterion 2 ("with or without text"): plan §4.4 Answer requires the edited text of an
    `edit` verdict, so an `edit` without text is a bad request (400 ApiError), never a draft."""
    req = build_extract(
        "case-fixture-01.m01.q1",
        mode="tap",
        text=None,
        lang="ja",
        tap={"verdict": "edit", "choice_ids": []},
    )
    assert_api_error(client.post(PATH, json=req), 400, "bad_request")


# --- criterion 3 ---------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(SAYS_SOMETHING))
@pytest.mark.parametrize(("question_id", "lang"), CANNED, ids=CANNED_IDS)
def test_c3_answer_with_text_on_a_canned_question_gets_the_canned_record(
    matrix, seed_for, question_id, lang, kind
):
    """#19 criterion 3: "A text or voice answer (`answer.text` non-null, not an edit) on a D-068
    canned question still gets the canned record. All 5 canned pairs listed in D-068 still
    hold." brain_api.md: the draft is that record with `id: null` and the request's
    `moment_id`, `question_id`, `answer_id`."""
    req, out = matrix(question_id, lang, kind)
    seed = seed_for(question_id, lang)
    assert seed is not None, "D-068 lists this pair as canned"
    _assert_canned_content(out, seed)
    draft = out["draft"]
    assert draft["id"] is None
    assert draft["moment_id"] == req["moment"]["id"]
    assert draft["question_id"] == question_id
    assert draft["language"] == lang
    for e in draft["evidence"]:
        if "answer_id" in e:
            assert e["answer_id"] == req["answer"]["answer_id"], e


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("question_id", QUESTIONS)
def test_c3_every_other_combination_gets_the_generic_draft(
    matrix,
    case_data,
    get_path,
    MISSING,  # noqa: N803
    question_id,
    lang,
    kind,
):
    """#19 criterion 3: "Every other combination gets the generic draft." (canned = a D-068 pair
    and an answer with text that is not an edit)."""
    if "choices" in kind and not case_data["questions"][question_id]["tap_options"]:
        pytest.skip("question has no tap options")
    if (question_id, lang) in CANNED and kind in SAYS_SOMETHING:
        pytest.skip("canned combination (test_c3_answer_with_text_on_a_canned_question...)")
    req, out = matrix(question_id, lang, kind)
    _assert_generic(req, out, case_data, get_path, MISSING)


# --- criterion 4 ---------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(SAYS_SOMETHING))
@pytest.mark.parametrize(("question_id", "lang"), CANNED, ids=CANNED_IDS)
def test_c4_canned_audio_comes_only_from_the_request(matrix, case_data, question_id, lang, kind):
    """#19 criterion 4 / decision (b): "Canned path: when `answer.audio_uri` is set, the draft has
    exactly one `answer_audio` evidence, with the request's `answer_id` and `uri`. When it is
    null, the draft has none, so no seed audio URI ever appears in a draft."""
    req, out = matrix(question_id, lang, kind)
    audio = [e for e in out["draft"]["evidence"] if e["kind"] == "answer_audio"]
    if req["answer"]["audio_uri"] is None:
        assert audio == []
    else:
        assert audio == [
            {
                "kind": "answer_audio",
                "answer_id": req["answer"]["answer_id"],
                "uri": req["answer"]["audio_uri"],
            }
        ]
    _, seed_uris = _seed_answer_ids_and_uris(case_data)
    for e in out["draft"]["evidence"]:
        assert e.get("uri") not in seed_uris, e


@pytest.fixture(scope="module")
def audio_seed_request(build_extract, case_data):
    """A request that reaches the only seed record carrying an `answer_audio` (moment-less, EN, on
    step rarp.p10.s01) through D-068 (b): question m05.q1 (no seed record of its own, a moment
    without a checkpoint) asked on its moment placed on that step. The moment keeps its own id
    and span (148-168 s)."""

    def build(*, mode: str, audio: bool) -> tuple[dict[str, Any], dict[str, Any]]:
        seed = next(
            s
            for s in case_data["seeds"]
            if s["moment_id"] is None and any(e["kind"] == "answer_audio" for e in s["evidence"])
        )
        req = build_extract(
            "case-fixture-01.m05.q1", mode=mode, text=PROBE_TEXT[seed["language"]], lang="en"
        )
        req["answer"]["lang"] = seed["language"]
        req["moment"]["step_id"] = seed["step_id"]
        req["case_context"]["step"] = copy.deepcopy(case_data["steps"][seed["step_id"]])
        if audio:
            req["answer"]["audio_uri"] = f"answers/{req['answer']['answer_id']}.webm"
        return req, copy.deepcopy(seed)

    return build


@pytest.mark.parametrize(("mode", "audio"), [("voice", True), ("voice", False), ("text", False)])
def test_c4_seed_audio_never_copied_into_a_reused_record(ask, audio_seed_request, mode, audio):
    """#19 decision (b): "The canned path never copies a seed `answer_audio`. The moment-less seed
    record (the one reused under D-068 (b)) carries `answers/01a1436a-….webm`, which today would
    come back under the request's `answer_id`." Also criterion 5: its media is the requested
    moment's span."""
    req, seed = audio_seed_request(mode=mode, audio=audio)
    out = ask(req)
    _assert_canned_content(out, seed)  # premise: the seed record is reused (D-068 (b))
    draft = out["draft"]
    seed_uris = {e["uri"] for e in seed["evidence"] if e["kind"] == "answer_audio"}
    seed_ids = {e["answer_id"] for e in seed["evidence"] if "answer_id" in e}
    for e in draft["evidence"]:
        assert e.get("uri") not in seed_uris, e
        assert e.get("answer_id") not in seed_ids, e
    audio_items = [e for e in draft["evidence"] if e["kind"] == "answer_audio"]
    if audio:
        assert audio_items == [
            {
                "kind": "answer_audio",
                "answer_id": req["answer"]["answer_id"],
                "uri": req["answer"]["audio_uri"],
            }
        ]
    else:
        assert audio_items == []
    _assert_media_on_moment(draft, req["moment"])


# --- criterion 5 ---------------------------------------------------------------------------------

_FRAGMENT = re.compile(r"video\.mp4#t=([0-9]+(?:\.[0-9]+)?),([0-9]+(?:\.[0-9]+)?)")


def _assert_media_on_moment(draft: dict[str, Any], moment: dict[str, Any]) -> None:
    media = [e for e in draft["evidence"] if e["kind"] == "media"]
    on_video = [e for e in media if e["uri"].startswith("video.mp4")]
    assert on_video, "the reused record keeps a media evidence on video.mp4"
    for e in on_video:
        m = _FRAGMENT.fullmatch(e["uri"])
        assert m, e
        assert (float(m.group(1)), float(m.group(2))) == (moment["t_start"], moment["t_end"]), e
        assert (e["t_start"], e["t_end"]) == (moment["t_start"], moment["t_end"]), e
    for e in media:
        if e["uri"].startswith("clips/"):
            assert e["uri"].startswith(f"clips/{moment['id']}."), e


@pytest.mark.parametrize("kind", sorted(SAYS_SOMETHING))
def test_c5_reused_moment_less_record_points_at_the_requested_moment(
    matrix, case_data, seed_for, kind
):
    """#19 criterion 5: "Canned via D-068 (b) (`m03.q1` ja): every `media` evidence on
    `video.mp4` is `video.mp4#t=<moment.t_start>,<moment.t_end>`, with `t_start`/`t_end` equal to
    the requested moment's. No `clips/` URI names another moment (D-064 rule 1)."""
    qid = "case-fixture-01.m03.q1"
    seed = seed_for(qid, "ja")
    assert seed is not None and seed["moment_id"] is None, "premise: m03.q1 ja is canned via (b)"
    req, out = matrix(qid, "ja", kind)
    _assert_canned_content(out, seed)
    _assert_media_on_moment(out["draft"], case_data["moments"]["case-fixture-01.m03"])


@pytest.mark.parametrize("kind", sorted(SAYS_SOMETHING))
@pytest.mark.parametrize(
    ("question_id", "lang"),
    [p for p in CANNED if p[0] != "case-fixture-01.m03.q1"],
    ids=[i for p, i in zip(CANNED, CANNED_IDS, strict=True) if p[0] != "case-fixture-01.m03.q1"],
)
def test_c5_canned_via_same_question_keeps_the_seed_evidence(
    matrix, seed_for, question_id, lang, kind
):
    """#19 criterion 5: "Canned via (a): the evidence stays the seed's." (with the request's
    `answer_id` on answer evidence, brain_api.md; audio only from the request, criterion 4)."""
    req, out = matrix(question_id, lang, kind)
    seed = seed_for(question_id, lang)
    assert seed["question_id"] == question_id, "premise: canned via (a)"
    expected = [
        {**e, "answer_id": req["answer"]["answer_id"]} if "answer_id" in e else e
        for e in seed["evidence"]
        if e["kind"] != "answer_audio"
    ]
    got = [e for e in out["draft"]["evidence"] if e["kind"] != "answer_audio"]
    assert got == expected


# --- criterion 6 ---------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("question_id", QUESTIONS)
def test_c6_missing_fields_list_every_null_why_not_in_reading_order(
    matrix, case_data, question_id, lang, kind
):
    """#19 criterion 6: "`missing_fields` contains `alternatives[i].why_not` for every alternative
    whose `why_not` is null, in reading order (after its `option`). It never contains a path that
    is also a chip, and every response still validates as `ExtractResponse`." (validated in
    `ask`)."""
    if "choices" in kind and not case_data["questions"][question_id]["tap_options"]:
        pytest.skip("question has no tap options")
    _, out = matrix(question_id, lang, kind)
    _assert_why_not_listed(out)


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("kind", ["text", "voice_audio", "tap_edit_text"])
def test_c6_generic_alternatives_answer_prompts_for_why_not(matrix, lang, kind):
    """#19 criterion 6 / issue #19 item 4: the generic draft of an `alternatives` question fills
    `alternatives[0].option`; its unstated `why_not` is in `missing_fields` (the app's fill-in
    prompt, D-056)."""
    req, out = matrix("case-fixture-01.m01.r2", lang, kind)
    assert req["question"]["type"] == "alternatives"
    alts = out["draft"]["alternatives"]
    assert len(alts) == 1 and alts[0]["why_not"] is None, alts
    assert "alternatives[0].why_not" in out["missing_fields"], out["missing_fields"]
    _assert_why_not_listed(out)


def test_c6_canned_record_with_null_why_not_prompts_for_each(
    monkeypatch, ask, build_extract, case_data, seed_for
):
    """#19 criterion 6 on the canned path (brain_api.md: "In both kinds of draft, `missing_fields`
    also lists `alternatives[i].why_not` for every alternative whose reason is null"). Hook:
    `logic.seed_records` returns the m01.q1 ja seed with three alternatives, the 1st and 3rd
    without a reason."""
    from scrubgpt_contracts.mock_brain import logic
    from scrubgpt_contracts.models.decision_record import DecisionRecord

    qid = "case-fixture-01.m01.q1"
    seed = seed_for(qid, "ja")
    seed["alternatives"] = [
        {"option": {"ja": "選択肢A", "en": "Option A"}, "why_not": None},
        {"option": {"ja": "選択肢B", "en": "Option B"}, "why_not": {"ja": "理由B", "en": "B"}},
        {"option": {"ja": "選択肢C", "en": "Option C"}, "why_not": None},
    ]
    seed["grounding"] = [g for g in seed["grounding"] if not g["field"].startswith("alternatives")]
    record = DecisionRecord.model_validate(seed)
    others = tuple(r for r in logic.seed_records() if str(r.id) != seed["id"])
    monkeypatch.setattr(logic, "seed_records", lambda: (record, *others))
    req = build_extract(qid, text=PROBE_TEXT["ja"], lang="ja")
    out = ask(req)
    assert out["draft"]["alternatives"] == seed["alternatives"], "premise: canned"
    missing = out["missing_fields"]
    assert "alternatives[0].why_not" in missing and "alternatives[2].why_not" in missing, missing
    assert "alternatives[1].why_not" not in missing
    assert missing.index("alternatives[0].why_not") < missing.index("alternatives[2].why_not")
    _assert_why_not_listed(out)


# --- criterion 7 ---------------------------------------------------------------------------------

UNNAMED = ("bleeding", "anatomical_variation")


@pytest.fixture
def trimmed_reference(monkeypatch):
    """Hook named in the brief: `logic.reference` returns the fixture reference without the
    `bleeding` and `anatomical_variation` families."""
    from scrubgpt_contracts.mock_brain import logic

    full = logic.reference()
    trimmed = full.model_copy(
        update={
            "obstacle_taxonomy": [e for e in full.obstacle_taxonomy if e.id.value not in UNNAMED]
        }
    )
    monkeypatch.setattr(logic, "reference", lambda: trimmed)
    return trimmed


def _briefing(client, endpoints, case_data, factors):
    from scrubgpt_contracts.models.decision_record import DecisionRecord

    body = {
        "case_factors": factors,
        "lang": "en",
        "candidates": [
            DecisionRecord.model_validate(s).model_dump(mode="json") for s in case_data["seeds"]
        ],
    }
    endpoints["briefing"].request.model_validate(body)
    r = client.post(BRIEFING, json=body)
    assert r.status_code == 200, r.text[:800]
    out = r.json()
    endpoints["briefing"].response.model_validate(out)
    return out


def _family_groups(case_data) -> dict[str | None, set[str]]:
    groups: dict[str | None, set[str]] = {}
    for s in case_data["seeds"]:
        fam = s["obstacle"]["family"] if s["obstacle"] else None
        groups.setdefault(fam, set()).add(s["id"])
    return groups


def _section_for(out, ids: set[str]) -> list[dict[str, Any]]:
    return [s for s in out["sections"] if {c["record_id"] for c in s["citations"]} == ids]


FACTORS = [[], [{"ja": "中葉肥大", "en": "Median lobe"}]]


@pytest.mark.parametrize("factors", FACTORS, ids=["no-factors", "factors"])
def test_c7_unnamed_family_titled_with_its_id_in_both_languages(
    client, endpoints, case_data, trimmed_reference, factors
):
    """#19 criterion 7: "a family id that isn't in the fixture reference gets a section titled
    with that family id, marked as unnamed in both JA and EN (e.g. `名称未登録の障害分類：bleeding`
    / `Unnamed obstacle family: bleeding`). Two such families get two different titles."
    brain_api.md /briefing: titled `名称未登録の障害分類：<id>` /
    `Unnamed obstacle family: <id>`."""
    out = _briefing(client, endpoints, case_data, factors)
    groups = _family_groups(case_data)
    titles = []
    for fam in UNNAMED:
        assert fam in groups, "premise: the fixture seeds use this family"
        found = _section_for(out, groups[fam])
        assert len(found) == 1, (fam, out["sections"])
        title = found[0]["title"]
        assert title == {
            "ja": f"名称未登録の障害分類：{fam}",
            "en": f"Unnamed obstacle family: {fam}",
        }, title
        assert title["en"] != "No obstacle recorded"
        titles.append((title["ja"], title["en"]))
    assert titles[0][0] != titles[1][0] and titles[0][1] != titles[1][1]


@pytest.mark.parametrize("trim", [False, True], ids=["full-reference", "trimmed-reference"])
@pytest.mark.parametrize("factors", FACTORS, ids=["no-factors", "factors"])
def test_c7_no_obstacle_title_only_for_records_without_obstacle(
    client, endpoints, case_data, monkeypatch, factors, trim
):
    """#19 criterion 7: ""No obstacle recorded" (JA + EN) titles only the group of records whose
    `obstacle` is null. Counts stay counts, never percentages." (named families keep their
    reference names, brain_api.md)."""
    if trim:
        from scrubgpt_contracts.mock_brain import logic

        full = logic.reference()
        trimmed = full.model_copy(
            update={
                "obstacle_taxonomy": [
                    e for e in full.obstacle_taxonomy if e.id.value not in UNNAMED
                ]
            }
        )
        monkeypatch.setattr(logic, "reference", lambda: trimmed)
    out = _briefing(client, endpoints, case_data, factors)
    groups = _family_groups(case_data)
    assert None in groups, "premise: some seed records have no obstacle"
    no_obstacle = [s for s in out["sections"] if s["title"]["en"] == "No obstacle recorded"]
    assert len(no_obstacle) == 1, out["sections"]
    assert {c["record_id"] for c in no_obstacle[0]["citations"]} == groups[None]
    assert no_obstacle[0]["title"]["ja"].strip()
    assert sum(1 for s in out["sections"] if s["title"] == no_obstacle[0]["title"]) == 1
    names = {e["id"]: e["name"] for e in case_data["reference"]["obstacle_taxonomy"]}
    for fam, ids in groups.items():
        found = _section_for(out, ids)
        assert len(found) == 1, (fam, out["sections"])
        if fam is not None and not (trim and fam in UNNAMED):
            assert found[0]["title"] == names[fam]
        for half in ("ja", "en"):
            body = found[0]["body"][half]
            assert "%" not in body and "％" not in body, body
            assert str(len(ids)) in body, (len(ids), body)
    for s in out["sections"]:
        for half in ("ja", "en"):
            assert "%" not in s["body"][half] and "％" not in s["body"][half]
            assert "%" not in s["title"][half]


# --- criterion 8 ---------------------------------------------------------------------------------


def test_c8_extract_fixture_response_passes_scrubgpt_validate(
    client, request_fixture, console_script, tmp_path, endpoints
):
    """#19 criterion 8: "Every fake-Brain `/extract` response for
    `fixtures/brain_api/extract.request.json` and the T2 request matrix still passes
    `scrubgpt-validate response` / the models" (the matrix validates in `ask`; codegen is
    test_p0_codegen_output.py::test_c18_committed_schema_and_ts_match_a_fresh_run)."""
    r = client.post(PATH, json=request_fixture("extract"))
    assert r.status_code == 200, r.text[:800]
    endpoints["extract"].response.model_validate(r.json())
    _assert_why_not_listed(r.json())
    saved = tmp_path / "extract.response.json"
    saved.write_bytes(r.content)
    done = subprocess.run(
        [str(console_script("scrubgpt-validate")), "response", "extract", str(saved)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr


# --- criteria 9 and 10 ---------------------------------------------------------------------------


def _row(paths, endpoint: str) -> str:
    text = (paths["contracts"] / "brain_api.md").read_text(encoding="utf-8")
    section = text.split("## The fake Brain", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith(f"| `{endpoint}` |")]
    assert len(rows) == 1, rows
    return rows[0]


def test_c9_brain_api_md_describes_the_extract_rules(paths):
    """#19 criterion 9: "The fake-Brain row in `contracts/brain_api.md` describes rules 1-7
    (canned only for a non-edit answer with text; audio from the request; (b) evidence on the
    requested moment; `why_not` in `missing_fields`; ...)"."""
    row = _row(paths, "/extract")
    assert "answer.text" in row and "edit" in row, "canned only for a non-edit answer with text"
    assert "answer_audio" in row and "audio_uri" in row, "audio from the request"
    assert "video.mp4#t=<t_start>,<t_end>" in row, "(b) evidence on the requested moment"
    assert "why_not" in row and "missing_fields" in row, "why_not in missing_fields"


def test_c9_brain_api_md_describes_the_briefing_titles(paths):
    """#19 criterion 9: "... unnamed-family titles" in the /briefing fake-Brain row."""
    row = _row(paths, "/briefing")
    assert "名称未登録の障害分類：<id>" in row and "Unnamed obstacle family: <id>" in row, row
    assert "No obstacle recorded" in row and "null" in row, row


DEV1_PATHS = (
    "contracts/scrubgpt_contracts/models/common.py",
    "contracts/scrubgpt_contracts/models/case_package.py",
    "contracts/scrubgpt_contracts/models/decision_record.py",
    "contracts/scrubgpt_contracts/models/reference.py",
    "contracts/scrubgpt_contracts/validate.py",
    "contracts/fixtures/cases/",
    "contracts/fixtures/reference/",
    "contracts/pyproject.toml",
)


def test_c10_dev1_files_and_generated_files_untouched(paths):
    """#19 criterion 10 / D-031: "Dev1's files in `contracts/` are untouched" and criterion 8 /
    triage: `schema/` and `ts/` unchanged; only Dev2's files change (D-031 list)."""
    repo = paths["repo"]
    base = subprocess.run(
        ["git", "merge-base", "origin/main", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if base.returncode != 0:
        pytest.skip("origin/main is not available in this checkout")
    changed = subprocess.run(
        ["git", "diff", "--name-only", base.stdout.strip(), "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    touched = [p for p in changed if p.startswith(DEV1_PATHS)]
    assert touched == [], touched
    generated = [p for p in changed if p.startswith(("contracts/schema/", "contracts/ts/"))]
    assert generated == [], generated
    outside = [p for p in changed if not p.startswith("contracts/")]
    assert outside == [], outside
