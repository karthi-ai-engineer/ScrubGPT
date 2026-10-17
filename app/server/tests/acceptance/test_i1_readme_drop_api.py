"""I1 acceptance: criterion 15 (new at 00ce6e4, from Tester 2's spec gaps).

Criterion 15 (brief): "`app/server/README.md` states: (a) the drop reference lookup without
`--reference` (the only `*.json` in `<drop>/reference/`, else the only one in
`DATA_DIR/reference/`, else the validator's own lookup), and drop mode behaves so; (b) the app API
is internal, not a contract; `contract_version` is in `/api/health` and inside every contract
document; every error is an `ApiError`."

The validator's own lookup is `<case_dir>/../../reference/<prefix>.json`
(`contracts/scrubgpt_contracts/validate.py` module docstring, Dev1's contract file). Exit codes
(README): 0 all loadable, 1 not all, 2 the check couldn't run.

How the reference in use is observed: the "wrong" reference is a valid Procedure Reference that
keeps only its first phase, so the fixture case's step ids are unknown to it and the package is not
loadable; the "right" one is the fixture reference. Whichever is picked decides exit 0 or not.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from scrubgpt_contracts.models.common import CONTRACT_VERSION, ApiError

CASE_ID = "case-fixture-01"


@pytest.fixture
def readme(repo_root: Path) -> str:
    return (repo_root / "app" / "server" / "README.md").read_text(encoding="utf-8")


@pytest.fixture
def drop_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "drop" / "2026-10-30"
    folder.mkdir(parents=True)
    return folder


@pytest.fixture
def wrong_reference(fixture_reference: Path, read_json) -> dict:
    """A valid Procedure Reference (`rarp`) whose steps don't include the fixture case's steps."""
    data = copy.deepcopy(read_json(fixture_reference))
    data["phases"] = data["phases"][:1]
    return data


@pytest.fixture
def right_reference(fixture_reference: Path, read_json) -> dict:
    return read_json(fixture_reference)


def _drop(run_cli, drop_dir: Path, data_dir: Path) -> tuple[int, str]:
    """`scrubgpt-app drop <drop>` with no `--reference`."""
    return run_cli("drop", str(drop_dir), "--data-dir", str(data_dir))


# --- (a) README text ----------------------------------------------------------------------


def test_readme_states_drop_reference_lookup(readme: str) -> None:
    """Criterion 15a: the README states the lookup without `--reference`: the only `*.json` in
    `<drop>/reference/`, else the only one in `DATA_DIR/reference/`, else the validator's own."""
    flat = " ".join(readme.split())
    assert "--reference" in flat
    m = re.search(
        r"only `?\*\.json`? in `?<drop>/reference/`?.{0,80}?only one in `?DATA_DIR/reference/`?"
        r".{0,80}?validator.{0,20}own lookup",
        flat,
        re.IGNORECASE,
    )
    assert m, "the drop reference lookup order is not stated in app/server/README.md"


# --- (a) drop mode behaves so -------------------------------------------------------------


def test_drop_reference_folder_is_used_first(
    run_cli, drop_dir: Path, data_dir: Path, clone_case, write_json, wrong_reference
) -> None:
    """Criterion 15a, step 1: the only `*.json` in `<drop>/reference/` is used, even though
    `DATA_DIR/reference/` holds a matching reference → here the wrong one → not loadable."""
    clone_case(drop_dir, CASE_ID)
    (drop_dir / "reference").mkdir()
    write_json(drop_dir / "reference" / "rarp.json", wrong_reference)
    code, out = _drop(run_cli, drop_dir, data_dir)
    assert code == 1, out
    assert "not loadable" in out.lower()
    assert "rarp.p03.s01" in out, "the problem should be the step the wrong reference lacks"


