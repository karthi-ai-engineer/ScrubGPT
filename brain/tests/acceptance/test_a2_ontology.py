"""A2 Core ontology (Layer 0): `knowledge/ontology/core.yaml` (criteria 7-8 of the A1-A4 brief).

Expected values: plan §2.1 A2 (the shared types), D-053 and issue #8 (the verified IRIs). The
PROV-O term list is the W3C PROV-O Recommendation (30 Apr 2013); the NCIT/UBERON list is exactly
the table in #8. NCIT_C54624 is left out on purpose (#8: "its definition was not checked").
"""

from __future__ import annotations

import re
import subprocess

import pytest

PLAN_TYPES = [  # plan §2.1 A2
    "Case", "Step", "Moment", "Obstacle", "Cue", "Action", "Actor", "Reason", "Outcome",
    "Evidence", "Decision Record",
]  # fmt: skip

PROV = "http://www.w3.org/ns/prov#"
PROV_O_TERMS = {  # every class and property of the PROV-O Recommendation
    # starting-point and expanded classes
    "Entity", "Activity", "Agent", "Collection", "EmptyCollection", "Bundle", "Person",
    "SoftwareAgent", "Organization", "Location",
    # qualified classes
    "Influence", "EntityInfluence", "Usage", "Start", "End", "Derivation", "PrimarySource",
    "Quotation", "Revision", "Generation", "Communication", "Invalidation", "ActivityInfluence",
    "AgentInfluence", "Attribution", "Association", "Plan", "Delegation", "InstantaneousEvent",
    "Role",
    # starting-point and expanded properties
    "wasGeneratedBy", "wasDerivedFrom", "wasAttributedTo", "startedAtTime", "used",
    "wasInformedBy", "endedAtTime", "wasAssociatedWith", "actedOnBehalfOf", "alternateOf",
    "specializationOf", "generatedAtTime", "hadPrimarySource", "value", "wasQuotedFrom",
    "wasRevisionOf", "invalidatedAtTime", "wasInvalidatedBy", "hadMember", "wasStartedBy",
    "wasEndedBy", "invalidated", "influenced", "atLocation", "generated",
    # qualified properties
    "wasInfluencedBy", "qualifiedInfluence", "qualifiedGeneration", "qualifiedDerivation",
    "qualifiedPrimarySource", "qualifiedQuotation", "qualifiedRevision", "qualifiedAttribution",
    "qualifiedInvalidation", "qualifiedStart", "qualifiedUsage", "qualifiedCommunication",
    "qualifiedAssociation", "qualifiedEnd", "qualifiedDelegation", "influencer", "entity",
    "hadUsage", "hadGeneration", "activity", "agent", "hadPlan", "hadActivity", "atTime",
    "hadRole",
}  # fmt: skip
OBO = "http://purl.obolibrary.org/obo/"
VERIFIED_OBO = {  # issue #8, "Verifiable fallback" table and instrument examples
    f"{OBO}{local}"
    for local in (
        "NCIT_C15329", "NCIT_C15399", "NCIT_C165183", "NCIT_C18071", "NCIT_C93067",
        "UBERON_0001062", "UBERON_0002367", "NCIT_C164157", "NCIT_C41331",
        "NCIT_C79090", "NCIT_C79082",
    )
}  # fmt: skip
XSD_DATETIME = "http://www.w3.org/2001/XMLSchema#dateTime"  # #8: generatedAtTime's verified range
OWN_NAMESPACE_PREFIX = "urn:scrubgpt:"


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def _expand(value: str, prefixes: dict[str, str]) -> str | None:
    """A CURIE with a declared prefix, or a full IRI, expanded; None for a bare local name."""
    if re.match(r"^(?:https?|urn):", value):
        return value
    prefix, sep, local = value.partition(":")
    if sep and prefix in prefixes:
        return prefixes[prefix] + local
    return None


def _is_allowed_alignment(iri: str) -> bool:
    if iri.startswith(PROV):
        return iri[len(PROV) :] in PROV_O_TERMS
    return iri in VERIFIED_OBO


