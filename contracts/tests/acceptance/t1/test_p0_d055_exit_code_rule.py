"""D-055: the Team Lead's newest ruling on issue #7 ("The rule (refines D-052 §exit codes)").

- **Exit 2:** the run cannot get an **input** it needs: a path given on the command line doesn't
  exist, is a folder where a file is expected, or the OS can't read it; the reference can't be
  found; an input that isn't the subject of the check (the reference) is invalid.
- **Exit 1:** the **subject** of the check was opened and its content is defective: bad
  encoding, broken JSON, a model error, a rule error, or a required file missing **inside** a
  package.
- 2 still wins over 1, and every check that could run is still printed (D-052).

"Acceptance criteria for T1" 3-5 are here (1-2, `live`, are in test_p0_live_fake_brain.py).
Everything runs on copies of `contracts/fixtures/` in `tmp_path`.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from scrubgpt_contracts.models.brain_api import ENDPOINTS

CASE_ID = "case-fixture-01"
PACKAGE_JSON_FILES = [
    "case.json",
    "timeline.json",
    "moments.json",
    "questions.json",
    "seed_records.json",
]
REQUIRED_FILES = ["video.mp4", "poster.jpg", *PACKAGE_JSON_FILES]
# Shift_JIS (a Japanese Windows default) and UTF-16 with a BOM (what PowerShell 5 writes for `>`).
ENCODINGS = ["cp932", "utf-16"]
VALID_TRANSLATE = {"contract_version": "1.0", "items": [{"ja": "出血", "en": "Bleeding"}]}


def _encode_not_utf8(text: str, encoding: str) -> bytes:
    """The same JSON text in another encoding; it must not decode as UTF-8."""
    data = text.encode(encoding, errors="replace")
    with pytest.raises(UnicodeDecodeError):
        data.decode("utf-8")
    return data


def _load(case_dir: Path, name: str):
    return json.loads((case_dir / name).read_text(encoding="utf-8"))


def _save(case_dir: Path, name: str, doc) -> None:
    (case_dir / name).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _break_case_json(case_dir: Path) -> str:
    """A rule error in `case.json` that needs no reference (`language: none` but narrated)."""
    case = _load(case_dir, "case.json")
    case["language"], case["narrated"] = "none", True
    _save(case_dir, "case.json", case)
    return "case.json"


def _break_questions_json(case_dir: Path) -> str:
    """A rule error in `questions.json` that needs no reference (a tap option uses a built-in
    verdict id)."""
    questions = _load(case_dir, "questions.json")
    q = next(q for q in questions["operating"] if q["tap_options"])
    q["tap_options"][0]["id"] = "reject"
    _save(case_dir, "questions.json", questions)
    return "questions.json"


def _assert_named(result, *names: str) -> None:
    for name in names:
        assert name in result.problems, f"{name!r} not reported:\n{result.output}"


@contextlib.contextmanager
def _os_unreadable(path: Path) -> Iterator[None]:
    """Make `path` exist but fail to read at the OS level (permission denied)."""
    if sys.platform == "win32":
        import msvcrt

        size = 1 << 20
        fd = os.open(path, os.O_RDWR)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, size)  # a byte-range lock: reads raise EACCES
        try:
            with pytest.raises(PermissionError):
                path.read_bytes()
            yield
        finally:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, size)
            os.close(fd)
    else:
        mode = path.stat().st_mode
        path.chmod(0)
        try:
            try:
                path.read_bytes()
            except PermissionError:
                pass
            else:
                pytest.skip("file permissions are not enforced for this user (root?)")
            yield
        finally:
            path.chmod(mode)


# --- AC3: `validate case` - defects inside the package are 1, the case path itself is 2 ------


def test_d055_ac3_questions_json_removed_exits_1_naming_it(data_dir, run_validate):
    """D-055 AC3: "`validate case` on a copy of the fixture case with `questions.json` removed ->
    exit 1, and the message names the file"."""
    (data_dir.case_dir / "questions.json").unlink()
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    _assert_named(result, "questions.json")


