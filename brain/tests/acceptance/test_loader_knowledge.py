"""Rule-book loader (no feature id): #14 acceptance criteria 1-3 (Team Lead answer; D-067;
brain/README.md "Rule-book loader").

Expected behaviour, written from the spec before the code was opened:
- AC1: `load_knowledge()` on the committed `knowledge/` returns typed (README: "typed, frozen")
  objects: the rule book's phases and steps in rule-book order, their checkpoints, the obstacle
  taxonomy (families, leaves) and the vocabulary (terms). Every step has non-empty `ja` and `en`
  names, and its `typical_duration_s` has 0 < p25 <= p50 <= p75. The loaded values are the YAML's
  values (checked against an independent parse of the files).
- AC2: on a copy in `tmp_path`, each of: a duplicate step id; a reference to an unknown obstacle,
  step or term; p25 > p50; a missing `ja` or `en` value, raises `KnowledgeError` (not a crash such
  as KeyError/TypeError), and the message names the file and the offending id (README: each
  problem as `<file>: <id>: <what's wrong>`; "Any problem raises `KnowledgeError`, listing each
  one").
- AC3: the loader reads the folder the caller gives, defaulting to the repo's `knowledge/`
  (`KNOWLEDGE_DIR`), and never reads `DATA_DIR` or `.env` (checked with an audit hook that records
  every file the loader opens, with `DATA_DIR` set and a `.env` in the working folder).

No step id is hard-coded: ids come from the YAML (Team Lead note on #14). The broken copies are
made by parsing the committed YAML, changing it and dumping it back into `tmp_path`.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import json
import os
import shutil
import subprocess
import sys
import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from scrubgpt_brain.engines import rulebook as loader

RULEBOOK_REL = Path("rulebooks") / "rarp.yaml"
TAXONOMY_REL = Path("taxonomy") / "obstacles.yaml"
VOCAB_REL = Path("vocab") / "terms.yaml"


# ── helpers ──────────────────────────────────────────────────────────────────


def _read(path: Path):
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _write(path: Path, data) -> None:
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _copy_knowledge(const, target: Path) -> Path:
    shutil.copytree(const.knowledge, target)
    return target


def _all_steps(rb: dict) -> list[dict]:
    return [step for phase in rb["phases"] for step in phase.get("steps") or []]


def _step_with_everything(rb: dict) -> dict:
    """A step with checkpoints, anatomy, instruments and known obstacles (ids from the YAML)."""
    return next(
        s
        for s in _all_steps(rb)
        if s.get("checkpoints") and s.get("anatomy") and s.get("instruments")
        and s.get("known_obstacles")
    )  # fmt: skip


def _unknown_phase_id(rb: dict) -> str:
    return f"{rb['id']}.p{len(rb['phases']) + 1:02d}"


def _unknown_step_id(rb: dict) -> str:
    return f"{_unknown_phase_id(rb)}.s01"


def _lines(error: BaseException) -> list[str]:
    return [line for line in str(error).splitlines() if line.strip()]


# Mutations for AC2: each changes the parsed (rule book, taxonomy, vocabulary) in place and
# returns (file name the error must name, offending id the error must name).
Mutation = Callable[[dict, dict, dict], tuple[str, str]]


def _dup_step_id(rb, tax, voc):
    phase = next(p for p in rb["phases"] if p.get("steps"))
    original = phase["steps"][0]
    clone = copy.deepcopy(original)
    clone["order"] = max(s["order"] for s in phase["steps"]) + 1
    clone["checkpoints"] = []  # so only the step id is duplicated
    phase["steps"].append(clone)
    return "rarp.yaml", original["id"]


def _dup_step_id_across_phases(rb, tax, voc):
    phases = [p for p in rb["phases"] if p.get("steps")]
    first, other = phases[0]["steps"][0], phases[-1]["steps"][-1]
    other_id = other["id"]
    other["id"] = first["id"]
    for checkpoint in other.get("checkpoints") or []:  # keep checkpoint ids unique
        checkpoint["id"] = checkpoint["id"].replace(other_id, first["id"] + "x")
    return "rarp.yaml", first["id"]


def _unknown_obstacle(rb, tax, voc):
    step = _step_with_everything(rb)
    bad = f"{tax['families'][0]['id']}.t1_no_such_leaf"
    step["known_obstacles"].append(bad)
    return "rarp.yaml", bad


def _unknown_step_in_taxonomy(rb, tax, voc):
    bad = _unknown_step_id(rb)
    tax["families"][0]["leaves"][0]["steps"].append(bad)
    return "obstacles.yaml", bad


def _unknown_step_in_grasp(rb, tax, voc):
    bad = _unknown_step_id(rb)
    label = next(
        s for s in rb["grasp"]["steps"] if isinstance(s.get("maps_to"), list) and s["maps_to"]
    )
    label["maps_to"] = [*label["maps_to"], bad]
    return "rarp.yaml", bad


def _unknown_phase_in_order_rules(rb, tax, voc):
    bad = _unknown_phase_id(rb)
    rb["order_rules"]["movable_phases"][0]["may_follow"].append(bad)
    return "rarp.yaml", bad


def _unknown_term_in_anatomy(rb, tax, voc):
    step = _step_with_everything(rb)
    step["anatomy"].append("t1_no_such_term")
    return "rarp.yaml", "t1_no_such_term"


def _unknown_term_in_instruments(rb, tax, voc):
    step = _step_with_everything(rb)
    step["instruments"].append("t1_no_such_instrument")
    return "rarp.yaml", "t1_no_such_instrument"


def _unknown_term_in_taxonomy(rb, tax, voc):
    tax["families"][0]["leaves"][0]["terms"].append("t1_no_such_term")
    return "obstacles.yaml", "t1_no_such_term"


def _step_p25_above_p50(rb, tax, voc):
    step = _step_with_everything(rb)
    d = step["typical_duration_s"]
    d["p25"] = d["p50"] + 1
    d["p75"] = max(d["p75"], d["p25"] + 1)  # only p25 > p50 is wrong
    return "rarp.yaml", step["id"]


def _phase_p25_above_p50(rb, tax, voc):
    phase = rb["phases"][len(rb["phases"]) // 2]
    d = phase["typical_duration_s"]
    d["p25"] = d["p50"] + 1
    d["p75"] = max(d["p75"], d["p25"] + 1)
    return "rarp.yaml", phase["id"]


def _step_p50_above_p75(rb, tax, voc):
    step = _all_steps(rb)[-1]
    d = step["typical_duration_s"]
    d["p50"] = d["p75"] + 1
    return "rarp.yaml", step["id"]


def _step_p25_zero(rb, tax, voc):
    step = _all_steps(rb)[0]
    step["typical_duration_s"]["p25"] = 0
    return "rarp.yaml", step["id"]


def _step_name_ja_missing(rb, tax, voc):
    step = _step_with_everything(rb)
    del step["name"]["ja"]
    return "rarp.yaml", step["id"]


def _step_name_en_missing(rb, tax, voc):
    step = _all_steps(rb)[1]
    del step["name"]["en"]
    return "rarp.yaml", step["id"]


def _step_name_en_empty(rb, tax, voc):
    step = _all_steps(rb)[2]
    step["name"]["en"] = "  "
    return "rarp.yaml", step["id"]


def _phase_name_ja_missing(rb, tax, voc):
    phase = rb["phases"][-1]
    del phase["name"]["ja"]
    return "rarp.yaml", phase["id"]


def _checkpoint_text_en_missing(rb, tax, voc):
    checkpoint = _step_with_everything(rb)["checkpoints"][0]
    del checkpoint["text"]["en"]
    return "rarp.yaml", checkpoint["id"]


def _leaf_name_ja_missing(rb, tax, voc):
    leaf = tax["families"][-1]["leaves"][-1]
    del leaf["name"]["ja"]
    return "obstacles.yaml", leaf["id"]


def _term_en_missing(rb, tax, voc):
    term = voc["terms"][0]
    del term["en"]
    return "terms.yaml", term["id"]


def _term_ja_empty(rb, tax, voc):
    term = voc["terms"][-1]
    term["ja"] = ""
    return "terms.yaml", term["id"]


AC2_MUTATIONS: dict[str, Mutation] = {
    "duplicate-step-id-in-a-phase": _dup_step_id,
    "duplicate-step-id-across-phases": _dup_step_id_across_phases,
    "unknown-obstacle-in-rulebook": _unknown_obstacle,
    "unknown-step-in-taxonomy-leaf": _unknown_step_in_taxonomy,
    "unknown-step-in-grasp-crosswalk": _unknown_step_in_grasp,
    "unknown-phase-in-order-rules": _unknown_phase_in_order_rules,
    "unknown-term-in-step-anatomy": _unknown_term_in_anatomy,
    "unknown-term-in-step-instruments": _unknown_term_in_instruments,
    "unknown-term-in-taxonomy-leaf": _unknown_term_in_taxonomy,
    "step-p25-above-p50": _step_p25_above_p50,
    "phase-p25-above-p50": _phase_p25_above_p50,
    "step-p50-above-p75": _step_p50_above_p75,
    "step-p25-zero": _step_p25_zero,
    "step-name-ja-missing": _step_name_ja_missing,
    "step-name-en-missing": _step_name_en_missing,
    "step-name-en-blank": _step_name_en_empty,
    "phase-name-ja-missing": _phase_name_ja_missing,
    "checkpoint-text-en-missing": _checkpoint_text_en_missing,
    "leaf-name-ja-missing": _leaf_name_ja_missing,
    "term-en-missing": _term_en_missing,
    "term-ja-empty": _term_ja_empty,
}


def _mutated_copy(
    const, tmp_path: Path, *mutations: Mutation
) -> tuple[Path, list[tuple[str, str]]]:
    root = _copy_knowledge(const, tmp_path / "knowledge")
    rb, tax, voc = (_read(root / rel) for rel in (RULEBOOK_REL, TAXONOMY_REL, VOCAB_REL))
    expected = [mutate(rb, tax, voc) for mutate in mutations]
    for rel, data in ((RULEBOOK_REL, rb), (TAXONOMY_REL, tax), (VOCAB_REL, voc)):
        _write(root / rel, data)
    return root, expected


@pytest.fixture(scope="module")
def knowledge():
    return loader.load_knowledge()


# ── AC1 ──────────────────────────────────────────────────────────────────────


def test_ac1_committed_knowledge_loads_into_typed_frozen_objects(knowledge):
    """#14 AC1 "Loading the committed `knowledge/` files returns typed objects: phases and steps
    in rule-book order, checkpoints, obstacle taxonomy and vocabulary" (README: "typed, frozen
    objects: `RuleBook`, `Phase`, `Step` …, `ObstacleFamily`/`ObstacleLeaf`, `Term`")."""
    book = knowledge.rulebook
    assert isinstance(book, loader.RuleBook)
    assert book.phases and all(isinstance(p, loader.Phase) for p in book.phases)
    steps = [s for p in book.phases for s in p.steps]
    assert steps and all(isinstance(s, loader.Step) for s in steps)
    leaves = knowledge.leaves()
    assert leaves and all(isinstance(leaf, loader.ObstacleLeaf) for leaf in leaves.values())
    assert all(isinstance(f, loader.ObstacleFamily) for f in knowledge.families)
    assert knowledge.terms and all(isinstance(t, loader.Term) for t in knowledge.terms.values())
    for obj in (knowledge, book, book.phases[0], steps[0], next(iter(leaves.values()))):
        assert dataclasses.is_dataclass(obj), f"{type(obj).__name__} is not a typed record"
        field = dataclasses.fields(obj)[0].name
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            setattr(obj, field, None)


