"""A4 Bilingual vocabulary: `knowledge/vocab/terms.yaml` (criterion 10 of the A1-A4 brief).

Expected values: plan §2.1 A4 ("JA/EN terms with synonyms (e.g. DVC = dorsal vein complex =
サントリーニ静脈叢)"), D-049 (instrument keys are snake_case) and knowledge/README.md. Lookups
normalise with NFKC + case folding, so "dvc" and "ＤＶＣ" name the same term.
"""

from __future__ import annotations

DVC_FORMS = ["DVC", "dorsal vein complex", "サントリーニ静脈叢"]  # plan §2.1 A4


def test_c10_vocabulary_loads_and_is_draft(load_yaml, const):
    """C10 "the file carries the review status" (knowledge/README.md) and loads with
    yaml.safe_load."""
    assert const.vocab_path.is_file(), f"missing {const.vocab_path}"
    data = load_yaml(const.vocab_path)
    assert isinstance(data, dict)
    assert data.get("review_status") == const.review_status
    assert isinstance(data.get("terms"), list) and data["terms"]


def test_c10_terms_have_ja_and_en_and_synonym_lists(vocab):
    """C10 "JA/EN terms with synonyms, both halves non-empty" (plan §2.1 A4; plan §4.1 Bilingual
    "both halves non-empty"). Synonyms are per-language lists of non-empty strings, and the
    vocabulary does carry synonyms."""
    problems = []
    synonym_count = 0
    for index, term in enumerate(vocab["terms"]):
        tid = term.get("id", f"terms[{index}]")
        for lang in ("ja", "en"):
            if not (isinstance(term.get(lang), str) and term[lang].strip()):
                problems.append(f"{tid}: {lang} is {term.get(lang)!r}")
        synonyms = term.get("synonyms")
        if not isinstance(synonyms, dict) or not {"ja", "en"} <= set(synonyms):
            problems.append(f"{tid}: synonyms is not {{ja: [...], en: [...]}}: {synonyms!r}")
            continue
        for lang in ("ja", "en"):
            values = synonyms[lang]
            if not isinstance(values, list):
                problems.append(f"{tid}: synonyms.{lang} is not a list")
                continue
            for value in values:
                synonym_count += 1
                if not (isinstance(value, str) and value.strip()):
                    problems.append(f"{tid}: empty synonym in synonyms.{lang}: {value!r}")
    assert not problems, "\n".join(problems)
    assert synonym_count, "no term has a synonym"


def test_c10_dvc_example_resolves_to_one_term(surface_index, helpers):
    """C10 "plan §2 A4's example (DVC = dorsal vein complex = サントリーニ静脈叢) resolves to one
    term"."""
    normalise = helpers["normalise"]
    found = {form: surface_index.get(normalise(form), set()) for form in DVC_FORMS}
    assert all(len(ids) == 1 for ids in found.values()), found
    assert len(set().union(*found.values())) == 1, found


def test_c10_term_ids_are_unique(vocab):
    """C10 "no duplicate term ids" (plan §2.1 A4)."""
    ids = [term.get("id") for term in vocab["terms"]]
    duplicates = sorted({i for i in ids if ids.count(i) > 1}, key=str)
    assert not duplicates, f"duplicate term ids: {duplicates}"
    assert all(isinstance(i, str) and i for i in ids), "a term without an id"


def test_c10_no_surface_form_maps_to_two_terms(surface_index):
    """C10 "no synonym that maps to two different terms" (plan §2.1 A4). Every JA/EN form and
    every synonym, normalised, names exactly one term."""
    ambiguous = {form: sorted(ids) for form, ids in surface_index.items() if len(ids) > 1}
    assert not ambiguous, f"forms that name more than one term: {ambiguous}"


def test_c10_instrument_keys_are_snake_case(vocab, const):
    """C10 "instrument keys are snake_case (D-049)" (plan §4.2 `instruments[]`: `key` (snake_case,
    e.g. needle_driver)). The vocabulary's instrument terms carry the keys as their ids."""
    instruments = [term for term in vocab["terms"] if term.get("kind") == "instrument"]
    assert instruments, "no instrument terms"
    bad = [
        term.get(field)
        for term in instruments
        for field in ("id", "key")
        if field in term and not const.snake_case_re.match(str(term.get(field)))
    ]
    assert not bad, f"instrument keys not in snake_case: {bad}"


def test_c10_term_kinds_are_declared(vocab, helpers):
    """C10 (plan §2.1 A4): when the file declares its term kinds, every term uses one of them and
    each kind's label is bilingual."""
    kinds = vocab.get("kinds")
    if kinds is None:
        return
    undeclared = sorted({t.get("kind") for t in vocab["terms"]} - set(kinds), key=str)
    assert not undeclared, f"terms use undeclared kinds: {undeclared}"
    unlabelled = [k for k, label in kinds.items() if not helpers["is_bilingual"](label)]
    assert not unlabelled, f"kinds without a non-empty {{ja, en}} label: {unlabelled}"