def test_drop_reference_folder_right_reference_loads(
    run_cli,
    drop_dir: Path,
    data_dir: Path,
    clone_case,
    write_json,
    wrong_reference,
    right_reference,
) -> None:
    """Criterion 15a, step 1 (the other way round): the drop's own reference is right and the
    one in `DATA_DIR/reference/` is wrong → the drop's is used → exit 0."""
    clone_case(drop_dir, CASE_ID)
    (drop_dir / "reference").mkdir()
    write_json(drop_dir / "reference" / "rarp.json", right_reference)
    write_json(data_dir / "reference" / "rarp.json", wrong_reference)
    code, out = _drop(run_cli, drop_dir, data_dir)
    assert code == 0, out


def test_drop_reference_file_name_does_not_matter(
    run_cli,
    drop_dir: Path,
    data_dir: Path,
    clone_case,
    write_json,
    wrong_reference,
    right_reference,
) -> None:
    """Criterion 15a, step 1: "the only `*.json`" means any name, not only `<procedure>.json`."""
    clone_case(drop_dir, CASE_ID)
    (drop_dir / "reference").mkdir()
    write_json(drop_dir / "reference" / "procedure-reference.json", right_reference)
    write_json(data_dir / "reference" / "rarp.json", wrong_reference)
    code, out = _drop(run_cli, drop_dir, data_dir)
    assert code == 0, out


def test_two_drop_references_fall_back_to_data_dir(
    run_cli, drop_dir: Path, data_dir: Path, clone_case, write_json, wrong_reference
) -> None:
    """Criterion 15a, step 2: two `*.json` in `<drop>/reference/` is not "the only one", so the
    only one in `DATA_DIR/reference/` (right) is used → exit 0."""
    clone_case(drop_dir, CASE_ID)
    (drop_dir / "reference").mkdir()
    write_json(drop_dir / "reference" / "rarp.json", wrong_reference)
    write_json(drop_dir / "reference" / "other.json", wrong_reference)
    code, out = _drop(run_cli, drop_dir, data_dir)
    assert code == 0, out


def test_no_drop_reference_uses_the_only_data_dir_reference(
    run_cli,
    drop_dir: Path,
    data_dir: Path,
    clone_case,
    write_json,
    wrong_reference,
    right_reference,
    tmp_path: Path,
) -> None:
    """Criterion 15a, step 2: no `<drop>/reference/` → the only `*.json` in
    `DATA_DIR/reference/` is used, even where the validator's own lookup would find another
    (here the wrong one in `DATA_DIR/reference/`, the right one at the validator's path)."""
    clone_case(drop_dir, CASE_ID)
    write_json(data_dir / "reference" / "rarp.json", wrong_reference)
    validator_ref = drop_dir.parent / "reference"  # <case_dir>/../../reference/
    validator_ref.mkdir()
    write_json(validator_ref / "rarp.json", right_reference)
    code, out = _drop(run_cli, drop_dir, data_dir)
    assert code == 1, out
    assert "not loadable" in out.lower()
    assert "rarp.p03.s01" in out, "the problem should be the step the wrong reference lacks"


def test_no_single_reference_uses_the_validator_lookup(
    run_cli,
    drop_dir: Path,
    data_dir: Path,
    clone_case,
    write_json,
    wrong_reference,
    right_reference,
) -> None:
    """Criterion 15a, step 3: neither the drop nor DATA_DIR has exactly one `*.json` (two wrong
    ones in `DATA_DIR/reference/`) → the validator's own lookup
    (`<case_dir>/../../reference/rarp.json`, right) is used → exit 0."""
    clone_case(drop_dir, CASE_ID)
    write_json(data_dir / "reference" / "rarp.json", wrong_reference)
    write_json(data_dir / "reference" / "other.json", wrong_reference)
    validator_ref = drop_dir.parent / "reference"
    validator_ref.mkdir()
    write_json(validator_ref / "rarp.json", right_reference)
    code, out = _drop(run_cli, drop_dir, data_dir)
    assert code == 0, out


