"""#9 AC1, AC2, AC10: timestamps on the wire, provenance coherence and canonical UUIDs (Team Lead
triage on issue #9, logged as D-058; refines D-048 and plan §4.1).

Triage decisions quoted by the tests below:
- Timestamps: "on the wire, only strings matching
  `^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d+)?(Z|\\+00:00)$` (uppercase `T`/`Z`). Numbers,
  numeric strings, a space separator, other offsets and naive values are rejected. Python callers
  may still pass an aware UTC `datetime`. Output is unchanged (`...Z`)."
- Provenance: "`attributed_to: dev_team_simulated` => `trust_label: simulated`, checked in the
  `Provenance` model. ... The reverse (`simulated` => `dev_team_simulated`) is not required
  (synthetic TTS narration, D-027)."
- UUIDs: "`RecordId`/`AnswerId` on the wire use the canonical lowercase hyphenated form
  `^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`; anything else is
  rejected. So the raw JSON string always equals `str(id)`."
"""

from __future__ import annotations

import copy
import json
import re
import typing
import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Annotated, Any

import pytest
import uuid6
from pydantic import BaseModel, TypeAdapter, ValidationError
from scrubgpt_contracts.models import brain_api, case_package, common, decision_record, reference
from scrubgpt_contracts.models.case_package import Moments, SeedRecords, Timeline
from scrubgpt_contracts.models.common import (
    AnswerId,
    Evidence,
    Provenance,
    RecordId,
    Role,
    TrustLabel,
)
from scrubgpt_contracts.models.decision_record import (
    DecisionRecord,
    DecisionRecordDraft,
    confirm_draft,
)

CASE_ID = "case-fixture-01"
EVIDENCE = TypeAdapter(Evidence)

TRIAGE_TIMESTAMP = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$"
TRIAGE_UUID7 = r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"


def _provenance(**changes: Any) -> dict[str, Any]:
    base = {
        "trust_label": "operating_surgeon",
        "attributed_to": "operating_surgeon",
        "generated_by": None,
        "confirmed_by": "x",
        "confirmed_at": "2026-10-21T09:30:00Z",
    }
    base.update(changes)
    return base


def _draft(record: dict[str, Any]) -> dict[str, Any]:
    draft = copy.deepcopy(record)
    draft["id"] = None
    draft["provenance"]["confirmed_by"] = None
    draft["provenance"]["confirmed_at"] = None
    return draft


# --- AC1: timestamps ----------------------------------------------------------------------------

AC1_REJECTED = [
    1792000000,
    "1792000000",
    "2026-10-21 09:30:00Z",
    "2026-10-21T09:30:00",
    "2026-10-21T18:30:00+09:00",
]
"""AC1, verbatim: each raises `ValidationError`."""

EDGE_REJECTED = [
    1792000000.0,
    1792000000.5,
    True,
    "1792000000.5",
    "2026-10-21t09:30:00Z",  # lowercase T
    "2026-10-21T09:30:00z",  # lowercase Z
    "2026-10-21T09:30:00-00:00",  # another offset form
    "2026-10-21T09:30:00+0000",
    "2026-10-21T09:30:00+00",
    "2026-10-21T04:30:00-05:00",
    "2026-10-21T09:30:00.5",  # naive with fraction
    "2026-10-21",
    "2026-10-21T09:30Z",  # no seconds
    "20261021T093000Z",  # basic (compact) ISO form
    "2026-10-21T09:30:00,5Z",  # comma fraction
    "2026-10-21T09:30:00.Z",
    " 2026-10-21T09:30:00Z",
    "2026-10-21T09:30:00Z ",
    "2026-10-21T09:30:00Z\n",
    "２０２６-10-21T09:30:00Z",  # full-width digits (the pattern's digits are ASCII)
    "2026-13-21T09:30:00Z",  # matches the pattern but isn't a date
    "",
    b"2026-10-21T09:30:00Z",
    date(2026, 10, 21),
    datetime(2026, 10, 21, 9, 30),  # naive datetime
    datetime(2026, 10, 21, 18, 30, tzinfo=timezone(timedelta(hours=9))),
]
"""Other inputs the triage pattern or D-048 (naive / non-UTC) rejects."""