def test_ac1_phases_and_steps_come_in_rule_book_order(knowledge, rulebook):
    """#14 AC1 "phases and steps in rule-book order": the loaded phase and step ids are the YAML's
    ids in its order (the `order` fields ascend), with the YAML's names."""
    book = knowledge.rulebook
    assert [p.id for p in book.phases] == [p["id"] for p in rulebook["phases"]]
    assert [p.order for p in book.phases] == sorted(p.order for p in book.phases)
    for loaded, raw in zip(book.phases, rulebook["phases"], strict=True):
        assert (loaded.name.ja, loaded.name.en) == (raw["name"]["ja"], raw["name"]["en"])
        assert [s.id for s in loaded.steps] == [s["id"] for s in raw.get("steps") or []]
        assert [s.order for s in loaded.steps] == sorted(s.order for s in loaded.steps)
        for step, raw_step in zip(loaded.steps, raw.get("steps") or [], strict=True):
            assert (step.name.ja, step.name.en) == (raw_step["name"]["ja"], raw_step["name"]["en"])


def test_ac1_every_step_has_bilingual_names_and_ordered_positive_durations(knowledge, rulebook):
    """#14 AC1 "Every step has non-empty `ja` and `en` names and its `typical_duration_s` p25 ≤
    p50 ≤ p75, all > 0." The values are the YAML's."""
    raw = {s["id"]: s for p in rulebook["phases"] for s in p.get("steps") or []}
    steps = [s for p in knowledge.rulebook.phases for s in p.steps]
    assert len(steps) == len(raw)
    for step in steps:
        assert isinstance(step.name.ja, str) and step.name.ja.strip(), step.id
        assert isinstance(step.name.en, str) and step.name.en.strip(), step.id
        d = step.duration
        assert 0 < d.p25 <= d.p50 <= d.p75, f"{step.id}: {d}"
        want = raw[step.id]["typical_duration_s"]
        assert (d.p25, d.p50, d.p75) == (want["p25"], want["p50"], want["p75"]), step.id