def test_validator_lookup_in_cases_layout(
    run_cli,
    drop_dir: Path,
    data_dir: Path,
    clone_case,
    write_json,
    wrong_reference,
    right_reference,
) -> None:
    """Criterion 15a, step 3 in the `<drop>/cases/<case_id>/` layout: the validator's own lookup
    is then `<drop>/reference/rarp.json`, which is also "the only `*.json` in
    `<drop>/reference/`" → used → exit 0 (DATA_DIR has two wrong ones)."""
    clone_case(drop_dir / "cases", CASE_ID)
    write_json(data_dir / "reference" / "rarp.json", wrong_reference)
    write_json(data_dir / "reference" / "other.json", wrong_reference)
    (drop_dir / "reference").mkdir()
    write_json(drop_dir / "reference" / "rarp.json", right_reference)
    code, out = _drop(run_cli, drop_dir, data_dir)
    assert code == 0, out


def test_explicit_reference_wins_over_the_lookup(
    run_cli,
    drop_dir: Path,
    data_dir: Path,
    clone_case,
    write_json,
    wrong_reference,
    fixture_reference: Path,
) -> None:
    """Criterion 15a: the lookup applies only without `--reference`; with it, the given file is
    used (the drop's own reference is wrong here) → exit 0."""
    clone_case(drop_dir, CASE_ID)
    (drop_dir / "reference").mkdir()
    write_json(drop_dir / "reference" / "rarp.json", wrong_reference)
    code, out = run_cli(
        "drop", str(drop_dir), "--reference", str(fixture_reference), "--data-dir", str(data_dir)
    )
    assert code == 0, out


# --- (b) README text and behaviour --------------------------------------------------------


def test_readme_states_api_is_internal_not_a_contract(readme: str) -> None:
    """Criterion 15b: the README says the app API is internal, not a contract."""
    flat = " ".join(readme.split())
    assert re.search(r"internal API \(not a contract", flat, re.IGNORECASE) or re.search(
        r"API.{0,60}internal.{0,40}not a contract", flat, re.IGNORECASE
    ), "app/server/README.md does not say the app API is internal, not a contract"


def test_readme_states_contract_version_and_api_error(readme: str) -> None:
    """Criterion 15b: the README says `/api/health` carries `contract_version`, every contract
    document inside a response carries its own, and every error is an `ApiError`."""
    flat = " ".join(readme.split())
    assert re.search(r"/api/health`? carries `?contract_version", flat), flat
    assert re.search(r"every contract document.{0,60}carries its own", flat), flat
    assert re.search(r"every error is an `?ApiError", flat), flat


def test_health_carries_contract_version(client: TestClient) -> None:
    """Criterion 15b: `GET /api/health` carries `contract_version` (plan §4.1)."""
    body = client.get("/api/health").json()
    assert body["contract_version"] == CONTRACT_VERSION


def test_every_contract_document_carries_its_contract_version(client: TestClient) -> None:
    """Criterion 15b: every contract document inside a response carries its own
    `contract_version`: in `/api/cases` the Case; in `/api/cases/{id}` the Case, Timeline,
    Moments, Questions, SeedRecords and Metrics; `/api/references/{id}` the Procedure Reference."""
    listing = client.get("/api/cases").json()
    for summary in listing["cases"]:
        assert summary["case"]["contract_version"] == CONTRACT_VERSION
    detail = client.get(f"/api/cases/{CASE_ID}").json()
    for key in ("case", "timeline", "moments", "questions", "seed_records", "metrics"):
        assert detail[key] is not None, key
        assert detail[key].get("contract_version") == CONTRACT_VERSION, key
    reference = client.get("/api/references/rarp").json()
    assert reference["contract_version"] == CONTRACT_VERSION


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/cases/no-such-case"),
        ("GET", "/api/references/no-such-procedure"),
        ("GET", "/api/no-such-route"),
        ("GET", "/media/cases/case-fixture-01/case.json"),
        ("DELETE", "/api/cases"),
    ],
)
def test_every_error_is_an_api_error(client: TestClient, method: str, path: str) -> None:
    """Criterion 15b: every error is an `ApiError` body (plan §4.1)."""
    response = client.request(method, path)
    assert response.status_code >= 400
    body = response.json()
    ApiError.model_validate(body)
    assert body["contract_version"] == CONTRACT_VERSION
    assert body["error"]["code"]
