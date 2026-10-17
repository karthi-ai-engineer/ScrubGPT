"""#9 AC11 (generated files), AC12 (fixture coverage) and AC13 (dependency bounds) (Team Lead triage
on issue #9, logged as D-058; Dev1's accepted analysis on #9).

AC12 (verbatim): "The fixture now contains at least: one `narration_extracted` 🎙️ seed record with
`transcript` evidence and a grounding with `source: narration`; one grounding with `source: edit`;
one `answer_audio` evidence; one `delayed_outcome` `known` and one `not_applicable`; one record
with `obstacle.type: null`; and a valid `metrics.json`. `contracts/fixtures/` stays <= 5 MB
(D-036)."
AC13 (verbatim): "`contracts/pyproject.toml` declares `pydantic>=2...,<3`; `uv sync --all-packages`
gives no build-backend warning on the team's uv" - uv 0.12.22 on this machine and uv 0.13.1 on
Dev2's (brief, from Dev1's accepted analysis).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
import unicodedata
from pathlib import Path
from typing import Any

import pytest
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version
from scrubgpt_contracts.models.case_package import Metrics, SeedRecords
from scrubgpt_contracts.models.decision_record import DecisionRecord, unverbatim_groundings

TEAM_UV = ("0.12.22", "0.13.1")


def _records(docs) -> list[dict[str, Any]]:
    SeedRecords.model_validate(docs["seed_records.json"])
    return docs["seed_records.json"]["records"]


# --- AC12: fixture coverage ---------------------------------------------------------------------


def test_9ac12_narration_record_with_transcript_evidence_and_narration_grounding(docs):
    """#9 AC12: "one `narration_extracted` 🎙️ seed record with `transcript` evidence and a
    grounding with `source: narration`" - in the same record, the transcript quoting an utterance
    of the case, and the narration grounding verbatim in it (AC7)."""
    utterances = {u["id"]: u for u in docs["timeline.json"]["utterances"]}
    found = []
    for record in _records(docs):
        if record["provenance"]["trust_label"] != "narration_extracted":
            continue
        transcripts = [e for e in record["evidence"] if e["kind"] == "transcript"]
        narration = [g for g in record["grounding"] if g["source"] == "narration"]
        if not (transcripts and narration):
            continue
        for e in transcripts:
            assert e["utterance_id"] in utterances, e
        quotes = [unicodedata.normalize("NFC", e["quote"]) for e in transcripts]
        for g in narration:
            assert any(unicodedata.normalize("NFC", g["quote"]) in q for q in quotes), g
        found.append(record["id"])
    assert found, "no narration_extracted record with transcript evidence and a narration grounding"


def test_9ac12_an_edit_grounding(docs):
    """#9 AC12: "one grounding with `source: edit`"."""
    assert any(g["source"] == "edit" for r in _records(docs) for g in r["grounding"])


def test_9ac12_an_answer_audio_evidence(docs):
    """#9 AC12: "one `answer_audio` evidence"."""
    assert any(e["kind"] == "answer_audio" for r in _records(docs) for e in r["evidence"])


@pytest.mark.parametrize("status", ["known", "not_applicable"])
def test_9ac12_delayed_outcome_known_and_not_applicable(docs, status):
    """#9 AC12: "one `delayed_outcome` `known` and one `not_applicable`" (coherent with AC9: a
    `known` outcome has text, a `not_applicable` one has none, since AC11 allows no warning)."""
    outcomes = [r["delayed_outcome"] for r in _records(docs)]
    matching = [o for o in outcomes if o["status"] == status]
    assert matching, f"no delayed_outcome {status}"
    if status == "known":
        assert any(o["text"] is not None for o in matching)
    else:
        assert any(o["text"] is None for o in matching)


