"""A1-A4 cross-file references (criterion 11 of the A1-A4 brief), and checks over all four files.

Expected: "every step id, phase id and obstacle leaf referenced anywhere in knowledge/ resolves
within knowledge/ (rule book <-> taxonomy <-> vocabulary <-> ontology)". References are found by
shape (the ID formats of plan §4.1 / §4.2b), not by key name, so a reference in any field counts.
"""

from __future__ import annotations

import re

import pytest

FILES = ["rulebook_path", "ontology_path", "taxonomy_path", "vocab_path"]
PROCEDURE_TOKEN = re.compile(r"\brarp\.p[0-9A-Za-z_.]*[0-9A-Za-z_]")


def _knowledge_yaml(const) -> list:
    return sorted(const.knowledge.rglob("*.yaml"))


def test_c11_the_four_knowledge_files_exist(const):
    """C11 precondition: the four A1-A4 files are where knowledge/README.md says they are."""
    missing = [name for name in FILES if not getattr(const, name).is_file()]
    assert not missing, missing
    assert set(_knowledge_yaml(const)) >= {getattr(const, name) for name in FILES}


@pytest.mark.parametrize("name", FILES)
def test_c11_files_load_without_duplicate_keys(name, const, load_yaml_unique_keys):
    """C1/C7/C9/C10 "loads with yaml.safe_load": a duplicate mapping key (which safe_load would
    silently drop) is not a clean load (YAML 1.2: mapping keys are unique)."""
    load_yaml_unique_keys(getattr(const, name))


@pytest.mark.parametrize("name", FILES)
def test_c11_every_bilingual_pair_has_both_halves(name, const, load_yaml, helpers):
    """Plan §4.1 "Bilingual = {ja, en}, both halves non-empty. Every human-readable field uses
    it" (also C2, C4, C9, C10 "bilingual"): every {ja, en} pair in each file."""
    problems = helpers["bilingual_problems"](load_yaml(getattr(const, name)))
    assert not problems, "\n".join(problems)


def test_c11_every_procedure_id_referenced_in_knowledge_resolves(
    const, load_yaml, helpers, defined_procedure_ids
):
    """C11 "every step id, phase id … referenced anywhere in knowledge/ resolves within
    knowledge/". Any `rarp.p…` token in any YAML string (keys and free text included) must be a
    phase, step or checkpoint defined in the rule book."""
    unresolved = []
    for path in _knowledge_yaml(const):
        for where, text in helpers["strings"](load_yaml(path)):
            for token in PROCEDURE_TOKEN.findall(text):
                if token not in defined_procedure_ids:
                    unresolved.append(f"{path.relative_to(const.knowledge)} {where}: {token}")
    assert not unresolved, "\n".join(unresolved)


def test_c11_every_obstacle_leaf_referenced_in_knowledge_resolves(
    const, load_yaml, helpers, leaves
):
    """C11 "every … obstacle leaf referenced anywhere in knowledge/ resolves within knowledge/".
    Any string shaped like a leaf id (`<family>.<slug>`, D-035) must be a taxonomy leaf."""
    unresolved = []
    for path in _knowledge_yaml(const):
        for where, text in helpers["strings"](load_yaml(path)):
            if const.leaf_id_re.match(text) and text not in leaves:
                unresolved.append(f"{path.relative_to(const.knowledge)} {where}: {text}")
    assert not unresolved, "\n".join(unresolved)


def test_c11_taxonomy_steps_are_rule_book_steps(taxonomy, steps):
    """C11 (taxonomy -> rule book): a leaf's step references name existing rule-book steps."""
    step_ids = {step["id"] for _, step in steps}
    unknown = [
        f"{leaf.get('id')}: {value!r}"
        for family in taxonomy["families"]
        for leaf in family.get("leaves") or []
        for value in leaf.get("steps") or []
        if value not in step_ids
    ]
    assert not unknown, "\n".join(unknown)


def test_c11_vocabulary_references_resolve(rulebook, taxonomy, terms_by_id, steps):
    """C11 (rule book / taxonomy -> vocabulary): the rule book's `anatomy` and `instruments` and the
    taxonomy's `terms` are vocabulary ids (the files' own reference convention), so each must be a
    term of vocab/terms.yaml."""
    unknown = []
    for _, step in steps:
        for field in ("anatomy", "instruments"):
            unknown += [
                f"rarp.yaml {step['id']}.{field}: {v!r}"
                for v in step.get(field) or []
                if v not in terms_by_id
            ]
    for family in taxonomy["families"]:
        for leaf in family.get("leaves") or []:
            unknown += [
                f"obstacles.yaml {leaf.get('id')}.terms: {v!r}"
                for v in leaf.get("terms") or []
                if v not in terms_by_id
            ]
    assert not unknown, "\n".join(unknown)


def test_c11_rule_book_procedure_id_matches_its_ids(rulebook, defined_procedure_ids):
    """C11 / plan §4.2b: the procedure is `rarp` and every phase, step and checkpoint id is
    inside it (`rarp.` prefix), so the export's step-id prefix lookup (D-049) finds this file."""
    assert rulebook.get("id") == "rarp"
    outside = sorted(i for i in defined_procedure_ids if not i.startswith("rarp."))
    assert not outside, outside


def test_c11a_step_obstacle_links_are_mirrored(steps, taxonomy):
    """C11a "the step<->obstacle relation is stored twice (the rule book's known_obstacles per step
    and the taxonomy's steps per leaf). Both copies must list the same pairs" (re-test brief,
    9200317; T1's suggested test)."""
    from_rule_book = {
        (step["id"], leaf_id) for _, step in steps for leaf_id in step.get("known_obstacles") or []
    }
    from_taxonomy = {
        (step_id, leaf.get("id"))
        for family in taxonomy["families"]
        for leaf in family.get("leaves") or []
        for step_id in leaf.get("steps") or []
    }
    assert from_rule_book, "the rule book links no obstacle at all"
    only_rule_book = sorted(from_rule_book - from_taxonomy)
    only_taxonomy = sorted(from_taxonomy - from_rule_book)
    assert not (only_rule_book or only_taxonomy), (
        f"only in rarp.yaml known_obstacles: {only_rule_book}\n"
        f"only in obstacles.yaml leaf steps: {only_taxonomy}"
    )