def test_ac1_checkpoints_are_loaded_per_step(knowledge, rulebook):
    """#14 AC1 "… checkpoints": every step's checkpoints, with their ids and bilingual texts, as in
    the YAML."""
    raw = {s["id"]: s for p in rulebook["phases"] for s in p.get("steps") or []}
    total = 0
    for step in (s for p in knowledge.rulebook.phases for s in p.steps):
        want = raw[step.id].get("checkpoints") or []
        assert [c.id for c in step.checkpoints] == [c["id"] for c in want], step.id
        for loaded, item in zip(step.checkpoints, want, strict=True):
            assert (loaded.text.ja, loaded.text.en) == (item["text"]["ja"], item["text"]["en"])
            total += 1
    assert total > 0, "no checkpoint loaded at all"


def test_ac1_obstacle_taxonomy_and_vocabulary_are_loaded(knowledge, taxonomy, vocab):
    """#14 AC1 "… obstacle taxonomy and vocabulary": the families and leaves of
    taxonomy/obstacles.yaml (leaf steps and terms as written) and the terms of vocab/terms.yaml
    (ja, en), all of them."""
    assert [f.id for f in knowledge.families] == [f["id"] for f in taxonomy["families"]]
    raw_leaves = {leaf["id"]: leaf for f in taxonomy["families"] for leaf in f.get("leaves") or []}
    leaves = knowledge.leaves()
    assert set(leaves) == set(raw_leaves)
    for leaf_id, leaf in leaves.items():
        raw = raw_leaves[leaf_id]
        assert (leaf.name.ja, leaf.name.en) == (raw["name"]["ja"], raw["name"]["en"])
        assert list(leaf.steps) == list(raw.get("steps") or []), leaf_id
        assert list(leaf.terms) == list(raw.get("terms") or []), leaf_id
    raw_terms = {t["id"]: t for t in vocab["terms"]}
    assert set(knowledge.terms) == set(raw_terms)
    for term_id, term in knowledge.terms.items():
        assert (term.ja, term.en) == (raw_terms[term_id]["ja"], raw_terms[term_id]["en"])


