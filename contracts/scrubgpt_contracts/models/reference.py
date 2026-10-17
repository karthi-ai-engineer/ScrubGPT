"""Contract #1b: the Procedure Reference, `<DATA_DIR>/reference/<procedure_id>.json`.

Plan §4.2b, D-035.

The public part of the rule book: phases, steps and checkpoints with bilingual names, and the
obstacle taxonomy. Timeline `step_id`s, moment `checkpoint_id`s and obstacle leaf ids point here.
Dev1 exports it from `knowledge/` (A1, A3, A4); the IDs stay stable once exported.
"""

from collections.abc import Iterable, Iterator
from typing import Annotated, Self

from pydantic import Field, StrictInt, model_validator

from scrubgpt_contracts.models.common import (
    Bilingual,
    CheckpointId,
    ContractModel,
    ObstacleFamily,
    ObstacleLeafId,
    PhaseId,
    ProcedureId,
    Seconds,
    StepId,
    VersionedModel,
)

Order = Annotated[StrictInt, Field(ge=1)]
"""Position within its list, from 1."""


def _unique(values: Iterable[object], what: str) -> None:
    seen: set[object] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"duplicate {what} {value}")
        seen.add(value)


def _prefixed(ids: Iterable[str], parent: str, what: str) -> None:
    for item_id in ids:
        if not item_id.startswith(f"{parent}."):
            raise ValueError(f"{what} {item_id} is not inside {parent}")


class DurationStats(ContractModel):
    """Typical duration in seconds: 25th, 50th and 75th percentile."""

    p25: Seconds
    p50: Seconds
    p75: Seconds

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not self.p25 <= self.p50 <= self.p75:
            raise ValueError("expected p25 <= p50 <= p75")
        return self


class Checkpoint(ContractModel):
    """Something that should be confirmed before moving on, e.g. "Ureteral orifices identified"."""

    id: CheckpointId
    text: Bilingual


class Step(ContractModel):
    """A step of a phase. Checkpoints belong to steps."""

    id: StepId
    name: Bilingual
    order: Order
    typical_duration_s: DurationStats
    checkpoints: list[Checkpoint]

    @model_validator(mode="after")
    def _checkpoints(self) -> Self:
        ids = [checkpoint.id for checkpoint in self.checkpoints]
        _unique(ids, "checkpoint")
        _prefixed(ids, self.id, "checkpoint")
        return self


class Phase(ContractModel):
    """A phase of the procedure."""

    id: PhaseId
    name: Bilingual
    order: Order
    typical_duration_s: DurationStats
    steps: list[Step]

    @model_validator(mode="after")
    def _steps(self) -> Self:
        ids = [step.id for step in self.steps]
        _unique(ids, "step")
        _prefixed(ids, self.id, "step")
        _unique((step.order for step in self.steps), f"step order in {self.id}")
        return self


class ObstacleLeaf(ContractModel):
    """A specific obstacle, e.g. `anatomical_variation.median_lobe`."""

    id: ObstacleLeafId
    name: Bilingual


class ObstacleFamilyEntry(ContractModel):
    """One of the 8 fixed obstacle families, with its leaves."""

    id: ObstacleFamily
    name: Bilingual
    leaves: list[ObstacleLeaf]

    @model_validator(mode="after")
    def _leaves(self) -> Self:
        ids = [leaf.id for leaf in self.leaves]
        _unique(ids, "obstacle leaf")
        _prefixed(ids, self.id.value, "obstacle leaf")
        return self


class ProcedureReference(VersionedModel):
    """`reference/<procedure_id>.json`: phases, steps, checkpoints and the obstacle taxonomy."""

    id: ProcedureId
    """e.g. `rarp`; the file is `reference/<id>.json`."""
    name: Bilingual
    phases: list[Phase]
    obstacle_taxonomy: list[ObstacleFamilyEntry]
    """Exactly the 8 fixed families (D-035), each with its leaves."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        ids = [phase.id for phase in self.phases]
        _unique(ids, "phase")
        _prefixed(ids, self.id, "phase")
        _unique((phase.order for phase in self.phases), "phase order")
        families = [entry.id for entry in self.obstacle_taxonomy]
        _unique(families, "obstacle family")
        missing = set(ObstacleFamily) - set(families)
        if missing:
            raise ValueError(f"obstacle families missing: {sorted(f.value for f in missing)}")
        return self

    def steps(self) -> Iterator[Step]:
        """Every step, phase by phase."""
        for phase in self.phases:
            yield from phase.steps

    def step(self, step_id: str) -> Step | None:
        """The step with this id, or `None`."""
        return next((step for step in self.steps() if step.id == step_id), None)

    def checkpoint_ids(self) -> set[str]:
        return {checkpoint.id for step in self.steps() for checkpoint in step.checkpoints}

    def leaf_ids(self) -> set[str]:
        return {leaf.id for entry in self.obstacle_taxonomy for leaf in entry.leaves}