AC1_ACCEPTED = [
    ("2026-10-21T09:30:00Z", datetime(2026, 10, 21, 9, 30, tzinfo=UTC)),
    ("2026-10-21T09:30:00.5Z", datetime(2026, 10, 21, 9, 30, 0, 500000, tzinfo=UTC)),
    ("2026-10-21T09:30:00+00:00", datetime(2026, 10, 21, 9, 30, tzinfo=UTC)),
    (datetime(2026, 10, 21, 9, 30, tzinfo=UTC), datetime(2026, 10, 21, 9, 30, tzinfo=UTC)),
]
"""AC1, verbatim: accepted, each dumping as `...Z` (paired with the instant it stands for)."""


def _ids(values):
    return [repr(v) for v in values]


@pytest.mark.parametrize("stamp", AC1_REJECTED, ids=_ids(AC1_REJECTED))
def test_9ac1_provenance_rejects_the_listed_non_iso_timestamps(stamp):
    """#9 AC1: "`Provenance(..., confirmed_at=X)` raises `ValidationError` for X = `1792000000`,
    `"1792000000"`, `"2026-10-21 09:30:00Z"`, `"2026-10-21T09:30:00"` and
    `"2026-10-21T18:30:00+09:00"`"."""
    with pytest.raises(ValidationError):
        Provenance(**_provenance(confirmed_at=stamp))
    with pytest.raises(ValidationError):
        Provenance.model_validate(_provenance(confirmed_at=stamp))


@pytest.mark.parametrize("stamp", EDGE_REJECTED, ids=_ids(EDGE_REJECTED))
def test_9ac1_provenance_rejects_other_forms_outside_the_pattern(stamp):
    """#9 triage: "on the wire, only strings matching `...(Z|\\+00:00)$` (uppercase `T`/`Z`).
    Numbers, numeric strings, a space separator, other offsets and naive values are rejected";
    D-048: naive and non-UTC values are rejected (also for a Python `datetime`)."""
    with pytest.raises(ValidationError):
        Provenance.model_validate(_provenance(confirmed_at=stamp))


@pytest.mark.parametrize(("stamp", "instant"), AC1_ACCEPTED, ids=_ids([a for a, _ in AC1_ACCEPTED]))
def test_9ac1_provenance_accepts_iso_utc_and_dumps_with_z(stamp, instant):
    """#9 AC1: "It accepts `"2026-10-21T09:30:00Z"`, `"2026-10-21T09:30:00.5Z"`,
    `"2026-10-21T09:30:00+00:00"` and an aware UTC `datetime`. Each accepted value dumps as
    `...Z`"."""
    parsed = Provenance(**_provenance(confirmed_at=stamp))
    assert parsed.confirmed_at == instant
    assert parsed.confirmed_at.utcoffset() == timedelta(0)
    for out in (
        parsed.model_dump(mode="json")["confirmed_at"],
        json.loads(parsed.model_dump_json())["confirmed_at"],
    ):
        assert isinstance(out, str) and out.endswith("Z"), out
        assert re.match(TRIAGE_TIMESTAMP, out), out  # what we write, we can read back
        assert datetime.fromisoformat(out) == instant
        assert Provenance.model_validate(_provenance(confirmed_at=out)).confirmed_at == instant


@pytest.mark.parametrize("stamp", AC1_REJECTED + ["2026-10-21T09:30:00-00:00", "1792000000.5"])
def test_9ac1_json_wire_rejects_numbers_and_non_iso_strings(stamp):
    """#9 AC1 on the wire (`model_validate_json`): numbers and non-ISO strings are rejected
    there too."""
    body = json.dumps(_provenance(confirmed_at=stamp))
    with pytest.raises(ValidationError):
        Provenance.model_validate_json(body)


