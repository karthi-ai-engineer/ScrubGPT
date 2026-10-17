"""I2 knowledge store acceptance (brief criteria 1, 2a–2d, 3).

Sources: plan §2.9 I2 ("Entities, edges, provenance and decision records. Keeps every
viewpoint"), §4.3 ("Several records may point to the same moment; they are different viewpoints,
all kept"); app/server/CLAUDE.md rule 3 (WAL, local `APP_DB_PATH`, small ordered migrations),
rule 4 (many records per moment, never overwrite), rule 5 (provenance required); D-071 (guardrail
criteria), D-073 (which records the store accepts; replaces D-071 criterion 2 with 2a–2e);
app/server/README.md "Knowledge store (I2)".

The store is used through its entry point `scrubgpt_app.store.KnowledgeStore` on a `tmp_path`
file, and through the app (`create_app`) with `APP_DB_PATH` under `tmp_path`.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from scrubgpt_contracts.models.decision_record import DecisionRecord
from uuid6 import uuid7

CASE = "case-fixture-01"
NARRATION_ID = "01a1436a-d1c2-7a51-9c3e-5d2f8b6e1a40"


# --- helpers --------------------------------------------------------------------------------------


@pytest.fixture
def seeds(fixture_docs) -> list[dict]:
    return copy.deepcopy(fixture_docs["seed_records"]["records"])  # type: ignore[index]


def _record(raw: dict, **provenance) -> DecisionRecord:
    data = copy.deepcopy(raw)
    data["provenance"].update(provenance)
    return DecisionRecord.model_validate(data)


def _fresh(raw: dict, **provenance) -> DecisionRecord:
    """A copy of a seed record under a new UUIDv7 id."""
    data = copy.deepcopy(raw)
    data["id"] = str(uuid7())
    data["provenance"].update(provenance)
    return DecisionRecord.model_validate(data)


def _without(record: DecisionRecord, field: str) -> DecisionRecord:
    """The record with `provenance.<field>` set to None, bypassing validation (a defective record
    as some code path might hand it to the store)."""
    provenance = record.provenance.model_copy(update={field: None})
    return record.model_copy(update={"provenance": provenance})


def _counts(path: Path) -> dict[str, int]:
    db = sqlite3.connect(path)
    try:
        return {
            table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            for table in ("records", "entities", "edges")
        }
    finally:
        db.close()


@pytest.fixture
def store(tmp_path: Path):
    from scrubgpt_app.store import KnowledgeStore

    opened = KnowledgeStore(tmp_path / "store" / "k.sqlite")
    yield opened
    opened.close()


def _ids(stored) -> list[str]:
    return [str(s.record.id) for s in stored]


# --- criterion 1: many records per moment, never overwritten or merged ------------------------


def test_c1_two_records_on_one_moment_are_two_rows(store, seeds):
    """Criterion 1 (I2, app/server/CLAUDE.md rule 4; plan §4.3): "Many records per moment, never
    overwritten or merged: a second record for the same moment (or question) from another answer
    is a new row"."""
    q1 = seeds[0]
    assert q1["question_id"] == f"{CASE}.m01.q1"
    first = _fresh(q1)
    second = _fresh(q1)  # another answer to the same question on the same moment
    store.add(first, source="answer", answer_id=str(uuid7()))
    store.add(second, source="answer", answer_id=str(uuid7()))

    on_moment = store.for_moment(f"{CASE}.m01")
    assert sorted(_ids(on_moment)) == sorted([str(first.id), str(second.id)])
    assert _counts(store.path)["records"] == 2
    # Each row is that answer's record, unchanged.
    by_id = {str(s.record.id): s.record for s in on_moment}
    assert by_id[str(first.id)].model_dump(mode="json") == first.model_dump(mode="json")
    assert by_id[str(second.id)].model_dump(mode="json") == second.model_dump(mode="json")


def test_c1_re_adding_a_stored_id_is_refused_and_the_stored_record_is_unchanged(store, seeds):
    """Criterion 1: "re-adding a stored id is refused; nothing edits a stored record"."""
    from scrubgpt_app.store import StoreError

    original = _fresh(seeds[0])
    store.add(original, source="answer", answer_id=str(uuid7()))
    before = _counts(store.path)

    same = DecisionRecord.model_validate(original.model_dump(mode="json"))
    with pytest.raises(StoreError):
        store.add(same, source="answer", answer_id=str(uuid7()))

    changed = original.model_dump(mode="json")
    changed["action"]["text"] = {"ja": "上書きの試み", "en": "An attempt to overwrite"}
    with pytest.raises(StoreError):
        store.add(DecisionRecord.model_validate(changed), source="answer", answer_id=None)

    assert _counts(store.path) == before
    kept = store.get(str(original.id))
    assert kept is not None
    assert kept.record.model_dump(mode="json") == original.model_dump(mode="json")


