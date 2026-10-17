"""B4 Case registry: criteria B4-1 to B4-4 of the T1 brief at 5a89091 (plan §2.2 B4, §4.2
`case.json`; D-049; brain/CLAUDE.md rule 4; brain/README.md "B4 Case registry"; the CLI
docstring).

Expected behaviour, written from the spec before the code was opened:
- The registry is a YAML list, one entry per case with the `case.json` fields except
  `duration_s` and `status` (README). `build_case(entry, duration_s)` gives the contract `Case`;
  `register_case(registry, case_id, video, out_dir)` (CLI `scrubgpt-brain case <registry.yaml>
  <case_id> <video.mp4> <out_dir>`) measures `duration_s` from the video and writes
  `out_dir/case.json` atomically.
- B4-1: an entry plus a duration gives a contract-valid `Case` with plan §4.2's fields,
  `status: partial`, `contract_version` "1.0", the entry's values; with no `data_note`, the
  source's documented default note (README: e.g. "public YouTube video, private internal demo use
  only"; `DEFAULT_DATA_NOTES` in `pipeline.cases`), both halves non-empty.
- B4-2: an invalid entry raises `RegistryError` naming the case id and the field: `language: none`
  with `narrated: true` (D-049), an id outside the case-id format, an empty title half, an unknown
  `source`, and other values the contract rejects.
- B4-3: registry problems are all listed in one `RegistryError`: a duplicate id, an unknown field,
  an entry without an id; a file that isn't a YAML list is an error too.
- B4-4: `register_case` and the CLI measure `duration_s` from the given video (±0.2 s) and write
  `case.json` atomically into the given folder (no `.part` or other temporary file left, other
  files untouched); a failed registration leaves an earlier `case.json` as it was. An unknown case
  id exits 1 with `scrubgpt-brain: error: …` on stderr.

All registries and videos are synthetic, in `tmp_path` (D-036); the video tests skip without
FFmpeg.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml
from scrubgpt_brain.pipeline import cases
from scrubgpt_contracts.models.case_package import Case

CASE_KEYS = {
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
}  # fmt: skip  (plan §4.2 case.json)

ENTRIES = [
    {
        "id": "yt-ja-01",
        "title": {"ja": "ロボット支援前立腺全摘除術 解説", "en": "RARP with commentary"},
        "source": "youtube",
        "source_url": "https://www.youtube.com/watch?v=t1synthetic",
        "language": "ja",
        "video_type": "edited",
        "narrated": True,
        "synthetic_speech": False,
        "default_step_track": "ai",
        "data_note": {"ja": "T1のテスト用メモ", "en": "A T1 test note"},
    },
    {
        "id": "grasp-01",
        "title": {"ja": "GraSP 症例1", "en": "GraSP case 1"},
        "source": "grasp",
        "source_url": None,
        "language": "none",
        "video_type": "full",
        "narrated": False,
        "synthetic_speech": False,
        "default_step_track": "dataset",
    },
    {
        "id": "yt-en-02",
        "title": {"ja": "【要翻訳】RARP full", "en": "RARP full"},
        "source": "youtube",
        "source_url": "https://www.youtube.com/watch?v=t1synthetic2",
        "language": "en",
        "video_type": "full",
        "narrated": False,
        "synthetic_speech": False,
        "default_step_track": "ai",
    },
    {
        "id": "psi-ava-01",
        "title": {"ja": "PSI-AVA 症例", "en": "PSI-AVA case"},
        "source": "psi-ava",
        "source_url": None,
        "language": "none",
        "video_type": "full",
        "narrated": False,
        "synthetic_speech": False,
        "default_step_track": "dataset",
    },
    {
        "id": "synthetic-01",
        "title": {"ja": "合成症例", "en": "Synthetic case"},
        "source": "synthetic",
        "source_url": None,
        "language": "en",
        "video_type": "full",
        "narrated": True,
        "synthetic_speech": True,
        "default_step_track": "ai",
    },
]


def _entry(case_id: str) -> dict:
    return copy.deepcopy(next(e for e in ENTRIES if e["id"] == case_id))


def _write_registry(path: Path, entries) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(entries, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _lines(error: BaseException) -> list[str]:
    return [line for line in str(error).splitlines() if line.strip()]


def _files(folder: Path) -> dict[str, bytes]:
    if not folder.exists():
        return {}
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


# ── B4-1 ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("case_id", [e["id"] for e in ENTRIES])
def test_b4_1_an_entry_and_a_duration_give_a_contract_valid_partial_case(case_id):
    """B4-1 "A registry entry plus a duration gives a contract-valid `Case` (plan §4.2 fields),
    with `status: partial`" (README: B4 adds `duration_s` and `status` (`partial` until the
    package is complete) and validates with the contract's `Case`)."""
    entry = _entry(case_id)
    case = cases.build_case(entry, 1234.5)
    dumped = json.loads(case.model_dump_json())
    assert set(dumped) == CASE_KEYS
    Case.model_validate(dumped)
    assert dumped["contract_version"] == "1.0"
    assert dumped["status"] == "partial"
    assert dumped["duration_s"] == 1234.5
    for key, value in entry.items():
        assert dumped[key] == value, key