def test_ac1_order_rules_are_loaded(knowledge, rulebook):
    """README "`OrderRules`" (the skip and move rules C3 decodes with, #14 AC5): the optional and
    movable phases are the YAML's."""
    rules = knowledge.rulebook.order_rules
    raw = rulebook["order_rules"]
    assert isinstance(rules, loader.OrderRules)
    assert list(rules.optional_phases) == list(raw["optional_phases"])
    assert [(m.phase, list(m.may_follow)) for m in rules.movable_phases] == [
        (m["phase"], list(m["may_follow"])) for m in raw["movable_phases"]
    ]


# ── AC2 ──────────────────────────────────────────────────────────────────────


def test_ac2_an_unchanged_round_tripped_copy_loads(const, tmp_path, knowledge):
    """Sanity for AC2: the committed YAML parsed and dumped back into `tmp_path` (the way the
    broken copies are made) loads without error and gives the same objects, so every AC2 error
    below comes from the one change made."""
    root, _ = _mutated_copy(const, tmp_path)
    assert loader.load_knowledge(root) == knowledge


@pytest.mark.parametrize("mutation", list(AC2_MUTATIONS.values()), ids=list(AC2_MUTATIONS))
def test_ac2_a_broken_copy_raises_a_clear_error_naming_file_and_id(const, tmp_path, mutation):
    """#14 AC2 "On a copy in `tmp_path`, each of the following raises a clear error that names the
    file and the offending ID, and the run doesn't crash: a duplicate step ID; a reference to an
    unknown obstacle, step or term; p25 > p50; a missing `ja` or `en` value." README: "Any problem
    raises `KnowledgeError`, listing each one as `<file>: <id>: <what's wrong>`" and "0 < p25 ≤
    p50 ≤ p75". One line of the error names both the file and the id."""
    root, [(file_name, offending)] = _mutated_copy(const, tmp_path, mutation)
    with pytest.raises(loader.KnowledgeError) as caught:
        loader.load_knowledge(root)
    lines = _lines(caught.value)
    assert any(file_name in line and offending in line for line in lines), (
        f"no line names both {file_name!r} and {offending!r}:\n{caught.value}"
    )


