"""Dev2's unit tests for `scrubgpt-codegen` (the schema half: TS needs Node)."""

import json
from pathlib import Path

from scrubgpt_contracts.codegen import bundle_schema, main, model_schema, top_level_models
from scrubgpt_contracts.models.brain_api import ENDPOINTS
from scrubgpt_contracts.models.decision_record import DecisionRecord


def test_top_level_models_cover_files_records_and_endpoints() -> None:
    names = {model.__name__ for model in top_level_models()}
    assert {"Case", "Timeline", "Moments", "Questions", "SeedRecords", "Metrics"} <= names
    assert {"ProcedureReference", "DecisionRecord", "DecisionRecordDraft", "ApiError"} <= names
    for endpoint in ENDPOINTS.values():
        assert endpoint.response.__name__ in names


def test_v1_fields_are_required_in_the_schema() -> None:
    schema = model_schema(DecisionRecord)
    assert set(schema["required"]) == set(DecisionRecord.model_fields)


def test_property_titles_are_dropped_and_refs_have_no_siblings() -> None:
    def walk(node: object, path: str) -> None:
        if isinstance(node, dict):
            if "$ref" in node:
                assert len(node) == 1, path
            for key, value in node.items():
                if key in ("properties", "$defs"):
                    for name, sub in value.items():
                        if key == "properties":
                            assert "title" not in sub, f"{path}.{name}"
                        walk(sub, f"{path}.{name}")
                else:
                    walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(bundle_schema(top_level_models()), "$")


def test_schema_only_run_is_reproducible(tmp_path: Path) -> None:
    assert main(["--out", str(tmp_path / "a"), "--schema-only"]) == 0
    assert main(["--out", str(tmp_path / "b"), "--schema-only"]) == 0
    a = sorted((tmp_path / "a" / "schema").iterdir())
    b = sorted((tmp_path / "b" / "schema").iterdir())
    assert [p.name for p in a] == [p.name for p in b]
    for left, right in zip(a, b, strict=True):
        assert left.read_bytes() == right.read_bytes()
        assert b"\r\n" not in left.read_bytes()
        json.loads(left.read_text(encoding="utf-8"))


def test_utterance_class_uses_the_wire_name(tmp_path: Path) -> None:
    main(["--out", str(tmp_path), "--schema-only"])
    timeline = json.loads((tmp_path / "schema" / "Timeline.schema.json").read_text("utf-8"))
    assert "class" in timeline["$defs"]["Utterance"]["properties"]