@pytest.mark.parametrize("encoding", ENCODINGS)
def test_d055_ac3_moments_json_not_utf8_exits_1_naming_it(data_dir, run_validate, encoding):
    """D-055 AC3: "The same holds when `moments.json` is replaced by non-UTF-8 bytes" (exit 1,
    the message names the file)."""
    path = data_dir.case_dir / "moments.json"
    path.write_bytes(_encode_not_utf8(path.read_text(encoding="utf-8"), encoding))
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    _assert_named(result, "moments.json")


def test_d055_ac3_case_path_that_does_not_exist_exits_2(tmp_path, run_validate):
    """D-055 AC3: "A case path that doesn't exist -> exit 2"."""
    result = run_validate("case", tmp_path / "cases" / CASE_ID)
    assert result.code == 2, result.output


def test_d055_ac3_case_path_that_does_not_exist_with_reference_exits_2(
    tmp_path, paths, run_validate
):
    """D-055 AC3: a case path that doesn't exist -> exit 2, also when a valid `--reference` is
    given (the package itself is the missing input)."""
    result = run_validate("case", tmp_path / "nope", "--reference", paths["reference"])
    assert result.code == 2, result.output


def test_d055_rule_case_path_that_is_a_file_exits_2(data_dir, run_validate):
    """D-055 ruling, case 2: "The case directory itself missing, or not a folder, is still exit
    2" (a path on the command line that is a file where a folder is expected)."""
    result = run_validate("case", data_dir.case_dir / "case.json")
    assert result.code == 2, result.output


@pytest.mark.parametrize("encoding", ENCODINGS)
@pytest.mark.parametrize("name", PACKAGE_JSON_FILES)
def test_d055_rule_package_json_not_utf8_exits_1_naming_it(data_dir, run_validate, name, encoding):
    """D-055 ruling, case 2: "A missing or unreadable file inside a case package ... exit 1, as a
    package defect ... The same applies to ... a JSON file that isn't UTF-8" (every JSON file
    of the package, plan §4.2)."""
    path = data_dir.case_dir / name
    path.write_bytes(_encode_not_utf8(path.read_text(encoding="utf-8"), encoding))
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    _assert_named(result, name)


@pytest.mark.parametrize("name", REQUIRED_FILES)
def test_d055_rule_required_file_that_is_a_folder_exits_1_naming_it(data_dir, run_validate, name):
    """D-055 ruling, case 2: "The same applies to a required file that is a folder" (exit 1,
    plan §4.2 Required column)."""
    path = data_dir.case_dir / name
    path.unlink()
    path.mkdir()
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    _assert_named(result, name)


def test_d055_rule_required_clips_folder_that_is_a_file_exits_1_naming_it(data_dir, run_validate):
    """D-055 ruling, case 2 (a required file missing inside a package is 1) with plan §4.2
    (`clips/` is a required folder): a regular file named `clips` leaves the required folder
    missing -> exit 1, naming `clips`."""
    clips = data_dir.case_dir / "clips"
    shutil.rmtree(clips)
    clips.write_bytes(b"not a folder")
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    _assert_named(result, "clips")


def test_d055_rule_package_file_the_os_cannot_read_exits_1_naming_it(data_dir, run_validate):
    """D-055 ruling, case 2: "A missing or unreadable file inside a case package. Confirmed:
    exit 1, as a package defect" (only a path given on the command line is exit 2)."""
    path = data_dir.case_dir / "moments.json"
    with _os_unreadable(path):
        result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    _assert_named(result, "moments.json")


def test_d055_ac3_removed_file_other_checks_still_printed(data_dir, run_validate):
    """D-055: "every check that could run is still printed (D-052)": `questions.json` removed and
    a rule error in `case.json` -> exit 1, both named."""
    (data_dir.case_dir / "questions.json").unlink()
    broken = _break_case_json(data_dir.case_dir)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    _assert_named(result, "questions.json", broken)


