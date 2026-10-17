"""The knowledge store (I2): every viewpoint kept, provenance required, ordered migrations."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from scrubgpt_app.settings import REPO_ROOT
from scrubgpt_app.store import KnowledgeStore, StoreError, connect, migrate
from scrubgpt_contracts.models.decision_record import DecisionRecord
from uuid6 import uuid7

SEEDS = REPO_ROOT / "contracts/fixtures/cases/case-fixture-01/seed_records.json"


def seeds() -> list[DecisionRecord]:
    data = json.loads(SEEDS.read_text(encoding="utf-8"))
    return [DecisionRecord.model_validate(record) for record in data["records"]]


def copy_of(record: DecisionRecord, **provenance: object) -> DecisionRecord:
    data = record.model_dump(mode="json", by_alias=True)
    data["id"] = str(uuid7())
    data["provenance"].update(provenance)
    return DecisionRecord.model_validate(data)


@pytest.fixture
def store(tmp_path: Path) -> KnowledgeStore:
    return KnowledgeStore(tmp_path / "store.sqlite")


def test_wal_and_migrations_are_ordered_and_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "store.sqlite"
    first = connect(path)
    assert migrate(first) == [1]
    assert migrate(first) == []
    assert first.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    first.close()
    KnowledgeStore(path).close()  # opening again applies nothing
    versions = sqlite3.connect(path).execute("SELECT version FROM schema_migrations").fetchall()
    assert versions == [(1,)]


def test_seeds_are_stored_once(store: KnowledgeStore) -> None:
    records = seeds()
    assert store.add_seeds(records) == len(records)
    assert store.add_seeds(records) == 0
    assert len(store.for_case("case-fixture-01")) == len(records)


def test_every_viewpoint_is_its_own_row_and_none_is_replaced(store: KnowledgeStore) -> None:
    first = seeds()[0]
    store.add(first, source="seed")
    second = copy_of(first)  # another answer about the same moment
    store.add(second, source="answer", answer_id=str(uuid7()))
    assert {str(s.record.id) for s in store.for_moment(first.moment_id)} == {
        str(first.id),
        str(second.id),
    }
    with pytest.raises(StoreError, match="never replaced"):
        store.add(first, source="seed")


@pytest.mark.parametrize("missing", ["generated_by", "confirmed_by", "confirmed_at"])
def test_a_record_without_provenance_is_refused(store: KnowledgeStore, missing: str) -> None:
    record = copy_of(seeds()[0], **{missing: None})
    with pytest.raises(StoreError, match=missing):
        store.add(record, source="answer")
    assert store.get(str(record.id)) is None


def test_a_mined_narration_seed_may_be_unconfirmed(store: KnowledgeStore) -> None:
    narration = next(r for r in seeds() if r.provenance.trust_label.value == "narration_extracted")
    assert narration.provenance.confirmed_by is None
    store.add(narration, source="seed")
    with pytest.raises(StoreError, match="confirmed_by"):  # but never as an answer
        store.add(copy_of(narration), source="answer")


def test_graph_change_names_new_nodes_and_record_edges(store: KnowledgeStore) -> None:
    record = seeds()[0]
    change = store.add(record, source="seed")
    kinds = {node["kind"] for node in change.nodes}
    assert {"case", "step", "moment", "record"} <= kinds
    edge = next(e for e in change.edges if e["src"] == str(record.id))
    assert edge["dst"] == record.moment_id and edge["kind"] == "answers"
    assert edge["trust_label"] == record.provenance.trust_label.value
    later = copy_of(record, confirmed_at=datetime.now(UTC).isoformat())
    again = store.add(later, source="seed")
    assert [node["kind"] for node in again.nodes] == ["record"]  # case/step/moment already known


def test_answered_questions_count_only_app_answers(store: KnowledgeStore) -> None:
    store.add_seeds(seeds())
    assert store.answered_questions("case-fixture-01") == set()
    answered = copy_of(seeds()[0])
    store.add(answered, source="answer", answer_id=str(uuid7()))
    assert store.answered_questions("case-fixture-01") == {answered.question_id}