@pytest.mark.parametrize("source", ["youtube", "grasp", "psi-ava", "synthetic"])
def test_b4_1_no_data_note_gives_the_sources_default_note(source):
    """B4-1 "With no `data_note`, the source's documented default note is used" (README: "A
    missing `data_note` gets the source's default note"; `DEFAULT_DATA_NOTES`): bilingual, both
    halves non-empty, one per source."""
    entry = next(_entry(e["id"]) for e in ENTRIES if e["source"] == source)
    entry.pop("data_note", None)
    note = cases.build_case(entry, 60.0).data_note
    assert note.ja.strip() and note.en.strip()
    assert (note.ja, note.en) == (
        cases.DEFAULT_DATA_NOTES[source]["ja"],
        cases.DEFAULT_DATA_NOTES[source]["en"],
    )
    notes = {s: cases.DEFAULT_DATA_NOTES[s]["en"] for s in ("youtube", "grasp", "psi-ava")}
    assert len(set(notes.values())) == 3, "the sources share one default note"


def test_b4_1_the_youtube_default_note_is_the_documented_one():
    """README: "e.g. "public YouTube video, private internal demo use only"": the YouTube default
    says both things."""
    entry = _entry("yt-en-02")
    note = cases.build_case(entry, 60.0).data_note.en.lower()
    assert "public youtube video" in note and "internal demo use only" in note, note


def test_b4_1_a_given_data_note_is_kept(tmp_path):
    """B4-1, the other way round: an entry's own `data_note` is used as it is."""
    entry = _entry("yt-ja-01")
    note = cases.build_case(entry, 60.0).data_note
    assert (note.ja, note.en) == (entry["data_note"]["ja"], entry["data_note"]["en"])


def test_b4_1_load_registry_returns_the_entries_by_id(tmp_path):
    """README "one registry, a YAML list with one entry per case": `load_registry` reads a valid
    registry into its entries, by case id."""
    registry = _write_registry(tmp_path / "registry.yaml", ENTRIES)
    loaded = cases.load_registry(registry)
    assert sorted(loaded) == sorted(e["id"] for e in ENTRIES)
    for entry in ENTRIES:
        for key, value in entry.items():
            assert loaded[entry["id"]][key] == value, (entry["id"], key)


# ── B4-2 ─────────────────────────────────────────────────────────────────────


def _bad_entry(how: str) -> tuple[dict, str, tuple[str, ...]]:
    """(entry, the id the error must name, fields of which one must be named)."""
    entry = _entry("yt-ja-01")
    if how == "none-but-narrated":
        entry.update(language="none", narrated=True)
        return entry, entry["id"], ("narrated", "language")
    if how == "none-but-synthetic-speech":
        entry.update(language="none", narrated=False, synthetic_speech=True)
        return entry, entry["id"], ("synthetic_speech", "language")
    if how == "id-format":
        entry["id"] = "YT_JA_01"
        return entry, "YT_JA_01", ("id",)
    if how == "empty-title-half":
        entry["title"]["en"] = "  "
        return entry, entry["id"], ("title",)
    if how == "missing-title-half":
        del entry["title"]["ja"]
        return entry, entry["id"], ("title",)
    if how == "unknown-source":
        entry["source"] = "vimeo"
        return entry, entry["id"], ("source",)
    if how == "bad-language":
        entry["language"] = "de"
        return entry, entry["id"], ("language",)
    if how == "bad-video-type":
        entry["video_type"] = "short"
        return entry, entry["id"], ("video_type",)
    if how == "narrated-not-a-bool":
        entry["narrated"] = "yes"
        return entry, entry["id"], ("narrated",)
    if how == "bad-step-track":
        entry["default_step_track"] = "human"
        return entry, entry["id"], ("default_step_track",)
    if how == "missing-video-type":
        del entry["video_type"]
        return entry, entry["id"], ("video_type",)
    raise ValueError(how)


BAD = [
    "none-but-narrated", "none-but-synthetic-speech", "id-format", "empty-title-half",
    "missing-title-half", "unknown-source", "bad-language", "bad-video-type",
    "narrated-not-a-bool", "bad-step-track", "missing-video-type",
]  # fmt: skip


