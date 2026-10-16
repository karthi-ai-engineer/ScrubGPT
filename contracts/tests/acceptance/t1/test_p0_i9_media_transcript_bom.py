"""#9 AC14-AC18: media evidence paths, verbatim transcript evidence, UTF-8 BOM and the no-step-ids
case (Team Lead reply on issue #9, the last "Team Lead · reply"; refines D-055 and D-058).

Team Lead decision, quoted by the tests below:
- "In `MediaEvidence`, the `uri` path (before `#`) is exactly `video.mp4` or
  `clips/<MomentId>.mp4`, where `<MomentId>` matches the existing moment-id format. Anything else is
  a model error. ... `validate case` gives an error (exit 1) when a seed record's clip evidence with
  this case's `case_id` names a moment that isn't in `moments.json`. Evidence carrying another
  `case_id` is not checked by `validate case`."
- "`validate case` gives an error (exit 1) when a seed record's `transcript` evidence (this case's
  `case_id`) names an `utterance_id` that isn't in `timeline.json`. It also errors when the `quote`
  isn't an exact substring of that utterance's `text` in its `original_lang`, after NFC on both
  sides and nothing else. The message names the record and the utterance."
- "Every JSON read in `scrubgpt-validate` ... accepts one leading BOM (`utf-8-sig`). It prints a
  warning naming the file ..., and the exit code doesn't change. Producers never write a BOM ...
  Anything that is still not valid UTF-8 stays exit 1 (D-055)." Brief clarification (D-055 by
  role): the reference as the subject of `validate reference` -> exit 1; as the input that
  `validate case` reads -> exit 2.
- "No step-id prefix. This stays a warning ..., never exit 2 ... If `--reference` is given, the
  file is still read and validated as an input under D-055 (exit 2 if it's missing or invalid)."
"""

from __future__ import annotations

import copy
import json
import shutil
import unicodedata
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError
from scrubgpt_contracts.models.common import Evidence, clip_moment_id
from scrubgpt_contracts.models.decision_record import DecisionRecord

CASE_ID = "case-fixture-01"
EVIDENCE = TypeAdapter(Evidence)
BOM = b"\xef\xbb\xbf"
PACKAGE_JSON = ["case.json", "timeline.json", "moments.json", "questions.json", "seed_records.json"]
NARRATION = 5  # fixture seed record mined from u0006 (transcript evidence)


def _media(uri: str, t_start: float = 58.0, t_end: float = 78.0) -> dict[str, Any]:
    return {"kind": "media", "case_id": CASE_ID, "uri": uri, "t_start": t_start, "t_end": t_end}


def _run_with_seeds(data_dir, run_validate, seeds: dict[str, Any]):
    data_dir.save("seed_records.json", seeds)
    return run_validate("case", data_dir.case_dir)


def _error_naming(result, *names: str) -> bool:
    """One ERROR line names every one of `names`."""
    return any(all(n in ln for n in names) for ln in result.error_lines)


# --- AC14: media evidence paths -------------------------------------------------------------------

AC14_ACCEPTED = [
    ("video.mp4#t=58.0,78.0", 58.0, 78.0),
    (f"clips/{CASE_ID}.m01.mp4#t=0,20", 58.0, 78.0),
    (f"clips/{CASE_ID}.m06.mp4#t=0.0,20.0", 280.0, 300.0),
    ("clips/grasp-01.m07.mp4#t=0,20", 58.0, 78.0),
    (f"clips/{CASE_ID}.m100.mp4#t=0,1", 58.0, 78.0),
]

AC14_REJECTED = [
    # verbatim from AC14
    "poster.jpg#t=58,78",
    "thumbs/x.jpg#t=58,78",
    "clips/x.mp4#t=0,20",
    f"clips/{CASE_ID}.m01.jpg#t=0,20",
    f"other/{CASE_ID}.m01.mp4#t=0,20",
    "./video.mp4#t=58,78",
    "clips/../video.mp4#t=58,78",
    "https://example.com/video.mp4#t=58,78",
]