def _alignment_values(ontology: dict):
    """(where, value) for every aligns_to entry and every examples IRI, entity and relation."""
    for section in ("entity_types", "relation_types"):
        for item in ontology.get(section) or []:
            for value in item.get("aligns_to") or []:
                yield f"{section}.{item.get('id')}.aligns_to", value
            for name, values in (item.get("examples") or {}).items():
                for value in values if isinstance(values, list) else [values]:
                    yield f"{section}.{item.get('id')}.examples.{name}", value


# ── Criterion 7 ──────────────────────────────────────────────────────────────


def test_c7_core_loads_and_is_draft(load_yaml, const):
    """C7 "knowledge/ontology/core.yaml loads … it carries the review status" (knowledge/README.md
    "every file carries review_status: draft_pending_urologist_review")."""
    assert const.ontology_path.is_file(), f"missing {const.ontology_path}"
    data = load_yaml(const.ontology_path)
    assert isinstance(data, dict)
    assert data.get("review_status") == const.review_status
    assert isinstance(data.get("entity_types"), list) and data["entity_types"]


def test_c7_defines_the_shared_types_of_plan_a2(ontology):
    """C7 "defines the shared types of plan §2 A2: Case, Step, Moment, Obstacle, Cue, Action,
    Actor, Reason, Outcome, Evidence and Decision Record"."""
    defined = {_key(str(t.get("id"))) for t in ontology["entity_types"]}
    missing = [name for name in PLAN_TYPES if _key(name) not in defined]
    assert not missing, f"types missing from entity_types: {missing}"


def test_c7_type_and_relation_ids_are_unique_and_types_are_named_bilingually(ontology, helpers):
    """C7 (plan §2.1 A2 "the shared types of things and relations"; plan §4.1 Bilingual): each type
    and relation id is defined once, and each type has a non-empty {ja, en} name."""
    type_ids = [t.get("id") for t in ontology["entity_types"]]
    relation_ids = [r.get("id") for r in ontology.get("relation_types") or []]
    assert len(type_ids) == len(set(type_ids)), "duplicate entity type ids"
    assert len(relation_ids) == len(set(relation_ids)), "duplicate relation type ids"
    unnamed = [
        t.get("id") for t in ontology["entity_types"] if not helpers["is_bilingual"](t.get("name"))
    ]
    assert not unnamed, f"types without a non-empty {{ja, en}} name: {unnamed}"
    problems = helpers["bilingual_problems"](ontology)
    assert not problems, "\n".join(problems)


def test_c7_every_relation_endpoint_is_a_defined_type(ontology):
    """C7 "every relation's endpoints are defined types" (plan §2.1 A2 "types of things and
    relations"). An endpoint must be the id of an entry in entity_types."""
    defined = {t.get("id") for t in ontology["entity_types"]}
    relations = ontology.get("relation_types") or []
    assert relations, "no relation_types"
    undefined = [
        f"{r.get('id')}.{end} = {r.get(end)!r}"
        for r in relations
        for end in ("from", "to")
        if r.get(end) not in defined
    ]
    assert not undefined, "relation endpoints that are not defined types:\n" + "\n".join(undefined)


# ── Criterion 8: alignment (D-053) ───────────────────────────────────────────


def test_c8_every_aligns_to_iri_is_verified_prov_o_or_ncit_uberon(ontology):
    """C8 "every aligns_to IRI is either a PROV-O IRI (http://www.w3.org/ns/prov#…) or one of the
    verified NCIT/UBERON IRIs listed in #8. No other IRI appears (no guessed OntoSPM IRIs)"
    (D-053). The `examples` IRIs are alignments too and are held to the same list."""
    prefixes = ontology.get("prefixes") or {}
    values = list(_alignment_values(ontology))
    assert values, "no aligns_to IRI at all"
    bad = []
    for where, value in values:
        iri = _expand(str(value), prefixes)
        if iri is None:
            bad.append(f"{where}: {value!r} is not an IRI or a CURIE with a declared prefix")
        elif not _is_allowed_alignment(iri):
            bad.append(f"{where}: {value!r} -> {iri} is not verified PROV-O / #8 NCIT-UBERON")
    assert not bad, "\n".join(bad)