@pytest.mark.parametrize("how", BAD)
def test_b4_2_an_invalid_entry_raises_registry_error_naming_case_and_field(how):
    """B4-2 "An invalid entry raises `RegistryError` naming the case id and the field. Examples:
    `language: none` with `narrated: true` (D-049), an id outside the case-id format, an empty
    title half, an unknown `source`" (README: "listing each one with the case id and field"). One
    line of the error names both."""
    entry, case_id, fields = _bad_entry(how)
    with pytest.raises(cases.RegistryError) as caught:
        cases.build_case(entry, 60.0)
    lines = _lines(caught.value)
    assert any(case_id in line and any(f in line for f in fields) for line in lines), (
        f"no line names {case_id!r} and one of {fields}:\n{caught.value}"
    )
    assert caught.value.problems, "RegistryError.problems is empty"


def test_b4_2_a_duration_that_isnt_positive_is_rejected():
    """D-049 "`case.json`: `duration_s` > 0": a zero duration is no valid case (a `ValueError`,
    which `RegistryError` is)."""
    with pytest.raises(ValueError):
        cases.build_case(_entry("yt-en-02"), 0.0)


def test_b4_2_several_bad_fields_are_all_named():
    """README "listing each one": an entry with a bad source and an empty title half names both
    fields."""
    entry = _entry("yt-en-02")
    entry["source"] = "vimeo"
    entry["title"]["ja"] = ""
    with pytest.raises(cases.RegistryError) as caught:
        cases.build_case(entry, 60.0)
    text = str(caught.value)
    assert "source" in text and "title" in text, text


# ── B4-3 ─────────────────────────────────────────────────────────────────────


def test_b4_3_registry_problems_are_all_listed(tmp_path):
    """B4-3 "Registry problems are all listed: a duplicate id, an unknown field, an entry without
    an id" (README "Registry problems raise `RegistryError`, listing each one with the case id and
    field: a duplicate id, an unknown field, …"): one registry with all three gives one error that
    names the duplicated id, the unknown field (with its case) and the entry without an id."""
    duplicate = _entry("grasp-01")
    unknown = _entry("yt-en-02")
    unknown["t1_unknown_field"] = 1
    no_id = _entry("synthetic-01")
    del no_id["id"]
    registry = _write_registry(
        tmp_path / "registry.yaml", [_entry("grasp-01"), duplicate, unknown, no_id]
    )
    with pytest.raises(cases.RegistryError) as caught:
        cases.load_registry(registry)
    lines = _lines(caught.value)
    assert any("grasp-01" in line for line in lines), str(caught.value)
    assert any("yt-en-02" in line and "t1_unknown_field" in line for line in lines), str(
        caught.value
    )
    assert any("id" in line and "grasp-01" not in line and "yt-en-02" not in line for line in lines)
    assert len(caught.value.problems) >= 3, caught.value.problems


@pytest.mark.parametrize("content", ["mapping", "scalar", "list-of-strings", "not-yaml", "empty"])
def test_b4_3_a_file_that_isnt_a_yaml_list_of_entries_is_an_error(tmp_path, content):
    """B4-3 "… a file that isn't a YAML list" raises `RegistryError` (README: the registry is "a
    YAML list with one entry per case"), as does a list whose items aren't entries, a file that
    isn't YAML and an empty file."""
    path = tmp_path / "registry.yaml"
    text = {
        "mapping": yaml.safe_dump({"yt-ja-01": _entry("yt-ja-01")}, allow_unicode=True),
        "scalar": "just a string\n",
        "list-of-strings": "- yt-ja-01\n- grasp-01\n",
        "not-yaml": "- id: [unclosed\n",
        "empty": "",
    }[content]
    path.write_text(text, encoding="utf-8")
    with pytest.raises(cases.RegistryError):
        cases.load_registry(path)


def test_b4_3_a_missing_registry_is_an_error(tmp_path):
    """README "Registry problems raise `RegistryError`": a registry file that doesn't exist."""
    with pytest.raises(cases.RegistryError):
        cases.load_registry(tmp_path / "nope.yaml")


# ── B4-4 (FFmpeg) ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def video(media, tmp_path_factory) -> Path:
    """A 12.4 s synthetic video (`testsrc2` + a tone), like B3's output."""
    return media.make_video(tmp_path_factory.mktemp("b4video") / "video.mp4", 12.4)


@pytest.fixture
def registry(tmp_path) -> Path:
    return _write_registry(tmp_path / "data" / "registry.yaml", ENTRIES)


def test_b4_4_register_case_measures_the_duration_and_writes_case_json(registry, video, tmp_path):
    """B4-4 "`register_case` … measure `duration_s` from the given video (±0.2 s) and write
    `case.json` atomically into the given folder (no `.part` left)" (README: written "into the
    folder it is given, normally `<DATA_DIR>/work/<case_id>/`"). The file is the contract `Case`
    of the entry with that duration, and the folder holds nothing else."""
    out = tmp_path / "data" / "work" / "yt-ja-01"
    path = cases.register_case(registry, "yt-ja-01", video, out)
    assert path == out / "case.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == CASE_KEYS
    case = Case.model_validate(data)
    assert abs(case.duration_s - 12.4) <= 0.2, case.duration_s
    assert data == json.loads(
        cases.build_case(_entry("yt-ja-01"), case.duration_s).model_dump_json()
    )
    assert set(_files(out)) == {"case.json"}
    assert set(_files(registry.parent)) == {"registry.yaml", "work/yt-ja-01/case.json"}