@pytest.mark.parametrize("stamp", [a for a, _ in AC1_ACCEPTED if isinstance(a, str)])
def test_9ac1_json_wire_accepts_the_iso_forms(stamp):
    """#9 AC1 on the wire: the three accepted string forms parse from JSON and dump with `Z`."""
    parsed = Provenance.model_validate_json(json.dumps(_provenance(confirmed_at=stamp)))
    assert json.loads(parsed.model_dump_json())["confirmed_at"].endswith("Z")


def _contract_models() -> list[type[BaseModel]]:
    seen: dict[str, type[BaseModel]] = {}
    for module in (common, case_package, decision_record, reference, brain_api):
        for value in vars(module).values():
            if isinstance(value, type) and issubclass(value, BaseModel) and value is not BaseModel:
                seen[f"{value.__module__}.{value.__qualname__}"] = value
    return list(seen.values())


def _mentions_datetime(annotation: Any) -> bool:
    """`datetime`, or one of pydantic's datetime marker types (`AwareDatetime`, ...)."""
    if isinstance(annotation, type) and (
        issubclass(annotation, datetime)
        or (
            annotation.__module__.startswith("pydantic")
            and annotation.__name__.endswith("Datetime")
        )
    ):
        return True
    return any(_mentions_datetime(arg) for arg in typing.get_args(annotation))


def _datetime_fields() -> list[tuple[type[BaseModel], str, Any]]:
    """Every contract-model field whose type involves `datetime` (a wall-clock timestamp)."""
    out = []
    for model in _contract_models():
        for name, info in model.model_fields.items():
            if _mentions_datetime(info.annotation):
                annotation = info.annotation
                if info.metadata:
                    annotation = Annotated[(annotation, *info.metadata)]
                out.append((model, name, annotation))
    return out


def test_9ac1_timestamp_fields_found():
    """#9 AC1 "the same holds for every other `UtcDatetime` field": the contract's timestamp
    fields are found (at least `Provenance.confirmed_at`, plan §4.1)."""
    names = {f"{m.__name__}.{n}" for m, n, _ in _datetime_fields()}
    assert "Provenance.confirmed_at" in names, names


@pytest.mark.parametrize(
    ("model", "name", "annotation"),
    _datetime_fields(),
    ids=[f"{m.__name__}.{n}" for m, n, _ in _datetime_fields()],
)
def test_9ac1_every_timestamp_field_follows_the_rule(model, name, annotation):
    """#9 AC1: "The same holds for every other `UtcDatetime` field": the same rejects and accepts
    for each timestamp field of every contract model (python and JSON input)."""
    adapter = TypeAdapter(annotation)
    accepted = []
    for stamp in AC1_REJECTED + EDGE_REJECTED:
        try:
            adapter.validate_python(stamp)
        except ValidationError:
            continue
        accepted.append(stamp)
    for stamp in AC1_REJECTED:
        try:
            adapter.validate_json(json.dumps(stamp))
        except ValidationError:
            continue
        accepted.append(f"json:{stamp!r}")
    assert not accepted, f"{model.__name__}.{name} accepted {accepted}"
    for stamp, instant in AC1_ACCEPTED:
        value = adapter.validate_python(stamp)
        if value is None:  # a field that may only be null (e.g. a draft's confirmed_at)
            continue
        assert value == instant
        assert adapter.dump_python(value, mode="json").endswith("Z")


def test_9ac1_draft_confirmed_at_stays_null_only():
    """Plan §4.3: a draft's `provenance.confirmed_at` is null; a timestamp is no reason to accept
    it there either."""
    adapter = TypeAdapter(decision_record.DraftProvenance)
    base = _provenance(confirmed_by=None, confirmed_at=None)
    adapter.validate_python(base)
    with pytest.raises(ValidationError):
        adapter.validate_python(dict(base, confirmed_at="2026-10-21T09:30:00Z"))