def test_c1_the_store_offers_no_way_to_edit_replace_merge_or_delete_a_record():
    """Criterion 1: "nothing edits a stored record" (rule 4: "Never overwrite one surgeon's record
    with another's"). The store's public API has no update, replace, merge or delete operation."""
    from scrubgpt_app.store import KnowledgeStore

    public = [name for name in dir(KnowledgeStore) if not name.startswith("_")]
    forbidden = ("update", "replace", "merge", "delete", "remove", "edit", "upsert", "overwrite")
    assert [n for n in public if any(word in n.lower() for word in forbidden)] == []


def test_c1_no_http_route_edits_or_deletes_a_stored_record(answer_app, data_dir):
    """Criterion 1: "nothing edits a stored record", through the app server's HTTP API."""
    app = answer_app(data_dir)
    before = app.client.get(f"/api/cases/{CASE}/records").json()
    rid = before["records"][0]["record"]["id"]
    body = {"record": before["records"][0]["record"]}
    for method in ("PUT", "PATCH", "DELETE"):
        for path in (
            f"/api/cases/{CASE}/records",
            f"/api/cases/{CASE}/records/{rid}",
            f"/api/records/{rid}",
        ):
            response = app.client.request(method, path, json=body)
            # Any refusal will do (the spec names no status); it must not succeed.
            assert response.status_code >= 400, (method, path, response.status_code)
    assert app.client.get(f"/api/cases/{CASE}/records").json() == before


def test_c1_a_restart_neither_duplicates_seeds_nor_loses_answers(answer_app, data_dir, seeds):
    """Criterion 1 with README "At start-up the loaded cases' seed records are stored once": a
    second start on the same store keeps every row once (seeds are not re-added as new rows)."""
    first = answer_app(data_dir, db_name="shared.db")
    from scrubgpt_app.store import KnowledgeStore

    extra = _fresh(seeds[0])
    side = KnowledgeStore(first.db_path)
    side.add(extra, source="answer", answer_id=str(uuid7()))
    side.close()

    second = answer_app(data_dir, db_name="shared.db")
    records = second.client.get(f"/api/cases/{CASE}/records").json()["records"]
    ids = [r["record"]["id"] for r in records]
    assert len(ids) == len(set(ids)) == len(seeds) + 1
    assert str(extra.id) in ids


# --- criterion 2a: seeding stores all 7, the 🎙️ one unchanged ---------------------------------


def test_c2a_seeding_the_fixture_stores_all_seven_records_unchanged(answer_app, data_dir, seeds):
    """Criterion 2a (D-073): "Seeding case-fixture-01 stores all 7 seed records, including the 🎙️
    one with null confirmed_by/confirmed_at unchanged"."""
    assert len(seeds) == 7
    app = answer_app(data_dir)
    response = app.client.get(f"/api/cases/{CASE}/records")
    assert response.status_code == 200
    stored = response.json()["records"]
    assert len(stored) == 7
    assert all(item["source"] == "seed" for item in stored)
    by_id = {item["record"]["id"]: item["record"] for item in stored}
    for raw in seeds:
        assert raw["id"] in by_id
        expected = DecisionRecord.model_validate(raw).model_dump(mode="json")
        assert DecisionRecord.model_validate(by_id[raw["id"]]).model_dump(mode="json") == expected

    narration = by_id[NARRATION_ID]
    assert narration["provenance"]["trust_label"] == "narration_extracted"
    assert narration["provenance"]["confirmed_by"] is None
    assert narration["provenance"]["confirmed_at"] is None
    assert _counts(app.db_path)["records"] == 7


def test_c2a_add_seeds_is_idempotent(store, seeds):
    """Criterion 2a with app/server/CLAUDE.md rule 9 (idempotent seeding): seeding twice stores
    each seed once."""
    records = [DecisionRecord.model_validate(r) for r in seeds]
    store.add_seeds(records)
    store.add_seeds(records)
    assert sorted(_ids(store.for_case(CASE))) == sorted(r["id"] for r in seeds)


# --- criterion 2b: missing or null trust_label / attributed_to / generated_by --------------------


