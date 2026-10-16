"""Shared fixtures for Tester 1's acceptance tests of A1-A4 (`knowledge/`).

Test files can't import each other under `--import-mode=importlib`, so the helpers live here and
reach the tests as fixtures. Everything is read from the working tree; nothing imports the
contracts package (D-051) and nothing is written outside `tmp_path`.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
KNOWLEDGE = REPO_ROOT / "knowledge"
RULEBOOK_PATH = KNOWLEDGE / "rulebooks" / "rarp.yaml"
ONTOLOGY_PATH = KNOWLEDGE / "ontology" / "core.yaml"
TAXONOMY_PATH = KNOWLEDGE / "taxonomy" / "obstacles.yaml"
VOCAB_PATH = KNOWLEDGE / "vocab" / "terms.yaml"
REFERENCE_FIXTURE_PATH = REPO_ROOT / "contracts" / "fixtures" / "reference" / "rarp.json"

REVIEW_STATUS = "draft_pending_urologist_review"  # knowledge/README.md

# ID patterns copied from the contract (plan §4.1, §4.2b; D-035), not imported (D-051).
SLUG = r"[a-z0-9]+(?:_[a-z0-9]+)*"
FAMILIES = (
    "bleeding",
    "anatomical_variation",
    "tissue_condition",
    "visibility",
    "technical_difficulty",
    "equipment",
    "patient_condition",
    "unexpected_finding",
)
PHASE_ID_RE = re.compile(r"^rarp\.p[0-9]{2,}$")
STEP_ID_RE = re.compile(r"^rarp\.p[0-9]{2,}\.s[0-9]{2,}$")
CHECKPOINT_ID_RE = re.compile(r"^rarp\.p[0-9]{2,}\.s[0-9]{2,}\.c[1-9][0-9]*$")
LEAF_ID_RE = re.compile(rf"^(?:{'|'.join(FAMILIES)})\.{SLUG}$")
SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


class _UniqueKeyLoader(yaml.SafeLoader):
    """A SafeLoader that refuses duplicate mapping keys (safe_load keeps the last one silently)."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode) -> dict:
    seen: set[Any] = set()
    for key_node, _value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in seen:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key {key!r}",
                key_node.start_mark,
            )
        seen.add(key)
    return loader.construct_mapping(node, deep=True)


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _safe_load(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def walk(node: Any, path: str = "$") -> Iterator[tuple[str, Any]]:
    """Every (path, value) in a parsed YAML/JSON tree, containers included."""
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}[{index}]")


def strings(node: Any) -> Iterator[tuple[str, str]]:
    """Every string in a tree, mapping keys included, with its path."""
    for path, value in walk(node):
        if isinstance(value, str):
            yield path, value
        elif isinstance(value, dict):
            for key in value:
                if isinstance(key, str):
                    yield f"{path}.<key>", key


def bilingual_problems(node: Any) -> list[str]:
    """Paths of `{ja, en}` pairs where a half is missing, empty or blank (plan §4.1 Bilingual)."""
    problems: list[str] = []
    for path, value in walk(node):
        if not isinstance(value, dict) or not ({"ja", "en"} & set(value)):
            continue
        if not {"ja", "en"} <= set(value):
            problems.append(f"{path}: has only {sorted({'ja', 'en'} & set(value))}")
            continue
        ja, en = value["ja"], value["en"]
        if isinstance(ja, list) and isinstance(en, list):  # synonym lists: each entry non-empty
            for lang, items in (("ja", ja), ("en", en)):
                for index, item in enumerate(items):
                    if not isinstance(item, str) or not item.strip():
                        problems.append(f"{path}.{lang}[{index}]: {item!r}")
            continue
        for lang, text in (("ja", ja), ("en", en)):
            if not isinstance(text, str) or not text.strip():
                problems.append(f"{path}.{lang}: {text!r}")
    return problems


def is_bilingual(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("ja"), str)
        and isinstance(value.get("en"), str)
        and bool(value["ja"].strip())
        and bool(value["en"].strip())
    )


