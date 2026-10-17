"""The case loader (I1): valid packages load, invalid ones are rejected with reasons, never
patched."""

import json
from pathlib import Path

from scrubgpt_app.catalog import scan
from scrubgpt_app.settings import REPO_ROOT
from scrubgpt_contracts.models.common import TrustLabel

FIXTURES = REPO_ROOT / "contracts" / "fixtures"
CASE_ID = "case-fixture-01"
FIXTURE_CASE = FIXTURES / "cases" / CASE_ID


def test_the_fixture_case_loads() -> None:
    catalog = scan(FIXTURES)
    assert list(catalog.cases) == [CASE_ID]
    assert catalog.rejected == []
    assert list(catalog.references) == ["rarp"]
    loaded = catalog.cases[CASE_ID]
    moments = json.loads((FIXTURE_CASE / "moments.json").read_text(encoding="utf-8"))
    questions = json.loads((FIXTURE_CASE / "questions.json").read_text(encoding="utf-8"))
    seeds = json.loads((FIXTURE_CASE / "seed_records.json").read_text(encoding="utf-8"))
    assert loaded.counts() == {
        "moments": len(moments["moments"]),
        "operating_questions": len(questions["operating"]),
        "reviewer_questions": len(questions["reviewer"]),
        "seed_records": len(seeds["records"]),
    }
    labels = loaded.trust_labels()
    assert TrustLabel.SIMULATED in labels
    assert labels == sorted(labels, key=list(TrustLabel).index)  # enum order
    assert loaded.metrics is not None


def test_an_invalid_package_is_rejected_with_its_reason(data_dir: Path) -> None:
    (data_dir / "cases" / CASE_ID / "moments.json").write_text("{ not json", encoding="utf-8")
    (data_dir / "cases" / "empty-folder").mkdir()
    catalog = scan(data_dir)
    assert catalog.cases == {}
    rejected = {item.path.name: item.problems for item in catalog.rejected}
    assert set(rejected) == {CASE_ID, "empty-folder"}
    assert any("moments.json" in problem for problem in rejected[CASE_ID])
    assert any("case.json" in problem for problem in rejected["empty-folder"])


def test_a_package_is_never_patched(data_dir: Path) -> None:
    case_json = data_dir / "cases" / CASE_ID / "case.json"
    before = case_json.read_bytes()
    data = json.loads(before)
    data["duration_s"] = -1
    case_json.write_text(json.dumps(data), encoding="utf-8")
    catalog = scan(data_dir)
    assert CASE_ID not in catalog.cases
    assert json.loads(case_json.read_bytes())["duration_s"] == -1


def test_no_cases_folder_is_an_empty_catalog(tmp_path: Path) -> None:
    catalog = scan(tmp_path)
    assert catalog.cases == {} and catalog.rejected == [] and catalog.references == {}


def test_an_invalid_reference_is_rejected(data_dir: Path) -> None:
    (data_dir / "reference" / "other.json").write_text("{}", encoding="utf-8")
    catalog = scan(data_dir)
    assert list(catalog.references) == ["rarp"]
    assert [item.path.name for item in catalog.rejected_references] == ["other.json"]