@pytest.mark.parametrize("stamp", ["2026-10-16 06:00:00Z", 1792000000, "2026-10-16T15:00:00+09:00"])
def test_9ac1_nested_timestamps_in_contract_files_are_checked(docs, stamp):
    """#9 AC1 for every place a `Provenance` appears: a seed record, a timeline item and a
    moment carrying a non-ISO `confirmed_at` are rejected (python and JSON)."""
    seeds = copy.deepcopy(docs["seed_records.json"])
    seeds["records"][0]["provenance"]["confirmed_at"] = stamp
    timeline = copy.deepcopy(docs["timeline.json"])
    timeline["utterances"][0]["provenance"]["confirmed_by"] = "dr-a"
    timeline["utterances"][0]["provenance"]["confirmed_at"] = stamp
    moments = copy.deepcopy(docs["moments.json"])
    moments["moments"][0]["provenance"]["confirmed_by"] = "dr-a"
    moments["moments"][0]["provenance"]["confirmed_at"] = stamp
    for model, doc in ((SeedRecords, seeds), (Timeline, timeline), (Moments, moments)):
        with pytest.raises(ValidationError):
            model.model_validate(doc)
        with pytest.raises(ValidationError):
            model.model_validate_json(json.dumps(doc, ensure_ascii=False))
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(seeds["records"][0])


def test_9ac1_fixture_timestamps_round_trip_unchanged(docs):
    """#9 AC1 + "Output is unchanged (`...Z`)": every fixture seed record dumps its
    `confirmed_at` exactly as written."""
    for raw in docs["seed_records.json"]["records"]:
        record = DecisionRecord.model_validate_json(json.dumps(raw, ensure_ascii=False))
        dumped = json.loads(record.model_dump_json())
        assert dumped["provenance"]["confirmed_at"] == raw["provenance"]["confirmed_at"]


def test_9ac1_validate_case_rejects_a_seed_record_with_a_space_separated_timestamp(
    data_dir, run_validate
):
    """#9 AC1 through `scrubgpt-validate case`: the issue's example
    (`"2026-10-21 09:30:00Z"` in a seed record) is an error naming seed_records.json (exit 1)."""
    seeds = data_dir.load("seed_records.json")
    seeds["records"][0]["provenance"]["confirmed_at"] = "2026-10-21 09:30:00Z"
    data_dir.save("seed_records.json", seeds)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert any("seed_records.json" in ln for ln in result.error_lines), result.output


@pytest.mark.parametrize(
    "when",
    [
        datetime(2026, 10, 21, 18, 30, tzinfo=timezone(timedelta(hours=9))),
        datetime(2026, 10, 21, 9, 30),
    ],
    ids=["+09:00", "naive"],
)
def test_9ac1_confirm_draft_rejects_a_non_utc_or_naive_datetime(docs, when):
    """#9 AC1 + D-048: `confirm_draft(confirmed_at=...)` fills a `UtcDatetime` field, so a
    non-UTC or naive `datetime` is rejected; an aware UTC one is accepted and dumps with `Z`."""
    draft = DecisionRecordDraft.model_validate(_draft(docs["seed_records.json"]["records"][0]))
    kwargs = {"record_id": str(uuid6.uuid7()), "confirmed_by": "dr-a"}
    with pytest.raises(ValueError):
        confirm_draft(draft, confirmed_at=when, **kwargs)
    ok = confirm_draft(draft, confirmed_at=datetime(2026, 10, 21, 9, 30, tzinfo=UTC), **kwargs)
    assert json.loads(ok.model_dump_json())["provenance"]["confirmed_at"] == "2026-10-21T09:30:00Z"


def _schema_patterns(node: Any, key: str) -> list[str]:
    """Every `pattern` inside the schema of each property named `key`."""
    found: list[str] = []

    def patterns(sub: Any) -> None:
        if isinstance(sub, dict):
            if isinstance(sub.get("pattern"), str):
                found.append(sub["pattern"])
            for value in sub.values():
                patterns(value)
        elif isinstance(sub, list):
            for value in sub:
                patterns(value)

    def walk(sub: Any) -> None:
        if isinstance(sub, dict):
            props = sub.get("properties")
            if isinstance(props, dict) and key in props:
                patterns(props[key])
            for value in sub.values():
                walk(value)
        elif isinstance(sub, list):
            for value in sub:
                walk(value)

    walk(node)
    return found