def normalise(text: str) -> str:
    """Surface form used to look a term up: NFKC, case-folded, whitespace collapsed."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def leaf_text(leaf_id: str, leaf: dict) -> str:
    """A leaf's slug and EN name as space-separated lower-case words, padded with spaces."""
    slug = leaf_id.split(".", 1)[-1]
    name = (leaf.get("name") or {}).get("en", "") if isinstance(leaf.get("name"), dict) else ""
    return " " + " ".join(re.sub(r"[^0-9a-z]+", " ", f"{slug} {name}".casefold()).split()) + " "


def has_word(text: str, keyword: str) -> bool:
    """`keyword` starts a word of `text` (a leaf_text); a trailing space also makes it end one.
    So "vascular" does not match "neurovascular", and "sv " matches only the word "sv"."""
    return " " + keyword.lstrip() in text


# ── Appendix A "Known obstacles" (plan Appendix A) ───────────────────────────


def _either(*clauses):
    """A leaf predicate that holds when any clause (a list of keyword groups) holds: every group
    of the clause has a keyword starting a word of the leaf's slug + EN name."""

    def predicate(family: str, text: str) -> bool:
        return any(
            all(any(has_word(text, k) for k in group) for group in clause) for clause in clauses
        )

    return predicate


def _in_family(required: str, *clauses):
    inner = _either(*clauses)
    return lambda family, text: family == required and inner(family, text)