def test_ac2_every_problem_is_listed(const, tmp_path):
    """README "Any problem raises `KnowledgeError`, listing each one": three independent problems
    in three files give one error that names all three (file and id each)."""
    root, expected = _mutated_copy(
        const, tmp_path, _step_p25_above_p50, _unknown_term_in_taxonomy, _term_en_missing
    )
    with pytest.raises(loader.KnowledgeError) as caught:
        loader.load_knowledge(root)
    lines = _lines(caught.value)
    for file_name, offending in expected:
        assert any(file_name in line and offending in line for line in lines), (
            f"{file_name}: {offending} is not listed:\n{caught.value}"
        )


@pytest.mark.parametrize("damage", ["missing", "not-yaml"])
@pytest.mark.parametrize("rel", [RULEBOOK_REL, TAXONOMY_REL, VOCAB_REL], ids=lambda p: p.name)
def test_ac2_a_missing_or_unparsable_file_is_a_clear_error(const, tmp_path, rel, damage):
    """#14 AC2 "… the run doesn't crash" with README "Any problem raises `KnowledgeError`": a copy
    with one of the three files deleted, or not valid YAML, raises `KnowledgeError` naming it."""
    root = _copy_knowledge(const, tmp_path / "knowledge")
    if damage == "missing":
        (root / rel).unlink()
    else:
        (root / rel).write_text("phases: [this is not closed\n", encoding="utf-8")
    with pytest.raises(loader.KnowledgeError) as caught:
        loader.load_knowledge(root)
    assert rel.name in str(caught.value), f"the error doesn't name {rel.name}:\n{caught.value}"


# ── AC3 ──────────────────────────────────────────────────────────────────────


def test_ac3_loads_the_folder_the_caller_gives(const, tmp_path, rulebook):
    """#14 AC3 "The loader reads from a path the caller gives": a copy whose first step has a new
    English name loads with that name, and the default load still has the committed one."""
    root = _copy_knowledge(const, tmp_path / "elsewhere")
    rb = _read(root / RULEBOOK_REL)
    first = _all_steps(rb)[0]
    first["name"]["en"] = "T1 marker: a name only the copy has"
    _write(root / RULEBOOK_REL, rb)
    copied = loader.load_knowledge(root).rulebook.phases[0].steps[0]
    assert copied.id == first["id"]
    assert copied.name.en == "T1 marker: a name only the copy has"
    default = loader.load_knowledge().rulebook.phases[0].steps[0]
    assert default.name.en == _all_steps(rulebook)[0]["name"]["en"]


def test_ac3_defaults_to_the_repo_knowledge_folder(const, knowledge):
    """#14 AC3 "… defaulting to the repo's `knowledge/`" (README "default: the repo's
    `knowledge/`"): `KNOWLEDGE_DIR` is the repo's knowledge/ folder and loading with no argument
    equals loading that folder explicitly."""
    assert Path(loader.KNOWLEDGE_DIR).resolve() == const.knowledge.resolve()
    assert loader.load_knowledge(const.knowledge) == knowledge