def _ecma_like(pattern: str) -> re.Pattern[str]:
    # JSON Schema patterns are ECMA-262: `$` is the end of input and `\d` is ASCII.
    return re.compile(pattern.replace("$", r"\Z"), re.ASCII)


def test_9ac1_committed_schema_carries_the_timestamp_pattern(paths):
    """#9 triage: "The UUID and timestamp patterns change the generated `schema/`/`ts/`": the
    committed `DecisionRecord` schema's `confirmed_at` pattern accepts and rejects the AC1
    strings like the triage pattern does."""
    schema = json.loads(
        (paths["repo"] / "contracts" / "schema" / "DecisionRecord.schema.json").read_text("utf-8")
    )
    found = _schema_patterns(schema, "confirmed_at")
    assert found, "no pattern on confirmed_at in schema/DecisionRecord.schema.json"
    strings = [s for s in AC1_REJECTED + EDGE_REJECTED if isinstance(s, str)]
    strings += [a for a, _ in AC1_ACCEPTED if isinstance(a, str)]
    strings = [s for s in strings if s != "2026-13-21T09:30:00Z"]  # a pattern can't check dates
    triage = _ecma_like(TRIAGE_TIMESTAMP)
    for pattern in found:
        mine = _ecma_like(pattern)
        diff = [s for s in strings if bool(mine.search(s)) != bool(triage.search(s))]
        assert not diff, f"schema pattern {pattern!r} disagrees with the triage on {diff}"


# --- AC2: provenance coherence ------------------------------------------------------------------

NOT_SIMULATED = [t.value for t in TrustLabel if t is not TrustLabel.SIMULATED]


@pytest.mark.parametrize("label", NOT_SIMULATED)
def test_9ac2_dev_team_simulated_requires_trust_label_simulated(label):
    """#9 AC2: "`Provenance(trust_label="operating_surgeon", attributed_to="dev_team_simulated",
    ...)` raises" - and so does every other label that isn't `simulated` (triage:
    "`attributed_to: dev_team_simulated` => `trust_label: simulated`")."""
    with pytest.raises(ValidationError):
        Provenance(**_provenance(trust_label=label, attributed_to="dev_team_simulated"))
    with pytest.raises(ValidationError):
        Provenance.model_validate_json(
            json.dumps(_provenance(trust_label=label, attributed_to="dev_team_simulated"))
        )


def test_9ac2_issue_example_raises_and_simulated_validates():
    """#9 AC2 verbatim: the issue's example raises; "with `trust_label="simulated"` it
    validates"."""
    example = dict(generated_by=None, confirmed_by=None, confirmed_at=None)
    with pytest.raises(ValidationError):
        Provenance(trust_label="operating_surgeon", attributed_to="dev_team_simulated", **example)
    ok = Provenance(trust_label="simulated", attributed_to="dev_team_simulated", **example)
    assert ok.trust_label is TrustLabel.SIMULATED


@pytest.mark.parametrize("role", [r.value for r in Role])
def test_9ac2_the_reverse_is_not_required(role):
    """#9 triage: "The reverse (`simulated` => `dev_team_simulated`) is not required (synthetic
    TTS narration, D-027)": `simulated` validates with every role."""
    parsed = Provenance(**_provenance(trust_label="simulated", attributed_to=role))
    assert parsed.attributed_to.value == role


