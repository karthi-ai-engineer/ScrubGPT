"""#9 AC3-AC9 and AC11: the cross-file rules of `scrubgpt-validate case` and the media-fragment rule
in `MediaEvidence` (Team Lead triage on issue #9, logged as D-058; Dev1's accepted analysis).

Triage: "Levels in `scrubgpt-validate case`: errors (exit 1): 3a, 3c, 3d, 3e. Warnings (exit 0,
printed): 3b, 3f. ... 3a is better checked in `MediaEvidence` itself". "Grounding verbatim (3e):
`source: answer` => `quote` is an exact substring of one of the record's `answer_text` evidence
quotes; `source: narration` => an exact substring of one of its `transcript` evidence quotes;
`source: edit` is not checked ... Same NFC normalisation on both sides, nothing else."
Dev1's accepted analysis (clarifies AC4): the rule applies to media evidence whose fragment is on
`video.mp4`, the normalised video; a clip's fragment (`clips/<moment_id>.mp4#t=...`) is relative to
the clip (W3C Media Fragments, plan §4.1; `MediaFragmentUri` docstring) and is not compared.

Fixture seed records (`case-fixture-01`, read-only; edits go to a `tmp_path` copy):
0 m01 ja 🧪, 1 m01 en 🧪, 2 m02 ja 🧪, 3 m04 en 🧪, 4 no moment ja 🧪, 5 m02 ja 🎙️ narration,
6 no moment en 🧪 (answer_audio, an `edit` grounding, outcome `known`).
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import unicodedata
from typing import Any

import pytest
import uuid6
from pydantic import TypeAdapter, ValidationError
from scrubgpt_contracts.models.case_package import Case
from scrubgpt_contracts.models.common import Evidence, media_fragment
from scrubgpt_contracts.models.decision_record import (
    DecisionRecord,
    DecisionRecordDraft,
    unverbatim_groundings,
)

CASE_ID = "case-fixture-01"
EVIDENCE = TypeAdapter(Evidence)
NARRATION = 5
WITH_EDIT = 6


def _names_record(result, record: dict[str, Any], index: int) -> bool:
    """An ERROR line names the record (by its id, or as `records[<index>]`)."""
    return any(record["id"] in ln or f"records[{index}]" in ln for ln in result.error_lines)


def _run_with_seeds(data_dir, run_validate, seeds: dict[str, Any]):
    data_dir.save("seed_records.json", seeds)
    return run_validate("case", data_dir.case_dir)


def _draft(record: dict[str, Any]) -> dict[str, Any]:
    draft = copy.deepcopy(record)
    draft["id"] = None
    draft["provenance"]["confirmed_by"] = None
    draft["provenance"]["confirmed_at"] = None
    return draft


# --- AC11 (first, as the baseline every other test edits) ---------------------------------------


def test_9ac11_unedited_fixture_passes_with_no_warnings(data_dir, run_validate):
    """#9 AC11: "The unedited `case-fixture-01` still passes `validate case` with exit 0 and no
    warnings"."""
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 0, result.output
    assert result.counts == (0, 0), result.output
    assert not result.warning_lines and not result.error_lines, result.output


