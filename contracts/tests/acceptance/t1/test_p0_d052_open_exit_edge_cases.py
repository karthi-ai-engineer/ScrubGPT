"""Exit-code edge cases that D-052 did not spell out (asked on issue #7, brief criterion 4).

These were first tested as **non-zero only** ("never a PASS"); the Team Lead's newest ruling on
#7 (D-055) settles them, so they are now tightened to its exact codes: a defect inside the
subject (a package file, or the `response` / `reference` file itself) is 1; an invalid reference
given to `case` (by `--reference` or found by the lookup) is an invalid input, 2. What D-052
settles is unchanged: "the checks that could run are still printed".

Edge cases: an unreadable file inside a case package (not UTF-8, or a folder where a file is
expected), an invalid `--reference` (or an invalid reference found by the lookup
`<case_dir>/../../reference/<prefix>.json`), and a `response` / `reference` file that isn't UTF-8.
The unreachable Brain is in test_p0_live_fake_brain.py; a *missing* required file inside a
package is AC15 (exit 1, test_p0_validate_case.py); broken JSON in `response` / `reference` is
AC16/AC17 (exit 1).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

CASE_ID = "case-fixture-01"


def _not_utf8(text: str) -> bytes:
    """The same JSON text in Shift_JIS (cp932): structurally JSON, but not UTF-8."""
    data = text.encode("cp932", errors="replace")
    with pytest.raises(UnicodeDecodeError):
        data.decode("utf-8")
    return data


def _break_reference_free_checks(case_dir: Path) -> list[str]:
    """Package errors that need no Procedure Reference; returns the names that must be
    reported."""

    def load(name):
        return json.loads((case_dir / name).read_text(encoding="utf-8"))

    def save(name, doc):
        (case_dir / name).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    case = load("case.json")
    case["language"], case["narrated"] = "none", True
    save("case.json", case)
    questions = load("questions.json")
    q = next(q for q in questions["operating"] if q["tap_options"])
    q["tap_options"][0]["id"] = "reject"
    save("questions.json", questions)
    return ["case.json", "questions.json"]


def _invalid_reference_docs(paths) -> dict[str, str]:
    doc = json.loads(paths["reference"].read_text(encoding="utf-8"))
    doc["obstacle_taxonomy"] = doc["obstacle_taxonomy"][1:]  # one of the 8 families missing
    return {
        "broken-json": "{ not json",
        "fails-model": json.dumps(doc, ensure_ascii=False),
    }


# --- an unreadable file inside a case package ---------------------------------------------------


@pytest.mark.parametrize("name", ["moments.json", "questions.json", "seed_records.json"])
def test_edge_case_file_not_utf8_exits_1(data_dir, run_validate, name):
    """Brief criterion 4 (#7), settled by D-055 case 2: a package JSON file that isn't UTF-8 ->
    exit 1, and the file is named (AC15: "an error naming the file")."""
    path = data_dir.case_dir / name
    path.write_bytes(_not_utf8(path.read_text(encoding="utf-8")))
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert name in result.output, result.output


@pytest.mark.parametrize("name", ["questions.json", "timeline.json"])
def test_edge_case_file_is_a_folder_exits_1(data_dir, run_validate, name):
    """Brief criterion 4 (#7), settled by D-055 case 2: a required package file that is a folder
    -> exit 1, and the file is named."""
    path = data_dir.case_dir / name
    path.unlink()
    path.mkdir()
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert name in result.output, result.output


def test_edge_case_unreadable_package_file_other_checks_still_printed(data_dir, run_validate):
    """D-052: "the checks that could run are still printed": with `moments.json` not UTF-8, the
    errors in `case.json` and `questions.json` are still reported (exit 1, D-055)."""
    names = _break_reference_free_checks(data_dir.case_dir)
    path = data_dir.case_dir / "moments.json"
    path.write_bytes(_not_utf8(path.read_text(encoding="utf-8")))
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    for name in [*names, "moments.json"]:
        assert name in result.problems, f"{name!r} not reported:\n{result.output}"


# --- an invalid reference -----------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["broken-json", "fails-model"])
def test_edge_case_invalid_reference_option_exits_2(data_dir, tmp_path, paths, run_validate, kind):
    """Brief criterion 4 (#7), settled by D-055 case 3: `case --reference <invalid reference>`
    -> exit 2."""
    bad = tmp_path / "ref" / "rarp.json"
    bad.parent.mkdir()
    bad.write_text(_invalid_reference_docs(paths)[kind], encoding="utf-8")
    result = run_validate("case", data_dir.case_dir, "--reference", bad)
    assert result.code == 2, result.output


@pytest.mark.parametrize("kind", ["broken-json", "fails-model"])
def test_edge_case_invalid_reference_found_by_lookup_exits_2(data_dir, paths, run_validate, kind):
    """Brief criterion 4 (#7), settled by D-055 case 3: an invalid reference at
    `<case_dir>/../../reference/rarp.json` (D-052 lookup, no `--reference`) -> exit 2 ("The
    reference is an input however it was found")."""
    data_dir.reference.write_text(_invalid_reference_docs(paths)[kind], encoding="utf-8")
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 2, result.output


@pytest.mark.parametrize("via", ["option", "lookup"])
def test_edge_case_invalid_reference_package_errors_still_printed(
    data_dir, tmp_path, paths, run_validate, via
):
    """D-052: "the checks that could run are still printed": an invalid reference doesn't hide
    the package errors that need no reference (exit 2, D-055 AC4)."""
    names = _break_reference_free_checks(data_dir.case_dir)
    broken = _invalid_reference_docs(paths)["broken-json"]
    if via == "option":
        bad = tmp_path / "ref" / "rarp.json"
        bad.parent.mkdir()
        bad.write_text(broken, encoding="utf-8")
        result = run_validate("case", data_dir.case_dir, "--reference", bad)
    else:
        data_dir.reference.write_text(broken, encoding="utf-8")
        result = run_validate("case", data_dir.case_dir)
    assert result.code == 2, result.output
    for name in names:
        assert name in result.problems, f"{name!r} not reported:\n{result.output}"


# --- a response / reference file that isn't UTF-8 -----------------------------------------------


def test_edge_case_reference_file_not_utf8_exits_1(tmp_path, paths, run_validate):
    """Brief criterion 4 (#7), settled by D-055 case 4: `reference <file not UTF-8>` -> exit 1
    ("It was opened, and its content is the defect")."""
    target = tmp_path / "rarp.json"
    target.write_bytes(_not_utf8(paths["reference"].read_text(encoding="utf-8")))
    assert run_validate("reference", target).code == 1


def test_edge_case_response_file_not_utf8_exits_1(tmp_path, run_validate):
    """Brief criterion 4 (#7), settled by D-055 case 4: `response translate <file not UTF-8>`
    -> exit 1."""
    body = {"contract_version": "1.0", "items": [{"ja": "出血", "en": "Bleeding"}]}
    target = tmp_path / "translate.response.json"
    target.write_bytes(_not_utf8(json.dumps(body, ensure_ascii=False)))
    assert run_validate("response", "translate", target).code == 1