@pytest.mark.parametrize("field", ["trust_label", "attributed_to", "generated_by"])
@pytest.mark.parametrize("source", ["seed", "answer"])
def test_c2b_a_record_without_required_provenance_is_refused_and_nothing_is_written(
    store, seeds, field, source
):
    """Criterion 2b (D-073; app/server/CLAUDE.md rule 5): "A record with a missing or null
    trust_label, attributed_to or generated_by is refused and nothing is written"."""
    from scrubgpt_app.store import StoreError

    before = _counts(store.path)
    bad = _without(_fresh(seeds[0]), field)
    with pytest.raises(StoreError):
        store.add(bad, source=source, answer_id=str(uuid7()) if source == "answer" else None)
    assert _counts(store.path) == before
    assert store.get(str(bad.id)) is None


@pytest.mark.parametrize("field", ["trust_label", "attributed_to", "generated_by"])
def test_c2b_seeding_refuses_a_record_without_required_provenance(store, seeds, field):
    """Criterion 2b through `add_seeds` (the seeding path): refused, nothing written."""
    from scrubgpt_app.store import StoreError

    bad = _without(_fresh(seeds[0]), field)
    with pytest.raises(StoreError):
        store.add_seeds([bad])
    assert _counts(store.path)["records"] == 0


@pytest.mark.parametrize("field", ["generated_by", "trust_label", "attributed_to"])
def test_c2b_confirm_refuses_a_draft_without_required_provenance(
    answer_app, data_dir, draft_for, field
):
    """Criterion 2b through `POST /api/answers/confirm`: a draft whose provenance lacks the field
    (null, or the key missing) is refused (an ApiError), nothing is stored."""
    app = answer_app(data_dir)
    status, body = draft_for(app.client, f"{CASE}.m05.q1", text="レンズが曇った。カメラを拭いた。")
    assert status == 200, body
    before = _counts(app.db_path)
    for variant in ("null", "missing"):
        draft = copy.deepcopy(body["extract"]["draft"])
        if variant == "null":
            draft["provenance"][field] = None
        else:
            del draft["provenance"][field]
        response = app.client.post(
            "/api/answers/confirm",
            json={
                "answer_id": body["answer_id"],
                "draft": draft,
                "edits": [
                    {"field": "situation_cue.text", "text": "レンズが曇った", "lang": "ja"},
                    {"field": "action.text", "text": "カメラを拭いた", "lang": "ja"},
                ],
                "confirmed_by": "Dr Test",
            },
        )
        assert 400 <= response.status_code < 500, (variant, response.status_code)
        error = response.json()["error"]
        assert error["code"] == "bad_request"
        assert _counts(app.db_path) == before


# --- criterion 2c: confirmation rules ---------------------------------------------------------


@pytest.mark.parametrize("seed_index", [0, 1, 2, 3, 4, 6])
def test_c2c_a_non_narration_seed_without_confirmation_is_refused(store, seeds, seed_index):
    """Criterion 2c (D-073): "A non-🎙️ seed with null confirmation is refused"."""
    from scrubgpt_app.store import StoreError

    raw = seeds[seed_index]
    assert raw["provenance"]["trust_label"] != "narration_extracted"
    bad = _fresh(raw, confirmed_by=None, confirmed_at=None)
    with pytest.raises(StoreError):
        store.add(bad, source="seed")
    with pytest.raises(StoreError):
        store.add_seeds([bad])
    assert _counts(store.path)["records"] == 0


def test_c2c_a_narration_seed_without_confirmation_is_accepted(store, seeds):
    """Criterion 2c (D-073): "A seed record with trust_label: narration_extracted 🎙️ may have
    both confirmation fields null"."""
    raw = seeds[5]
    assert raw["id"] == NARRATION_ID
    record = DecisionRecord.model_validate(raw)
    store.add(record, source="seed")
    kept = store.get(NARRATION_ID)
    assert kept is not None
    assert kept.record.provenance.confirmed_by is None
    assert kept.record.provenance.confirmed_at is None


def test_c2c_an_unconfirmed_narration_record_through_the_answer_path_is_refused(store, seeds):
    """Criterion 2c/2d (D-073): "Records stored through Confirm always have confirmed_by and
    confirmed_at"; the 🎙️ exception is for seed records only."""
    from scrubgpt_app.store import StoreError

    record = _fresh(seeds[5])
    with pytest.raises(StoreError):
        store.add(record, source="answer", answer_id=str(uuid7()))
    assert _counts(store.path)["records"] == 0