EDGE_REJECTED = [
    # "exactly `video.mp4` or `clips/<MomentId>.mp4` ... Anything else is a model error"
    "/video.mp4#t=58,78",
    "Video.mp4#t=58,78",
    "video.MP4#t=58,78",
    "video.mp4/#t=58,78",
    "file:video.mp4#t=58,78",
    "video.mp4?x=1#t=58,78",
    "thumbs/video.mp4#t=58,78",
    f"clips//{CASE_ID}.m01.mp4#t=0,20",
    f"clips/./{CASE_ID}.m01.mp4#t=0,20",
    f"clips/sub/{CASE_ID}.m01.mp4#t=0,20",
    f"./clips/{CASE_ID}.m01.mp4#t=0,20",
    f"clips/{CASE_ID}.m01.mp4.mp4#t=0,20",
    f"clips\\{CASE_ID}.m01.mp4#t=0,20",
    f"clips/{CASE_ID}.m1.mp4#t=0,20",  # mNN needs 2+ digits (D-048)
    f"clips/{CASE_ID.upper()}.m01.mp4#t=0,20",
    f"clips/{CASE_ID}.e001.mp4#t=0,20",  # an event id, not a moment id
    f"clips/{CASE_ID}.m01.q1.mp4#t=0,20",  # a question id
    "clips/.m01.mp4#t=0,20",
    f"clips/{CASE_ID}.mp4#t=0,20",
    f"clips/{CASE_ID}.m01.mp4",  # no fragment
    "video.mp4",
]


@pytest.mark.parametrize(("uri", "t_start", "t_end"), AC14_ACCEPTED, ids=repr)
def test_9ac14_media_evidence_accepts_video_and_clip_paths(uri, t_start, t_end):
    """#9 AC14: "`MediaEvidence` accepts `video.mp4#t=...` and `clips/<valid moment id>.mp4#t=...`"
    (a clip fragment stays clip-relative and isn't compared)."""
    assert EVIDENCE.validate_python(_media(uri, t_start, t_end)).uri == uri
    EVIDENCE.validate_json(json.dumps(_media(uri, t_start, t_end)))


@pytest.mark.parametrize("uri", AC14_REJECTED + EDGE_REJECTED, ids=repr)
def test_9ac14_media_evidence_rejects_every_other_path(uri):
    """#9 AC14: "It rejects `poster.jpg#t=...`, `thumbs/x.jpg#t=...`, `clips/x.mp4` with an
    invalid moment id, `clips/<id>.jpg`, `other/<id>.mp4`, `./video.mp4`, `clips/../video.mp4` and
    `https://.../video.mp4`" (and, per the decision, anything else). The span is 58-78, so a
    `video.mp4` fragment of 58,78 could only fail on its path."""
    with pytest.raises(ValidationError):
        EVIDENCE.validate_python(_media(uri))
    with pytest.raises(ValidationError):
        EVIDENCE.validate_json(json.dumps(_media(uri)))


def test_9ac14_rejected_path_inside_a_record(docs):
    """#9 AC14 "a model error": a `DecisionRecord` citing `poster.jpg#t=...` is rejected."""
    record = copy.deepcopy(docs["seed_records.json"]["records"][0])
    record["evidence"][0]["uri"] = "poster.jpg#t=58.0,78.0"
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(record)


def _media_uri_patterns(schema: dict[str, Any]) -> list[str]:
    out = []
    for definition in schema.get("$defs", {}).values():
        props = definition.get("properties", {})
        kind = props.get("kind", {})
        if kind.get("const") == "media" or kind.get("enum") == ["media"]:
            pattern = props.get("uri", {}).get("pattern")
            assert pattern, f"media evidence uri has no pattern in the schema: {props.get('uri')}"
            out.append(pattern)
    return out


def test_9ac14_committed_schema_carries_the_media_uri_pattern(paths):
    """#9 Team Lead reply, notes: "The schema should carry the uri pattern too, so the TS side
    sees it": the committed `DecisionRecord` schema's media `uri` pattern accepts the AC14 paths
    and rejects the AC14 list (ECMA semantics: `$` is the end of input)."""
    import re

    schema = json.loads(
        (paths["repo"] / "contracts" / "schema" / "DecisionRecord.schema.json").read_text("utf-8")
    )
    patterns = _media_uri_patterns(schema)
    assert patterns, "no media evidence definition in schema/DecisionRecord.schema.json"
    for pattern in patterns:
        rx = re.compile(pattern.replace("$", r"\Z"), re.ASCII)
        assert all(rx.search(uri) for uri, _, _ in AC14_ACCEPTED), pattern
        wrongly = [u for u in AC14_REJECTED + EDGE_REJECTED if rx.search(u)]
        assert not wrongly, f"schema pattern {pattern!r} accepts {wrongly}"