def test_b4_4_a_rewrite_replaces_case_json_and_leaves_other_files(registry, video, tmp_path):
    """B4-4 "write `case.json` atomically … (no `.part` left)": a second registration replaces
    `case.json` (here after the registry entry changed) and leaves other files in the folder."""
    out = tmp_path / "work"
    cases.register_case(registry, "yt-en-02", video, out)
    (out / "notes.txt").write_text("keep", encoding="utf-8")
    entries = [*ENTRIES]
    entries[2] = {**_entry("yt-en-02"), "video_type": "edited"}
    _write_registry(registry, entries)
    cases.register_case(registry, "yt-en-02", video, out)
    assert set(_files(out)) == {"case.json", "notes.txt"}
    assert json.loads((out / "case.json").read_text(encoding="utf-8"))["video_type"] == "edited"


def test_b4_4_a_failed_registration_keeps_the_earlier_case_json(registry, video, tmp_path):
    """B4-4 atomic write (README: B4 "validates the result … and writes it atomically"): when the
    entry has become invalid, `register_case` raises `RegistryError` and the earlier `case.json` is
    byte for byte as it was, with no temporary file left."""
    out = tmp_path / "work"
    cases.register_case(registry, "grasp-01", video, out)
    before = _files(out)
    entries = [*ENTRIES]
    entries[1] = {**_entry("grasp-01"), "narrated": True}  # language none (D-049)
    _write_registry(registry, entries)
    with pytest.raises(cases.RegistryError) as caught:
        cases.register_case(registry, "grasp-01", video, out)
    assert "grasp-01" in str(caught.value)
    assert _files(out) == before


def test_b4_4_the_cli_writes_case_json(media, registry, video, tmp_path):
    """B4-4 "… and the CLI measure `duration_s` …" (README: `scrubgpt-brain case <registry.yaml>
    <case_id> <video.mp4> <out_dir>`): exit 0, a result on stdout, nothing on stderr, and the same
    `case.json` as `register_case`."""
    out = tmp_path / "cli"
    result = media.run_cli("case", str(registry), "synthetic-01", str(video), str(out))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() and not result.stderr.strip(), (result.stdout, result.stderr)
    expected = cases.register_case(registry, "synthetic-01", video, tmp_path / "py")
    assert json.loads((out / "case.json").read_text(encoding="utf-8")) == json.loads(
        expected.read_text(encoding="utf-8")
    )
    assert set(_files(out)) == {"case.json"}


def test_b4_4_an_unknown_case_id_exits_1_on_stderr(media, registry, video, tmp_path):
    """B4-4 "An unknown case id exits 1, with the message on stderr": `scrubgpt-brain case` for an
    id the registry lacks; the message names the id, stdout is empty and nothing is written."""
    out = tmp_path / "out"
    result = media.run_cli("case", str(registry), "yt-ja-99", str(video), str(out))
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert "scrubgpt-brain: error:" in result.stderr and "yt-ja-99" in result.stderr, result.stderr
    assert not result.stdout.strip()
    assert _files(out) == {}


def test_b4_4_an_unknown_case_id_raises_registry_error(registry, video, tmp_path):
    """B4-4 in Python: `register_case` for an id the registry lacks raises `RegistryError` naming
    it, and writes nothing."""
    with pytest.raises(cases.RegistryError) as caught:
        cases.register_case(registry, "yt-ja-99", video, tmp_path / "out")
    assert "yt-ja-99" in str(caught.value)
    assert not (tmp_path / "out" / "case.json").exists()


@pytest.mark.parametrize("bad", ["missing", "not-a-video"])
def test_b4_4_a_missing_or_non_video_input_exits_1(media, registry, tmp_path, bad):
    """CLI docstring "1 = the input is missing, isn't a video, …" for `case`: exit 1 with
    `scrubgpt-brain: error: …` on stderr, nothing on stdout, no `case.json`."""
    video = tmp_path / "video.mp4"
    if bad == "not-a-video":
        video.write_text("not a video\n", encoding="utf-8")
    out = tmp_path / "out"
    result = media.run_cli("case", str(registry), "yt-ja-01", str(video), str(out))
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert "scrubgpt-brain: error:" in result.stderr, result.stderr
    assert not result.stdout.strip()
    assert not (out / "case.json").exists()