@pytest.mark.parametrize("seed_index", [0, 5])
@pytest.mark.parametrize("source", ["seed", "answer"])
@pytest.mark.parametrize("half", ["only_by", "only_at"])
def test_c2c_exactly_one_confirmation_field_is_refused_for_any_record(
    store, seeds, seed_index, source, half
):
    """Criterion 2c (D-073): "a record of any label with only one of confirmed_by/confirmed_at set
    is refused" (🧪 and 🎙️, seed and answer)."""
    from scrubgpt_app.store import StoreError

    if half == "only_by":
        bad = _fresh(seeds[seed_index], confirmed_by="Dr Half", confirmed_at=None)
    else:
        bad = _fresh(seeds[seed_index], confirmed_by=None, confirmed_at="2026-10-18T09:00:00Z")
    with pytest.raises(StoreError):
        store.add(bad, source=source, answer_id=str(uuid7()) if source == "answer" else None)
    assert _counts(store.path)["records"] == 0


# --- criterion 2d: a record from Confirm always has both set ----------------------------------


@pytest.mark.parametrize("role", ["dev_team_simulated", "operating_surgeon"])
def test_c2d_a_record_from_confirm_has_the_answerer_and_a_utc_time(
    answer_app, data_dir, draft_for, role
):
    """Criterion 2d (D-073; plan §4.3 "The app assigns the UUIDv7 id and fills the confirmation
    fields when the surgeon taps Confirm"; §4.1 timestamps are UTC): "A record from Confirm always
    has both set (the answerer and a UTC time)"."""
    app = answer_app(data_dir)
    status, body = draft_for(
        app.client, f"{CASE}.m05.q1", role, text="レンズの曇りに気づいた。カメラを拭いた。"
    )
    assert status == 200, body
    start = datetime.now(UTC)
    response = app.client.post(
        "/api/answers/confirm",
        json={
            "answer_id": body["answer_id"],
            "draft": body["extract"]["draft"],
            "edits": [
                {"field": "situation_cue.text", "text": "レンズの曇り", "lang": "ja"},
                {"field": "action.text", "text": "カメラを拭いた", "lang": "ja"},
            ],
            "confirmed_by": "Dr Sato",
        },
    )
    end = datetime.now(UTC)
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["provenance"]["confirmed_by"] == "Dr Sato"
    at = datetime.fromisoformat(record["provenance"]["confirmed_at"].replace("Z", "+00:00"))
    assert at.utcoffset() is not None and at.utcoffset().total_seconds() == 0
    assert start.replace(microsecond=0) <= at <= end
    # The record id is a new UUIDv7 (plan §4.1).
    from uuid import UUID

    assert UUID(record["id"]).version == 7
    stored = {
        r["record"]["id"]: r for r in app.client.get(f"/api/cases/{CASE}/records").json()["records"]
    }
    assert stored[record["id"]]["source"] == "answer"
    assert stored[record["id"]]["record"]["provenance"]["confirmed_by"] == "Dr Sato"


def test_c2d_confirm_without_a_confirmer_is_refused(answer_app, data_dir, draft_for):
    """Criterion 2d: no record from Confirm without `confirmed_by` (rule 5: "confirmation info")."""
    app = answer_app(data_dir)
    status, body = draft_for(app.client, f"{CASE}.m05.q1", text="カメラを拭いた")
    assert status == 200, body
    before = _counts(app.db_path)
    for confirmed_by in ("", None):
        payload = {
            "answer_id": body["answer_id"],
            "draft": body["extract"]["draft"],
            "edits": [
                {"field": "situation_cue.text", "text": "曇り", "lang": "ja"},
                {"field": "action.text", "text": "拭いた", "lang": "ja"},
            ],
            "confirmed_by": confirmed_by,
        }
        response = app.client.post("/api/answers/confirm", json=payload)
        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "bad_request"
    assert _counts(app.db_path) == before


# --- criterion 3: migrations, WAL, APP_DB_PATH ------------------------------------------------


