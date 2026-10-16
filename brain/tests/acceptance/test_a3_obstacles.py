"""A3 Obstacle family tree: `knowledge/taxonomy/obstacles.yaml` (criterion 9 of the A1-A4 brief).

Expected values: D-035 / plan §4.2b (the 8 fixed family ids, leaf ids `<family>.<slug>`), plan
Appendix A ("Universal obstacle families" and the "Known obstacles" column), plan §2.1 A3 (the
cause attribution) and knowledge/README.md (review status).
"""

from __future__ import annotations

# Appendix A "Universal obstacle families", in order, against the D-035 ids.
FAMILY_NAMES_EN = {
    "bleeding": "Bleeding",
    "anatomical_variation": "Anatomical variation",
    "tissue_condition": "Tissue condition",
    "visibility": "Visibility",
    "technical_difficulty": "Technical difficulty",
    "equipment": "Equipment",
    "patient_condition": "Patient condition",
    "unexpected_finding": "Unexpected finding",
}
CAUSES = {"patient", "event", "technical", "equipment", "unknown"}  # plan §2.1 A3


def test_c9_taxonomy_loads_and_is_draft(load_yaml, const):
    """C9 "the file carries the review status" (knowledge/README.md) and loads with
    yaml.safe_load."""
    assert const.taxonomy_path.is_file(), f"missing {const.taxonomy_path}"
    data = load_yaml(const.taxonomy_path)
    assert isinstance(data, dict)
    assert data.get("review_status") == const.review_status
    assert isinstance(data.get("families"), list)


def test_c9_exactly_the_eight_fixed_families_in_order(taxonomy, const):
    """C9 "exactly the 8 fixed families of D-035 / Appendix A, in that order" (D-035 "Family IDs
    are fixed"; plan §4.2b "lists each family exactly once")."""
    ids = [family.get("id") for family in taxonomy["families"]]
    assert ids == list(const.families)


def test_c9_family_names_are_bilingual_and_match_appendix_a(taxonomy, helpers):
    """C9 "… with bilingual names" (plan §4.2b `{id, name: Bilingual, leaves[]}`); the EN names
    are Appendix A's "Universal obstacle families"."""
    wrong = []
    for family in taxonomy["families"]:
        name = family.get("name")
        if not helpers["is_bilingual"](name):
            wrong.append(f"{family.get('id')}: name is not a non-empty {{ja, en}}: {name!r}")
        elif name["en"].casefold() != FAMILY_NAMES_EN.get(family.get("id"), "").casefold():
            wrong.append(f"{family['id']}: EN {name['en']!r}, Appendix A says "
                         f"{FAMILY_NAMES_EN.get(family['id'])!r}")  # fmt: skip
    assert not wrong, "\n".join(wrong)


def test_c9_leaves_are_family_slug_ids_under_their_own_family(taxonomy, const, helpers):
    """C9 "leaves are <family>.<slug> and sit under their own family" (plan §4.1, §4.2b; D-035),
    each leaf id once, each with a bilingual name (§4.2b "each with name: Bilingual")."""
    problems, ids = [], []
    for family in taxonomy["families"]:
        leaves = family.get("leaves")
        if not isinstance(leaves, list):
            problems.append(f"{family.get('id')}: `leaves` is not a list")
            continue
        for leaf in leaves:
            leaf_id = leaf.get("id")
            ids.append(leaf_id)
            if not (isinstance(leaf_id, str) and const.leaf_id_re.match(leaf_id)):
                problems.append(f"{leaf_id!r}: not <family>.<slug>")
            elif leaf_id.split(".", 1)[0] != family.get("id"):
                problems.append(f"{leaf_id}: listed under {family.get('id')}")
            if not helpers["is_bilingual"](leaf.get("name")):
                problems.append(f"{leaf_id}: name is not a non-empty {{ja, en}}")
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    assert not problems, "\n".join(problems)
    assert not duplicates, f"duplicate leaf ids: {duplicates}"
    assert ids, "the taxonomy has no leaves"


def test_c9_cause_attribution_uses_only_the_five_causes(taxonomy):
    """C9 "cause attribution uses only patient / event / technical / equipment / unknown" (plan
    §2.1 A3 "Also records what caused each obstacle (patient, event, technical, equipment,
    unknown)"). Every leaf records a cause, and any declared cause list is exactly these five."""
    problems = []
    declared = taxonomy.get("causes")
    if declared is not None and set(declared) != CAUSES:
        problems.append(f"`causes` declares {sorted(declared)}, expected {sorted(CAUSES)}")
    for family in taxonomy["families"]:
        for leaf in family.get("leaves") or []:
            cause_keys = [k for k in leaf if "cause" in str(k)]
            if not cause_keys:
                problems.append(f"{leaf.get('id')}: no cause attribution")
            for key in cause_keys:
                values = leaf[key] if isinstance(leaf[key], list) else [leaf[key]]
                bad = [v for v in values if v not in CAUSES]
                if bad or not values:
                    problems.append(f"{leaf.get('id')}.{key}: {leaf[key]!r}")
    assert not problems, "\n".join(problems)


def test_c9_appendix_a_obstacles_are_leaves(appendix_a_obstacle, leaves, helpers):
    """C9 "the RARP-specific obstacles named in Appendix A's 'Known obstacles' column are present
    as leaves" (Appendix A: "The RARP-specific obstacles above sit beneath these as leaves").
    Parametrized from Appendix A's column (conftest.py)."""
    number, obstacle, predicate = appendix_a_obstacle
    leaf_text = helpers["leaf_text"]
    hits = [i for i, (family, leaf) in leaves.items() if predicate(family, leaf_text(i, leaf))]
    assert hits, f"no leaf for Appendix A row {number} obstacle {obstacle!r}"
