"""I1 acceptance: `scrubgpt-app check`, the case loader's validation (brief criterion 1).

Sources: plan §2.9 I1 ("scans case packages and validates them against the contracts"), §4.2
(required files), app/server/CLAUDE.md rule 2 ("loads only complete packages … rejects invalid
ones with a clear error and never patches them silently"), app/server/README.md (exit codes
0 all loadable, 1 not all, 2 the check couldn't run), D-026 (DATA_DIR = ./contracts/fixtures).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scrubgpt_contracts.validate import validate_case

BROKEN_ID = "case-fixture-02"


def _break_invalid_json(case: Path) -> str:
    (case / "moments.json").write_text('{"contract_version": "1.0", "moments": [', encoding="utf-8")
    return "moments.json"


def _break_missing_file(case: Path) -> str:
    (case / "poster.jpg").unlink()
    return "poster.jpg"


def _break_contract_rule(case: Path) -> str:
    # D-059: a seed record's question_id must exist in questions.json (a `validate case` error);
    # the record itself stays model-valid (same moment, same q/r kind).
    path = case / "seed_records.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    record = next(r for r in data["records"] if r["question_id"] == f"{BROKEN_ID}.m01.q1")
    record["question_id"] = f"{BROKEN_ID}.m01.q9"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return "seed_records.json"


def _break_case_enum(case: Path) -> str:
    path = case / "case.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["source"] = "hospital"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return "case.json"


BREAKERS = {
    "invalid_json": _break_invalid_json,
    "missing_required_file": _break_missing_file,
    "validate_case_rule": _break_contract_rule,
    "model_violation": _break_case_enum,
}


def test_check_fixtures_loads_case_and_reference(run_cli, data_dir: Path) -> None:
    """Criterion 1: `check` with DATA_DIR = the fixtures loads `case-fixture-01` and the `rarp`
    reference, exit 0 (README: 0 = all loadable)."""
    code, out = run_cli("check", "--data-dir", str(data_dir))
    assert code == 0, out
    assert "case-fixture-01" in out
    assert "rarp" in out


def test_check_committed_fixtures_via_console_script(run_script, repo_root: Path) -> None:
    """Criterion 1 with the documented command: `uv run scrubgpt-app check` and
    DATA_DIR=./contracts/fixtures (D-026) → exit 0, the case and the reference are reported."""
    result = run_script("check", env={"DATA_DIR": "./contracts/fixtures"}, cwd=repo_root)
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "case-fixture-01" in out
    assert "rarp" in out


def test_two_valid_packages_both_load(run_cli, data_dir: Path, clone_case) -> None:
    """Sanity for the broken-package tests: a valid renamed copy of the fixture also loads."""
    clone = clone_case(data_dir / "cases", BROKEN_ID)
    assert not validate_case(clone).errors
    code, out = run_cli("check", "--data-dir", str(data_dir))
    assert code == 0, out
    assert BROKEN_ID in out and "case-fixture-01" in out


@pytest.mark.parametrize("breaker", list(BREAKERS))
def test_broken_package_rejected_with_reason_others_load(
    breaker: str, run_cli, data_dir: Path, clone_case, tree_digest, make_client
) -> None:
    """Criterion 1: a broken package (invalid JSON, a missing required file, a contract violation
    `scrubgpt-validate case` reports) is rejected with its reason, exit 1; other packages still
    load; the broken files are not modified (CLAUDE.md rule 2: never patched silently)."""
    broken = clone_case(data_dir / "cases", BROKEN_ID)
    broken_file = BREAKERS[breaker](broken)
    assert validate_case(broken).errors, "test setup: the validator must report this package"
    before = tree_digest(data_dir)

    code, out = run_cli("check", "--data-dir", str(data_dir))

    assert code == 1, out
    assert BROKEN_ID in out, f"the rejected package is not named:\n{out}"
    assert broken_file in out, f"the reason does not name {broken_file}:\n{out}"
    assert "case-fixture-01" in out
    assert tree_digest(data_dir) == before, "check modified or created files in DATA_DIR"

    # The server loads the same way: only the valid package is served.
    client = make_client(data_dir)
    ids = [c["case"]["id"] for c in client.get("/api/cases").json()["cases"]]
    assert ids == ["case-fixture-01"]
    assert client.get(f"/api/cases/{BROKEN_ID}").status_code == 404
    catalog = json.dumps(client.get("/api/catalog").json(), ensure_ascii=False)
    assert BROKEN_ID in catalog and broken_file in catalog
    health = client.get("/api/health").json()
    assert health["cases"] == {"loaded": 1, "rejected": 1}
    assert tree_digest(data_dir) == before, "the server modified or created files in DATA_DIR"


def test_missing_data_dir_exits_2(run_cli, tmp_path: Path) -> None:
    """Criterion 1: a missing DATA_DIR → exit 2 (README: 2 = the check couldn't run)."""
    code, out = run_cli("check", "--data-dir", str(tmp_path / "does-not-exist"))
    assert code == 2, out


def test_missing_data_dir_from_env_exits_2(run_script, tmp_path: Path) -> None:
    """Criterion 1 through the console script, DATA_DIR from the environment."""
    result = run_script("check", env={"DATA_DIR": str(tmp_path / "nope")})
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
