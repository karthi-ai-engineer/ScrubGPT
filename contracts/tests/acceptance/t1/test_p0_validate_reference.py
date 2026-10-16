"""AC16: `scrubgpt-validate reference <file>` (plan §4.2b, §4.5; D-035; #4 point 10)."""

from __future__ import annotations

import json
import shutil


def test_ac16_valid_reference_exits_0(tmp_path, paths, run_validate):
    """AC16: "exit 0 or 1" - 0 for a valid reference."""
    target = tmp_path / "rarp.json"
    shutil.copy2(paths["reference"], target)
    result = run_validate("reference", target)
    assert result.code == 0, result.output


def test_ac16_file_name_must_equal_procedure_id(tmp_path, paths, run_validate):
    """AC16: "the file name must equal the procedure id" (`<DATA_DIR>/reference/<procedure_id>
    .json`, §4.2b)."""
    target = tmp_path / "prostatectomy.json"
    shutil.copy2(paths["reference"], target)
    result = run_validate("reference", target)
    assert result.code == 1, result.output


def test_ac16_invalid_reference_exits_1(tmp_path, paths, run_validate):
    """AC16: exit 1 for an invalid reference (a family is missing, D-035)."""
    doc = json.loads(paths["reference"].read_text(encoding="utf-8"))
    doc["obstacle_taxonomy"] = doc["obstacle_taxonomy"][:-1]
    target = tmp_path / "rarp.json"
    target.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    result = run_validate("reference", target)
    assert result.code == 1, result.output


def test_ac16_broken_json_exits_1(tmp_path, run_validate):
    """AC16: exit 1 for a file that is not valid JSON."""
    target = tmp_path / "rarp.json"
    target.write_text("{ broken", encoding="utf-8")
    result = run_validate("reference", target)
    assert result.code == 1, result.output


def test_ac16_missing_file_exits_2(tmp_path, run_validate):
    """AC16: a reference file that doesn't exist is never exit 0; tightened to exit 2 by D-052
    and D-055 AC5 ("`validate reference`: ... a missing path -> 2")."""
    result = run_validate("reference", tmp_path / "rarp.json")
    assert result.code == 2, result.output
