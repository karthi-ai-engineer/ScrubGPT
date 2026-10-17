"""Dev1's unit tests for the Procedure Reference export (pipeline/reference.py; D-035)."""

import json
import shutil
from pathlib import Path

import pytest
import yaml
from scrubgpt_brain import cli
from scrubgpt_brain.engines.rulebook import KNOWLEDGE_DIR, KnowledgeError, load_knowledge
from scrubgpt_brain.pipeline import reference as ref
from scrubgpt_contracts.models.reference import ProcedureReference

FIXTURE = KNOWLEDGE_DIR.parent / "contracts" / "fixtures" / "reference" / "rarp.json"


def _ids(data: dict) -> tuple[list, ...]:
    steps = [s for p in data["phases"] for s in p["steps"]]
    return (
        [(p["id"], p["name"], p["order"]) for p in data["phases"]],
        [(s["id"], s["name"], s["order"]) for s in steps],
        [(c["id"], c["text"]) for s in steps for c in s["checkpoints"]],
        [(f["id"], f["name"]) for f in data["obstacle_taxonomy"]],
        [(leaf["id"], leaf["name"]) for f in data["obstacle_taxonomy"] for leaf in f["leaves"]],
    )


def test_export_matches_the_contract_fixture_ids_and_names(tmp_path: Path):
    path = ref.export_reference(tmp_path)
    assert path == tmp_path / "reference" / "rarp.json"
    exported = json.loads(path.read_text("utf-8"))
    ProcedureReference.model_validate(exported)
    # The contract fixture leads (D-051): every id, name and order is the same.
    assert _ids(exported) == _ids(json.loads(FIXTURE.read_text("utf-8")))
    assert sorted(p.name for p in path.parent.iterdir()) == ["rarp.json"]  # no staging left


def test_export_publishes_only_the_public_part(tmp_path: Path):
    text = ref.export_reference(tmp_path).read_text("utf-8")
    for internal in ("visual_cues", "known_obstacles", "anatomy", "order_rules", "grasp"):
        assert internal not in text
    book = load_knowledge().rulebook
    exported = json.loads(text)
    first = book.steps()[0]
    step = exported["phases"][0]["steps"][0]
    assert step["typical_duration_s"] == {
        "p25": first.duration.p25,
        "p50": first.duration.p50,
        "p75": first.duration.p75,
    }


def test_re_export_is_byte_identical(tmp_path: Path):
    first = ref.export_reference(tmp_path).read_bytes()
    assert ref.export_reference(tmp_path).read_bytes() == first
    assert first.endswith(b"\n") and b"\r\n" not in first


def test_broken_knowledge_writes_nothing_and_keeps_the_earlier_export(tmp_path: Path):
    knowledge = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_DIR, knowledge)
    data_dir = tmp_path / "data"
    earlier = ref.export_reference(data_dir, knowledge_dir=knowledge).read_bytes()
    path = knowledge / "rulebooks" / "rarp.yaml"
    book = yaml.safe_load(path.read_text("utf-8"))
    book["phases"][0]["steps"][0]["name"]["en"] = ""
    path.write_text(yaml.safe_dump(book, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with pytest.raises(KnowledgeError):
        ref.export_reference(data_dir, knowledge_dir=knowledge)
    assert (data_dir / "reference" / "rarp.json").read_bytes() == earlier


def test_cli_reference(tmp_path: Path, monkeypatch):
    lines: list[str] = []
    assert cli.main(["reference", str(tmp_path / "d1")], out=lines.append) == 0
    assert (tmp_path / "d1" / "reference" / "rarp.json").is_file()
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "d2"))
    assert cli.main(["reference"], out=lines.append) == 0
    assert (tmp_path / "d2" / "reference" / "rarp.json").is_file()
    monkeypatch.delenv("DATA_DIR")
    assert cli.main(["reference"], out=lines.append) == 1
    assert "set DATA_DIR" in lines[-1]