def test_c3_migrations_are_ordered_recorded_and_a_rerun_is_a_no_op(tmp_path):
    """Criterion 3 (app/server/CLAUDE.md rule 3: "Schema changes are migration scripts, kept small
    and ordered"; README "Migrations are ordered and applied once (schema_migrations)")."""
    from scrubgpt_app.store import KnowledgeStore

    path = tmp_path / "m" / "k.sqlite"
    KnowledgeStore(path).close()
    db = sqlite3.connect(path)
    rows = db.execute("SELECT version, applied_at FROM schema_migrations ORDER BY rowid").fetchall()
    db.close()
    versions = [v for v, _ in rows]
    assert versions, "schema_migrations records the applied migrations"
    assert versions == sorted(versions) == list(range(versions[0], versions[0] + len(versions)))
    assert all(applied for _, applied in rows)

    KnowledgeStore(path).close()  # re-run
    db = sqlite3.connect(path)
    again = db.execute(
        "SELECT version, applied_at FROM schema_migrations ORDER BY rowid"
    ).fetchall()
    db.close()
    assert again == rows


def test_c3_migrate_reports_nothing_applied_on_a_rerun(tmp_path):
    """Criterion 3: "a re-run is a no-op" through the `migrate` entry point."""
    from scrubgpt_app.store import connect, migrate

    path = tmp_path / "k.sqlite"
    db = connect(path)
    first = migrate(db)
    assert first and first == sorted(first)
    assert migrate(db) == []
    db.close()


def test_c3_a_rerun_keeps_the_data(tmp_path, seeds):
    """Criterion 3: re-running the migrations on a store with data changes nothing."""
    from scrubgpt_app.store import KnowledgeStore

    path = tmp_path / "k.sqlite"
    first = KnowledgeStore(path)
    first.add_seeds([DecisionRecord.model_validate(r) for r in seeds])
    first.close()
    before = _counts(path)
    KnowledgeStore(path).close()
    assert _counts(path) == before


def test_c3_wal_is_on(tmp_path):
    """Criterion 3 (rule 3: "Use WAL mode")."""
    from scrubgpt_app.store import KnowledgeStore

    path = tmp_path / "k.sqlite"
    store = KnowledgeStore(path)
    try:
        db = sqlite3.connect(path)
        mode = db.execute("PRAGMA journal_mode").fetchone()[0]
        db.close()
    finally:
        store.close()
    assert mode.lower() == "wal"


def test_c3_the_app_opens_its_store_at_app_db_path_and_writes_nowhere_else(
    make_settings, data_dir, tmp_path, repo_root, draft_for, wire_brain
):
    """Criterion 3 (rule 3: "keep the database file local (APP_DB_PATH)"; brief: "the store file
    is at APP_DB_PATH (never written elsewhere by the app)")."""
    from fastapi.testclient import TestClient
    from scrubgpt_app.api import create_app

    target = tmp_path / "chosen" / "nested" / "knowledge.sqlite"
    local = repo_root / "app" / "server" / ".local"
    local_existed = local.exists()
    repo_dbs = {p for p in repo_root.glob("**/*.sqlite*") if ".venv" not in p.parts}
    data_before = {p.relative_to(data_dir) for p in data_dir.rglob("*")}

    brain, _ = wire_brain()
    app = create_app(make_settings(data_dir, APP_DB_PATH=str(target)), brain=brain)
    with TestClient(app) as client:
        status, body = draft_for(client, f"{CASE}.m05.q1", text="カメラを拭いた")
        assert status == 200
        response = client.post(
            "/api/answers/confirm",
            json={
                "answer_id": body["answer_id"],
                "draft": body["extract"]["draft"],
                "edits": [
                    {"field": "situation_cue.text", "text": "曇り", "lang": "ja"},
                    {"field": "action.text", "text": "拭いた", "lang": "ja"},
                ],
                "confirmed_by": "Dr Test",
            },
        )
        assert response.status_code == 201

    assert target.is_file()
    db = sqlite3.connect(target)
    assert db.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 8
    db.close()
    assert local.exists() == local_existed, "the app wrote app/server/.local"
    assert {p for p in repo_root.glob("**/*.sqlite*") if ".venv" not in p.parts} == repo_dbs
    assert {p.relative_to(data_dir) for p in data_dir.rglob("*")} == data_before, (
        "nothing is written into DATA_DIR"
    )


def test_c3_the_records_table_rows_hold_contract_valid_records(answer_app, data_dir):
    """Criterion 3 / plan §4.3: what the store returns validates against the contract model."""
    app = answer_app(data_dir)
    for item in app.client.get(f"/api/cases/{CASE}/records").json()["records"]:
        DecisionRecord.model_validate(item["record"])
        assert item["source"] in ("seed", "answer")
        assert isinstance(item["stored_at"], str) and item["stored_at"]
        json.dumps(item)