@pytest.mark.parametrize("encoding", ENCODINGS)
def test_d055_ac3_not_utf8_file_other_checks_still_printed(data_dir, run_validate, encoding):
    """D-055: "every check that could run is still printed": `moments.json` not UTF-8 plus rule
    errors in `case.json` and `questions.json` -> exit 1, all three named."""
    names = [_break_case_json(data_dir.case_dir), _break_questions_json(data_dir.case_dir)]
    path = data_dir.case_dir / "moments.json"
    path.write_bytes(_encode_not_utf8(path.read_text(encoding="utf-8"), encoding))
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    _assert_named(result, "moments.json", *names)


# --- AC4: an invalid reference is an input problem: exit 2, with its errors printed ----------


def _reference_doc(paths) -> dict:
    return json.loads(paths["reference"].read_text(encoding="utf-8"))


def _invalid_reference_bytes(paths, kind: str) -> bytes:
    if kind == "broken-json":
        return b"{ not json"
    doc = _reference_doc(paths)
    if kind == "fails-model-type":
        doc["phases"] = "none"  # the model error is located at `phases`
    elif kind == "fails-model-rule":
        assert doc["obstacle_taxonomy"][0]["id"] == "bleeding"
        doc["obstacle_taxonomy"] = doc["obstacle_taxonomy"][1:]  # one of the 8 families missing
    else:
        raise AssertionError(kind)
    return json.dumps(doc, ensure_ascii=False).encode("utf-8")


INVALID_REFERENCES = ["broken-json", "fails-model-type", "fails-model-rule"]


def _assert_reference_errors_printed(result, reference: Path, kind: str) -> None:
    """The reference's own errors are printed: the file is named; a model error located at
    `phases` names that field; the missing-family error names the family (`bleeding`, the one
    removed) or `obstacle_taxonomy`."""
    _assert_named(result, reference.name)
    if kind == "fails-model-type":
        _assert_named(result, "phases")
    if kind == "fails-model-rule":
        assert "bleeding" in result.problems or "obstacle_taxonomy" in result.problems, (
            f"the missing obstacle family is not reported:\n{result.output}"
        )


@pytest.mark.parametrize("kind", INVALID_REFERENCES)
def test_d055_ac4_invalid_reference_option_exits_2_with_its_errors(
    data_dir, tmp_path, paths, run_validate, kind
):
    """D-055 AC4: "`validate case --reference <broken JSON>`, and `--reference <file that fails
    ProcedureReference>` -> exit 2, with the reference errors printed". A valid reference sits
    at the lookup path, so `case` must not fall back to it."""
    bad = tmp_path / "ref" / "bad-reference.json"
    bad.parent.mkdir()
    bad.write_bytes(_invalid_reference_bytes(paths, kind))
    result = run_validate("case", data_dir.case_dir, "--reference", bad)
    assert result.code == 2, result.output
    _assert_reference_errors_printed(result, bad, kind)


@pytest.mark.parametrize("kind", INVALID_REFERENCES)
def test_d055_ac4_invalid_reference_found_by_lookup_exits_2_with_its_errors(
    data_dir, paths, run_validate, kind
):
    """D-055 AC4: "The same holds with the invalid reference placed at `../../reference/
    <prefix>.json` and no `--reference`" (exit 2, the reference errors printed)."""
    data_dir.reference.write_bytes(_invalid_reference_bytes(paths, kind))
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 2, result.output
    _assert_reference_errors_printed(result, data_dir.reference, kind)


@pytest.mark.parametrize("kind", INVALID_REFERENCES)
@pytest.mark.parametrize("via", ["option", "lookup"])
def test_d055_ac4_package_errors_still_printed_and_exit_2(
    data_dir, tmp_path, paths, run_validate, via, kind
):
    """D-055 AC4: "Package errors found alongside are still printed, and the exit code is 2"
    ("The checks that don't need the reference still run and print")."""
    names = [_break_case_json(data_dir.case_dir), _break_questions_json(data_dir.case_dir)]
    if via == "option":
        bad = tmp_path / "ref" / "bad-reference.json"
        bad.parent.mkdir()
        bad.write_bytes(_invalid_reference_bytes(paths, kind))
        result = run_validate("case", data_dir.case_dir, "--reference", bad)
    else:
        bad = data_dir.reference
        bad.write_bytes(_invalid_reference_bytes(paths, kind))
        result = run_validate("case", data_dir.case_dir)
    assert result.code == 2, result.output
    _assert_named(result, *names)
    _assert_reference_errors_printed(result, bad, kind)