@pytest.mark.parametrize("label", NOT_SIMULATED)
def test_9ac2_rule_holds_wherever_provenance_appears(docs, label):
    """#9 AC2 "checked in the `Provenance` model": a seed record, its draft, a timeline item and
    a moment attributed to `dev_team_simulated` with another label are all rejected."""
    record = copy.deepcopy(docs["seed_records.json"]["records"][0])
    assert record["provenance"]["attributed_to"] == "dev_team_simulated"
    record["provenance"]["trust_label"] = label
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(record)
    with pytest.raises(ValidationError):
        DecisionRecordDraft.model_validate(_draft(record))
    timeline = copy.deepcopy(docs["timeline.json"])
    timeline["utterances"][0]["provenance"].update(
        trust_label=label, attributed_to="dev_team_simulated"
    )
    with pytest.raises(ValidationError):
        Timeline.model_validate(timeline)
    moments = copy.deepcopy(docs["moments.json"])
    moments["moments"][0]["provenance"].update(
        trust_label=label, attributed_to="dev_team_simulated"
    )
    with pytest.raises(ValidationError):
        Moments.model_validate(moments)


def test_9ac2_dev_team_simulated_simulated_timeline_item_is_fine(docs):
    """#9 AC2 control: a timeline utterance labelled 🧪 `simulated` and attributed to
    `dev_team_simulated` validates."""
    timeline = copy.deepcopy(docs["timeline.json"])
    timeline["utterances"][0]["provenance"].update(
        trust_label="simulated", attributed_to="dev_team_simulated"
    )
    Timeline.model_validate(timeline)


def test_9ac2_validate_case_names_the_incoherent_file(data_dir, run_validate):
    """#9 AC2 through `scrubgpt-validate case`: an utterance attributed to `dev_team_simulated`
    but labelled 🤖 `ai_detected` is an error naming timeline.json (exit 1)."""
    timeline = data_dir.load("timeline.json")
    timeline["utterances"][0]["provenance"]["attributed_to"] = "dev_team_simulated"
    assert timeline["utterances"][0]["provenance"]["trust_label"] == "ai_detected"
    data_dir.save("timeline.json", timeline)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert any("timeline.json" in ln for ln in result.error_lines), result.output


# --- AC10: canonical UUIDs ----------------------------------------------------------------------


def _canonical() -> str:
    value = str(uuid6.uuid7())
    assert re.match(TRIAGE_UUID7, value)
    return value


def _non_canonical(c: str) -> dict[str, str]:
    first_letter = next(i for i, ch in enumerate(c) if ch in "abcdef")
    nibble_v4 = c[:14] + "4" + c[15:]
    variant_c = c[:19] + "c" + c[20:]
    return {
        "uppercase": c.upper(),
        "one uppercase letter": c[:first_letter] + c[first_letter].upper() + c[first_letter + 1 :],
        "hyphen-less": c.replace("-", ""),
        "uppercase hyphen-less": c.upper().replace("-", ""),
        "urn:uuid:": f"urn:uuid:{c}",
        "braces": "{" + c + "}",
        "leading space": " " + c,
        "trailing space": c + " ",
        "trailing newline": c + "\n",
        "version 4": nibble_v4,
        "variant c": variant_c,
        "nil": "00000000-0000-0000-0000-000000000000",
        "regrouped hyphens": c.replace("-", "")[:12] + "-" + c.replace("-", "")[12:],
        "uuid4": str(uuid.uuid4()),
    }


IDS = [pytest.param(RecordId, id="RecordId"), pytest.param(AnswerId, id="AnswerId")]


@pytest.mark.parametrize("id_type", IDS)
def test_9ac10_ids_reject_non_canonical_forms(id_type):
    """#9 AC10: "`RecordId`/`AnswerId` reject uppercase, hyphen-less, `urn:uuid:` and `{...}`
    forms" (triage: "anything else is rejected"), in python and JSON input."""
    adapter = TypeAdapter(id_type)
    accepted = []
    for what, value in _non_canonical(_canonical()).items():
        try:
            adapter.validate_python(value)
        except ValidationError:
            pass
        else:
            accepted.append(what)
        try:
            adapter.validate_json(json.dumps(value))
        except ValidationError:
            pass
        else:
            accepted.append(f"json {what}")
    assert not accepted, f"accepted: {accepted}"