@pytest.mark.parametrize(
    ("uri", "moment"),
    [
        (f"clips/{CASE_ID}.m07.mp4#t=0,20", f"{CASE_ID}.m07"),
        ("clips/grasp-01.m07.mp4#t=0,20", "grasp-01.m07"),
        ("video.mp4#t=58.0,78.0", None),
    ],
)
def test_9ac14_clip_moment_id(uri, moment):
    """`clip_moment_id()` docstring (common.py): "The moment whose clip a media `uri` names, or
    `None` for the normalised video"."""
    assert clip_moment_id(uri) == moment


# --- AC15: clip evidence names a moment of this case ----------------------------------------------


@pytest.mark.parametrize(
    "uri",
    [f"clips/{CASE_ID}.m09.mp4#t=0,20", f"clips/{CASE_ID}.m07.mp4#t=0.0,20.0"],
)
def test_9ac15_clip_of_a_moment_not_in_moments_json_fails_naming_the_record(
    data_dir, run_validate, uri
):
    """#9 AC15: "A copy of `case-fixture-01` whose seed record cites `clips/<moment id not in
    moments.json>.mp4` with this case's `case_id` -> exit 1, naming the record"."""
    seeds = data_dir.load("seed_records.json")
    record = seeds["records"][0]
    record["evidence"][0]["uri"] = uri
    assert record["evidence"][0]["case_id"] == CASE_ID
    result = _run_with_seeds(data_dir, run_validate, seeds)
    assert result.code == 1, result.output
    assert _error_naming(result, record["id"]), result.output


def test_9ac15_clip_of_another_cases_moment_under_this_case_id_fails(data_dir, run_validate):
    """#9 AC15: with this case's `case_id`, `clips/grasp-01.m01.mp4` names a moment that isn't in
    this package's moments.json -> exit 1, naming the record."""
    seeds = data_dir.load("seed_records.json")
    record = seeds["records"][0]
    record["evidence"][0]["uri"] = "clips/grasp-01.m01.mp4#t=0,20"
    result = _run_with_seeds(data_dir, run_validate, seeds)
    assert result.code == 1, result.output
    assert _error_naming(result, record["id"]), result.output


@pytest.mark.parametrize("moment", ["m01", "m02", "m06"])
def test_9ac15_clip_of_an_existing_moment_passes(data_dir, run_validate, moment):
    """#9 AC15 control: clip evidence naming a moment in moments.json passes (clip-relative
    fragment, not compared)."""
    seeds = data_dir.load("seed_records.json")
    seeds["records"][0]["evidence"][0]["uri"] = f"clips/{CASE_ID}.{moment}.mp4#t=0.0,20.0"
    result = _run_with_seeds(data_dir, run_validate, seeds)
    assert result.code == 0, result.output
    assert result.counts == (0, 0), result.output


# --- AC16: transcript evidence is verbatim --------------------------------------------------------


def _utterance(docs, n: int) -> dict[str, Any]:
    uid = f"{CASE_ID}.u{n:04d}"
    return next(u for u in docs["timeline.json"]["utterances"] if u["id"] == uid)


def _with_transcript(data_dir, run_validate, utterance_id: str, quote: str, case_id=CASE_ID):
    seeds = data_dir.load("seed_records.json")
    record = seeds["records"][0]
    record["evidence"].append(
        {"kind": "transcript", "case_id": case_id, "utterance_id": utterance_id, "quote": quote}
    )
    return record, _run_with_seeds(data_dir, run_validate, seeds)


@pytest.mark.parametrize(
    "make",
    [
        lambda u: "fixture quote",
        lambda u: u["text"]["en"],  # the other language half (original_lang is ja)
        lambda u: u["text"]["en"][:12],
        lambda u: u["text"]["ja"] + " ",
        lambda u: u["text"]["ja"].replace("。", "."),
    ],
    ids=["fixture-quote", "other-half", "other-half-part", "trailing-space", "punctuation"],
)
def test_9ac16_transcript_quote_not_verbatim_fails_naming_record_and_utterance(
    docs, data_dir, run_validate, make
):
    """#9 AC16: "Transcript evidence whose quote isn't an NFC substring of the utterance's
    `original_lang` text (e.g. `"fixture quote"` on u0001, or text taken from the other language
    half) -> exit 1, naming the record and the utterance" ("nothing else" is normalised)."""
    u = _utterance(docs, 1)
    assert u["original_lang"] == "ja"
    record, result = _with_transcript(data_dir, run_validate, u["id"], make(u))
    assert result.code == 1, result.output
    assert _error_naming(result, record["id"], u["id"]), result.output