def test_9ac12_a_record_with_obstacle_type_null(docs):
    """#9 AC12: "one record with `obstacle.type: null`" (an obstacle whose family is known but no
    taxonomy leaf)."""
    hits = [
        r for r in _records(docs) if r["obstacle"] is not None and r["obstacle"]["type"] is None
    ]
    assert hits
    for record in hits:
        DecisionRecord.model_validate(record)


def test_9ac12_valid_metrics_json(paths, docs, run_validate, monkeypatch):
    """#9 AC12: "a valid `metrics.json`": it validates against `Metrics` (plan §4.2), belongs to
    the case, names steps of the fixture reference, and `validate case` checks it with no
    error."""
    path = paths["case"] / "metrics.json"
    assert path.is_file()
    metrics = Metrics.model_validate_json(path.read_text(encoding="utf-8"))
    dumped = metrics.model_dump(mode="json")
    assert dumped["case_id"] == docs["case.json"]["id"]
    steps = {s["id"] for p in docs["rarp.json"]["phases"] for s in p["steps"]}
    assert dumped["per_step"] and {s["step_id"] for s in dumped["per_step"]} <= steps
    monkeypatch.setenv("DATA_DIR", str(paths["fixtures"]))
    result = run_validate("case", paths["case"])
    assert result.code == 0, result.output
    assert "checked metrics.json" in result.output, result.output
    assert not [ln for ln in result.error_lines + result.warning_lines if "metrics" in ln]


def test_9ac12_new_records_are_verbatim_and_grounded(docs):
    """#9 AC12 + AC7/AC11: the added records keep the fixture's G5 rules: every `answer` and
    `narration` grounding is verbatim (`unverbatim_groundings() == []`)."""
    for record in _records(docs):
        assert list(unverbatim_groundings(DecisionRecord.model_validate(record))) == [], record[
            "id"
        ]


def test_9ac12_fixtures_folder_at_most_5_mb(paths):
    """#9 AC12: "`contracts/fixtures/` stays <= 5 MB (D-036)"."""
    total = sum(p.stat().st_size for p in paths["fixtures"].rglob("*") if p.is_file())
    assert total <= 5 * 1000 * 1000, f"contracts/fixtures/ is {total} bytes"


# --- AC11: schema/ and ts/ match scrubgpt-codegen -----------------------------------------------