def test_9ac11_unedited_fixture_passes_with_no_warnings_cli(paths):
    """#9 AC11 with the installed script, as in the brief:
    `uv run scrubgpt-validate case contracts/fixtures/cases/case-fixture-01`."""
    exe = shutil.which("scrubgpt-validate")
    assert exe
    proc = subprocess.run(
        [exe, "case", "contracts/fixtures/cases/case-fixture-01"],
        cwd=paths["repo"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "0 error(s), 0 warning(s)" in proc.stdout, proc.stdout
    assert "WARNING" not in proc.stdout, proc.stdout


# --- AC3: seed records are 🧪 simulated or 🎙️ narration_extracted --------------------------------

OTHER_LABELS = [
    ("operating_surgeon", "operating_surgeon"),
    ("reviewer", "reviewer"),
    ("ai_detected", "ai"),
    ("dataset_annotation", "dataset"),
    ("expert_validated", "expert"),
]


@pytest.mark.parametrize("index", [0, NARRATION, WITH_EDIT])
@pytest.mark.parametrize(("label", "role"), OTHER_LABELS, ids=[x for x, _ in OTHER_LABELS])
def test_9ac3_seed_record_with_another_trust_label_fails_naming_it(
    data_dir, run_validate, index, label, role
):
    """#9 AC3: "A copy of `case-fixture-01` whose seed record has `trust_label:
    operating_surgeon` (or `reviewer`, `ai_detected`): `validate case` exits 1 and names the
    record" (triage: each seed record's label is in {`simulated`, `narration_extracted`},
    otherwise an error). `attributed_to` follows the label, so only this rule can fire."""
    seeds = data_dir.load("seed_records.json")
    record = seeds["records"][index]
    record["provenance"]["trust_label"] = label
    record["provenance"]["attributed_to"] = role
    result = _run_with_seeds(data_dir, run_validate, seeds)
    assert result.code == 1, result.output
    assert _names_record(result, record, index), result.output


@pytest.mark.parametrize("label", ["operating_surgeon", "reviewer", "ai_detected"])
def test_9ac3_relabelled_role_play_record_fails_naming_it(data_dir, run_validate, label):
    """#9 AC3 as the issue found it: only `trust_label` changed (still `dev_team_simulated`):
    exit 1, the record named."""
    seeds = data_dir.load("seed_records.json")
    record = seeds["records"][0]
    assert record["provenance"]["attributed_to"] == "dev_team_simulated"
    record["provenance"]["trust_label"] = label
    result = _run_with_seeds(data_dir, run_validate, seeds)
    assert result.code == 1, result.output
    assert _names_record(result, record, 0), result.output


@pytest.mark.parametrize(
    ("index", "label", "role"),
    [
        (0, "narration_extracted", "narrator"),
        (WITH_EDIT, "narration_extracted", "narrator"),
        (NARRATION, "simulated", "narrator"),  # synthetic TTS narration (D-027)
        (NARRATION, "simulated", "dev_team_simulated"),
    ],
)
def test_9ac3_simulated_or_narration_extracted_passes(data_dir, run_validate, index, label, role):
    """#9 AC3: "With `simulated` or `narration_extracted` it passes". A record turned into
    narration also gets `question_id: null`: narration answers no question (Team Lead ruling on
    #10 of 2026-10-17, decision 2 / criterion 14; D-059 rule 1). Record 0 answers `m01.q1`, so
    without that it is expected to fail (next test)."""
    seeds = data_dir.load("seed_records.json")
    seeds["records"][index]["provenance"]["trust_label"] = label
    seeds["records"][index]["provenance"]["attributed_to"] = role
    if label == "narration_extracted":
        seeds["records"][index]["question_id"] = None
    result = _run_with_seeds(data_dir, run_validate, seeds)
    assert result.code == 0, result.output
    assert result.counts == (0, 0), result.output


def test_9ac3_narration_extracted_seed_still_answering_a_question_fails(data_dir, run_validate):
    """#9 AC3 x #10 criterion 14: record 0 (answers `m01.q1`) relabelled `narration_extracted`
    without clearing `question_id`: `validate case` exits 1 naming `seed_records.json`."""
    seeds = data_dir.load("seed_records.json")
    record = seeds["records"][0]
    assert record["question_id"] is not None
    record["provenance"]["trust_label"] = "narration_extracted"
    record["provenance"]["attributed_to"] = "narrator"
    result = _run_with_seeds(data_dir, run_validate, seeds)
    assert result.code == 1, result.output
    assert any("seed_records.json" in ln for ln in result.error_lines), result.output


# --- AC4: a fragment on video.mp4 equals t_start/t_end -------------------------------------------


def _media(uri: str, t_start: float, t_end: float) -> dict[str, Any]:
    return {"kind": "media", "case_id": CASE_ID, "uri": uri, "t_start": t_start, "t_end": t_end}


MISMATCHED = [
    ("video.mp4#t=250.0,290.0", 58.0, 78.0),  # the issue's example (3a)
    ("video.mp4#t=57.0,78.0", 58.0, 78.0),  # start only
    ("video.mp4#t=58.0,79.0", 58.0, 78.0),  # end only
    ("video.mp4#t=78,58.0", 58.0, 78.0),  # swapped
    ("video.mp4#t=0,20", 58.0, 78.0),  # clip-relative numbers on the full video
    ("video.mp4#t=58,78", 58.0, 78.5),
    ("video.mp4#t=58.002,78", 58.0, 78.0),  # 2 ms
    ("video.mp4#t=58,78", 58.0, 58.0),
]

MATCHING = [
    ("video.mp4#t=58,78", 58.0, 78.0),  # "`58` vs `58.0` counts as equal"
    ("video.mp4#t=58.0,78.0", 58.0, 78.0),
    ("video.mp4#t=58.000,78.00", 58.0, 78.0),
    ("video.mp4#t=058,78", 58.0, 78.0),
    ("video.mp4#t=58.5,78.25", 58.5, 78.25),
    ("video.mp4#t=0,0", 0.0, 0.0),
    ("video.mp4#t=300,300", 300.0, 300.0),
]

CLIPS = [
    (f"clips/{CASE_ID}.m01.mp4#t=0,20", 58.0, 78.0),
    (f"clips/{CASE_ID}.m01.mp4#t=0.0,20.0", 58.0, 78.0),
    (f"clips/{CASE_ID}.m01.mp4#t=250,290", 58.0, 78.0),
    (f"clips/{CASE_ID}.m01.mp4#t=58,78", 58.0, 78.0),
]


@pytest.mark.parametrize(("uri", "t_start", "t_end"), MISMATCHED, ids=repr)
def test_9ac4_video_fragment_differing_from_span_is_rejected(uri, t_start, t_end):
    """#9 AC4: "Media evidence whose `uri` fragment `#t=a,b` differs numerically from its
    `t_start`/`t_end` is rejected (model ...)" - on `video.mp4` (Dev1's accepted analysis)."""
    with pytest.raises(ValidationError):
        EVIDENCE.validate_python(_media(uri, t_start, t_end))
    with pytest.raises(ValidationError):
        EVIDENCE.validate_json(json.dumps(_media(uri, t_start, t_end)))


@pytest.mark.parametrize(("uri", "t_start", "t_end"), MATCHING, ids=repr)
def test_9ac4_video_fragment_equal_to_span_is_accepted(uri, t_start, t_end):
    """#9 AC4: equal numbers pass; "`58` vs `58.0` counts as equal"."""
    parsed = EVIDENCE.validate_python(_media(uri, t_start, t_end))
    assert parsed.uri == uri  # stored as written


@pytest.mark.parametrize(("uri", "t_start", "t_end"), CLIPS, ids=repr)
def test_9ac4_clip_fragment_is_not_compared(uri, t_start, t_end):
    """#9 AC4 as clarified: "A clip's fragment (`clips/<moment_id>.mp4#t=...`) is relative to the
    clip ..., so it is not compared with `t_start`/`t_end`" (`MediaFragmentUri` docstring)."""
    EVIDENCE.validate_python(_media(uri, t_start, t_end))


@pytest.mark.parametrize("t_start", [58.0, 58.0004, 58.1234, 1234.5678])
def test_9ac4_media_fragment_helper_output_is_accepted(t_start):
    """`common.py` docstrings: `media_fragment()` writes milliseconds, and the comparison allows
    half a millisecond (`FRAGMENT_TOLERANCE_S`), so the helper's own uri for a span validates."""
    t_end = t_start + 20.0
    uri = media_fragment("video.mp4", t_start, t_end)
    EVIDENCE.validate_python(_media(uri, t_start, t_end))


def test_9ac4_dot_slash_video_path_is_still_the_normalised_video():
    """#9 AC4 applies to "media evidence whose fragment is on `video.mp4`, the normalised
    video". `./video.mp4` is a relative POSIX path to that same file (the uri path is relative to
    the case folder, `MediaFragmentUri` docstring; D-048), so its fragment must match too."""
    with pytest.raises(ValidationError):
        EVIDENCE.validate_python(_media("./video.mp4#t=250.0,290.0", 58.0, 78.0))


def test_9ac4_dot_slash_video_mismatch_fails_validate_case(data_dir, run_validate):
    """#9 AC4 / 3a through `validate case`: the issue's example spelled `./video.mp4#t=250.0,290.0`
    (the file exists, it is the normalised video) while `t_start`/`t_end` are 58-78: exit 1."""
    seeds = data_dir.load("seed_records.json")
    seeds["records"][0]["evidence"][0]["uri"] = "./video.mp4#t=250.0,290.0"
    result = _run_with_seeds(data_dir, run_validate, seeds)
    assert result.code == 1, result.output


def test_9ac4_mismatch_inside_a_record_is_rejected(docs):
    """#9 AC4 in a `DecisionRecord` (and its draft): the model rejects the issue's example."""
    record = copy.deepcopy(docs["seed_records.json"]["records"][0])
    assert record["evidence"][0]["uri"] == "video.mp4#t=58.0,78.0"
    record["evidence"][0]["uri"] = "video.mp4#t=250.0,290.0"
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(record)
    with pytest.raises(ValidationError):
        DecisionRecordDraft.model_validate(_draft(record))


def test_9ac4_validate_case_exits_1_on_the_issue_example(data_dir, run_validate):
    """#9 AC4 "(model or `validate case`, exit 1)" and 3a: `uri: video.mp4#t=250.0,290.0` while
    `t_start`/`t_end` are 58-78 is an error naming seed_records.json."""
    seeds = data_dir.load("seed_records.json")
    seeds["records"][0]["evidence"][0]["uri"] = "video.mp4#t=250.0,290.0"
    result = _run_with_seeds(data_dir, run_validate, seeds)
    assert result.code == 1, result.output
    assert any("seed_records.json" in ln for ln in result.error_lines), result.output


def test_9ac4_validate_case_accepts_a_clip_fragment(data_dir, run_validate):
    """#9 AC4 control through `validate case`: the same evidence pointing at the moment's clip
    (`clips/<moment_id>.mp4#t=0.0,20.0`, clip-relative) passes."""
    seeds = data_dir.load("seed_records.json")
    seeds["records"][0]["evidence"][0]["uri"] = f"clips/{CASE_ID}.m01.mp4#t=0.0,20.0"
    result = _run_with_seeds(data_dir, run_validate, seeds)
    assert result.code == 0, result.output


def test_9ac4_every_fixture_media_fragment_matches(docs):
    """#9 AC4 + AC11: every fixture media evidence on `video.mp4` already matches its span."""
    for record in docs["seed_records.json"]["records"]:
        for evidence in record["evidence"]:
            if evidence["kind"] == "media":
                EVIDENCE.validate_python(evidence)


# --- AC5: a question's quote equals the quoted utterance ----------------------------------------


def _question(questions: dict[str, Any], qid: str) -> dict[str, Any]:
    return next(q for q in questions["operating"] + questions["reviewer"] if q["id"] == qid)


def _utterance(timeline: dict[str, Any], uid: str) -> dict[str, Any]:
    return next(u for u in timeline["utterances"] if u["id"] == uid)


@pytest.mark.parametrize(
    ("half", "change"),
    [
        ("ja", lambda s: s[:-1]),
        ("en", lambda s: s.replace("Raise", "Lower")),
        ("ja", lambda s: s + " "),
        ("en", lambda s: s.upper()),
        ("ja", lambda s: s + "。"),
    ],
    ids=["ja-truncated", "en-changed", "ja-trailing-space", "en-uppercase", "ja-extra-char"],
)
def test_9ac5_quote_text_differing_from_the_utterance_fails_naming_the_question(
    data_dir, run_validate, half, change
):
    """#9 AC5: "`questions[].quote.text` that differs from the quoted utterance's `text` (either
    half): exit 1, naming the question id"."""
    questions = data_dir.load("questions.json")
    q = _question(questions, f"{CASE_ID}.m01.q2")
    assert q["quote"]["utterance_id"] == f"{CASE_ID}.u0003"
    q["quote"]["text"][half] = change(q["quote"]["text"][half])
    data_dir.save("questions.json", questions)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert any(q["id"] in ln for ln in result.error_lines), result.output


def test_9ac5_quote_of_another_utterance_fails(data_dir, run_validate):
    """#9 AC5: the text of u0003 quoted under u0004's id differs from u0004's text: exit 1."""
    questions = data_dir.load("questions.json")
    q = _question(questions, f"{CASE_ID}.m01.q2")
    q["quote"]["utterance_id"] = f"{CASE_ID}.u0004"
    data_dir.save("questions.json", questions)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert any(q["id"] in ln for ln in result.error_lines), result.output


@pytest.mark.parametrize("exact", [True, False], ids=["exact", "differs"])
def test_9ac5_reviewer_question_quote_is_checked_too(data_dir, run_validate, exact):
    """#9 AC5 for `questions[]` of both lists: a reviewer question quoting u0003 passes with its
    exact text and fails (naming the question) when the text differs."""
    timeline = data_dir.load("timeline.json")
    text = copy.deepcopy(_utterance(timeline, f"{CASE_ID}.u0003")["text"])
    if not exact:
        text["en"] = "Some bleeding. Raise the pressure."
    questions = data_dir.load("questions.json")
    q = _question(questions, f"{CASE_ID}.m01.r1")
    q["quote"] = {"utterance_id": f"{CASE_ID}.u0003", "text": text}
    data_dir.save("questions.json", questions)
    result = run_validate("case", data_dir.case_dir)
    if exact:
        assert result.code == 0, result.output
    else:
        assert result.code == 1, result.output
        assert any(q["id"] in ln for ln in result.error_lines), result.output


def test_9ac5_fixture_quotes_equal_their_utterances(docs):
    """#9 AC5 + AC11: every fixture question quote equals its utterance's text (both halves)."""
    utterances = {u["id"]: u for u in docs["timeline.json"]["utterances"]}
    q = docs["questions.json"]
    for question in q["operating"] + q["reviewer"]:
        if question["quote"]:
            uid = question["quote"]["utterance_id"]
            assert question["quote"]["text"] == utterances[uid]["text"], question["id"]


# --- AC6: language none => no utterances --------------------------------------------------------


def _speechless_case(data_dir) -> None:
    case = data_dir.load("case.json")
    case.update(language="none", narrated=False, synthetic_speech=False)
    data_dir.save("case.json", case)


def _remove_all_speech(data_dir) -> None:
    """No utterances, so nothing may quote one: the two `confirm_quote` questions become
    `decision` questions without a quote, and the 🎙️ narration record is dropped."""
    timeline = data_dir.load("timeline.json")
    timeline["utterances"] = []
    data_dir.save("timeline.json", timeline)
    questions = data_dir.load("questions.json")
    for q in questions["operating"] + questions["reviewer"]:
        if q["quote"] is not None:
            q["type"], q["quote"] = "decision", None
    data_dir.save("questions.json", questions)
    seeds = data_dir.load("seed_records.json")
    seeds["records"] = [
        r for r in seeds["records"] if not any(e["kind"] == "transcript" for e in r["evidence"])
    ]
    data_dir.save("seed_records.json", seeds)


def test_9ac6_language_none_with_utterances_fails(data_dir, run_validate):
    """#9 AC6: "`case.json` `language: none` with any utterance in `timeline.json`: exit 1"
    (the issue's 3d: `language: none` + `narrated: false`, 11 utterances; D-049)."""
    _speechless_case(data_dir)
    assert len(data_dir.load("timeline.json")["utterances"]) == 11
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert result.error_lines, result.output


def test_9ac6_language_none_without_utterances_passes(data_dir, run_validate):
    """#9 AC6 control: the same case with no utterances (and so nothing quoting one) passes,
    which shows the utterances are what fails it."""
    _speechless_case(data_dir)
    _remove_all_speech(data_dir)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 0, result.output


def test_9ac6_language_none_with_a_single_utterance_fails(data_dir, run_validate, docs):
    """#9 AC6 "with any utterance": the passing control plus one unquoted utterance fails."""
    _speechless_case(data_dir)
    _remove_all_speech(data_dir)
    timeline = data_dir.load("timeline.json")
    timeline["utterances"] = [copy.deepcopy(docs["timeline.json"]["utterances"][0])]
    data_dir.save("timeline.json", timeline)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert result.error_lines, result.output


@pytest.mark.parametrize(
    "flags",
    [
        {"narrated": False, "synthetic_speech": True},
        {"narrated": True, "synthetic_speech": False},
        {"narrated": True, "synthetic_speech": True},
    ],
    ids=repr,
)
def test_9ac6_language_none_with_synthetic_speech_or_narration_is_rejected(
    data_dir, run_validate, docs, flags
):
    """#9 AC6: "(`synthetic_speech: true` with `none` is already rejected under D-049; still
    verify it.)" D-049: "`language: none` => no narration or synthetic speech". Rejected by the
    `Case` model and by `validate case` (exit 1, naming case.json), even with no utterances."""
    case = dict(copy.deepcopy(docs["case.json"]), language="none", **flags)
    with pytest.raises(ValidationError):
        Case.model_validate(case)
    _remove_all_speech(data_dir)
    data_dir.save("case.json", case)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert any("case.json" in ln for ln in result.error_lines), result.output


# --- AC7: grounding quotes are verbatim in the record's own evidence ------------------------------


def _answers(record: dict[str, Any]) -> list[str]:
    return [e["quote"] for e in record["evidence"] if e["kind"] == "answer_text"]


def _bad_after(record: dict[str, Any]) -> list[int]:
    return list(unverbatim_groundings(DecisionRecord.model_validate(record)))


def test_9ac7_fixture_groundings_are_all_verbatim(docs):
    """#9 AC7 + AC11 control: `unverbatim_groundings()` finds nothing in the fixture records (and
    in their drafts)."""
    for record in docs["seed_records.json"]["records"]:
        assert _bad_after(record) == [], record["id"]
        draft = DecisionRecordDraft.model_validate(_draft(record))
        assert list(unverbatim_groundings(draft)) == [], record["id"]


def _check_case(data_dir, run_validate, index: int, record: dict[str, Any]):
    seeds = data_dir.load("seed_records.json")
    seeds["records"][index] = record
    return _run_with_seeds(data_dir, run_validate, seeds)


def _expect_unverbatim(data_dir, run_validate, index, record, bad_index):
    assert _bad_after(record) == [bad_index]
    draft = DecisionRecordDraft.model_validate(_draft(record))
    assert list(unverbatim_groundings(draft)) == [bad_index]
    result = _check_case(data_dir, run_validate, index, record)
    assert result.code == 1, result.output
    assert any("seed_records.json" in ln for ln in result.error_lines), result.output


def _expect_verbatim(data_dir, run_validate, index, record):
    assert _bad_after(record) == []
    result = _check_case(data_dir, run_validate, index, record)
    assert result.code == 0, result.output


def test_9ac7_answer_quote_not_in_any_answer_text_fails(docs, data_dir, run_validate):
    """#9 AC7: "A grounding with `source: answer` whose quote is not a substring of any
    `answer_text` evidence quote of that record: exit 1" (the issue's 3e example)."""
    record = copy.deepcopy(docs["seed_records.json"]["records"][0])
    record["grounding"][0]["quote"] = "The surgeon never said this"
    _expect_unverbatim(data_dir, run_validate, 0, record, 0)


def test_9ac7_narration_quote_not_in_any_transcript_fails(docs, data_dir, run_validate):
    """#9 AC7: "The same for `source: narration` against `transcript` evidence"."""
    record = copy.deepcopy(docs["seed_records.json"]["records"][NARRATION])
    assert record["grounding"][1]["source"] == "narration"
    record["grounding"][1]["quote"] = "中葉を持ち上げます"
    _expect_unverbatim(data_dir, run_validate, NARRATION, record, 1)


def test_9ac7_answer_quote_found_only_in_transcript_evidence_fails(docs, data_dir, run_validate):
    """#9 triage: a `source: answer` quote is checked against `answer_text` evidence only: the
    narration record's verbatim transcript words relabelled `source: answer` fail."""
    record = copy.deepcopy(docs["seed_records.json"]["records"][NARRATION])
    assert not _answers(record)
    record["grounding"][0]["source"] = "answer"
    _expect_unverbatim(data_dir, run_validate, NARRATION, record, 0)


def test_9ac7_narration_without_transcript_evidence_fails(docs, data_dir, run_validate):
    """#9 triage risks: "A narration grounding without `transcript` evidence fails by design": a
    verbatim answer quote relabelled `source: narration` fails."""
    record = copy.deepcopy(docs["seed_records.json"]["records"][0])
    assert not [e for e in record["evidence"] if e["kind"] == "transcript"]
    record["grounding"][2]["source"] = "narration"
    _expect_unverbatim(data_dir, run_validate, 0, record, 2)


def test_9ac7_quote_from_another_records_answer_fails(docs, data_dir, run_validate):
    """#9 AC7 "...any `answer_text` evidence quote of **that record**": words from record 0's
    answer, grounded in record 1, fail."""
    records = docs["seed_records.json"]["records"]
    record = copy.deepcopy(records[1])
    other = "まず気腹圧を15に上げて"
    assert other in _answers(records[0])[0] and not any(other in a for a in _answers(record))
    record["grounding"][0]["quote"] = other
    _expect_unverbatim(data_dir, run_validate, 1, record, 0)


def test_9ac7_quote_spanning_two_transcript_quotes_fails(docs, data_dir, run_validate):
    """#9 triage: "an exact substring of **one** of its `transcript` evidence quotes": a quote
    that only exists when two transcript quotes are joined fails."""
    utterances = {u["id"]: u for u in docs["timeline.json"]["utterances"]}
    record = copy.deepcopy(docs["seed_records.json"]["records"][NARRATION])
    u5 = utterances[f"{CASE_ID}.u0005"]["text"]["ja"]
    record["evidence"].append(
        {"kind": "transcript", "case_id": CASE_ID, "utterance_id": f"{CASE_ID}.u0005", "quote": u5}
    )
    transcript = record["evidence"][1]["quote"]
    joined = u5[-6:] + transcript[:4]
    assert not any(joined in e.get("quote", "") for e in record["evidence"])
    record["grounding"][1]["quote"] = joined
    _expect_unverbatim(data_dir, run_validate, NARRATION, record, 1)


@pytest.mark.parametrize("quote", ["The surgeon never said this", "　編集した文 ", "x"])
def test_9ac7_edit_grounding_with_any_quote_passes(docs, data_dir, run_validate, quote):
    """#9 AC7: "A `source: edit` grounding with any quote passes" (the surgeon's own chip edit;
    any non-empty quote, since `Grounding.quote` is a non-empty string)."""
    record = copy.deepcopy(docs["seed_records.json"]["records"][0])
    record["grounding"][0]["source"] = "edit"
    record["grounding"][0]["quote"] = quote
    _expect_verbatim(data_dir, run_validate, 0, record)


def test_9ac7_fixture_edit_grounding_is_not_in_any_evidence(docs):
    """#9 AC7 + AC12: the fixture's `edit` grounding quotes words that appear in no evidence, and
    still counts as verbatim."""
    record = docs["seed_records.json"]["records"][WITH_EDIT]
    edit = [g for g in record["grounding"] if g["source"] == "edit"]
    assert edit
    quotes = [e.get("quote", "") for e in record["evidence"]]
    assert any(not any(g["quote"] in q for q in quotes) for g in edit)
    assert _bad_after(record) == []


def test_9ac7_whole_answer_as_quote_passes(docs, data_dir, run_validate):
    """#9 AC7: the whole answer is an exact substring of itself."""
    record = copy.deepcopy(docs["seed_records.json"]["records"][0])
    record["grounding"][0]["quote"] = _answers(record)[0]
    _expect_verbatim(data_dir, run_validate, 0, record)


def test_9ac7_quote_in_a_second_answer_text_passes(docs, data_dir, run_validate):
    """#9 AC7 "one of the record's `answer_text` evidence quotes": a quote found only in a second
    `answer_text` evidence passes."""
    record = copy.deepcopy(docs["seed_records.json"]["records"][0])
    record["evidence"].append(
        {
            "kind": "answer_text",
            "answer_id": str(uuid6.uuid7()),
            "quote": "追加で言うと、吸引も使いました。",
        }
    )
    record["grounding"][0]["quote"] = "吸引も使いました"
    _expect_verbatim(data_dir, run_validate, 0, record)


def test_9ac7_nfd_grounding_quote_matches_nfc_evidence(docs, data_dir, run_validate):
    """#9 triage: "Same NFC normalisation on both sides": a grounding quote in NFD (が = か +
    U+3099) matches the NFC answer text."""
    record = copy.deepcopy(docs["seed_records.json"]["records"][0])
    quote = record["grounding"][0]["quote"]
    nfd = unicodedata.normalize("NFD", quote)
    assert nfd != quote and unicodedata.normalize("NFC", nfd) == quote
    record["grounding"][0]["quote"] = nfd
    _expect_verbatim(data_dir, run_validate, 0, record)


def test_9ac7_nfd_evidence_matches_nfc_grounding_quotes(docs, data_dir, run_validate):
    """#9 triage: NFC on **both** sides: an NFD answer text still grounds the NFC quotes."""
    record = copy.deepcopy(docs["seed_records.json"]["records"][0])
    i = next(i for i, e in enumerate(record["evidence"]) if e["kind"] == "answer_text")
    original = record["evidence"][i]["quote"]
    record["evidence"][i]["quote"] = unicodedata.normalize("NFD", original)
    assert record["evidence"][i]["quote"] != original
    _expect_verbatim(data_dir, run_validate, 0, record)


@pytest.mark.parametrize(
    ("index", "verbatim", "changed"),
    [
        (0, "まず気腹圧を15に上げて", "まず気腹圧を１５に上げて"),  # equal only under NFKC
        (1, "With bleeding from the DVC like this", "with bleeding from the DVC like this"),
        (1, "bleeding from the DVC", "bleeding  from the DVC"),
        (1, "the view only gets worse while you wait", "the view only gets worse while you wait "),
        (0, "1分くらいで止まりました。", "1分くらいで止まりました."),
    ],
    ids=["nfkc-width", "case", "double-space", "trailing-space", "punctuation"],
)
def test_9ac7_nothing_but_nfc_is_normalised(docs, data_dir, run_validate, index, verbatim, changed):
    """#9 triage: "Same NFC normalisation on both sides, nothing else": width (NFKC), case,
    whitespace and punctuation differences are not verbatim. (Control: the unchanged words are
    verbatim and pass.)"""
    record = copy.deepcopy(docs["seed_records.json"]["records"][index])
    assert any(verbatim in a for a in _answers(record))
    assert not any(changed in a for a in _answers(record))
    assert unicodedata.normalize("NFC", changed) == changed
    record["grounding"][0]["quote"] = verbatim
    assert _bad_after(record) == []
    record["grounding"][0]["quote"] = changed
    _expect_unverbatim(data_dir, run_validate, index, record, 0)


# --- AC8: a record's step differs from its moment's step: warning -------------------------------


@pytest.mark.parametrize(("index", "step"), [(0, "rarp.p12.s02"), (NARRATION, "rarp.p04.s01")])
def test_9ac8_step_differing_from_the_moment_is_a_warning(data_dir, run_validate, index, step):
    """#9 AC8: "A record whose `step_id` differs from its moment's step: printed as a warning,
    exit 0 (if nothing else fails)" (3b: `rarp.p12.s02` while m01 is in `rarp.p04.s02`)."""
    seeds = data_dir.load("seed_records.json")
    moment_step = {m["id"]: m["step_id"] for m in data_dir.load("moments.json")["moments"]}
    record = seeds["records"][index]
    assert moment_step[record["moment_id"]] != step
    record["step_id"] = step
    result = _run_with_seeds(data_dir, run_validate, seeds)
    assert result.code == 0, result.output
    errors, warnings = result.counts
    assert errors == 0 and warnings >= 1, result.output
    assert any("seed_records.json" in ln for ln in result.warning_lines), result.output


def test_9ac8_record_without_a_moment_has_nothing_to_compare(data_dir, run_validate):
    """#9 AC8 control: a moment-less record (`moment_id: null`) on another step gets no
    warning."""
    seeds = data_dir.load("seed_records.json")
    record = seeds["records"][4]
    assert record["moment_id"] is None
    record["step_id"] = "rarp.p12.s02"
    result = _run_with_seeds(data_dir, run_validate, seeds)
    assert result.code == 0, result.output
    assert result.counts == (0, 0), result.output


def test_9ac8_mismatch_warning_does_not_hide_an_error(data_dir, run_validate):
    """#9 AC8 "(if nothing else fails)": with a real error as well, the run exits 1 and the
    warning is still printed."""
    seeds = data_dir.load("seed_records.json")
    seeds["records"][0]["step_id"] = "rarp.p12.s02"
    seeds["records"][1]["grounding"][0]["quote"] = "The surgeon never said this"
    result = _run_with_seeds(data_dir, run_validate, seeds)
    assert result.code == 1, result.output
    assert result.warning_lines and result.error_lines, result.output


# --- AC9: delayed_outcome status vs text: warning -----------------------------------------------

TEXT = {"ja": "術後3か月で尿禁制が戻った", "en": "Continence returned at 3 months"}

INCOHERENT = [
    {"status": "known", "text": None, "source": None},
    {"status": "known", "text": None, "source": "follow-up clinic note"},
    {"status": "pending", "text": TEXT, "source": None},
    {"status": "pending", "text": TEXT, "source": "follow-up clinic note"},
    {"status": "not_applicable", "text": TEXT, "source": None},
]

COHERENT = [
    {"status": "known", "text": TEXT, "source": "follow-up clinic note"},
    {"status": "pending", "text": None, "source": None},
    {"status": "not_applicable", "text": None, "source": None},
]


@pytest.mark.parametrize("outcome", INCOHERENT, ids=repr)
def test_9ac9_incoherent_delayed_outcome_is_a_warning(data_dir, run_validate, outcome):
    """#9 AC9: "`delayed_outcome` `status: known` with `text: null`, or
    `status: pending`/`not_applicable` with `text` set: a warning, exit 0"."""
    seeds = data_dir.load("seed_records.json")
    seeds["records"][0]["delayed_outcome"] = outcome
    DecisionRecord.model_validate(seeds["records"][0])  # a warning, so the model accepts it
    result = _run_with_seeds(data_dir, run_validate, seeds)
    assert result.code == 0, result.output
    errors, warnings = result.counts
    assert errors == 0 and warnings >= 1, result.output
    assert any("seed_records.json" in ln for ln in result.warning_lines), result.output


@pytest.mark.parametrize("outcome", COHERENT, ids=repr)
def test_9ac9_coherent_delayed_outcome_has_no_warning(data_dir, run_validate, outcome):
    """#9 AC9 controls: `known` with text, `pending` / `not_applicable` without: no warning (and
    `delayed_outcome.text` needs no grounding, D-052)."""
    seeds = data_dir.load("seed_records.json")
    seeds["records"][0]["delayed_outcome"] = outcome
    result = _run_with_seeds(data_dir, run_validate, seeds)
    assert result.code == 0, result.output
    assert result.counts == (0, 0), result.output