def test_9ac16_nfkc_only_difference_fails(docs, data_dir, run_validate):
    """#9 decision: "after NFC on both sides and nothing else": full-width digits that only NFKC
    would equate are not verbatim (u0004 says `15`)."""
    u = _utterance(docs, 4)
    assert "15" in u["text"]["ja"]
    record, result = _with_transcript(data_dir, run_validate, u["id"], "気腹圧を１５に上げました")
    assert result.code == 1, result.output
    assert _error_naming(result, record["id"], u["id"]), result.output


def test_9ac16_unknown_utterance_fails(data_dir, run_validate):
    """#9 AC16: "An unknown `utterance_id` -> exit 1" (named with the record)."""
    record, result = _with_transcript(data_dir, run_validate, f"{CASE_ID}.u0999", "気腹圧")
    assert result.code == 1, result.output
    assert _error_naming(result, record["id"]), result.output


@pytest.mark.parametrize(
    ("n", "quote"),
    [(1, None), (1, "レチウス腔を展開"), (3, "気腹圧を上げてください"), (11, "水密です。")],
    ids=["whole-text", "u0001-part", "u0003-part", "u0011-part"],
)
def test_9ac16_verbatim_substring_passes(docs, data_dir, run_validate, n, quote):
    """#9 AC16: "A verbatim substring passes" (the whole text too)."""
    u = _utterance(docs, n)
    quote = quote or u["text"]["ja"]
    assert quote in u["text"]["ja"]
    _, result = _with_transcript(data_dir, run_validate, u["id"], quote)
    assert result.code == 0, result.output
    assert result.counts == (0, 0), result.output


def test_9ac16_nfd_copy_of_a_verbatim_ja_quote_passes(docs, data_dir, run_validate):
    """#9 AC16: "An NFD-encoded copy of a verbatim JA quote passes" (u0003: げ, だ decompose)."""
    u = _utterance(docs, 3)
    nfd = unicodedata.normalize("NFD", "気腹圧を上げてください")
    assert nfd != "気腹圧を上げてください"
    _, result = _with_transcript(data_dir, run_validate, u["id"], nfd)
    assert result.code == 0, result.output


def test_9ac16_nfd_copy_in_the_narration_record_passes(data_dir, run_validate):
    """#9 AC16 on the fixture's narration record: its u0006 transcript quote re-encoded as NFD
    still passes (and its narration groundings stay verbatim, D-058 3e: NFC on both sides)."""
    seeds = data_dir.load("seed_records.json")
    evidence = next(e for e in seeds["records"][NARRATION]["evidence"] if e["kind"] == "transcript")
    nfd = unicodedata.normalize("NFD", evidence["quote"])
    assert nfd != evidence["quote"]
    evidence["quote"] = nfd
    result = _run_with_seeds(data_dir, run_validate, seeds)
    assert result.code == 0, result.output


def test_9ac16_the_utterances_original_lang_decides(docs, data_dir, run_validate):
    """#9 decision: "...that utterance's `text` in its `original_lang`": with u0001 marked
    `original_lang: en`, its English text is verbatim and its Japanese text is not."""
    timeline = data_dir.load("timeline.json")
    u = next(x for x in timeline["utterances"] if x["id"] == f"{CASE_ID}.u0001")
    u["original_lang"] = "en"
    data_dir.save("timeline.json", timeline)
    _, ok = _with_transcript(data_dir, run_validate, u["id"], u["text"]["en"])
    assert ok.code == 0, ok.output
    record, bad = _with_transcript(data_dir, run_validate, u["id"], u["text"]["ja"])
    assert bad.code == 1, bad.output
    assert _error_naming(bad, record["id"], u["id"]), bad.output


# --- AC17: UTF-8 BOM ------------------------------------------------------------------------------


def _prefix(path: Path, prefix: bytes) -> None:
    path.write_bytes(prefix + path.read_bytes())


def _break_utf8(path: Path) -> None:
    """A leading BOM, then the file with one byte that is never valid UTF-8 inside the first
    string."""
    data = path.read_bytes()
    i = data.index(b'"') + 1
    path.write_bytes(BOM + data[:i] + b"\xff" + data[i:])


def _bom_warning(result, name: str) -> bool:
    return any(name in ln and "BOM" in ln for ln in result.warning_lines)


def _ensure_metrics_has_no_bom(data_dir) -> None:
    assert not (data_dir.case_dir / "metrics.json").read_bytes().startswith(BOM)


