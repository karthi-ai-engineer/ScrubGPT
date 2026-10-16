"""AC13-AC14: the fixture case `case-fixture-01` and the fixture reference `rarp.json`
(plan §4.2, §4.2b, §4.5, Appendix A; D-026, D-035, D-036; CLAUDE.md product guardrails)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any

import pytest
from scrubgpt_contracts.models.case_package import (
    Case,
    Moments,
    Questions,
    SeedRecords,
    Timeline,
)
from scrubgpt_contracts.models.reference import ProcedureReference

CASE_ID = "case-fixture-01"
FAMILIES = {
    "bleeding",
    "anatomical_variation",
    "tissue_condition",
    "visibility",
    "technical_difficulty",
    "equipment",
    "patient_condition",
    "unexpected_finding",
}
HUMAN_READABLE_KEYS = {
    "title",
    "data_note",
    "text",
    "detail",
    "deep_look",
    "label",
    "name",
    "ai_draft",
    "option",
    "why_not",
    "reason",
    "immediate_result",
    "anticipation",
    "preop_plan",
}


def _is_bilingual(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("ja"), str)
        and isinstance(value.get("en"), str)
        and value["ja"].strip() != ""
        and value["en"].strip() != ""
    )


def _walk(node: Any, where: str = "$"):
    yield where, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{where}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk(value, f"{where}[{i}]")


# --- AC13: case-fixture-01 ----------------------------------------------------------------


def test_ac13_every_required_file_present(paths):
    """AC13: "every required file of §4.2" (case.json, video.mp4, poster.jpg, timeline.json,
    moments.json, questions.json, clips/, seed_records.json)."""
    case = paths["case"]
    for name in ("case.json", "video.mp4", "poster.jpg", "timeline.json", "moments.json"):
        assert (case / name).is_file(), name
    for name in ("questions.json", "seed_records.json"):
        assert (case / name).is_file(), name
    assert (case / "clips").is_dir()


def test_ac13_every_json_file_validates_against_its_model(docs):
    """AC13 / Definition of Done: the fixture validates against the contracts."""
    assert Case.model_validate(docs["case.json"]).id == CASE_ID
    for name, model in (
        ("timeline.json", Timeline),
        ("moments.json", Moments),
        ("questions.json", Questions),
        ("seed_records.json", SeedRecords),
    ):
        assert model.model_validate(docs[name]).case_id == CASE_ID, name


def test_ac13_six_moments_each_with_clip_and_poster(paths, docs):
    """AC13: "6 moments m01...m06, each with a clip and a poster" (plan §4.5, D-026)."""
    ids = [m["id"] for m in docs["moments.json"]["moments"]]
    assert sorted(ids) == [f"{CASE_ID}.m0{i}" for i in range(1, 7)]
    for m in docs["moments.json"]["moments"]:
        clip = paths["case"] / m["clip"]
        poster = paths["case"] / m["poster"]
        assert clip.is_file() and clip.name == f"{m['id']}.mp4", clip
        assert poster.is_file() and poster.name == f"{m['id']}.jpg", poster
        assert clip.read_bytes()[4:8] == b"ftyp", f"{clip} is not an MP4"
        assert poster.read_bytes()[:3] == b"\xff\xd8\xff", f"{poster} is not a JPEG"


def test_ac13_operating_and_reviewer_questions(docs):
    """AC13: "operating and reviewer questions" (plan §4.5: `case-fixture-01.m01.q1` ...
    operating and `case-fixture-01.m01.r1` ... reviewer); every question points to a fixture
    moment."""
    q = docs["questions.json"]
    assert q["operating"] and q["reviewer"]
    op_ids = {x["id"] for x in q["operating"]}
    rv_ids = {x["id"] for x in q["reviewer"]}
    assert f"{CASE_ID}.m01.q1" in op_ids
    assert f"{CASE_ID}.m01.r1" in rv_ids
    moments = {m["id"] for m in docs["moments.json"]["moments"]}
    for x in q["operating"] + q["reviewer"]:
        assert x["moment_id"] in moments, x["id"]


def test_ac13_five_seed_records_labelled_simulated(docs):
    """AC13: "5 seed records labelled `simulated`" (plan §4.5; CLAUDE.md: role-played content
    is always labelled simulated)."""
    records = docs["seed_records.json"]["records"]
    assert len(records) == 5
    assert [r["provenance"]["trust_label"] for r in records] == ["simulated"] * 5


def test_ac13_fixtures_folder_at_most_5_mb(paths):
    """AC13: "`contracts/fixtures/` <= 5 MB (D-036)"."""
    total = sum(p.stat().st_size for p in paths["fixtures"].rglob("*") if p.is_file())
    assert total <= 5 * 1000 * 1000, f"contracts/fixtures/ is {total} bytes"


def test_ac13_media_is_synthetic(paths, docs):
    """AC13: "synthetic media only" (D-036): the case is declared `source: synthetic`, and the
    video matches the D-036 recipe (426x240 at 5 fps, 300 s, same as `duration_s`)."""
    assert docs["case.json"]["source"] == "synthetic"
    assert "synthetic" in docs["case.json"]["data_note"]["en"].lower()
    assert (paths["case"] / "poster.jpg").read_bytes()[:3] == b"\xff\xd8\xff"
    assert (paths["case"] / "video.mp4").read_bytes()[4:8] == b"ftyp"
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        pytest.skip("ffprobe not installed: video properties not checked")
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate:format=duration",
            "-of",
            "json",
            str(paths["case"] / "video.mp4"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    info = json.loads(proc.stdout)
    stream = info["streams"][0]
    assert (stream["width"], stream["height"]) == (426, 240)
    assert stream["r_frame_rate"] == "5/1"
    duration = float(info["format"]["duration"])
    assert abs(duration - 300.0) <= 1.0
    assert abs(duration - docs["case.json"]["duration_s"]) <= 1.0


def test_ac13_every_human_readable_field_bilingual(docs):
    """AC13: "every human-readable field bilingual" (CLAUDE.md Conventions: both halves
    non-empty; no English-only content)."""
    problems = []
    for name in ("case.json", "timeline.json", "moments.json", "questions.json"):
        for where, node in _walk(docs[name], name):
            if isinstance(node, dict):
                if ("ja" in node or "en" in node) and not _is_bilingual(node):
                    problems.append(f"{where}: half-filled Bilingual {node}")
                for key in HUMAN_READABLE_KEYS & set(node):
                    if node[key] is not None and not _is_bilingual(node[key]):
                        problems.append(f"{where}.{key}: not Bilingual")
    for where, node in _walk(docs["seed_records.json"], "seed_records.json"):
        if isinstance(node, dict):
            if ("ja" in node or "en" in node) and not _is_bilingual(node):
                problems.append(f"{where}: half-filled Bilingual {node}")
            for key in (HUMAN_READABLE_KEYS - {"name", "label"}) & set(node):
                if node[key] is not None and not _is_bilingual(node[key]):
                    problems.append(f"{where}.{key}: not Bilingual")
            if "patient_factors" in node:
                for i, pf in enumerate(node["patient_factors"]):
                    if not _is_bilingual(pf):
                        problems.append(f"{where}.patient_factors[{i}]: not Bilingual")
    assert not problems, "\n".join(problems)


def _filled_paths(record: dict[str, Any]) -> list[str]:
    """The surgeon-content fields of §4.3 that carry a value in this record."""
    out = []
    for i, _ in enumerate(record["context"]["patient_factors"]):
        out.append(f"context.patient_factors[{i}]")
    if record["context"]["preop_plan"] is not None:
        out.append("context.preop_plan")
    out.append("situation_cue.text")
    if record["obstacle"] is not None:
        out.append("obstacle")
    for key in ("anticipation", "reason", "immediate_result"):
        if record[key] is not None:
            out.append(key)
    out.append("action.text")
    for i, alt in enumerate(record["alternatives"]):
        out.append(f"alternatives[{i}].option")
        if alt["why_not"] is not None:
            out.append(f"alternatives[{i}].why_not")
    if record["delayed_outcome"]["text"] is not None:
        out.append("delayed_outcome.text")
    return out


def _covers(grounded: str, path: str) -> bool:
    return (
        grounded == path
        or grounded.startswith((path + ".", path + "["))
        or path.startswith((grounded + ".", grounded + "["))
    )


def test_ac13_every_filled_record_field_grounded(docs):
    """AC13: "every filled record field grounded" (plan §4.3 grounding[]: "every filled field
    points to the words that support it" (G5); CLAUDE.md: never invent reasoning)."""
    problems = []
    for record in docs["seed_records.json"]["records"]:
        grounded = [g["field"] for g in record["grounding"]]
        for path in _filled_paths(record):
            if not any(_covers(g, path) for g in grounded):
                problems.append(f"{record['id']}: {path} has no grounding")
    assert not problems, "\n".join(problems)


def test_ac13_answer_grounding_quotes_are_verbatim(docs):
    """AC13 + #3 point 1: grounding quotes are the surgeon's verbatim words; a quote with
    `source: answer` appears word for word in the record's answer text evidence."""
    problems = []
    for record in docs["seed_records.json"]["records"]:
        answers = [e["quote"] for e in record["evidence"] if e["kind"] == "answer_text"]
        if not answers:
            continue
        for g in record["grounding"]:
            if g["source"] == "answer" and not any(g["quote"] in a for a in answers):
                problems.append(f"{record['id']}: {g['field']} quote {g['quote']!r} not verbatim")
    assert not problems, "\n".join(problems)


AVOIDANCE = re.compile(
    r"avoid|prevent|could (this|it|you) have been|should have|防げ|避けられ|回避でき|予防でき",
    re.IGNORECASE,
)


def test_ac13_no_could_this_have_been_avoided_questions(docs):
    """AC13: "no 'could this have been avoided?' questions" (CLAUDE.md product guardrails;
    D-027: no "prevention" question)."""
    q = docs["questions.json"]
    hits = []
    for x in q["operating"] + q["reviewer"]:
        texts = [x["text"]["ja"], x["text"]["en"]]
        if x["ai_draft"]:
            texts += [x["ai_draft"]["ja"], x["ai_draft"]["en"]]
        texts += [t["label"][lang] for t in x["tap_options"] for lang in ("ja", "en")]
        hits += [f"{x['id']}: {t}" for t in texts if AVOIDANCE.search(t)]
    assert not hits, "\n".join(hits)


def test_ac13_validate_case_passes_on_the_fixture(paths, run_validate, monkeypatch):
    """AC13: "`scrubgpt-validate case` passes on it" (DATA_DIR=./contracts/fixtures, D-026)."""
    monkeypatch.setenv("DATA_DIR", str(paths["fixtures"]))
    result = run_validate("case", paths["case"])
    assert result.code == 0, result.output


def test_ac13_validate_case_cli_passes_on_the_fixture(paths, monkeypatch):
    """AC13: the installed console script, as in the brief:
    `uv run scrubgpt-validate case contracts/fixtures/cases/case-fixture-01`."""
    monkeypatch.setenv("DATA_DIR", "./contracts/fixtures")
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


# --- AC14: rarp.json ----------------------------------------------------------------------

APPENDIX_A = {
    1: ("port", "ポート"),
    2: ("lymph node", "リンパ節"),
    3: ("retzius", "レチウス"),
    4: ("dvc", "dvc"),
    5: ("anterior bladder neck", "膀胱頸部前壁"),
    6: ("posterior bladder neck", "膀胱頸部後壁"),
    7: ("seminal vesicle", "精嚢"),
    8: ("denonvilliers", "デノンビリエ"),
    9: ("nerve sparing", "神経温存"),
    10: ("apical", "尖部"),
    11: ("posterior reconstruction", "後壁再建"),
    12: ("vesicourethral anastomosis", "吻合"),
    13: ("closure", "閉創"),
}
APPENDIX_A_WITH_CHECKPOINT = {2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13}


def test_ac14_phases_p01_to_p13(docs):
    """AC14: "phases rarp.p01...p13 (Appendix A)" in order."""
    ref = ProcedureReference.model_validate(docs["rarp.json"]).model_dump(mode="json")
    assert ref["id"] == "rarp"
    assert [p["id"] for p in ref["phases"]] == [f"rarp.p{i:02d}" for i in range(1, 14)]
    assert [p["order"] for p in ref["phases"]] == list(range(1, 14))


def test_ac14_phase_names_follow_appendix_a(docs):
    """AC14: phase names follow Appendix A (EN and 日本語)."""
    problems = []
    for phase in docs["rarp.json"]["phases"]:
        n = int(phase["id"].split(".p")[1])
        en_kw, ja_kw = APPENDIX_A[n]
        if en_kw not in phase["name"]["en"].lower():
            problems.append(f"{phase['id']} en {phase['name']['en']!r} lacks {en_kw!r}")
        if ja_kw not in phase["name"]["ja"].lower():
            problems.append(f"{phase['id']} ja {phase['name']['ja']!r} lacks {ja_kw!r}")
    assert not problems, "\n".join(problems)


def test_ac14_steps_and_checkpoints(docs):
    """AC14: "steps and checkpoints": every phase has steps; every Appendix A phase with a
    checkpoint has at least one (checkpoints belong to steps, §4.2b)."""
    for phase in docs["rarp.json"]["phases"]:
        assert phase["steps"], phase["id"]
        n = int(phase["id"].split(".p")[1])
        checkpoints = [c for s in phase["steps"] for c in s["checkpoints"]]
        if n in APPENDIX_A_WITH_CHECKPOINT:
            assert checkpoints, f"{phase['id']} has no checkpoint (Appendix A lists one)"


def test_ac14_eight_families_with_leaves(docs):
    """AC14: "the 8 families with leaves" (D-035; §4.2b example
    `anatomical_variation.median_lobe`)."""
    taxonomy = docs["rarp.json"]["obstacle_taxonomy"]
    assert {f["id"] for f in taxonomy} == FAMILIES
    assert len(taxonomy) == 8
    for family in taxonomy:
        assert family["leaves"], f"{family['id']} has no leaves"
        for leaf in family["leaves"]:
            assert leaf["id"].startswith(family["id"] + ".")
    leaves = {leaf["id"] for f in taxonomy for leaf in f["leaves"]}
    assert "anatomical_variation.median_lobe" in leaves


def test_ac14_validate_reference_passes(paths, run_validate):
    """AC14: "`scrubgpt-validate reference` passes on it"."""
    result = run_validate("reference", paths["reference"])
    assert result.code == 0, result.output


def test_ac14_validate_reference_cli_passes(paths):
    """AC14: the installed console script, as in the brief:
    `uv run scrubgpt-validate reference contracts/fixtures/reference/rarp.json`."""
    exe = shutil.which("scrubgpt-validate")
    assert exe
    proc = subprocess.run(
        [exe, "reference", "contracts/fixtures/reference/rarp.json"],
        cwd=paths["repo"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