# (Appendix A row #, obstacle as written there, predicate on (family id, leaf_text)).
# Bleeding obstacles sit under Bleeding; the median lobe under Anatomical variation (plan §4.2b
# example `anatomical_variation.median_lobe`). Row 8's "Adherent plane / rectal injury risk" is one
# item, so a leaf for either half covers it.
APPENDIX_A_OBSTACLES = [
    (1, "Adhesions from prior surgery",
     _either([["adhesion"], ["prior", "previous", "surgery", "surgical"]])),
    (1, "Obesity", _either([["obes"]])),
    (2, "Vessel bleeding", _in_family("bleeding", [["vessel", "iliac", "vascular", "obturator"]])),
    (2, "Nerve proximity", _either([["nerve"], ["proxim", "close", "near"]])),
    (3, "Hernia-mesh adhesions", _either([["mesh"]])),
    (3, "Obesity", _either([["obes"]])),
    (4, "DVC (Santorini) bleeding", _in_family("bleeding", [["dvc", "santorini", "dorsal vein"]])),
    (5, "Median lobe", _in_family("anatomical_variation", [["median lobe", "middle lobe"]])),
    (5, "Large prostate", _either([["large prostate", "enlarged prostate", "prostatomegaly"]])),
    (5, "Prior TURP", _either([["turp", "transurethral resection"]])),
    (6, "Median lobe", _in_family("anatomical_variation", [["median lobe", "middle lobe"]])),
    (6, "Wide bladder neck", _either([["wide"], ["bladder neck"]])),
    (7, "Inflammation", _either([["inflam"]])),
    (7, "Bleeding from SV artery", _in_family("bleeding", [["sv ", "seminal"], ["arter"]])),
    (8, "Adherent plane / rectal injury risk",
     _either([["rectal", "rectum"]], [["adher"], ["plane"]])),
    (9, "Pedicle/NVB bleeding", _in_family("bleeding", [["pedicle", "nvb", "neurovascular"]])),
    (9, "Accessory pudendal artery", _either([["pudendal"]])),
    (10, "Difficult apex", _either([["apex", "apical"]])),
    (10, "Positive-margin risk", _either([["margin"]])),
    (11, "Tissue tension", _either([["tension"]])),
    (12, "Anastomotic tension", _either([["anastomo"], ["tension"]])),
    (12, "Leak", _either([["leak"]])),
    (13, "Port-site bleeding", _in_family("bleeding", [["port"]])),
]  # fmt: skip


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize any test that asks for `appendix_a_obstacle` with the table above."""
    if "appendix_a_obstacle" in metafunc.fixturenames:
        metafunc.parametrize(
            "appendix_a_obstacle",
            APPENDIX_A_OBSTACLES,
            ids=[f"p{n:02d}-{label}" for n, label, _ in APPENDIX_A_OBSTACLES],
        )


# ── Loaded files ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def load_yaml() -> Callable[[Path], Any]:
    return _safe_load


@pytest.fixture(scope="session")
def load_yaml_unique_keys() -> Callable[[Path], Any]:
    def load(path: Path) -> Any:
        with path.open(encoding="utf-8") as handle:
            return yaml.load(handle, Loader=_UniqueKeyLoader)  # noqa: S506 (SafeLoader subclass)

    return load


@pytest.fixture(scope="session")
def rulebook() -> dict:
    return _safe_load(RULEBOOK_PATH)


@pytest.fixture(scope="session")
def ontology() -> dict:
    return _safe_load(ONTOLOGY_PATH)


@pytest.fixture(scope="session")
def taxonomy() -> dict:
    return _safe_load(TAXONOMY_PATH)


@pytest.fixture(scope="session")
def vocab() -> dict:
    return _safe_load(VOCAB_PATH)


# ── Derived views ────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def phases(rulebook: dict) -> list[dict]:
    return list(rulebook["phases"])


@pytest.fixture(scope="session")
def steps(phases: list[dict]) -> list[tuple[dict, dict]]:
    """Every (phase, step) pair, in order."""
    return [(phase, step) for phase in phases for step in phase.get("steps") or []]


@pytest.fixture(scope="session")
def defined_procedure_ids(phases: list[dict]) -> set[str]:
    """Phase, step and checkpoint ids defined in the rule book."""
    ids: set[str] = set()
    for phase in phases:
        ids.add(phase["id"])
        for step in phase.get("steps") or []:
            ids.add(step["id"])
            for checkpoint in step.get("checkpoints") or []:
                ids.add(checkpoint["id"])
    return ids


@pytest.fixture(scope="session")
def leaves(taxonomy: dict) -> dict[str, tuple[str, dict]]:
    """Leaf id -> (family id, leaf)."""
    found: dict[str, tuple[str, dict]] = {}
    for family in taxonomy["families"]:
        for leaf in family.get("leaves") or []:
            found[leaf["id"]] = (family["id"], leaf)
    return found


@pytest.fixture(scope="session")
def terms_by_id(vocab: dict) -> dict[str, dict]:
    return {term["id"]: term for term in vocab["terms"]}


@pytest.fixture(scope="session")
def surface_index(vocab: dict) -> dict[str, set[str]]:
    """Normalised surface form (ja, en and every synonym) -> the term ids it names."""
    index: dict[str, set[str]] = {}
    for term in vocab["terms"]:
        forms = [term.get("ja"), term.get("en")]
        synonyms = term.get("synonyms") or {}
        for lang in ("ja", "en"):
            forms.extend(synonyms.get(lang) or [])
        for form in forms:
            if isinstance(form, str) and form.strip():
                index.setdefault(normalise(form), set()).add(term["id"])
    return index


@pytest.fixture(scope="session")
def const() -> SimpleNamespace:
    """Paths, ID patterns and fixed values, for tests that can't import this module."""
    return SimpleNamespace(
        repo_root=REPO_ROOT,
        knowledge=KNOWLEDGE,
        rulebook_path=RULEBOOK_PATH,
        ontology_path=ONTOLOGY_PATH,
        taxonomy_path=TAXONOMY_PATH,
        vocab_path=VOCAB_PATH,
        reference_fixture_path=REFERENCE_FIXTURE_PATH,
        review_status=REVIEW_STATUS,
        families=FAMILIES,
        phase_id_re=PHASE_ID_RE,
        step_id_re=STEP_ID_RE,
        checkpoint_id_re=CHECKPOINT_ID_RE,
        leaf_id_re=LEAF_ID_RE,
        snake_case_re=SNAKE_CASE_RE,
    )


@pytest.fixture(scope="session")
def helpers() -> dict[str, Callable]:
    return {
        "walk": walk,
        "strings": strings,
        "bilingual_problems": bilingual_problems,
        "is_bilingual": is_bilingual,
        "normalise": normalise,
        "leaf_text": leaf_text,
    }