@pytest.mark.parametrize("name", PACKAGE_JSON)
def test_9ac17_package_file_with_one_bom_warns_and_keeps_exit_0(data_dir, run_validate, name):
    """#9 AC17: "Each of `case.json`, `timeline.json`, `moments.json`, `questions.json`,
    `seed_records.json` ... saved with a leading UTF-8 BOM: a warning names the file, and the exit
    code equals the code without the BOM (0 for the otherwise valid fixture)"."""
    _ensure_metrics_has_no_bom(data_dir)
    _prefix(data_dir.case_dir / name, BOM)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 0, result.output
    assert result.counts[0] == 0, result.output
    assert _bom_warning(result, name), result.output


@pytest.mark.parametrize("name", PACKAGE_JSON)
def test_9ac17_bom_does_not_change_an_exit_1(data_dir, run_validate, name):
    """#9 AC17 "the exit code equals the code without the BOM": a package that already fails
    (a tap option named `confirm` in questions.json) still exits 1 with the BOM, and its error is
    still reported."""
    questions = data_dir.load("questions.json")
    i = next(i for i, q in enumerate(questions["operating"]) if q["tap_options"])
    questions["operating"][i]["tap_options"][0]["id"] = "confirm"
    data_dir.save("questions.json", questions)
    without = run_validate("case", data_dir.case_dir)
    assert without.code == 1, without.output
    _prefix(data_dir.case_dir / name, BOM)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == without.code, result.output
    assert any("questions.json" in ln for ln in result.error_lines), result.output
    assert _bom_warning(result, name), result.output


@pytest.mark.parametrize("name", PACKAGE_JSON)
@pytest.mark.parametrize("damage", ["two-boms", "invalid-utf8-after-bom"])
def test_9ac17_two_boms_or_invalid_utf8_in_a_package_file_exits_1(
    data_dir, run_validate, name, damage
):
    """#9 AC17: "Two BOMs, or invalid UTF-8 after a BOM -> exit 1" (the package file is the
    subject, D-055), with an error naming the file."""
    path = data_dir.case_dir / name
    if damage == "two-boms":
        _prefix(path, BOM + BOM)
    else:
        _break_utf8(path)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert any(name in ln for ln in result.error_lines), result.output


@pytest.mark.parametrize("how", ["lookup", "--reference"])
def test_9ac17_reference_with_one_bom_warns_and_keeps_exit_0(data_dir, run_validate, how):
    """#9 AC17: "... and the reference file, saved with a leading UTF-8 BOM: a warning names the
    file, and the exit code equals the code without the BOM" (found by lookup or given)."""
    _prefix(data_dir.reference, BOM)
    args = ["case", data_dir.case_dir]
    if how == "--reference":
        args += ["--reference", data_dir.reference]
    result = run_validate(*args)
    assert result.code == 0, result.output
    assert _bom_warning(result, data_dir.reference.name), result.output


def test_9ac17_reference_subject_with_one_bom_warns_and_exits_0(data_dir, run_validate):
    """#9 AC17 for `scrubgpt-validate reference <file>`: one BOM -> a warning naming the file,
    exit 0 (as without it)."""
    _prefix(data_dir.reference, BOM)
    result = run_validate("reference", data_dir.reference)
    assert result.code == 0, result.output
    assert _bom_warning(result, data_dir.reference.name), result.output


@pytest.mark.parametrize("damage", ["two-boms", "invalid-utf8-after-bom"])
def test_9ac17_reference_subject_damaged_exits_1(data_dir, run_validate, damage):
    """Brief clarification of AC17 (D-055 by role): as the subject of
    `scrubgpt-validate reference <file>`, two BOMs or invalid UTF-8 -> exit 1."""
    if damage == "two-boms":
        _prefix(data_dir.reference, BOM + BOM)
    else:
        _break_utf8(data_dir.reference)
    result = run_validate("reference", data_dir.reference)
    assert result.code == 1, result.output


@pytest.mark.parametrize("how", ["lookup", "--reference"])
@pytest.mark.parametrize("damage", ["two-boms", "invalid-utf8-after-bom"])
def test_9ac17_reference_input_damaged_exits_2(data_dir, run_validate, how, damage):
    """Brief clarification of AC17 (D-055 by role): "as the input that `validate case` reads: an
    invalid reference -> exit 2"."""
    if damage == "two-boms":
        _prefix(data_dir.reference, BOM + BOM)
    else:
        _break_utf8(data_dir.reference)
    args = ["case", data_dir.case_dir]
    if how == "--reference":
        args += ["--reference", data_dir.reference]
    result = run_validate(*args)
    assert result.code == 2, result.output


