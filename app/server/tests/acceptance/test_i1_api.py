"""I1 acceptance: the app server API (brief criterion 3).

Sources: app/server/README.md "API" table (shapes; "all errors are ApiError bodies, plan §4.1";
"trust_labels are the distinct labels in the package (timeline items, moments, seed records), in
enum order"), app/server/CLAUDE.md rules 2 and 10 (references loaded; API responses pass through
both `ja` and `en`), plan §4.1 (ApiError; 404 for not_found; 422 → 400 bad_request), §4.2, §4.2b,
D-049 (utterance `class` on the wire).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from scrubgpt_contracts.models.case_package import (
    Case,
    Metrics,
    Moments,
    Questions,
    SeedRecords,
    Timeline,
)
from scrubgpt_contracts.models.common import CONTRACT_VERSION, ApiError, TrustLabel
from scrubgpt_contracts.models.reference import ProcedureReference

CASE_ID = "case-fixture-01"
SUMMARY_KEYS = {"case", "media", "counts", "trust_labels", "has_metrics"}
COUNT_KEYS = {"moments", "operating_questions", "reviewer_questions", "seed_records"}
DETAIL_DOCS = {
    "timeline": ("timeline.json", Timeline),
    "moments": ("moments.json", Moments),
    "questions": ("questions.json", Questions),
    "seed_records": ("seed_records.json", SeedRecords),
    "metrics": ("metrics.json", Metrics),
}


def _assert_api_error(response, status: int, code: str | None = None) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/json"), response.headers
    body = response.json()
    ApiError.model_validate(body)
    assert set(body) >= {"contract_version", "error"}
    assert set(body["error"]) >= {"code", "message", "retryable"}
    if code is not None:
        assert body["error"]["code"] == code
    return body


def _expected_trust_labels(case_dir: Path, read_json) -> list[str]:
    timeline = read_json(case_dir / "timeline.json")
    moments = read_json(case_dir / "moments.json")
    seeds = read_json(case_dir / "seed_records.json")
    found: set[str] = set()
    for key in ("steps", "events", "instruments", "utterances"):
        found |= {item["provenance"]["trust_label"] for item in timeline[key]}
    found |= {m["provenance"]["trust_label"] for m in moments["moments"]}
    found |= {r["provenance"]["trust_label"] for r in seeds["records"]}
    return [label.value for label in TrustLabel if label.value in found]


def _bilingual_pairs(value: Any) -> list[dict]:
    """Every dict in a document whose keys include both `ja` and `en`."""
    out: list[dict] = []
    if isinstance(value, dict):
        if "ja" in value and "en" in value:
            out.append(value)
        for item in value.values():
            out += _bilingual_pairs(item)
    elif isinstance(value, list):
        for item in value:
            out += _bilingual_pairs(item)
    return out


def test_health_shape(client: TestClient) -> None:
    """Criterion 3: `GET /api/health` → `status`, `contract_version`, `brain_mode`,
    `cases: {loaded, rejected}` (README)."""
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"status", "contract_version", "brain_mode", "cases"}
    assert body["contract_version"] == CONTRACT_VERSION
    assert body["brain_mode"] == "mock"
    assert body["cases"] == {"loaded": 1, "rejected": 0}


def test_cases_list_shape(client: TestClient, fixture_case: Path, read_json) -> None:
    """Criterion 3: `GET /api/cases` → `{cases: CaseSummary[]}`; CaseSummary = `{case, media:
    {video, poster}, counts: {moments, operating_questions, reviewer_questions, seed_records},
    trust_labels[], has_metrics}`; `case` is the unchanged `case.json`."""
    response = client.get("/api/cases")
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"cases"}
    assert len(body["cases"]) == 1
    summary = body["cases"][0]
    assert set(summary) >= SUMMARY_KEYS
    assert summary["case"] == read_json(fixture_case / "case.json")
    Case.model_validate(summary["case"])
    assert set(summary["media"]) >= {"video", "poster"}
    assert set(summary["counts"]) >= COUNT_KEYS
    assert summary["has_metrics"] is True


def test_cases_sorted_by_id(make_client, data_dir: Path, clone_case) -> None:
    """Criterion 3 (README): the case list is ordered by case id."""
    for new_id in ("case-fixture-03", "case-fixture-00", "case-fixture-02"):
        clone_case(data_dir / "cases", new_id)
    ids = [c["case"]["id"] for c in make_client(data_dir).get("/api/cases").json()["cases"]]
    assert ids == sorted(ids)
    assert ids == ["case-fixture-00", CASE_ID, "case-fixture-02", "case-fixture-03"]


def test_counts_match_package(client: TestClient, fixture_case: Path, read_json) -> None:
    """Criterion 3: counts are the package's numbers of moments, operating and reviewer
    questions and seed records."""
    questions = read_json(fixture_case / "questions.json")
    expected = {
        "moments": len(read_json(fixture_case / "moments.json")["moments"]),
        "operating_questions": len(questions["operating"]),
        "reviewer_questions": len(questions["reviewer"]),
        "seed_records": len(read_json(fixture_case / "seed_records.json")["records"]),
    }
    summary = client.get("/api/cases").json()["cases"][0]
    assert {k: summary["counts"][k] for k in COUNT_KEYS} == expected


def test_trust_labels_distinct_in_enum_order(
    client: TestClient, fixture_case: Path, read_json
) -> None:
    """Criterion 3 (README): `trust_labels` = the distinct labels in the package (timeline
    items, moments, seed records), in enum order (plan §4.1 TrustLabel order)."""
    expected = _expected_trust_labels(fixture_case, read_json)
    summary = client.get("/api/cases").json()["cases"][0]
    assert summary["trust_labels"] == expected
    detail = client.get(f"/api/cases/{CASE_ID}").json()
    assert detail["trust_labels"] == expected


def test_trust_labels_follow_package_content(
    make_client, data_dir: Path, read_json, write_json
) -> None:
    """Criterion 3: a label used only by one moment appears in its enum position; the list is
    computed from the package, not a fixed list."""
    case_dir = data_dir / "cases" / CASE_ID
    moments = read_json(case_dir / "moments.json")
    moments["moments"][0]["provenance"]["trust_label"] = "reviewer"
    moments["moments"][0]["provenance"]["attributed_to"] = "reviewer"
    moments["moments"][0]["provenance"]["generated_by"] = None
    moments["moments"][0]["provenance"]["confirmed_by"] = "reviewer-1"
    moments["moments"][0]["provenance"]["confirmed_at"] = "2026-10-18T09:00:00Z"
    write_json(case_dir / "moments.json", moments)
    client = make_client(data_dir)
    summary = client.get("/api/cases").json()["cases"]
    assert len(summary) == 1, client.get("/api/catalog").json()
    expected = _expected_trust_labels(case_dir, read_json)
    assert "reviewer" in expected
    assert summary[0]["trust_labels"] == expected


def test_case_detail_documents_unchanged(client: TestClient, fixture_case: Path, read_json) -> None:
    """Criterion 3: `GET /api/cases/{id}` = CaseSummary + `timeline`, `moments`, `questions`,
    `seed_records`, `metrics`: unchanged contract documents that validate against the
    `scrubgpt_contracts` models."""
    response = client.get(f"/api/cases/{CASE_ID}")
    assert response.status_code == 200
    detail = response.json()
    assert set(detail) >= SUMMARY_KEYS | set(DETAIL_DOCS)
    assert detail["case"] == read_json(fixture_case / "case.json")
    for key, (file_name, model) in DETAIL_DOCS.items():
        assert detail[key] == read_json(fixture_case / file_name), f"{key} was changed"
        model.model_validate(detail[key])


def test_case_detail_metrics_null_without_file(
    make_client, data_dir: Path, clone_case, fixture_case: Path
) -> None:
    """Criterion 3 (README): `metrics` is null when the package has no `metrics.json`
    (optional file, plan §4.2), and `has_metrics` is false."""
    clone = clone_case(data_dir / "cases", "case-fixture-02")
    (clone / "metrics.json").unlink()
    client = make_client(data_dir)
    detail = client.get("/api/cases/case-fixture-02")
    assert detail.status_code == 200, client.get("/api/catalog").json()
    assert detail.json()["metrics"] is None
    assert detail.json()["has_metrics"] is False


def test_utterance_class_stays_class(client: TestClient) -> None:
    """Criterion 3 (D-049): utterances carry `class` on the wire, never `class_`."""
    timeline = client.get(f"/api/cases/{CASE_ID}").json()["timeline"]
    assert timeline["utterances"], "fixture has utterances"
    for utterance in timeline["utterances"]:
        assert "class" in utterance
        assert "class_" not in utterance


def test_bilingual_fields_keep_both_languages(client: TestClient) -> None:
    """Criterion 3, CLAUDE.md rule 10: API responses pass through both `ja` and `en`, both
    non-empty."""
    detail = client.get(f"/api/cases/{CASE_ID}").json()
    reference = client.get("/api/references/rarp").json()
    pairs = _bilingual_pairs(detail) + _bilingual_pairs(reference)
    assert len(pairs) > 20
    for pair in pairs:
        assert isinstance(pair["ja"], str) and pair["ja"].strip()
        assert isinstance(pair["en"], str) and pair["en"].strip()


def test_reference_passes_through(client: TestClient, fixture_reference: Path, read_json) -> None:
    """Criterion 3: `GET /api/references/{procedure_id}` → the Procedure Reference, unchanged
    and valid (plan §4.2b)."""
    response = client.get("/api/references/rarp")
    assert response.status_code == 200
    assert response.json() == read_json(fixture_reference)
    ProcedureReference.model_validate(response.json())


def test_catalog_lists_loaded_and_references(client: TestClient) -> None:
    """Criterion 3 (README): `GET /api/catalog` → loaded ids (with warnings), rejected packages
    and references with their problems."""
    response = client.get("/api/catalog")
    assert response.status_code == 200
    text = response.text
    assert CASE_ID in text
    assert "rarp" in text


def test_catalog_reports_rejected_reference(make_client, data_dir: Path, write_json) -> None:
    """Criterion 3 + CLAUDE.md rule 2: an invalid reference file is reported with its problem in
    the catalog and is not served."""
    write_json(data_dir / "reference" / "broken.json", {"contract_version": "1.0", "id": "broken"})
    client = make_client(data_dir)
    text = client.get("/api/catalog").text
    assert "broken" in text
    _assert_api_error(client.get("/api/references/broken"), 404, "not_found")
    assert client.get("/api/references/rarp").status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/api/cases/no-such-case",
        "/api/cases/CASE-FIXTURE-01",
        "/api/references/no-such-procedure",
        "/api/no-such-endpoint",
        "/api/cases/case-fixture-01/extra",
        "/api",
        "/no-such-page",
    ],
)
def test_unknown_ids_and_paths_are_not_found(client: TestClient, path: str) -> None:
    """Criterion 3: unknown ids and unknown paths → 404 `ApiError` with `code: not_found`
    (plan §4.1)."""
    body = _assert_api_error(client.get(path), 404, "not_found")
    assert body["contract_version"] == CONTRACT_VERSION


def test_wrong_method_is_an_api_error(client: TestClient) -> None:
    """Criterion 3: every error body is an `ApiError` (here a method the route doesn't allow)."""
    response = client.post("/api/cases", json={})
    assert 400 <= response.status_code < 500
    _assert_api_error(response, response.status_code)


def test_every_error_carries_contract_version_and_code(client: TestClient) -> None:
    """Criterion 3: error bodies use the plan §4.1 `ErrorCode` values."""
    codes = {
        "bad_request",
        "not_found",
        "payload_too_large",
        "unavailable",
        "upstream_error",
        "refused",
        "timeout",
    }
    for response in (
        client.get("/api/cases/nope"),
        client.delete("/api/cases"),
        client.get("/media/cases/nope/video.mp4"),
    ):
        body = _assert_api_error(response, response.status_code)
        assert body["error"]["code"] in codes
        assert isinstance(body["error"]["retryable"], bool)