@pytest.mark.parametrize("id_type", IDS)
def test_9ac10_canonical_uuid7_passes_and_round_trips(id_type):
    """#9 AC10: "a canonical lowercase UUIDv7 passes and round-trips to the same string"."""
    adapter = TypeAdapter(id_type)
    for _ in range(20):
        c = _canonical()
        value = adapter.validate_python(c)
        assert str(value) == c
        assert adapter.dump_python(value, mode="json") == c
        assert json.loads(adapter.dump_json(value)) == c
        assert str(adapter.validate_json(json.dumps(c))) == c


@pytest.mark.parametrize("what", sorted(_non_canonical(_canonical())))
def test_9ac10_models_reject_non_canonical_record_and_answer_ids(docs, what):
    """#9 AC10 inside the models: `DecisionRecord.id` and the `answer_id` of `answer_text` /
    `answer_audio` evidence reject the same forms."""
    record = docs["seed_records.json"]["records"][6]
    kinds = {e["kind"] for e in record["evidence"]}
    assert {"answer_text", "answer_audio"} <= kinds
    bad_id = _non_canonical(record["id"])[what]
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(dict(record, id=bad_id))
    for i, evidence in enumerate(record["evidence"]):
        if "answer_id" not in evidence:
            continue
        bad = _non_canonical(evidence["answer_id"])[what]
        with pytest.raises(ValidationError):
            EVIDENCE.validate_python(dict(evidence, answer_id=bad))
        doc = copy.deepcopy(record)
        doc["evidence"][i]["answer_id"] = bad
        with pytest.raises(ValidationError):
            DecisionRecord.model_validate_json(json.dumps(doc, ensure_ascii=False))


def test_9ac10_fixture_ids_raw_string_equals_str_id(docs):
    """#9 triage: "So the raw JSON string always equals `str(id)`": every fixture record id and
    answer id parses and dumps back to its raw string."""
    for raw in docs["seed_records.json"]["records"]:
        record = DecisionRecord.model_validate_json(json.dumps(raw, ensure_ascii=False))
        assert str(record.id) == raw["id"]
        dumped = json.loads(record.model_dump_json())
        assert dumped["id"] == raw["id"]
        for before, after, parsed in zip(
            raw["evidence"], dumped["evidence"], record.evidence, strict=True
        ):
            if "answer_id" in before:
                assert after["answer_id"] == before["answer_id"]
                assert str(parsed.answer_id) == before["answer_id"]


def test_9ac10_validate_case_rejects_an_uppercase_record_id(data_dir, run_validate):
    """#9 AC10 through `scrubgpt-validate case`: an uppercase seed record id is an error naming
    seed_records.json (exit 1)."""
    seeds = data_dir.load("seed_records.json")
    seeds["records"][0]["id"] = seeds["records"][0]["id"].upper()
    data_dir.save("seed_records.json", seeds)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert any("seed_records.json" in ln for ln in result.error_lines), result.output


@pytest.mark.parametrize(
    ("schema_file", "key"),
    [("DecisionRecord.schema.json", "id"), ("DecisionRecord.schema.json", "answer_id")],
)
def test_9ac10_committed_schema_carries_the_uuid_pattern(paths, schema_file, key):
    """#9 triage: "The UUID and timestamp patterns change the generated `schema/`/`ts/`": the
    committed schema's `id` / `answer_id` patterns agree with the triage pattern."""
    schema = json.loads((paths["repo"] / "contracts" / "schema" / schema_file).read_text("utf-8"))
    found = _schema_patterns(schema, key)
    assert found, f"no pattern on {key} in {schema_file}"
    c = _canonical()
    samples = [c, _canonical()] + [v for v in _non_canonical(c).values() if not v.endswith("\n")]
    triage = _ecma_like(TRIAGE_UUID7)
    for pattern in found:
        mine = _ecma_like(pattern)
        diff = [s for s in samples if bool(mine.search(s)) != bool(triage.search(s))]
        assert not diff, f"{schema_file} {key} pattern {pattern!r} disagrees on {diff}"
