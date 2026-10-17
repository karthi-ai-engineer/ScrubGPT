"""Procedure Reference export (Block 1; plan §4.2b, D-035): `knowledge/` → the contract file the
App reads, `<DATA_DIR>/reference/<procedure_id>.json`.

The App never reads the Brain's YAML knowledge. It reads this file to name and order the steps of
a timeline, the checkpoints of a moment and the obstacle families and leaves of the Knowledge
Library, in both languages. So the export publishes exactly the public part of the rule book:
- phases and steps, with bilingual names, order and typical durations;
- checkpoints;
- the 8 obstacle families with their leaves.

Everything else stays Brain-internal: descriptions, visual cues, anatomy, instruments, known
obstacles, order rules, the GraSP crosswalk.

The output is built from the loader's checked objects, validated by the contract's own
`ProcedureReference` model and by `scrubgpt-validate reference`, then written atomically. The App
can never see a half-written or invalid file. **The ids are stable from the first export on**:
timelines, moments and Decision Records point at them (D-051 and the reference README).
"""

import json
import os
from pathlib import Path

from scrubgpt_contracts.models.common import CONTRACT_VERSION
from scrubgpt_contracts.models.reference import ProcedureReference
from scrubgpt_contracts.validate import validate_reference

from scrubgpt_brain.engines.rulebook import KNOWLEDGE_DIR, Duration, Knowledge, Text, load_knowledge

REFERENCE_DIR = "reference"


def _bilingual(text: Text) -> dict[str, str]:
    return {"ja": text.ja, "en": text.en}


def _duration(duration: Duration) -> dict[str, float]:
    return {"p25": duration.p25, "p50": duration.p50, "p75": duration.p75}


def build_reference(knowledge: Knowledge) -> ProcedureReference:
    """The Procedure Reference for the loaded knowledge, validated by the contract model."""
    book = knowledge.rulebook
    data = {
        "contract_version": CONTRACT_VERSION,
        "id": book.id,
        "name": _bilingual(book.name),
        "phases": [
            {
                "id": phase.id,
                "name": _bilingual(phase.name),
                "order": phase.order,
                "typical_duration_s": _duration(phase.duration),
                "steps": [
                    {
                        "id": step.id,
                        "name": _bilingual(step.name),
                        "order": step.order,
                        "typical_duration_s": _duration(step.duration),
                        "checkpoints": [
                            {"id": checkpoint.id, "text": _bilingual(checkpoint.text)}
                            for checkpoint in step.checkpoints
                        ],
                    }
                    for step in phase.steps
                ],
            }
            for phase in book.phases
        ],
        "obstacle_taxonomy": [
            {
                "id": family.id,
                "name": _bilingual(family.name),
                "leaves": [
                    {"id": leaf.id, "name": _bilingual(leaf.name)} for leaf in family.leaves
                ],
            }
            for family in knowledge.families
        ],
    }
    return ProcedureReference.model_validate(data)


def reference_path(data_dir: Path, procedure_id: str) -> Path:
    """`<data_dir>/reference/<procedure_id>.json`."""
    return data_dir / REFERENCE_DIR / f"{procedure_id}.json"


def export_reference(data_dir: Path, *, knowledge_dir: Path = KNOWLEDGE_DIR) -> Path:
    """Export the Procedure Reference into `<data_dir>/reference/<id>.json` and return its path.

    Raises `KnowledgeError` if `knowledge/` is inconsistent, or `ValueError` if the result fails the
    contract; in both cases nothing is written and an earlier export stays as it was.
    """
    reference = build_reference(load_knowledge(knowledge_dir))
    target = reference_path(data_dir, reference.id)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(reference.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    # The validator wants the final file name (`<id>.json`), so check a staged copy under that name.
    staging = target.parent / f".{reference.id}.export"
    staging.mkdir(exist_ok=True)
    staged = staging / target.name
    try:
        staged.write_text(text, encoding="utf-8", newline="\n")
        report = validate_reference(staged)
        if not report.ok:
            raise ValueError(f"the exported reference fails the contract:\n{report.render()}")
        os.replace(staged, target)
    finally:
        staged.unlink(missing_ok=True)
        staging.rmdir()
    return target
