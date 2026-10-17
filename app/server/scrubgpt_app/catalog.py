"""The case loader (I1): scan `DATA_DIR`, validate every case package against the contracts, keep
only complete, valid ones.

A package is checked with `scrubgpt_contracts.validate.validate_case`, the same check as
`scrubgpt-validate case` (plan §4.2, D-052 … D-064), so the app and the Brain agree on what a valid
package is. A package with any error is **rejected with its errors and never patched**; warnings
are kept and shown. Procedure References (`reference/<procedure_id>.json`, §4.2b) are loaded the
same way, for step and obstacle names.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from scrubgpt_contracts.models.case_package import (
    Case,
    Metrics,
    Moments,
    Questions,
    SeedRecords,
    Timeline,
)
from scrubgpt_contracts.models.common import Provenance, TrustLabel
from scrubgpt_contracts.models.reference import ProcedureReference
from scrubgpt_contracts.validate import (
    Report,
    ToolError,
    load_case,
    validate_case,
    validate_reference,
)


def report_problems(report: Report) -> tuple[str, ...]:
    """Every error and every check that could not run, one line each."""
    return tuple(str(issue) for issue in report.errors) + tuple(
        f"NOT RUN {reason}" for reason in report.blocked
    )


@dataclass(frozen=True)
class LoadedCase:
    """One complete, valid case package."""

    folder: Path
    case: Case
    timeline: Timeline
    moments: Moments
    questions: Questions
    seed_records: SeedRecords
    metrics: Metrics | None
    warnings: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return self.case.id

    def provenances(self) -> Iterable[Provenance]:
        timeline = self.timeline
        for items in (timeline.steps, timeline.events, timeline.instruments, timeline.utterances):
            yield from (item.provenance for item in items)
        yield from (moment.provenance for moment in self.moments.moments)
        yield from (record.provenance for record in self.seed_records.records)

    def trust_labels(self) -> list[TrustLabel]:
        """The distinct trust labels in the package, in the enum's order (for the case badges)."""
        found = {provenance.trust_label for provenance in self.provenances()}
        return [label for label in TrustLabel if label in found]

    def counts(self) -> dict[str, int]:
        return {
            "moments": len(self.moments.moments),
            "operating_questions": len(self.questions.operating),
            "reviewer_questions": len(self.questions.reviewer),
            "seed_records": len(self.seed_records.records),
        }


@dataclass(frozen=True)
class Rejected:
    """A package or reference file that failed validation, with the reasons."""

    path: Path
    problems: tuple[str, ...]


@dataclass(frozen=True)
class Catalog:
    """Everything the server loaded from `DATA_DIR` at the last scan."""

    data_dir: Path
    cases: dict[str, LoadedCase] = field(default_factory=dict)
    rejected: list[Rejected] = field(default_factory=list)
    references: dict[str, ProcedureReference] = field(default_factory=dict)
    rejected_references: list[Rejected] = field(default_factory=list)


def _load_valid_case(folder: Path, warnings: tuple[str, ...]) -> LoadedCase:
    """The parsed documents of a package that has just passed `validate_case`."""
    load = load_case(folder)
    optional_metrics = load.get("metrics.json", Metrics)
    documents = {
        "case": load.get("case.json", Case),
        "timeline": load.get("timeline.json", Timeline),
        "moments": load.get("moments.json", Moments),
        "questions": load.get("questions.json", Questions),
        "seed_records": load.get("seed_records.json", SeedRecords),
    }
    missing = [name for name, document in documents.items() if document is None]
    if missing:  # pragma: no cover (validate_case already failed in that case)
        raise ToolError(f"{folder}: {missing} did not load after validation")
    return LoadedCase(folder=folder, metrics=optional_metrics, warnings=warnings, **documents)


def load_references(reference_dir: Path) -> tuple[dict[str, ProcedureReference], list[Rejected]]:
    references: dict[str, ProcedureReference] = {}
    rejected: list[Rejected] = []
    if not reference_dir.is_dir():
        return references, rejected
    for path in sorted(reference_dir.glob("*.json")):
        report = validate_reference(path)
        if not report.ok:
            rejected.append(Rejected(path, report_problems(report)))
            continue
        reference = ProcedureReference.model_validate_json(path.read_bytes())
        references[reference.id] = reference
    return references, rejected


def scan(data_dir: Path) -> Catalog:
    """Validate every `cases/<case_id>/` folder and every `reference/*.json` under `data_dir`.

    A missing `cases/` folder gives an empty catalog (the UI says there are no cases).
    """
    references, rejected_references = load_references(data_dir / "reference")
    catalog = Catalog(
        data_dir=data_dir, references=references, rejected_references=rejected_references
    )
    cases_dir = data_dir / "cases"
    if not cases_dir.is_dir():
        return catalog
    for folder in sorted(p for p in cases_dir.iterdir() if p.is_dir()):
        try:
            report = validate_case(folder)
        except ToolError as exc:
            catalog.rejected.append(Rejected(folder, (f"NOT RUN {exc}",)))
            continue
        if not report.ok:
            catalog.rejected.append(Rejected(folder, report_problems(report)))
            continue
        loaded = _load_valid_case(folder, tuple(str(w) for w in report.warnings))
        catalog.cases[loaded.id] = loaded
    return catalog
