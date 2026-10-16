"""T2 acceptance: scrubgpt-codegen (brief criterion 18).

Sources: plan §4.1 "Code generation" (JSON Schema with mode="serialization"; v1.0 models have no
defaults, so every v1.0 key is required in the schema and the TS types); plan §4.5
(scrubgpt-codegen generates schema/ and ts/ via pinned json-schema-to-typescript);
contracts/README.md (--out lets Tester 2 test it without touching tracked files); brain_api.md
"Generated types" (one schema per top-level model, ts/contracts.ts, byte-for-byte reproducible,
LF line endings, CI fails if stale); D-049 (utterance `class` on the wire).

Codegen runs only with --out <tmp dir>. The TypeScript half needs npx (Node); the package is
pinned and normally cached, so this test is not `live`; it is skipped if npx is missing.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

CASE_PACKAGE_MODELS = ("Case", "Timeline", "Moments", "Questions", "SeedRecords", "Metrics")


@pytest.fixture(scope="module")
def expected_models(endpoints) -> set[str]:
    """Brief c18: Case Package files, ProcedureReference, DecisionRecord, DecisionRecordDraft,
    ApiError, every ENDPOINTS request and response."""
    from scrubgpt_contracts.models import case_package, common, decision_record, reference

    names = set()
    for n in CASE_PACKAGE_MODELS:
        assert hasattr(case_package, n), f"case_package has no {n} model"
        names.add(getattr(case_package, n).__name__)
    names.add(reference.ProcedureReference.__name__)
    names.add(decision_record.DecisionRecord.__name__)
    names.add(decision_record.DecisionRecordDraft.__name__)
    names.add(common.ApiError.__name__)
    for ep in endpoints.values():
        if ep.request is not None:
            names.add(ep.request.__name__)
        names.add(ep.response.__name__)
    return names


def _npx_available() -> bool:
    return shutil.which("npx") is not None or shutil.which("npx.cmd") is not None


def _run_codegen(out: Path, *, schema_only: bool = False) -> None:
    from scrubgpt_contracts.codegen import main

    argv = ["--out", str(out)] + (["--schema-only"] if schema_only else [])
    assert main(argv) == 0


def _files(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != ".gitkeep"
    }


@pytest.fixture(scope="module")
def generated(tmp_path_factory) -> tuple[dict[str, bytes], dict[str, bytes]]:
    """Two full codegen runs into two temporary folders."""
    if not _npx_available():
        pytest.skip("npx (Node) not on PATH: the TypeScript half of codegen can't run")
    a = tmp_path_factory.mktemp("codegen_a")
    b = tmp_path_factory.mktemp("codegen_b")
    _run_codegen(a)
    _run_codegen(b)
    return _files(a), _files(b)


@pytest.fixture(scope="module")
def schemas_only(tmp_path_factory) -> dict[str, bytes]:
    out = tmp_path_factory.mktemp("codegen_schema_only")
    _run_codegen(out, schema_only=True)
    return _files(out)


def test_c18_one_schema_per_top_level_model(schemas_only, expected_models):
    """Brief c18: writes schema/<Model>.schema.json for every top-level model."""
    written = {
        Path(k).name.removesuffix(".schema.json")
        for k in schemas_only
        if k.startswith("schema/") and k.endswith(".schema.json")
    }
    missing = expected_models - written
    assert not missing, f"missing schemas: {sorted(missing)}"
    assert all(k.startswith("schema/") for k in schemas_only), sorted(schemas_only)


def _object_nodes(node: Any, where: str = "#"):
    if isinstance(node, dict):
        if isinstance(node.get("properties"), dict):
            yield where, node
        for k, v in node.items():
            yield from _object_nodes(v, f"{where}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _object_nodes(v, f"{where}/{i}")


def test_c18_every_v1_field_is_required(schemas_only):
    """Brief c18 / plan §4.1: every v1.0 field is required in the schema (no MINOR-added fields
    exist yet at contract 1.0, so every property of every object is required)."""
    problems = []
    for name, data in schemas_only.items():
        schema = json.loads(data)
        for where, node in _object_nodes(schema):
            props = set(node["properties"])
            required = set(node.get("required", []))
            if props - required:
                problems.append(f"{name} {where}: optional {sorted(props - required)}")
    assert not problems, "\n".join(problems[:30])


def test_c18_schema_is_the_wire_format(schemas_only):
    """plan §4.1 mode="serialization" (the wire format) / D-049: the utterance field is `class`
    on the wire, never the Python name `class_`; every schema declares JSON Schema 2020-12
    (brain_api.md)."""
    timeline = json.loads(schemas_only["schema/Timeline.schema.json"])
    text = json.dumps(timeline)
    assert '"class_"' not in text
    assert any("class" in node["properties"] for _, node in _object_nodes(timeline))
    for name, data in schemas_only.items():
        schema = json.loads(data)
        assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", name


def test_c18_typescript_written_with_every_model(generated, expected_models):
    """Brief c18: ts/contracts.ts is written and declares every top-level model; v1.0 keys are
    required in the TS types too (plan §4.1), so no property is optional (`?:`)."""
    first, _ = generated
    assert "ts/contracts.ts" in first
    ts = first["ts/contracts.ts"].decode("utf-8")
    for name in sorted(expected_models):
        assert re.search(rf"export (interface|type) {name}\b", ts), f"no TS type for {name}"
    optional = re.findall(r"^\s*[\"']?[A-Za-z_][\w]*[\"']?\?:", ts, flags=re.M)
    assert not optional, optional[:10]


def test_c18_two_runs_are_byte_identical_with_lf(generated):
    """Brief c18: two runs give byte-identical output with LF line endings."""
    first, second = generated
    assert sorted(first) == sorted(second)
    for name in first:
        assert first[name] == second[name], f"{name} differs between runs"
        assert b"\r" not in first[name], f"{name} has CR line endings"
        assert first[name].endswith(b"\n"), f"{name} doesn't end with a newline"


def test_c18_schema_only_matches_full_run(generated, schemas_only):
    """brain_api.md: --schema-only writes the same schema/ as a full run."""
    first, _ = generated
    assert {k: v for k, v in first.items() if k.startswith("schema/")} == schemas_only


def test_c18_committed_schema_and_ts_match_a_fresh_run(generated, paths):
    """Brief c18 / brain_api.md "CI fails if they are stale": the committed contracts/schema/ and
    contracts/ts/ (as stored in git at HEAD) match a fresh run byte for byte."""
    first, _ = generated
    repo = paths["repo"]
    listed = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD", "--", "contracts/schema", "contracts/ts"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    committed = {}
    for path in listed:
        if path.endswith(".gitkeep"):
            continue
        blob = subprocess.run(
            ["git", "show", f"HEAD:{path}"], cwd=repo, capture_output=True, check=True
        ).stdout
        committed[path.removeprefix("contracts/")] = blob
    assert sorted(committed) == sorted(first)
    stale = [k for k in first if committed[k] != first[k]]
    assert not stale, f"stale generated files: {stale}"
