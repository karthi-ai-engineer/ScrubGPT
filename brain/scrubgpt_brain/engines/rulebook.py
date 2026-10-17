"""Rule-book loader: the Brain's one reader of `knowledge/` (A1 rule book, A3 taxonomy, A4 vocab).

Every stage that needs surgical knowledge asks this module, so the files are parsed and checked
once, the same way:
- step recognition (C2: the step list and visual cues for the prompt);
- rule-book decoding (C3: step order and typical durations);
- deviation detection (E2: optional and movable phases);
- the reference export (after `contracts-v1.0`).

The loader checks what the files promise each other:
- unique ids;
- every reference resolves: step → obstacle leaf and vocabulary term, leaf → step and term,
  order rules → phases, GraSP crosswalk → phases/steps;
- the rule book's `known_obstacles` and the taxonomy's leaf `steps` list the same pairs;
- every name is bilingual;
- every typical duration has 0 < p25 ≤ p50 ≤ p75.

A broken file raises `KnowledgeError`, listing every problem with the file and the id, instead
of failing later deep inside a pipeline stage. The loader reads only the folder it is given
(default: the repo's `knowledge/`), never `DATA_DIR` or `.env`.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

KNOWLEDGE_DIR = Path(__file__).resolve().parents[3] / "knowledge"
"""The repo's `knowledge/` folder."""
RULEBOOK_FILE = Path("rulebooks/rarp.yaml")
TAXONOMY_FILE = Path("taxonomy/obstacles.yaml")
VOCAB_FILE = Path("vocab/terms.yaml")