@pytest.mark.parametrize("encoding", ENCODINGS)
@pytest.mark.parametrize("via", ["option", "lookup"])
def test_d055_rule_reference_not_utf8_with_case_exits_2(
    data_dir, tmp_path, paths, run_validate, via, encoding
):
    """D-055 rule: "Exit 2: ... an input that isn't the subject of the check (the reference) is
    invalid" ("The reference is an input however it was found"): a reference that isn't UTF-8
    makes `validate case` exit 2 and is named."""
    data = _encode_not_utf8(paths["reference"].read_text(encoding="utf-8"), encoding)
    if via == "option":
        bad = tmp_path / "ref" / "bad-reference.json"
        bad.parent.mkdir()
        bad.write_bytes(data)
        result = run_validate("case", data_dir.case_dir, "--reference", bad)
    else:
        bad = data_dir.reference
        bad.write_bytes(data)
        result = run_validate("case", data_dir.case_dir)
    assert result.code == 2, result.output
    _assert_named(result, bad.name)


def test_d055_rule_reference_option_that_is_a_folder_exits_2(data_dir, tmp_path, run_validate):
    """D-055 rule: "a path given on the command line ... is a folder where a file is expected"
    -> 2 (`case --reference <folder>`)."""
    folder = tmp_path / "rarp.json"
    folder.mkdir()
    result = run_validate("case", data_dir.case_dir, "--reference", folder)
    assert result.code == 2, result.output


def test_d055_rule_reference_option_the_os_cannot_read_exits_2(data_dir, tmp_path, run_validate):
    """D-055 rule: "a path given on the command line ... the OS can't read it (for example,
    permission denied)" -> 2 (`case --reference <locked file>`)."""
    ref = tmp_path / "rarp.json"
    shutil.copy2(data_dir.reference, ref)
    with _os_unreadable(ref):
        result = run_validate("case", data_dir.case_dir, "--reference", ref)
    assert result.code == 2, result.output


# --- AC5: `validate response` / `validate reference` ------------------------------------------


def test_d055_ac5_reference_broken_json_exits_1(tmp_path, run_validate):
    """D-055 AC5: "`validate reference`: broken JSON -> 1"."""
    target = tmp_path / "rarp.json"
    target.write_text("{ not json", encoding="utf-8")
    result = run_validate("reference", target)
    assert result.code == 1, result.output


@pytest.mark.parametrize("encoding", ENCODINGS)
def test_d055_ac5_reference_not_utf8_exits_1(tmp_path, paths, run_validate, encoding):
    """D-055 AC5: "`validate reference`: ... a non-UTF-8 file -> 1" ("It was opened, and its
    content is the defect"). The content is the valid fixture; only the encoding is wrong."""
    target = tmp_path / "rarp.json"
    target.write_bytes(_encode_not_utf8(paths["reference"].read_text(encoding="utf-8"), encoding))
    result = run_validate("reference", target)
    assert result.code == 1, result.output


def test_d055_ac5_reference_missing_path_exits_2(tmp_path, run_validate):
    """D-055 AC5: "`validate reference`: ... a missing path -> 2"."""
    result = run_validate("reference", tmp_path / "nope" / "rarp.json")
    assert result.code == 2, result.output


def test_d055_ac5_reference_folder_exits_2(tmp_path, run_validate):
    """D-055 AC5: "`validate reference`: ... a folder -> 2"."""
    folder = tmp_path / "rarp.json"
    folder.mkdir()
    result = run_validate("reference", folder)
    assert result.code == 2, result.output


def test_d055_rule_reference_the_os_cannot_read_exits_2(tmp_path, paths, run_validate):
    """D-055 ruling, case 4: "Only OS-level read failures (for example permission denied) stay
    2" (`validate reference <locked file>`)."""
    target = tmp_path / "rarp.json"
    shutil.copy2(paths["reference"], target)
    with _os_unreadable(target):
        result = run_validate("reference", target)
    assert result.code == 2, result.output