def _codegen(out: Path, *extra: str) -> None:
    exe = shutil.which("scrubgpt-codegen")
    assert exe, "scrubgpt-codegen is not installed in the uv environment"
    proc = subprocess.run(
        [exe, "--out", str(out), *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def _files(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8").replace("\r\n", "\n")
        for p in root.rglob("*")
        if p.is_file() and p.name != ".gitkeep"
    }


def _same_tree(generated: Path, committed: Path) -> None:
    mine, theirs = _files(generated), _files(committed)
    assert sorted(mine) == sorted(theirs), (sorted(mine), sorted(theirs))
    stale = [name for name in mine if mine[name] != theirs[name]]
    assert not stale, f"committed files differ from scrubgpt-codegen output: {stale}"


def test_9ac11_committed_schema_matches_codegen(tmp_path, paths):
    """#9 AC11: "`schema/` ... match `scrubgpt-codegen` (CI)" (codegen only with `--out <tmp>`)."""
    _codegen(tmp_path, "--schema-only")
    _same_tree(tmp_path / "schema", paths["repo"] / "contracts" / "schema")


def test_9ac11_committed_ts_matches_codegen(tmp_path, paths):
    """#9 AC11: "... `ts/` match `scrubgpt-codegen` (CI)" (needs Node's `npx`)."""
    if not shutil.which("npx"):
        pytest.skip("npx not on PATH: TypeScript generation not checked")
    _codegen(tmp_path)
    _same_tree(tmp_path / "ts", paths["repo"] / "contracts" / "ts")


# --- AC13: dependency bounds and the build backend -----------------------------------------------


def _pyproject(paths) -> dict[str, Any]:
    return tomllib.loads((paths["repo"] / "contracts" / "pyproject.toml").read_text("utf-8"))


def test_9ac13_pydantic_has_lower_bound_2_and_upper_bound_3(paths):
    """#9 AC13: "`contracts/pyproject.toml` declares `pydantic>=2...,<3`" (triage: "`pydantic`
    gets an upper bound `<3`")."""
    deps = [Requirement(d) for d in _pyproject(paths)["project"]["dependencies"]]
    pydantic = [r for r in deps if r.name.lower() == "pydantic"]
    assert len(pydantic) == 1, deps
    specs = {(s.operator, s.version) for s in pydantic[0].specifier}
    assert ("<", "3") in specs, specs
    floors = [Version(v) for op, v in specs if op == ">="]
    assert floors and floors[0].major == 2, specs
    assert not pydantic[0].specifier.contains("3.0.0")
    assert not pydantic[0].specifier.contains("3.0.0a1", prereleases=True)


def test_9ac13_installed_metadata_carries_the_bound():
    """#9 AC13: the installed `scrubgpt-contracts` metadata has the same `<3` bound."""
    import importlib.metadata as metadata

    requires = metadata.distribution("scrubgpt-contracts").requires or []
    pydantic = [Requirement(r) for r in requires if Requirement(r).name.lower() == "pydantic"]
    assert pydantic and ("<", "3") in {(s.operator, s.version) for s in pydantic[0].specifier}


@pytest.mark.parametrize("uv_version", TEAM_UV)
def test_9ac13_uv_build_bound_covers_the_teams_uv(paths, uv_version):
    """#9 AC13 + triage: "Dev1 picks the `uv_build` bound to match the uv the team runs": the
    `build-system.requires` range of `uv_build` admits uv 0.12.22 (this machine) and 0.13.1
    (Dev2's), so uv builds the package itself with no version-mismatch warning."""
    build = _pyproject(paths)["build-system"]
    assert build["build-backend"] == "uv_build"
    reqs = [Requirement(r) for r in build["requires"]]
    uv_build = [r for r in reqs if r.name.lower().replace("-", "_") == "uv_build"]
    assert len(uv_build) == 1, reqs
    assert SpecifierSet(str(uv_build[0].specifier)).contains(uv_version), uv_build[0]


def test_9ac13_uv_sync_all_packages_gives_no_build_backend_warning(tmp_path, paths):
    """#9 AC13: "`uv sync --all-packages` gives no build-backend warning on the team's uv". Run
    offline into a throw-away environment (`UV_PROJECT_ENVIRONMENT=<tmp>`, `--locked` so
    `uv.lock` is never rewritten) and force a fresh build of `scrubgpt-contracts`
    (`--reinstall-package`), so the build backend really runs."""
    uv = os.environ.get("UV") or shutil.which("uv")
    assert uv, "uv not found"
    version = subprocess.run([uv, "--version"], capture_output=True, text=True, timeout=60)
    lock = paths["repo"] / "uv.lock"
    before = lock.read_bytes()
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "UV_OFFLINE")}
    env["UV_PROJECT_ENVIRONMENT"] = str(tmp_path / "venv")
    proc = subprocess.run(
        [
            uv,
            "sync",
            "--all-packages",
            "--locked",
            "--offline",
            "--reinstall-package",
            "scrubgpt-contracts",
        ],
        cwd=paths["repo"],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    output = proc.stdout + proc.stderr
    assert lock.read_bytes() == before, "uv.lock was rewritten"
    assert proc.returncode == 0, f"{version.stdout}{output}"
    assert "Built scrubgpt-contracts" in output, output  # the backend ran
    warnings = [ln for ln in output.splitlines() if "warn" in ln.lower()]
    backend = [ln for ln in output.splitlines() if "uv_build" in ln or "build backend" in ln]
    assert not warnings and not backend, f"{version.stdout.strip()}:\n{output}"