def test_9ac17_fixtures_are_bom_free_and_give_no_warning(paths, run_validate):
    """#9 decision: "Producers never write a BOM: ... the fixtures stay BOM-free, and the unedited
    fixtures give no warning" (every JSON file under contracts/fixtures/)."""
    with_bom = [
        p.relative_to(paths["fixtures"]).as_posix()
        for p in paths["fixtures"].rglob("*.json")
        if p.read_bytes().startswith(BOM)
    ]
    assert not with_bom, with_bom
    result = run_validate("reference", paths["reference"])
    assert result.code == 0 and result.counts == (0, 0), result.output


# --- AC18: no step ids anywhere -------------------------------------------------------------------


def _strip_step_ids(case_dir: Path, seeds: str) -> None:
    """Remove `timeline.json` and `moments.json`, and every other step id: `metrics.json`
    (`per_step[].step_id`) and the seed records (`step_id` is required in a record)."""
    for name in ("timeline.json", "moments.json", "metrics.json"):
        (case_dir / name).unlink()
    path = case_dir / "seed_records.json"
    if seeds == "missing":
        path.unlink()
    else:
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["records"] = []
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    left = "".join(p.read_text(encoding="utf-8") for p in case_dir.glob("*.json"))
    assert "rarp." not in left, "a step id is left in the package"


def _assert_exit_1_with_no_step_ids_warning(result, *missing: str) -> None:
    assert result.code == 1, result.output
    assert result.code != 2
    for name in missing:
        assert any(name in ln for ln in result.error_lines), result.output
    assert any("no step ids" in ln for ln in result.warning_lines), result.output


@pytest.mark.parametrize("seeds", ["empty", "missing"])
def test_9ac18_no_step_ids_is_exit_1_with_a_warning(data_dir, run_validate, seeds):
    """#9 AC18: "A package whose `timeline.json` and `moments.json` are both missing, with no step
    ids elsewhere: exit 1 (missing required files) plus the no-step-ids warning, never 2"."""
    _strip_step_ids(data_dir.case_dir, seeds)
    result = run_validate("case", data_dir.case_dir)
    _assert_exit_1_with_no_step_ids_warning(result, "timeline.json", "moments.json")


def test_9ac18_no_reference_on_disk_is_still_not_exit_2(tmp_path, paths, run_validate, monkeypatch):
    """#9 decision: "a reference that isn't needed can't be 'not found'": the same package in a
    folder with no `reference/` next to it (and no `DATA_DIR`) still exits 1, not 2."""
    monkeypatch.delenv("DATA_DIR", raising=False)
    case_dir = tmp_path / "lonely" / "cases" / CASE_ID
    shutil.copytree(paths["case"], case_dir)
    _strip_step_ids(case_dir, "empty")
    assert not (tmp_path / "lonely" / "reference").exists()
    result = run_validate("case", case_dir)
    _assert_exit_1_with_no_step_ids_warning(result, "timeline.json", "moments.json")


def test_9ac18_missing_reference_option_is_exit_2(data_dir, run_validate, tmp_path):
    """#9 AC18: "The same package with `--reference <missing path>` -> exit 2"."""
    _strip_step_ids(data_dir.case_dir, "empty")
    missing = tmp_path / "nowhere" / "rarp.json"
    result = run_validate("case", data_dir.case_dir, "--reference", missing)
    assert result.code == 2, result.output


def test_9ac18_invalid_reference_option_is_exit_2(data_dir, run_validate, tmp_path):
    """#9 decision: "If `--reference` is given, the file is still read and validated as an input
    under D-055 (exit 2 if it's missing or invalid)"."""
    _strip_step_ids(data_dir.case_dir, "empty")
    bad = tmp_path / "bad-reference.json"
    bad.write_text("{ not json", encoding="utf-8")
    result = run_validate("case", data_dir.case_dir, "--reference", bad)
    assert result.code == 2, result.output


def test_9ac18_valid_reference_option_keeps_exit_1(data_dir, run_validate):
    """#9 decision: "Other errors in the run keep their exit code": a valid `--reference` with
    the step-less package still exits 1 (the missing required files)."""
    _strip_step_ids(data_dir.case_dir, "empty")
    result = run_validate("case", data_dir.case_dir, "--reference", data_dir.reference)
    assert result.code == 1, result.output
    assert any("timeline.json" in ln for ln in result.error_lines), result.output