@pytest.mark.parametrize("endpoint", list(ENDPOINTS))
def test_d055_ac5_response_broken_json_exits_1(tmp_path, run_validate, endpoint):
    """D-055 AC5: "`validate response`: broken JSON -> 1" (every ENDPOINTS entry)."""
    target = tmp_path / f"{endpoint}.response.json"
    target.write_text('{"contract_version": "1.0", ', encoding="utf-8")
    result = run_validate("response", endpoint, target)
    assert result.code == 1, result.output


def test_d055_ac5_response_control_valid_utf8_exits_0(tmp_path, run_validate):
    """Control for the non-UTF-8 test below: the same body in UTF-8 is valid."""
    target = tmp_path / "translate.response.json"
    target.write_text(json.dumps(VALID_TRANSLATE, ensure_ascii=False), encoding="utf-8")
    result = run_validate("response", "translate", target)
    assert result.code == 0, result.output


@pytest.mark.parametrize("encoding", ENCODINGS)
def test_d055_ac5_response_not_utf8_exits_1(tmp_path, run_validate, encoding):
    """D-055 AC5: "`validate response`: ... a non-UTF-8 file -> 1" (a valid `/v1/translate`
    body; only the encoding is wrong)."""
    target = tmp_path / "translate.response.json"
    target.write_bytes(_encode_not_utf8(json.dumps(VALID_TRANSLATE, ensure_ascii=False), encoding))
    result = run_validate("response", "translate", target)
    assert result.code == 1, result.output


@pytest.mark.parametrize("endpoint", list(ENDPOINTS))
def test_d055_ac5_response_not_utf8_exits_1_every_endpoint(tmp_path, run_validate, endpoint):
    """D-055 AC5: "a non-UTF-8 file -> 1", for every ENDPOINTS entry (UTF-16 with a BOM)."""
    target = tmp_path / f"{endpoint}.response.json"
    target.write_bytes(_encode_not_utf8('{"contract_version": "1.0"}', "utf-16"))
    result = run_validate("response", endpoint, target)
    assert result.code == 1, result.output


@pytest.mark.parametrize("endpoint", list(ENDPOINTS))
def test_d055_ac5_response_missing_path_exits_2(tmp_path, run_validate, endpoint):
    """D-055 AC5: "`validate response`: ... a missing path -> 2"."""
    result = run_validate("response", endpoint, tmp_path / "nope.json")
    assert result.code == 2, result.output


@pytest.mark.parametrize("endpoint", list(ENDPOINTS))
def test_d055_ac5_response_folder_exits_2(tmp_path, run_validate, endpoint):
    """D-055 AC5: "`validate response`: ... a folder -> 2"."""
    folder = tmp_path / f"{endpoint}.response.json"
    folder.mkdir()
    result = run_validate("response", endpoint, folder)
    assert result.code == 2, result.output


def test_d055_rule_response_the_os_cannot_read_exits_2(tmp_path, run_validate):
    """D-055 ruling, case 4: "Only OS-level read failures (for example permission denied) stay
    2" (`validate response translate <locked file>`)."""
    target = tmp_path / "translate.response.json"
    target.write_text(json.dumps(VALID_TRANSLATE, ensure_ascii=False), encoding="utf-8")
    with _os_unreadable(target):
        result = run_validate("response", "translate", target)
    assert result.code == 2, result.output


def test_d055_rule_unknown_endpoint_with_a_non_utf8_file_exits_2(tmp_path, run_validate):
    """D-055: "2 still wins over 1": an unknown endpoint (2) with a non-UTF-8 file (1) -> 2."""
    target = tmp_path / "x.response.json"
    target.write_bytes(_encode_not_utf8(json.dumps(VALID_TRANSLATE, ensure_ascii=False), "cp932"))
    result = run_validate("response", "no_such_endpoint", target)
    assert result.code == 2, result.output
