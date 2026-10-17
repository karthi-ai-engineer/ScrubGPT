"""Procedure Reference export (Block 1): criteria R1-R6 of the T1 brief at 5a89091 (plan §4.2b;
D-035, D-049, D-051; brain/README.md "Procedure Reference export"; the CLI docstring).

Expected behaviour, written from the spec before the code was opened:
- R1: `export_reference(data_dir)` / `scrubgpt-brain reference <data_dir>` writes
  `<data_dir>/reference/rarp.json`, which validates as the contract's `ProcedureReference` and
  passes `scrubgpt-validate reference` (exit 0).
- R2: phase, step and checkpoint ids, names and orders, and the obstacle families and leaves (ids
  and names) equal `contracts/fixtures/reference/rarp.json` (D-051: the contract leads; README:
  "The ids are stable from the first export on: they equal the contract fixture").
- R3: only the public part: exactly the contract's keys at every level, so no description, visual
  cue, anatomy, instrument, known obstacle, order rule or GraSP crosswalk; every phase's and step's
  `typical_duration_s` equals the rule book's p25/p50/p75.
- R4: re-exporting unchanged knowledge is byte-identical, with LF line ends and one trailing
  newline.
- R5: inconsistent knowledge (a broken copy, through the loader's folder argument) is an error:
  exit 1 with `scrubgpt-brain: error: …` on stderr, nothing written, an earlier export unchanged,
  no staging file left (README: "A failed export (inconsistent knowledge, or a contract error)
  writes nothing and leaves the earlier file as it was").
- R6: without an argument the CLI uses `DATA_DIR`; a relative `DATA_DIR` resolves against the repo
  root (plan §4.1, D-034), not the working folder; with neither, exit 1 and a message saying so.

Everything is written in `tmp_path`; no step id is hard-coded (they come from the fixture and the
rule book).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
from pathlib import Path

import pytest
import yaml
from scrubgpt_brain.pipeline.reference import export_reference
from scrubgpt_contracts.models.reference import ProcedureReference

TOP_KEYS = {"contract_version", "id", "name", "phases", "obstacle_taxonomy"}
PHASE_KEYS = {"id", "name", "order", "typical_duration_s", "steps"}
STEP_KEYS = {"id", "name", "order", "typical_duration_s", "checkpoints"}
CHECKPOINT_KEYS = {"id", "text"}
FAMILY_KEYS = {"id", "name", "leaves"}
LEAF_KEYS = {"id", "name"}
DURATION_KEYS = {"p25", "p50", "p75"}
PRIVATE = (
    "description", "visual_cues", "anatomy", "instruments", "known_obstacles", "order_rules",
    "grasp", "typical_cause", "terms", "optional", "approach", "review_status",
)  # fmt: skip


def _keys(node, path="$"):
    """Every (path, key) of a JSON tree."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key
            yield from _keys(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _keys(value, f"{path}[{index}]")


def _files(folder: Path) -> dict[str, bytes]:
    if not folder.exists():
        return {}
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


def _public(reference: dict) -> dict:
    """What R2 compares: ids, names and orders of phases, steps and checkpoints, and the families
    and leaves (ids and names)."""
    return {
        "phases": [
            {
                "id": p["id"], "name": p["name"], "order": p["order"],
                "steps": [
                    {
                        "id": s["id"], "name": s["name"], "order": s["order"],
                        "checkpoints": [
                            {"id": c["id"], "text": c["text"]} for c in s["checkpoints"]
                        ],
                    }
                    for s in p["steps"]
                ],
            }
            for p in reference["phases"]
        ],
        "obstacle_taxonomy": [
            {"id": f["id"], "name": f["name"],
             "leaves": [{"id": leaf["id"], "name": leaf["name"]} for leaf in f["leaves"]]}
            for f in reference["obstacle_taxonomy"]
        ],
    }  # fmt: skip


@pytest.fixture(scope="module")
def exported(tmp_path_factory) -> Path:
    data = tmp_path_factory.mktemp("data")
    return export_reference(data)


@pytest.fixture(scope="module")
def document(exported) -> dict:
    return json.loads(exported.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fixture_reference(const) -> dict:
    return json.loads(const.reference_fixture_path.read_text(encoding="utf-8"))


# ── R1 ───────────────────────────────────────────────────────────────────────


def test_r1_export_writes_reference_rarp_json_in_the_data_folder(exported, rulebook):
    """R1 "It writes `<data_dir>/reference/rarp.json`" (plan §4.2b
    `<DATA_DIR>/reference/<procedure_id>.json`): the returned path is that file, and the data
    folder holds nothing else."""
    data = exported.parent.parent
    assert exported == data / "reference" / f"{rulebook['id']}.json"
    assert exported.is_file()
    assert set(_files(data)) == {f"reference/{rulebook['id']}.json"}


def test_r1_the_file_validates_as_the_contract_procedure_reference(exported):
    """R1 "… which validates as the contract's `ProcedureReference`" (contract_version 1.0)."""
    model = ProcedureReference.model_validate_json(exported.read_bytes())
    assert model.contract_version == "1.0"
    assert model.id == "rarp"


def test_r1_the_file_passes_scrubgpt_validate_reference(cli, exported):
    """R1 "… and passes `scrubgpt-validate reference`" (plan §4.2b: exit 0 = all checks passed)."""
    result = cli.validate("reference", str(exported))
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_r1_the_cli_exports_the_same_file(cli, exported, tmp_path):
    """R1 through `scrubgpt-brain reference <data_dir>` (README usage): exit 0, a result line on
    stdout, nothing on stderr, and the same bytes as `export_reference`."""
    result = cli.run("reference", str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() and not result.stderr.strip(), (result.stdout, result.stderr)
    assert (tmp_path / "reference" / exported.name).read_bytes() == exported.read_bytes()


# ── R2 ───────────────────────────────────────────────────────────────────────


def test_r2_ids_names_and_orders_equal_the_contract_fixture(document, fixture_reference):
    """R2 "Phase, step and checkpoint ids, names and orders, and the obstacle families and leaves
    (ids and names), equal `contracts/fixtures/reference/rarp.json` (D-051, the contract leads)",
    compared in list order."""
    got, want = _public(document), _public(fixture_reference)
    assert [p["id"] for p in got["phases"]] == [p["id"] for p in want["phases"]]
    for g, w in zip(got["phases"], want["phases"], strict=True):
        assert g == w, f"phase {w['id']} differs:\n{g}\n{w}"
    assert [f["id"] for f in got["obstacle_taxonomy"]] == [
        f["id"] for f in want["obstacle_taxonomy"]
    ]
    for g, w in zip(got["obstacle_taxonomy"], want["obstacle_taxonomy"], strict=True):
        assert g == w, f"family {w['id']} differs:\n{g}\n{w}"
    assert document["id"] == fixture_reference["id"]


# ── R3 ───────────────────────────────────────────────────────────────────────


def test_r3_only_the_public_part_is_published(document):
    """R3 "Only the public part is published: no descriptions, visual cues, anatomy,
    instruments, known obstacles, order rules or GraSP crosswalk" (README: "Descriptions, visual
    cues, anatomy, instruments, known obstacles, order rules and the GraSP crosswalk stay
    Brain-internal"). The contract model ignores unknown keys (D-023), so the raw JSON is checked:
    exactly the contract's keys at every level."""
    assert set(document) == TOP_KEYS
    for phase in document["phases"]:
        assert set(phase) == PHASE_KEYS, phase["id"]
        assert set(phase["typical_duration_s"]) == DURATION_KEYS
        for step in phase["steps"]:
            assert set(step) == STEP_KEYS, step["id"]
            assert set(step["typical_duration_s"]) == DURATION_KEYS
            for checkpoint in step["checkpoints"]:
                assert set(checkpoint) == CHECKPOINT_KEYS, checkpoint["id"]
    for family in document["obstacle_taxonomy"]:
        assert set(family) == FAMILY_KEYS, family["id"]
        for leaf in family["leaves"]:
            assert set(leaf) == LEAF_KEYS, leaf["id"]
    leaked = [f"{path}.{key}" for path, key in _keys(document) if key in PRIVATE]
    assert not leaked, f"Brain-internal keys published: {leaked}"


def test_r3_typical_durations_are_the_rule_books(document, rulebook):
    """R3 "`typical_duration_s` equals the rule book's p25/p50/p75", for every phase and step."""
    raw_phases = {p["id"]: p for p in rulebook["phases"]}
    raw_steps = {s["id"]: s for p in rulebook["phases"] for s in p.get("steps") or []}
    assert [p["id"] for p in document["phases"]] == list(raw_phases)
    for phase in document["phases"]:
        want = raw_phases[phase["id"]]["typical_duration_s"]
        assert {k: phase["typical_duration_s"][k] for k in DURATION_KEYS} == {
            k: want[k] for k in DURATION_KEYS
        }, phase["id"]
        for step in phase["steps"]:
            want = raw_steps[step["id"]]["typical_duration_s"]
            assert {k: step["typical_duration_s"][k] for k in DURATION_KEYS} == {
                k: want[k] for k in DURATION_KEYS
            }, step["id"]
    assert sum(len(p["steps"]) for p in document["phases"]) == len(raw_steps)


# ── R4 ───────────────────────────────────────────────────────────────────────


def test_r4_a_re_export_of_unchanged_knowledge_is_byte_identical(exported, tmp_path):
    """R4 "Re-exporting unchanged knowledge is byte-identical (LF, trailing newline)": over the
    same file, and into a second data folder."""
    first = exported.read_bytes()
    again = export_reference(tmp_path)
    assert again.read_bytes() == first
    copy = tmp_path / "over"
    (copy / "reference").mkdir(parents=True)
    shutil.copy2(exported, copy / "reference" / exported.name)
    assert export_reference(copy).read_bytes() == first
    assert b"\r" not in first, "CR in the export: not LF line ends"
    assert first.endswith(b"\n") and not first.endswith(b"\n\n"), first[-20:]
    json.loads(first.decode("utf-8"))


# ── R5 ───────────────────────────────────────────────────────────────────────


def _broken(const, tmp_path: Path, how: str) -> Path:
    root = tmp_path / "knowledge"
    shutil.copytree(const.knowledge, root)
    path = root / "rulebooks" / "rarp.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = [s for p in raw["phases"] for s in p.get("steps") or []]
    if how == "unknown-term":  # the loader's check
        steps[0]["anatomy"].append("t1_no_such_term")
    elif how == "p25-above-p50":  # the loader's check
        d = steps[-1]["typical_duration_s"]
        d["p25"], d["p75"] = d["p50"] + 1, max(d["p75"], d["p50"] + 2)
    elif how == "duplicate-phase-order":  # the contract's check (unique phase order)
        raw["phases"][1]["order"] = raw["phases"][0]["order"]
    else:
        raise ValueError(how)
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return root


BROKEN = ["unknown-term", "p25-above-p50", "duplicate-phase-order"]


@pytest.mark.parametrize("how", BROKEN)
def test_r5_inconsistent_knowledge_writes_nothing(const, tmp_path, how):
    """R5 "Inconsistent knowledge (a broken copy via the loader's folder argument): an error …,
    with nothing written … and no staging files left" (README: "A failed export (inconsistent
    knowledge, or a contract error) writes nothing"). Into an empty data folder."""
    broken = _broken(const, tmp_path, how)
    data = tmp_path / "data"
    data.mkdir()
    with pytest.raises(ValueError):  # KnowledgeError is a ValueError, as is a contract error
        export_reference(data, knowledge_dir=broken)
    assert _files(data) == {}, _files(data)


@pytest.mark.parametrize("how", BROKEN)
def test_r5_a_failed_export_keeps_the_earlier_one(const, tmp_path, how):
    """R5 "… an earlier export unchanged, and no staging files left" (README: "leaves the earlier
    file as it was")."""
    data = tmp_path / "data"
    export_reference(data)
    before = _files(data)
    broken = _broken(const, tmp_path, how)
    with pytest.raises(ValueError):
        export_reference(data, knowledge_dir=broken)
    assert _files(data) == before, sorted(_files(data))


_CHILD = textwrap.dedent(
    """
    import functools, sys
    from pathlib import Path
    import scrubgpt_brain.pipeline.reference as reference
    reference.export_reference = functools.partial(
        reference.export_reference, knowledge_dir=Path(sys.argv[1])
    )
    from scrubgpt_brain.cli import main
    sys.exit(main(sys.argv[2:]))
    """
)


def test_r5_the_cli_exits_1_with_the_error_on_stderr(cli, const, tmp_path):
    """R5 "an error (exit 1, message on stderr)": `scrubgpt-brain reference <data_dir>` run in a
    child process whose export reads a broken knowledge copy (the CLI has no knowledge-folder
    option): exit 1, `scrubgpt-brain: error: …` naming the problem on stderr, nothing on stdout,
    and the earlier export unchanged."""
    data = tmp_path / "data"
    export_reference(data)
    before = _files(data)
    broken = _broken(const, tmp_path, "unknown-term")
    result = cli.run(command=[sys.executable, "-c", _CHILD, str(broken), "reference", str(data)])
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert "scrubgpt-brain: error:" in result.stderr, result.stderr
    assert "t1_no_such_term" in result.stderr, result.stderr
    assert not result.stdout.strip(), result.stdout
    assert _files(data) == before


def test_r5_the_child_harness_exports_when_knowledge_is_fine(cli, const, tmp_path):
    """Sanity for the R5 CLI test: the same child harness with an unchanged knowledge copy exits 0
    and exports, so the exit 1 above comes from the broken copy."""
    copy = tmp_path / "knowledge"
    shutil.copytree(const.knowledge, copy)
    data = tmp_path / "data"
    result = cli.run(command=[sys.executable, "-c", _CHILD, str(copy), "reference", str(data)])
    assert result.returncode == 0, result.stderr
    assert (data / "reference" / "rarp.json").is_file()


# ── R6 ───────────────────────────────────────────────────────────────────────


def test_r6_without_an_argument_data_dir_is_used(cli, exported, tmp_path):
    """R6 "Without an argument, `DATA_DIR` is used" (README "default: $DATA_DIR"): an absolute
    `DATA_DIR`, run from another working folder."""
    data = tmp_path / "data"
    work = tmp_path / "work"
    work.mkdir()
    result = cli.run("reference", env={"DATA_DIR": str(data)}, cwd=work)
    assert result.returncode == 0, result.stderr
    assert (data / "reference" / exported.name).read_bytes() == exported.read_bytes()
    assert _files(work) == {}


def test_r6_a_relative_data_dir_resolves_against_the_repo_root(cli, const, exported, tmp_path):
    """R6 "a relative `DATA_DIR` resolves against the repo root" (plan §4.1 "relative paths
    (`DATA_DIR`, …) resolve against the repo root, not the working directory", D-034): `DATA_DIR`
    is a path relative to the repo root that points into `tmp_path`; run from another working
    folder, the file lands there and nothing lands under the working folder."""
    target = tmp_path / "relative-data"
    try:
        relative = os.path.relpath(target, const.repo_root)
    except ValueError:
        pytest.skip("tmp_path is on another drive than the repo: no relative path between them")
    assert not Path(relative).is_absolute()
    work = tmp_path / "elsewhere" / "deeper"
    work.mkdir(parents=True)
    result = cli.run("reference", env={"DATA_DIR": relative}, cwd=work)
    assert result.returncode == 0, result.stderr
    assert (target / "reference" / exported.name).read_bytes() == exported.read_bytes()
    assert _files(tmp_path / "elsewhere") == {}


def test_r6_with_neither_exit_1_and_say_so(cli, tmp_path):
    """R6 "With neither, exit 1 with a message saying so" (CLI docstring: exit 1 for `reference`
    "… or no data folder"): no argument and no `DATA_DIR`: exit 1, `scrubgpt-brain: error: …`
    naming `DATA_DIR` on stderr, nothing written."""
    work = tmp_path / "work"
    work.mkdir()
    result = cli.run("reference", drop_env=("DATA_DIR",), cwd=work)
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert "scrubgpt-brain: error:" in result.stderr and "DATA_DIR" in result.stderr, result.stderr
    assert not result.stdout.strip()
    assert _files(work) == {}


def test_r6_an_empty_data_dir_counts_as_unset(cli, tmp_path):
    """R6 "With neither …": an empty `DATA_DIR` is no data folder either (exit 1, nothing written
    into the working folder)."""
    work = tmp_path / "work"
    work.mkdir()
    result = cli.run("reference", env={"DATA_DIR": ""}, cwd=work)
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert "DATA_DIR" in result.stderr
    assert _files(work) == {}
