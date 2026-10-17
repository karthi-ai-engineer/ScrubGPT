"""The knowledge store (I2): SQLite at `APP_DB_PATH`, kept local (never in the Drive folder).

- **Every viewpoint is kept** (app/server/CLAUDE.md rule 4): each Decision Record is its own row;
  a record id can be stored once, and nothing ever overwrites, edits or merges a stored record.
- **Provenance is required** (rule 5): a record without `trust_label`, `attributed_to` and
  `generated_by` is refused. An answered record (`source="answer"`) must also be confirmed
  (`confirmed_by`, `confirmed_at`); a seed record must be too, except a narration-mined one
  (`narration_extracted` 🎙️), which is stored as not yet confirmed (issue #20, D-073);
  exactly one of the two confirmation fields set is refused for any record.
- **Small, ordered migrations** (rule 3), recorded in `schema_migrations`; re-running is a no-op.
  WAL mode, foreign keys on.
- A record also adds **entities and edges** (the knowledge graph behind J5/J8): the case, its
  step, its moment, its obstacle and the record itself, each edge tagged with the record it
  came from and that record's trust label.
"""

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from scrubgpt_contracts.models.common import TrustLabel
from scrubgpt_contracts.models.decision_record import DecisionRecord

Source = Literal["seed", "answer"]

MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE records (
            id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            moment_id TEXT,
            question_id TEXT,
            step_id TEXT NOT NULL,
            language TEXT NOT NULL,
            kind TEXT NOT NULL,
            trust_label TEXT NOT NULL,
            attributed_to TEXT NOT NULL,
            confirmed_by TEXT,
            confirmed_at TEXT,
            source TEXT NOT NULL CHECK (source IN ('seed', 'answer')),
            answer_id TEXT,
            body TEXT NOT NULL,
            stored_at TEXT NOT NULL
        );
        CREATE INDEX records_by_case ON records (case_id);
        CREATE INDEX records_by_moment ON records (moment_id);
        CREATE TABLE entities (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            case_id TEXT
        );
        CREATE TABLE edges (
            src TEXT NOT NULL REFERENCES entities (id),
            dst TEXT NOT NULL REFERENCES entities (id),
            kind TEXT NOT NULL,
            record_id TEXT NOT NULL REFERENCES records (id),
            trust_label TEXT NOT NULL,
            PRIMARY KEY (src, dst, kind, record_id)
        );
        """,
    ),
)
"""Ordered schema migrations: (version, SQL). Append only; never edit an applied one."""


class StoreError(ValueError):
    """A record the store refuses (missing provenance, or an id already stored)."""


@dataclass(frozen=True)
class StoredRecord:
    record: DecisionRecord
    source: Source
    answer_id: str | None
    stored_at: str


@dataclass(frozen=True)
class GraphChange:
    """What one stored record added to the graph (the `graph.updated` payload)."""

    case_id: str
    nodes: list[dict[str, str]]
    edges: list[dict[str, str]]


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def migrate(connection: sqlite3.Connection) -> list[int]:
    """Apply the migrations not applied yet, in order; returns the versions applied now."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT)"
    )
    done = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
    applied = []
    for version, sql in MIGRATIONS:
        if version in done:
            continue
        connection.execute("BEGIN")
        try:
            for statement in filter(str.strip, sql.split(";")):
                connection.execute(statement)
            connection.execute("INSERT INTO schema_migrations VALUES (?, ?)", (version, _now()))
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        applied.append(version)
    return applied


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def check_provenance(record: DecisionRecord, source: Source) -> None:
    """Rule 5 (and issue #20): raises `StoreError` naming what is missing."""
    provenance = record.provenance
    missing = [
        name
        for name, value in [
            ("trust_label", provenance.trust_label),
            ("attributed_to", provenance.attributed_to),
            ("generated_by", provenance.generated_by),
        ]
        if value is None
    ]
    confirmed = (provenance.confirmed_by is not None, provenance.confirmed_at is not None)
    if confirmed[0] != confirmed[1]:
        raise StoreError(
            f"record {record.id} has only one of confirmed_by and confirmed_at (D-073)"
        )
    mined = source == "seed" and provenance.trust_label is TrustLabel.NARRATION_EXTRACTED
    if not mined:
        missing += [
            name
            for name, value in [
                ("confirmed_by", provenance.confirmed_by),
                ("confirmed_at", provenance.confirmed_at),
            ]
            if value is None
        ]
    if missing:
        raise StoreError(f"record {record.id} can't be stored without {', '.join(missing)}")


class KnowledgeStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._db = connect(path)
        self._lock = threading.Lock()
        migrate(self._db)

    def close(self) -> None:
        self._db.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield self._db
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def add(
        self, record: DecisionRecord, *, source: Source, answer_id: str | None = None
    ) -> GraphChange:
        """Store one record (never replacing another) and its graph entities and edges."""
        check_provenance(record, source)
        record_id = str(record.id)
        with self._transaction() as db:
            if db.execute("SELECT 1 FROM records WHERE id = ?", (record_id,)).fetchone():
                raise StoreError(
                    f"record {record_id} is already stored; records are never replaced"
                )
            provenance = record.provenance
            db.execute(
                "INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record_id,
                    record.case_id,
                    record.moment_id,
                    record.question_id,
                    record.step_id,
                    record.language.value,
                    record.kind.value,
                    provenance.trust_label.value,
                    provenance.attributed_to.value,
                    provenance.confirmed_by,
                    provenance.confirmed_at.isoformat() if provenance.confirmed_at else None,
                    source,
                    answer_id,
                    record.model_dump_json(by_alias=True),
                    _now(),
                ),
            )
            return self._link(db, record)

    def _link(self, db: sqlite3.Connection, record: DecisionRecord) -> GraphChange:
        record_id = str(record.id)
        label = record.provenance.trust_label.value
        nodes = [("case", record.case_id), ("step", record.step_id), ("record", record_id)]
        edges = [(record.step_id, record.case_id, "step_of")]
        anchor = record.step_id
        if record.moment_id is not None:
            nodes.append(("moment", record.moment_id))
            edges.append((record.moment_id, record.step_id, "moment_in"))
            anchor = record.moment_id
        edges.append((record_id, anchor, "answers" if record.question_id else "about"))
        if record.obstacle is not None:
            obstacle = record.obstacle.type or record.obstacle.family.value
            nodes.append(("obstacle", obstacle))
            edges.append((record_id, obstacle, "obstacle"))
        added_nodes = []
        for kind, node_id in nodes:
            cursor = db.execute(
                "INSERT OR IGNORE INTO entities VALUES (?, ?, ?)", (node_id, kind, record.case_id)
            )
            if cursor.rowcount:
                added_nodes.append({"id": node_id, "kind": kind})
        added_edges = []
        for src, dst, kind in edges:
            db.execute(
                "INSERT OR IGNORE INTO edges VALUES (?, ?, ?, ?, ?)",
                (src, dst, kind, record_id, label),
            )
            added_edges.append(
                {"src": src, "dst": dst, "kind": kind, "record_id": record_id, "trust_label": label}
            )
        return GraphChange(record.case_id, added_nodes, added_edges)

    def add_seeds(self, records: Iterable[DecisionRecord]) -> int:
        """Store seed records not stored yet (by id); returns how many were added. Idempotent."""
        added = 0
        for record in records:
            if self.get(str(record.id)) is None:
                self.add(record, source="seed")
                added += 1
        return added

    def _rows(self, where: str, args: tuple) -> list[StoredRecord]:
        with self._lock:
            rows = self._db.execute(
                f"SELECT body, source, answer_id, stored_at FROM records WHERE {where} "
                "ORDER BY stored_at, id",
                args,
            ).fetchall()
        return [
            StoredRecord(
                DecisionRecord.model_validate(json.loads(row["body"])),
                row["source"],
                row["answer_id"],
                row["stored_at"],
            )
            for row in rows
        ]

    def get(self, record_id: str) -> StoredRecord | None:
        rows = self._rows("id = ?", (record_id,))
        return rows[0] if rows else None

    def for_case(self, case_id: str) -> list[StoredRecord]:
        return self._rows("case_id = ?", (case_id,))

    def for_moment(self, moment_id: str) -> list[StoredRecord]:
        return self._rows("moment_id = ?", (moment_id,))

    def answered_questions(self, case_id: str) -> set[str]:
        """Questions of the case that have at least one record from an answer in the app."""
        with self._lock:
            rows = self._db.execute(
                "SELECT DISTINCT question_id FROM records "
                "WHERE case_id = ? AND source = 'answer' AND question_id IS NOT NULL",
                (case_id,),
            ).fetchall()
        return {row[0] for row in rows}
