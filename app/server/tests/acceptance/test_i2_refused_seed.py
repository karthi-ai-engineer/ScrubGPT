"""I2 at start-up: a seed record the store refuses takes only its case offline (Block 3 re-test,
criterion 13).

Criterion 13 (brief, from T2 spec gap 1; D-073 "A refused record is reported, never patched"): "A
loaded case whose seed record the store refuses doesn't stop the server: that case is taken
offline (not in `/api/cases`, 404 on its routes) and is listed in `/api/catalog` → `rejected` with
the reason; the other cases and the server keep working; the seed file isn't modified."
app/server/README.md "Knowledge store (I2)": "At start-up the loaded cases' seed records are stored
once; a case whose seed record the store refuses is taken offline and listed in `/api/catalog`
with the reason (the server and the other cases keep running)."

The broken seed is contract-valid (the package passes `validate_case`), so the refusal is the
store's (D-073 rules), not the loader's. Everything runs on a private copy of the fixtures.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest
from scrubgpt_contracts.models.common import ApiError
from scrubgpt_contracts.validate import validate_case
from uuid6 import uuid7

GOOD = "case-fixture-01"
BAD = "case-fixture-02"


def _non_narration(records: list[dict]) -> int:
    return next(
        i for i, r in enumerate(records) if r["provenance"]["trust_label"] != "narration_extracted"
    )


# D-073: each of these is a record the store refuses, though the contract model accepts it.
BREAKS = {
    # "every other seed needs both [confirmation fields]"
    "non_narration_seed_unconfirmed": {"confirmed_by": None, "confirmed_at": None},
    # "exactly one of the two set is refused for any record"
    "only_confirmed_by": {"confirmed_at": None},
    # "I2 refuses a record with a missing or null … generated_by"
    "null_generated_by": {"generated_by": None},
}


@pytest.fixture
def broken_data(data_dir: Path, clone_case, read_json, write_json):
    """`broken_data(break_name)` → (data dir, path of the bad case's seed file, refused record id).
    The good fixture case stays as it is; a clone `case-fixture-02` gets fresh record ids (no id
    clash with the good case) and one seed record broken per `BREAKS`."""

    def make(name: str) -> tuple[Path, Path, str]:
        clone = clone_case(data_dir / "cases", BAD)
        seed_path = clone / "seed_records.json"
        doc = read_json(seed_path)
        records = doc["records"]
        for record in records:
            record["id"] = str(uuid7())
        index = _non_narration(records)
        records[index] = copy.deepcopy(records[index])
        records[index]["provenance"].update(BREAKS[name])
        write_json(seed_path, doc)
        report = validate_case(clone)
        assert not report.errors, (
            f"precondition: the broken package must be contract-valid: {report}"
        )
        return data_dir, seed_path, records[index]["id"]

    return make


def _not_found(response) -> None:
    assert response.status_code == 404, (response.request.url, response.status_code, response.text)
    assert ApiError.model_validate(response.json()).error.code.value == "not_found"


@pytest.mark.parametrize("name", list(BREAKS))
def test_c13_a_refused_seed_takes_only_its_case_offline(answer_app, broken_data, draft_for, name):
    """Criterion 13: the server starts; the case is not in `/api/cases` and its routes are 404;
    the other case and the server keep working."""
    data, _, _ = broken_data(name)
    app = answer_app(data)  # create_app must not raise
    client = app.client

    health = client.get("/api/health")
    assert health.status_code == 200, health.text
    assert health.json()["cases"] == {"loaded": 1, "rejected": 1}

    ids = [c["case"]["id"] for c in client.get("/api/cases").json()["cases"]]
    assert ids == [GOOD]

    _not_found(client.get(f"/api/cases/{BAD}"))
    _not_found(client.get(f"/api/cases/{BAD}/answer-queue", params={"role": "operating"}))
    _not_found(client.get(f"/api/cases/{BAD}/records"))
    _not_found(client.post(f"/api/cases/{BAD}/replay-ended"))
    _not_found(client.get(f"/media/cases/{BAD}/poster.jpg"))
    _not_found(client.get(f"/media/cases/{BAD}/video.mp4"))

    # The other case keeps working: detail, queue, its 7 seed records, and a new answer's draft.
    assert client.get(f"/api/cases/{GOOD}").status_code == 200
    queue = client.get(f"/api/cases/{GOOD}/answer-queue", params={"role": "operating"})
    assert queue.status_code == 200, queue.text
    records = client.get(f"/api/cases/{GOOD}/records")
    assert records.status_code == 200
    assert len(records.json()["records"]) == 7
    assert client.get(f"/media/cases/{GOOD}/poster.jpg").status_code == 200
    status, body = draft_for(client, f"{GOOD}.m05.q1", "operating_surgeon", text="レンズが曇った")
    assert status == 200, body


@pytest.mark.parametrize("name", list(BREAKS))
def test_c13_the_offline_case_is_listed_in_the_catalog_with_the_reason(
    answer_app, broken_data, name
):
    """Criterion 13: "listed in `/api/catalog` → `rejected` with the reason"; the good case stays
    under `loaded`."""
    data, _, refused_id = broken_data(name)
    catalog = answer_app(data).client.get("/api/catalog")
    assert catalog.status_code == 200
    body = catalog.json()
    assert [item["case_id"] for item in body["loaded"]] == [GOOD]
    entries = [item for item in body["rejected"] if BAD in json.dumps(item)]
    assert len(entries) == 1, body["rejected"]
    problems = entries[0].get("problems")
    assert problems, entries[0]
    text = json.dumps(problems, ensure_ascii=False)
    # The reason identifies what was refused: the record or the field the store objects to.
    field_named = any(field in text for field in BREAKS[name]) or "confirm" in text
    assert refused_id in text or field_named, text


@pytest.mark.parametrize("name", list(BREAKS))
def test_c13_the_refused_record_is_not_stored_and_the_seed_file_is_unchanged(
    answer_app, broken_data, tree_digest, name
):
    """Criterion 13: "the seed file isn't modified"; D-073 "a refused record is reported, never
    patched": the refused record is not in the store in any form."""
    data, seed_path, refused_id = broken_data(name)
    before = tree_digest(seed_path.parent)
    seed_bytes = seed_path.read_bytes()
    app = answer_app(data)
    assert seed_path.read_bytes() == seed_bytes
    assert tree_digest(seed_path.parent) == before

    db = sqlite3.connect(app.db_path)
    try:
        dump = "\n".join(db.iterdump())
    finally:
        db.close()
    assert refused_id not in dump