class KnowledgeError(ValueError):
    """The knowledge files are missing, unreadable or inconsistent. `problems` lists each one."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__(
            f"{len(problems)} problem(s) in the knowledge files:\n"
            + "\n".join(f"- {p}" for p in problems)
        )


@dataclass(frozen=True)
class Text:
    """A human-readable text in Japanese and English, both non-empty."""

    ja: str
    en: str


@dataclass(frozen=True)
class Duration:
    """Typical duration in seconds (p25, p50, p75): a draft estimate until measured on GraSP."""

    p25: float
    p50: float
    p75: float


@dataclass(frozen=True)
class Checkpoint:
    id: str
    text: Text


@dataclass(frozen=True)
class Step:
    id: str
    phase_id: str
    order: int
    name: Text
    description: Text | None
    visual_cues: Text | None
    duration: Duration
    anatomy: tuple[str, ...]
    """Vocabulary term ids."""
    instruments: tuple[str, ...]
    """Vocabulary term ids (= instrument keys on the timeline, D-049)."""
    checkpoints: tuple[Checkpoint, ...]
    known_obstacles: tuple[str, ...]
    """Taxonomy leaf ids."""


@dataclass(frozen=True)
class Phase:
    id: str
    order: int
    name: Text
    optional: bool
    duration: Duration
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class MovablePhase:
    phase: str
    may_follow: tuple[str, ...]
    """Phases it may come right after (its own place in the order is one of them)."""


@dataclass(frozen=True)
class OrderRules:
    default: str
    """`sequential`: phases and steps follow their `order`."""
    optional_phases: tuple[str, ...]
    movable_phases: tuple[MovablePhase, ...]
    edited_videos: str


@dataclass(frozen=True)
class GraspLabel:
    """One GraSP phase or step and the rule-book phases/steps it maps to (A1 crosswalk)."""

    grasp_id: int
    code: str | None
    name: str
    maps_to: tuple[str, ...] | Literal["phase"]
    """Rule-book ids, or `phase`: "whatever its GraSP phase maps to"."""
    by_phase: Mapping[int, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class GraspCrosswalk:
    verified: bool
    phases: tuple[GraspLabel, ...]
    steps: tuple[GraspLabel, ...]


@dataclass(frozen=True)
class RuleBook:
    id: str
    version: str
    name: Text
    review_status: str
    phases: tuple[Phase, ...]
    """In rule-book order."""
    order_rules: OrderRules
    grasp: GraspCrosswalk | None

    def steps(self) -> tuple[Step, ...]:
        """Every step, in rule-book order."""
        return tuple(step for phase in self.phases for step in phase.steps)

    def step(self, step_id: str) -> Step:
        for step in self.steps():
            if step.id == step_id:
                return step
        raise KeyError(step_id)

    def phase(self, phase_id: str) -> Phase:
        for phase in self.phases:
            if phase.id == phase_id:
                return phase
        raise KeyError(phase_id)


@dataclass(frozen=True)
class ObstacleLeaf:
    id: str
    family: str
    name: Text
    typical_cause: str
    steps: tuple[str, ...]
    terms: tuple[str, ...]


@dataclass(frozen=True)
class ObstacleFamily:
    id: str
    name: Text
    leaves: tuple[ObstacleLeaf, ...]


@dataclass(frozen=True)
class Term:
    id: str
    kind: str
    ja: str
    en: str
    synonyms_ja: tuple[str, ...]
    synonyms_en: tuple[str, ...]


@dataclass(frozen=True)
class Knowledge:
    """Everything in `knowledge/`, loaded and checked."""

    rulebook: RuleBook
    families: tuple[ObstacleFamily, ...]
    terms: Mapping[str, Term]

    def leaves(self) -> dict[str, ObstacleLeaf]:
        return {leaf.id: leaf for family in self.families for leaf in family.leaves}


class _Reader:
    """Builds the dataclasses from YAML and collects problems instead of stopping at the first."""

    def __init__(self) -> None:
        self.problems: list[str] = []

    def problem(self, file: Path, where: str, message: str) -> None:
        self.problems.append(f"{file.as_posix()}: {where}: {message}")

    def load(self, root: Path, relative: Path) -> dict[str, Any]:
        path = root / relative
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except OSError as exc:
            self.problem(relative, "(file)", f"can't read: {exc}")
            return {}
        except UnicodeDecodeError:
            self.problem(relative, "(file)", "not UTF-8 text")
            return {}
        except yaml.YAMLError as exc:
            self.problem(relative, "(file)", f"not valid YAML: {exc}")
            return {}
        if not isinstance(data, dict):
            self.problem(relative, "(file)", "the top level is not a mapping")
            return {}
        return data

    def text(self, file: Path, where: str, value: Any, *, required: bool = True) -> Text | None:
        if value is None and not required:
            return None
        if not isinstance(value, dict):
            self.problem(file, where, "needs a {ja, en} text")
            return Text("", "")
        halves = {lang: value.get(lang) for lang in ("ja", "en")}
        for lang, half in halves.items():
            if not isinstance(half, str) or not half.strip():
                self.problem(file, where, f"missing or empty `{lang}`")
        return Text(str(halves["ja"] or ""), str(halves["en"] or ""))

    def duration(self, file: Path, where: str, value: Any) -> Duration:
        try:
            p25, p50, p75 = (float(value[k]) for k in ("p25", "p50", "p75"))
        except (TypeError, KeyError, ValueError):
            self.problem(file, where, "typical_duration_s needs numbers p25, p50 and p75")
            return Duration(1.0, 1.0, 1.0)
        if not 0 < p25 <= p50 <= p75:
            self.problem(file, where, f"typical_duration_s needs 0 < p25 ≤ p50 ≤ p75, not {value}")
        return Duration(p25, p50, p75)

    def ids(self, file: Path, what: str, ids: Iterable[str]) -> None:
        for item_id, count in Counter(ids).items():
            if count > 1:
                self.problem(file, item_id, f"duplicate {what} id ({count} times)")

    def refs(self, file: Path, where: str, ids: Iterable[str], known: set[str], what: str) -> None:
        for item_id in ids:
            if item_id not in known:
                self.problem(file, where, f"unknown {what} `{item_id}`")


def _strings(value: Any) -> tuple[str, ...]:
    return tuple(str(v) for v in value) if isinstance(value, list) else ()


def _vocab(r: _Reader, data: dict[str, Any]) -> dict[str, Term]:
    terms: dict[str, Term] = {}
    raw = data.get("terms") or []
    r.ids(VOCAB_FILE, "term", (str(t.get("id")) for t in raw if isinstance(t, dict)))
    for item in raw:
        if not isinstance(item, dict) or not item.get("id"):
            r.problem(VOCAB_FILE, "terms", f"a term without an id: {item!r}")
            continue
        term_id = str(item["id"])
        r.text(VOCAB_FILE, term_id, {"ja": item.get("ja"), "en": item.get("en")})
        synonyms = item.get("synonyms") or {}
        terms[term_id] = Term(
            id=term_id,
            kind=str(item.get("kind", "")),
            ja=str(item.get("ja") or ""),
            en=str(item.get("en") or ""),
            synonyms_ja=_strings(synonyms.get("ja")),
            synonyms_en=_strings(synonyms.get("en")),
        )
    return terms


def _taxonomy(r: _Reader, data: dict[str, Any]) -> tuple[ObstacleFamily, ...]:
    causes = set((data.get("causes") or {}).keys())
    families = []
    raw = [f for f in data.get("families") or [] if isinstance(f, dict)]
    r.ids(TAXONOMY_FILE, "family", (str(f.get("id")) for f in raw))
    r.ids(
        TAXONOMY_FILE,
        "leaf",
        (str(leaf.get("id")) for f in raw for leaf in f.get("leaves") or []),
    )
    for item in raw:
        family_id = str(item.get("id"))
        name = r.text(TAXONOMY_FILE, family_id, item.get("name"))
        leaves = []
        for leaf in item.get("leaves") or []:
            leaf_id = str(leaf.get("id"))
            if not leaf_id.startswith(f"{family_id}."):
                r.problem(TAXONOMY_FILE, leaf_id, f"a leaf of `{family_id}` must start with it")
            cause = str(leaf.get("typical_cause"))
            if cause not in causes:
                r.problem(TAXONOMY_FILE, leaf_id, f"unknown typical_cause `{cause}`")
            leaf_name = r.text(TAXONOMY_FILE, leaf_id, leaf.get("name"))
            leaves.append(
                ObstacleLeaf(
                    id=leaf_id,
                    family=family_id,
                    name=leaf_name or Text("", ""),
                    typical_cause=cause,
                    steps=_strings(leaf.get("steps")),
                    terms=_strings(leaf.get("terms")),
                )
            )
        families.append(ObstacleFamily(family_id, name or Text("", ""), tuple(leaves)))
    return tuple(families)


def _grasp_labels(r: _Reader, raw: Any, where: str) -> tuple[GraspLabel, ...]:
    labels = []
    for item in raw or []:
        maps_to = item.get("maps_to")
        by_phase = {int(k): _strings(v) for k, v in (item.get("by_phase") or {}).items()}
        labels.append(
            GraspLabel(
                grasp_id=int(item.get("grasp_id")),
                code=item.get("code"),
                name=str(item.get("name")),
                maps_to="phase" if maps_to == "phase" else _strings(maps_to),
                by_phase=by_phase,
            )
        )
    r.ids(RULEBOOK_FILE, f"grasp {where}", (str(label.grasp_id) for label in labels))
    return tuple(labels)


def _rulebook(r: _Reader, data: dict[str, Any]) -> RuleBook:
    raw_phases = sorted(
        (p for p in data.get("phases") or [] if isinstance(p, dict)),
        key=lambda p: p.get("order", 0),
    )
    raw_steps = [s for p in raw_phases for s in p.get("steps") or []]
    r.ids(RULEBOOK_FILE, "phase", (str(p.get("id")) for p in raw_phases))
    r.ids(RULEBOOK_FILE, "step", (str(s.get("id")) for s in raw_steps))
    r.ids(
        RULEBOOK_FILE,
        "checkpoint",
        (str(c.get("id")) for s in raw_steps for c in s.get("checkpoints") or []),
    )
    phases = []
    for p in raw_phases:
        phase_id = str(p.get("id"))
        steps = []
        for s in sorted(p.get("steps") or [], key=lambda s: s.get("order", 0)):
            step_id = str(s.get("id"))
            if not step_id.startswith(f"{phase_id}."):
                r.problem(RULEBOOK_FILE, step_id, f"a step of `{phase_id}` must start with it")
            checkpoints = tuple(
                Checkpoint(
                    str(c.get("id")),
                    r.text(RULEBOOK_FILE, str(c.get("id")), c.get("text")) or Text("", ""),
                )
                for c in s.get("checkpoints") or []
            )
            steps.append(
                Step(
                    id=step_id,
                    phase_id=phase_id,
                    order=int(s.get("order", 0)),
                    name=r.text(RULEBOOK_FILE, step_id, s.get("name")) or Text("", ""),
                    description=r.text(
                        RULEBOOK_FILE,
                        f"{step_id}.description",
                        s.get("description"),
                        required=False,
                    ),  # fmt: skip
                    visual_cues=r.text(
                        RULEBOOK_FILE,
                        f"{step_id}.visual_cues",
                        s.get("visual_cues"),
                        required=False,
                    ),  # fmt: skip
                    duration=r.duration(RULEBOOK_FILE, step_id, s.get("typical_duration_s")),
                    anatomy=_strings(s.get("anatomy")),
                    instruments=_strings(s.get("instruments")),
                    checkpoints=checkpoints,
                    known_obstacles=_strings(s.get("known_obstacles")),
                )
            )
        phases.append(
            Phase(
                id=phase_id,
                order=int(p.get("order", 0)),
                name=r.text(RULEBOOK_FILE, phase_id, p.get("name")) or Text("", ""),
                optional=bool(p.get("optional", False)),
                duration=r.duration(RULEBOOK_FILE, phase_id, p.get("typical_duration_s")),
                steps=tuple(steps),
            )
        )
    rules = data.get("order_rules") or {}
    order_rules = OrderRules(
        default=str(rules.get("default", "sequential")),
        optional_phases=_strings(rules.get("optional_phases")),
        movable_phases=tuple(
            MovablePhase(str(m.get("phase")), _strings(m.get("may_follow")))
            for m in rules.get("movable_phases") or []
        ),
        edited_videos=str(rules.get("edited_videos", "")),
    )
    grasp_raw = data.get("grasp")
    grasp = (
        GraspCrosswalk(
            verified=bool(grasp_raw.get("verified", False)),
            phases=_grasp_labels(r, grasp_raw.get("phases"), "phase"),
            steps=_grasp_labels(r, grasp_raw.get("steps"), "step"),
        )
        if isinstance(grasp_raw, dict)
        else None
    )
    return RuleBook(
        id=str(data.get("id")),
        version=str(data.get("version")),
        name=r.text(RULEBOOK_FILE, "name", data.get("name")) or Text("", ""),
        review_status=str(data.get("review_status")),
        phases=tuple(phases),
        order_rules=order_rules,
        grasp=grasp,
    )


def _cross_check(r: _Reader, knowledge: Knowledge) -> None:
    rulebook = knowledge.rulebook
    steps = {step.id for step in rulebook.steps()}
    phases = {phase.id for phase in rulebook.phases}
    leaves = knowledge.leaves()
    terms = set(knowledge.terms)
    for step in rulebook.steps():
        r.refs(RULEBOOK_FILE, step.id, step.anatomy, terms, "term (anatomy)")
        r.refs(RULEBOOK_FILE, step.id, step.instruments, terms, "term (instrument)")
        r.refs(RULEBOOK_FILE, step.id, step.known_obstacles, set(leaves), "obstacle leaf")
    for leaf in leaves.values():
        r.refs(TAXONOMY_FILE, leaf.id, leaf.steps, steps, "step")
        r.refs(TAXONOMY_FILE, leaf.id, leaf.terms, terms, "term")
    rules = rulebook.order_rules
    r.refs(RULEBOOK_FILE, "order_rules.optional_phases", rules.optional_phases, phases, "phase")
    for movable in rules.movable_phases:
        r.refs(RULEBOOK_FILE, "order_rules.movable_phases", [movable.phase], phases, "phase")
        r.refs(RULEBOOK_FILE, movable.phase, movable.may_follow, phases, "phase")
    for phase_id in rules.optional_phases:
        if phase_id in phases and not rulebook.phase(phase_id).optional:
            r.problem(RULEBOOK_FILE, phase_id, "in optional_phases but `optional: false`")
    # The step ↔ obstacle relation is stored twice; both copies must list the same pairs.
    by_step = {(s.id, o) for s in rulebook.steps() for o in s.known_obstacles}
    by_leaf = {(s, leaf.id) for leaf in leaves.values() for s in leaf.steps}
    for step_id, leaf_id in sorted(by_step - by_leaf):
        r.problem(TAXONOMY_FILE, leaf_id, f"its `steps` lack `{step_id}` (rule book lists it)")
    for step_id, leaf_id in sorted(by_leaf - by_step):
        r.problem(RULEBOOK_FILE, step_id, f"`known_obstacles` lacks `{leaf_id}` (taxonomy has it)")
    if rulebook.grasp is not None:
        targets = steps | phases
        for label in (*rulebook.grasp.phases, *rulebook.grasp.steps):
            where = f"grasp {label.grasp_id} ({label.name})"
            if label.maps_to != "phase":
                r.refs(RULEBOOK_FILE, where, label.maps_to, targets, "rule-book id")
            for ids in label.by_phase.values():
                r.refs(RULEBOOK_FILE, where, ids, targets, "rule-book id")


def load_knowledge(root: Path = KNOWLEDGE_DIR) -> Knowledge:
    """Load and check the rule book, the obstacle taxonomy and the vocabulary under `root`.

    Raises `KnowledgeError` listing every problem found (file, id, what's wrong).
    """
    r = _Reader()
    vocab = r.load(root, VOCAB_FILE)
    taxonomy = r.load(root, TAXONOMY_FILE)
    rulebook = r.load(root, RULEBOOK_FILE)
    if r.problems:
        raise KnowledgeError(r.problems)
    knowledge = Knowledge(
        rulebook=_rulebook(r, rulebook),
        families=_taxonomy(r, taxonomy),
        terms=_vocab(r, vocab),
    )
    _cross_check(r, knowledge)
    if r.problems:
        raise KnowledgeError(r.problems)
    return knowledge