def test_c8_no_unverified_iri_appears_in_the_ontology_structure(ontology):
    """C8 "No other IRI appears (no guessed OntoSPM IRIs)" (D-053 "no IRI is guessed"). Checked in
    every structural field: namespace, prefixes, aligns_to, examples and relation endpoints. The
    only extras allowed are the file's own `urn:scrubgpt:` namespace, the namespaces of the allowed
    IRIs, and xsd:dateTime (the range of prov:generatedAtTime verified in #8). Free-text notes and
    descriptions are prose, not alignments, and are not scanned here."""
    prefixes = ontology.get("prefixes") or {}
    allowed_namespaces = {PROV, OBO, "http://www.w3.org/2001/XMLSchema#"}
    bad = []
    namespace = ontology.get("namespace")
    if namespace is not None and not str(namespace).startswith(OWN_NAMESPACE_PREFIX):
        bad.append(f"namespace {namespace!r}")
    for prefix, iri in prefixes.items():
        if not (str(iri).startswith(OWN_NAMESPACE_PREFIX) or iri in allowed_namespaces):
            bad.append(f"prefixes.{prefix}: {iri!r}")
    for relation in ontology.get("relation_types") or []:
        for end in ("from", "to"):
            iri = _expand(str(relation.get(end)), prefixes)
            if iri is not None and not (
                iri.startswith(OWN_NAMESPACE_PREFIX) or iri == XSD_DATETIME
            ):
                bad.append(f"{relation.get('id')}.{end}: {relation.get(end)!r}")
    for where, value in _alignment_values(ontology):
        iri = _expand(str(value), prefixes)
        if iri is not None and not _is_allowed_alignment(iri):
            bad.append(f"{where}: {value!r}")
    assert not bad, "\n".join(bad)


def test_c8_no_ontospm_iri_anywhere_in_the_file(const):
    """C8 "no guessed OntoSPM IRIs" (D-053: OntoSPM IRIs only once read from the downloaded OWL
    file; none could be verified, #8). Scans the raw text, comments included, for an OntoSPM IRI or
    CURIE (an `ontospm: pending` marker key is not an IRI)."""
    text = const.ontology_path.read_text(encoding="utf-8")
    hits = re.findall(r"(?i)https?://\S*ontospm\S*|\bontospm:(?=\S)\S+", text)
    assert not hits, f"OntoSPM IRIs found: {hits}"


def test_c8_each_unaligned_type_carries_a_note(ontology):
    """C8 "each type without an alignment carries a note" (D-053 "each unaligned type carries a
    note"; #8 "leave OntoSPM aligns_to empty with a note")."""
    missing = [
        t.get("id")
        for t in ontology["entity_types"]
        if not t.get("aligns_to") and not str(t.get("note") or "").strip()
    ]
    assert not missing, f"unaligned types without a note: {missing}"


def test_c8_the_ontospm_owl_file_is_not_in_the_repo(const):
    """C8 "the OntoSPM OWL file is not in the repo" (D-053 "Never commit the OntoSPM OWL file").
    Checks the tracked files (git ls-files); without git, the working tree outside the ignored
    folders."""
    root = const.repo_root
    try:
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            check=True,
            timeout=60,
        ).stdout.decode("utf-8", "replace")
        files = [f for f in listed.split("\0") if f]
    except (OSError, subprocess.SubprocessError):
        skip = {".git", ".venv", "node_modules", "data", "__pycache__"}
        files = [
            str(p.relative_to(root)).replace("\\", "/")
            for p in root.rglob("*")
            if p.is_file() and not skip & set(p.relative_to(root).parts)
        ]
    assert files, "found no files to check"
    owl = [
        f
        for f in files
        if f.casefold().endswith((".owl", ".owx", ".ofn", ".omn"))
        or ("ontospm" in f.casefold() and not f.casefold().endswith(".py"))
    ]
    assert not owl, f"OWL / OntoSPM files in the repo: {owl}"


def test_c8_the_owl_file_check_sees_tracked_files(const):
    """Guard for the check above: it must actually see the knowledge files, so an empty or wrong
    file list can't make it pass vacuously."""
    try:
        listed = subprocess.run(
            ["git", "-C", str(const.repo_root), "ls-files", "knowledge"],
            capture_output=True,
            check=True,
            text=True,
            timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git is not available; the walk fallback is used instead")
    assert "knowledge/ontology/core.yaml" in listed.splitlines()