_AUDIT_CHILD = textwrap.dedent(
    """
    import json, os, sys
    from pathlib import Path
    from scrubgpt_brain.engines.rulebook import load_knowledge

    seen = []
    def hook(event, args):
        if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
            seen.append(["open", os.fsdecode(args[0])])
        elif event in ("os.listdir", "os.scandir", "glob.glob") and args:
            seen.append([event, os.fsdecode(args[0]) if args[0] is not None else "."])

    sys.addaudithook(hook)
    given = load_knowledge(Path(sys.argv[1]))
    default = load_knowledge()
    names = [s.name.en for p in given.rulebook.phases for s in p.steps]
    default_names = [s.name.en for p in default.rulebook.phases for s in p.steps]
    print(json.dumps({"seen": seen, "given": names, "default": default_names}))
    """
)


def test_ac3_never_reads_data_dir_or_env(const, tmp_path, rulebook):
    """#14 AC3 "It never reads `DATA_DIR` or `.env`." A child interpreter runs the loader on a copy
    and on the default folder with `DATA_DIR` pointing at a folder holding a planted, broken
    knowledge/ and a `.env` (also naming it) in the working folder. An audit hook records every
    file opened and folder listed: only files inside the two knowledge folders (and Python's own
    modules) are opened, nothing under `DATA_DIR`, no `.env`, and the steps are the committed ones.
    """
    given = _copy_knowledge(const, tmp_path / "given")
    data_dir = tmp_path / "data"
    planted = data_dir / "knowledge" / RULEBOOK_REL
    planted.parent.mkdir(parents=True)
    planted.write_text("phases: [this is not the rule book\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    (work / ".env").write_text(
        f"DATA_DIR={data_dir}\nKNOWLEDGE_DIR={data_dir / 'knowledge'}\n", encoding="utf-8"
    )
    env = {**os.environ, "DATA_DIR": str(data_dir), "PYTHONUTF8": "1"}
    result = subprocess.run(
        [sys.executable, "-c", _AUDIT_CHILD, str(given)],
        cwd=work,
        capture_output=True,
        timeout=300,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    report = json.loads(result.stdout.strip().splitlines()[-1])
    committed = [s["name"]["en"] for p in rulebook["phases"] for s in p.get("steps") or []]
    assert report["given"] == committed and report["default"] == committed
    python_dirs = {Path(p).resolve() for p in (sys.prefix, sys.base_prefix, sys.exec_prefix)}
    allowed = (given.resolve(), const.knowledge.resolve())
    unexpected = []
    for event, raw_path in report["seen"]:
        path = Path(raw_path) if Path(raw_path).is_absolute() else work / raw_path
        path = path.resolve()
        assert data_dir.resolve() not in (path, *path.parents), f"{event} under DATA_DIR: {path}"
        assert path.name != ".env", f"{event} of a .env file: {path}"
        if event != "open" or path.suffix in {".py", ".pyc", ".pyd", ".so", ".dll", ".pth"}:
            continue
        if any(d in path.parents for d in python_dirs):
            continue
        if not any(root in path.parents for root in allowed):
            unexpected.append(str(path))
    assert not unexpected, f"the loader opened files outside the knowledge folders: {unexpected}"
    opened_yaml = {Path(p).name for e, p in report["seen"] if e == "open" and p.endswith(".yaml")}
    assert {"rarp.yaml", "obstacles.yaml", "terms.yaml"} <= opened_yaml


def test_ac3_loader_code_reads_no_environment(const):
    """#14 AC3 "never reads `DATA_DIR` or `.env`", statically: the loader module touches no
    `os.environ` / `os.getenv` and imports no dotenv package."""
    source = Path(loader.__file__).read_text(encoding="utf-8")
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv", "environb"}:
            hits.append(f"line {node.lineno}: .{node.attr}")
        elif isinstance(node, ast.Name) and node.id in {"environ", "getenv"}:
            hits.append(f"line {node.lineno}: {node.id}")
        elif isinstance(node, ast.Import | ast.ImportFrom):
            names = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
            if any("dotenv" in n for n in names):
                hits.append(f"line {node.lineno}: imports dotenv")
    assert not hits, f"engines/rulebook.py reads the environment: {hits}"
