"""Shared helpers for Tester 1's Phase 0 contract acceptance tests (D-044).

Everything here is offline: the synthetic fixtures in `contracts/fixtures/` are read-only;
anything that has to be modified or broken is copied into `tmp_path` first.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURES = REPO_ROOT / "contracts" / "fixtures"
FIXTURE_CASE = FIXTURES / "cases" / "case-fixture-01"
FIXTURE_REFERENCE = FIXTURES / "reference" / "rarp.json"
CASE_ID = "case-fixture-01"

REQUIRED_CASE_FILES = (
    "case.json",
    "video.mp4",
    "poster.jpg",
    "timeline.json",
    "moments.json",
    "questions.json",
    "clips",
    "seed_records.json",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture(scope="session")
def paths() -> dict[str, Path]:
    return {
        "repo": REPO_ROOT,
        "fixtures": FIXTURES,
        "case": FIXTURE_CASE,
        "reference": FIXTURE_REFERENCE,
    }


@pytest.fixture(scope="session")
def _fixture_docs() -> dict[str, Any]:
    docs = {
        name: read_json(FIXTURE_CASE / name)
        for name in (
            "case.json",
            "timeline.json",
            "moments.json",
            "questions.json",
            "seed_records.json",
        )
    }
    docs["rarp.json"] = read_json(FIXTURE_REFERENCE)
    return docs


@pytest.fixture
def docs(_fixture_docs: dict[str, Any]) -> dict[str, Any]:
    """Fresh deep copies of the fixture JSON documents (safe to mutate)."""
    return copy.deepcopy(_fixture_docs)


@pytest.fixture
def metrics_doc() -> dict[str, Any]:
    """A hand-written metrics.json per plan §4.2 (the fixture case is not a GraSP case)."""
    return {
        "contract_version": "1.0",
        "case_id": CASE_ID,
        "frame_accuracy": 0.71,
        "segment_f1": 0.64,
        "per_step": [
            {"step_id": "rarp.p03.s01", "precision": 0.8, "recall": 0.75},
            {"step_id": "rarp.p04.s02", "precision": 0.6, "recall": 0.5},
        ],
        "n_frames": 1500,
        "model_info": {
            "model_tier": "VISION_FAST",
            "model": "fixture",
            "prompt_version": "step_window.v1",
        },
    }


@pytest.fixture
def api_error_doc() -> dict[str, Any]:
    return {
        "contract_version": "1.0",
        "error": {"code": "bad_request", "message": "missing field 'texts'", "retryable": False},
    }


@dataclass
class DataDir:
    """A throw-away copy of the fixtures laid out like DATA_DIR (plan §4.5, D-026)."""

    root: Path
    case_dir: Path
    reference: Path

    def load(self, name: str) -> Any:
        return read_json(self.case_dir / name)

    def save(self, name: str, data: Any) -> None:
        write_json(self.case_dir / name, data)


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DataDir:
    root = tmp_path / "data"
    case_dir = root / "cases" / CASE_ID
    shutil.copytree(FIXTURE_CASE, case_dir)
    (root / "reference").mkdir(parents=True)
    reference = root / "reference" / "rarp.json"
    shutil.copy2(FIXTURE_REFERENCE, reference)
    monkeypatch.setenv("DATA_DIR", str(root))
    return DataDir(root=root, case_dir=case_dir, reference=reference)


@dataclass
class CliResult:
    code: int
    output: str

    @property
    def problems(self) -> str:
        """The output without the header, the "checked ..." progress lines and the verdict, so
        a file name found here comes from an error or warning, not from progress lines."""
        keep = []
        for line in self.output.splitlines():
            text = line.strip()
            if (
                line.startswith("scrubgpt-validate:")
                or text.startswith("checked")
                or text.startswith(("PASS", "FAIL"))
            ):
                continue
            keep.append(line)
        return "\n".join(keep)

    @property
    def error_lines(self) -> list[str]:
        """The printed `ERROR ...` lines."""
        return [ln.strip() for ln in self.output.splitlines() if ln.strip().startswith("ERROR")]

    @property
    def warning_lines(self) -> list[str]:
        """The printed `WARNING ...` lines."""
        return [ln.strip() for ln in self.output.splitlines() if ln.strip().startswith("WARNING")]

    @property
    def counts(self) -> tuple[int, int]:
        """(errors, warnings) from the verdict line `PASS|FAIL: <n> error(s), <m> warning(s)`."""
        match = re.search(r"(\d+) error\(s\), (\d+) warning\(s\)", self.output)
        assert match, f"no verdict line:\n{self.output}"
        return int(match.group(1)), int(match.group(2))


@pytest.fixture
def run_validate():
    """Run `scrubgpt-validate` in-process via its `main(argv)` entry point."""
    from scrubgpt_contracts import validate

    def _run(*argv: str | Path) -> CliResult:
        lines: list[str] = []
        try:
            code = validate.main([str(a) for a in argv], out=lambda s: lines.append(str(s)))
        except SystemExit as exc:  # argparse usage errors
            code = exc.code if isinstance(exc.code, int) else 2
        return CliResult(code=code, output="\n".join(lines))

    return _run
