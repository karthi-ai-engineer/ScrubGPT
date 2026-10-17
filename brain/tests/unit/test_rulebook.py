"""Dev1's unit tests for the rule-book loader (engines/rulebook.py)."""

import shutil
from pathlib import Path

import pytest
import yaml
from scrubgpt_brain.engines import rulebook as rb


def test_the_committed_knowledge_loads_typed_and_ordered():
    knowledge = rb.load_knowledge()
    book = knowledge.rulebook
    assert [p.order for p in book.phases] == sorted(p.order for p in book.phases)
    for phase in book.phases:
        assert [s.order for s in phase.steps] == sorted(s.order for s in phase.steps)
    for step in book.steps():
        assert step.name.ja.strip() and step.name.en.strip()
        assert 0 < step.duration.p25 <= step.duration.p50 <= step.duration.p75
        assert step.id.startswith(f"{step.phase_id}.")
    assert book.step(book.steps()[3].id) is book.steps()[3]
    assert len(knowledge.families) == 8
    assert all(term.ja and term.en for term in knowledge.terms.values())
    assert book.grasp is not None and not book.grasp.verified


@pytest.fixture
def knowledge_copy(tmp_path: Path) -> Path:
    shutil.copytree(rb.KNOWLEDGE_DIR, tmp_path / "knowledge")
    return tmp_path / "knowledge"


def _edit(root: Path, relative: Path, change) -> None:
    path = root / relative
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _problems(root: Path) -> str:
    with pytest.raises(rb.KnowledgeError) as info:
        rb.load_knowledge(root)
    return str(info.value)


def test_a_duplicate_step_id_names_the_file_and_id(knowledge_copy: Path):
    def duplicate(data):
        steps = data["phases"][2]["steps"]
        steps.append({**steps[0], "order": 99})

    _edit(knowledge_copy, rb.RULEBOOK_FILE, duplicate)
    first = yaml.safe_load((knowledge_copy / rb.RULEBOOK_FILE).read_text("utf-8"))["phases"][2]
    text = _problems(knowledge_copy)
    assert f"rulebooks/rarp.yaml: {first['steps'][0]['id']}: duplicate step id" in text


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda d: d["phases"][3]["steps"][0]["known_obstacles"].append("bleeding.nowhere"),
         "unknown obstacle leaf `bleeding.nowhere`"),
        (lambda d: d["phases"][3]["steps"][0]["anatomy"].append("no_such_term"),
         "unknown term (anatomy) `no_such_term`"),
        (lambda d: d["phases"][3]["steps"][0]["typical_duration_s"].update(p25=999, p50=10),
         "0 < p25 ≤ p50 ≤ p75"),
        (lambda d: d["phases"][3]["steps"][0]["name"].pop("ja"), "missing or empty `ja`"),
        (lambda d: d["phases"][3]["steps"][0]["name"].update(en="  "), "missing or empty `en`"),
    ],
)  # fmt: skip
def test_rule_book_problems_name_the_file_and_id(knowledge_copy: Path, change, expected):
    _edit(knowledge_copy, rb.RULEBOOK_FILE, change)
    step_id = yaml.safe_load((knowledge_copy / rb.RULEBOOK_FILE).read_text("utf-8"))["phases"][3][
        "steps"
    ][0]["id"]
    text = _problems(knowledge_copy)
    assert f"rulebooks/rarp.yaml: {step_id}: " in text and expected in text


def test_taxonomy_problems_and_the_mirror_check(knowledge_copy: Path):
    def break_leaf(data):
        leaf = data["families"][0]["leaves"][0]
        leaf["steps"].append("rarp.p99.s01")
        leaf["terms"].append("no_such_term")

    _edit(knowledge_copy, rb.TAXONOMY_FILE, break_leaf)
    leaf_id = yaml.safe_load((knowledge_copy / rb.TAXONOMY_FILE).read_text("utf-8"))["families"][0][
        "leaves"
    ][0]["id"]
    text = _problems(knowledge_copy)
    assert f"taxonomy/obstacles.yaml: {leaf_id}: unknown step `rarp.p99.s01`" in text
    assert f"taxonomy/obstacles.yaml: {leaf_id}: unknown term `no_such_term`" in text
    assert "known_obstacles` lacks" in text  # the two copies of step ↔ obstacle disagree


def test_unreadable_or_broken_yaml(knowledge_copy: Path):
    (knowledge_copy / rb.VOCAB_FILE).write_text("terms: [unclosed", encoding="utf-8")
    assert "vocab/terms.yaml: (file): not valid YAML" in _problems(knowledge_copy)
    (knowledge_copy / rb.VOCAB_FILE).unlink()
    assert "vocab/terms.yaml: (file): can't read" in _problems(knowledge_copy)


def test_reads_only_the_given_folder(knowledge_copy: Path, monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "nowhere"))
    assert rb.load_knowledge(knowledge_copy).rulebook.id == rb.load_knowledge().rulebook.id
    with pytest.raises(rb.KnowledgeError):
        rb.load_knowledge(tmp_path / "empty")
