"""A1 RARP Rule Book: `knowledge/rulebooks/rarp.yaml` (criteria 1-6 of the A1-A4 brief).

Expected values come from the plan (§2.1 A1, §4.1 IDs, §4.2b, Appendix A), knowledge/README.md
and D-034/D-035/D-051, never from the file under test. "Matching Appendix A's meaning" is
checked with keywords taken from Appendix A's wording, so a rephrased name still passes.
"""

from __future__ import annotations

import re

import pytest

# Appendix A, row by row: (#, EN, JA, optional?, EN keyword groups, JA keyword groups).
# A name matches when every group has at least one keyword in it (NFKC, case-folded).
APPENDIX_A_PHASES = [
    (1, "Port placement and docking", "ポート留置・ドッキング", False,
     [["port"], ["dock"]], [["ポート"], ["ドッキング"]]),
    (2, "Pelvic lymph node dissection (optional)", "骨盤リンパ節郭清", True,
     [["lymph"]], [["リンパ節"]]),
    (3, "Retzius space development / bladder drop", "レチウス腔の展開", False,
     [["retzius"]], [["レチウス"]]),
    (4, "Endopelvic fascia and DVC control", "内骨盤筋膜切開・DVC処理", False,
     [["endopelvic"], ["dvc", "dorsal vein"]],
     [["内骨盤筋膜"], ["dvc", "背側静脈", "サントリーニ"]]),
    (5, "Anterior bladder neck dissection", "膀胱頸部前壁の切開", False,
     [["anterior"], ["bladder neck"]], [["膀胱頸部", "膀胱頚部"], ["前"]]),
    (6, "Posterior bladder neck dissection", "膀胱頸部後壁の切開", False,
     [["posterior"], ["bladder neck"]], [["膀胱頸部", "膀胱頚部"], ["後"]]),
    (7, "Seminal vesicle and vas dissection", "精嚢・精管の剥離", False,
     [["seminal vesicle"], ["vas"]], [["精嚢", "精のう"], ["精管"]]),
    (8, "Posterior dissection (Denonvilliers)", "後面剥離（デノンビリエ筋膜）", False,
     [["posterior"], ["denonvilliers"]], [["後面"], ["デノンビリエ"]]),
    (9, "Pedicle control and nerve sparing", "側方茎処理・神経温存", False,
     [["pedicle"], ["nerve"]], [["側方茎"], ["神経温存"]]),
    (10, "Apical dissection and urethral transection", "尖部処理・尿道切断", False,
     [["apical", "apex"], ["urethra"]], [["尖部"], ["尿道"]]),
    (11, "Posterior reconstruction (optional)", "後壁再建（Rocco）", True,
     [["posterior reconstruction", "rocco"]], [["後壁再建", "rocco"]]),
    (12, "Vesicourethral anastomosis", "膀胱尿道吻合", False,
     [["vesicourethral", "vesico-urethral"], ["anastomosis"]], [["吻合"]]),
    (13, "Specimen extraction and closure", "標本摘出・閉創", False,
     [["specimen"], ["clos"]], [["標本"], ["閉創"]]),
]  # fmt: skip

# Appendix A "Checkpoint(s)": (#, checkpoint, EN keyword groups). Rows 1 and 11 are "—".
# Row 8 and row 10 each name two things; both must be covered by the phase's checkpoints.
APPENDIX_A_CHECKPOINTS = [
    (2, "Obturator nerve identified", [["obturator"], ["nerve"]]),
    (3, "Space adequately developed", [["space", "retzius"], ["develop"]]),
    (4, "DVC secured", [["dvc", "dorsal vein"], ["secur", "control", "ligat"]]),
    (5, "Bladder neck identified", [["bladder neck"], ["identif"]]),
    (6, "Ureteral orifices identified", [["ureter"], ["orifice"]]),
    (7, "SVs fully mobilised", [["seminal vesicle", "sv"], ["mobili"]]),
    (8, "Correct plane", [["plane"]]),
    (8, "Rectum safe", [["rectum", "rectal"]]),
    (9, "Nerve-sparing grade decided", [["nerve"], ["spar"], ["grade"]]),
    (10, "Urethral length kept", [["urethra"], ["length"]]),
    (10, "Margin check", [["margin"]]),
    (12, "Leak test watertight", [["leak", "watertight"]]),
    (13, "Haemostasis at low pressure", [["haemostasis", "hemostasis"], ["pressure"]]),
]
DASH_PHASES = (1, 11)  # Appendix A gives "—": no checkpoint required


def _matches(text: str, groups: list[list[str]], normalise) -> bool:
    text = normalise(text)
    return all(any(normalise(keyword) in text for keyword in group) for group in groups)


def _phase(phases: list[dict], number: int) -> dict:
    assert len(phases) >= number, f"the rule book has only {len(phases)} phases"
    return phases[number - 1]


# ── Criterion 1: file ────────────────────────────────────────────────────────


def test_c1_rulebook_loads_with_safe_load_and_is_draft(load_yaml, const):
    """C1 "A1, file: knowledge/rulebooks/rarp.yaml loads with yaml.safe_load and carries
    review_status: draft_pending_urologist_review" (plan §2.1 A1 "one YAML file … Draft until a
    surgeon reviews it"; knowledge/README.md "Review status")."""
    assert const.rulebook_path.is_file(), f"missing {const.rulebook_path}"
    data = load_yaml(const.rulebook_path)
    assert isinstance(data, dict), "the rule book must be a YAML mapping"
    assert data.get("review_status") == const.review_status
    assert isinstance(data.get("phases"), list) and data["phases"], "no phases list"


# ── Criterion 2: phases and steps in order ───────────────────────────────────


def test_c2_thirteen_phases_in_appendix_a_order(phases, helpers):
    """C2 "the 13 phases of Appendix A, in Appendix A's order; each has a bilingual name (JA and
    EN both non-empty) matching Appendix A's meaning" (plan Appendix A; §2.1 A1 "Phases and steps
    in order")."""
    normalise = helpers["normalise"]
    assert len(phases) == 13, [p.get("id") for p in phases]
    wrong = []
    for number, en, ja, _optional, en_groups, ja_groups in APPENDIX_A_PHASES:
        name = _phase(phases, number).get("name")
        if not helpers["is_bilingual"](name):
            wrong.append(f"#{number}: name is not a non-empty {{ja, en}}: {name!r}")
            continue
        if not _matches(name["en"], en_groups, normalise):
            wrong.append(f"#{number}: EN {name['en']!r} does not match Appendix A {en!r}")
        if not _matches(name["ja"], ja_groups, normalise):
            wrong.append(f"#{number}: JA {name['ja']!r} does not match Appendix A {ja!r}")
    assert not wrong, "\n".join(wrong)


def test_c2_phase_ids_follow_the_format_and_appendix_a_numbering(phases, const):
    """C2 "phase ids are rarp.pNN … in the §4.1 ID formats, all unique" (plan §4.1 "phases
    rarp.p01"; D-035). Appendix A numbers the phases 1-13, so phase #n is rarp.p{n:02d} (plan
    §4.2b example rarp.p06.s02.c1 is the Appendix A row 6 checkpoint)."""
    ids = [phase.get("id") for phase in phases]
    bad = [i for i in ids if not (isinstance(i, str) and const.phase_id_re.match(i))]
    assert not bad, f"phase ids not in the rarp.pNN format: {bad}"
    assert len(ids) == len(set(ids)), f"duplicate phase ids: {ids}"
    assert ids == [f"rarp.p{n:02d}" for n in range(1, len(ids) + 1)]


def test_c2_order_fields_follow_the_listed_order(phases):
    """C2 "phases and steps in order" (plan §2.1 A1); §4.2b gives each phase and step an `order`
    (positions from 1, unique within their list)."""
    wrong = []
    for index, phase in enumerate(phases, start=1):
        if phase.get("order") != index:
            wrong.append(f"{phase.get('id')}: order {phase.get('order')!r}, expected {index}")
        for s_index, step in enumerate(phase.get("steps") or [], start=1):
            if step.get("order") != s_index:
                wrong.append(f"{step.get('id')}: order {step.get('order')!r}, expected {s_index}")
    assert not wrong, "\n".join(wrong)


def test_c2_every_phase_has_steps(phases):
    """C2 "phases and steps in order" (plan §2.1 A1): timeline step_ids point to steps (§4.2b), so
    every phase needs at least one step."""
    empty = [phase.get("id") for phase in phases if not phase.get("steps")]
    assert not empty, f"phases without steps: {empty}"


def test_c2_step_ids_follow_the_format_under_their_own_phase(steps, const):
    """C2 "step ids rarp.pNN.sNN, in the §4.1 ID formats, all unique, and each step under its own
    phase" (plan §4.1, §4.2b; D-035)."""
    wrong, ids = [], []
    for phase, step in steps:
        step_id = step.get("id")
        ids.append(step_id)
        if not (isinstance(step_id, str) and const.step_id_re.match(step_id)):
            wrong.append(f"{step_id!r}: not in the rarp.pNN.sNN format")
        elif not step_id.startswith(f"{phase['id']}."):
            wrong.append(f"{step_id}: listed under {phase['id']}")
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    assert not wrong, "\n".join(wrong)
    assert not duplicates, f"duplicate step ids: {duplicates}"


def test_c2_step_names_are_bilingual(steps, helpers):
    """C2 / plan §4.1 "Bilingual = {ja, en}, both halves non-empty. Every human-readable field
    uses it"; §4.2b steps carry `name: Bilingual`."""
    bad = [step.get("id") for _, step in steps if not helpers["is_bilingual"](step.get("name"))]
    assert not bad, f"steps without a non-empty {{ja, en}} name: {bad}"


# ── Criterion 3: per step ────────────────────────────────────────────────────


def _duration_problems(owner: str, value) -> list[str]:
    if not isinstance(value, dict) or not {"p25", "p50", "p75"} <= set(value):
        return [f"{owner}: typical_duration_s is not {{p25, p50, p75}}: {value!r}"]
    numbers = [value[k] for k in ("p25", "p50", "p75")]
    if any(isinstance(n, bool) or not isinstance(n, int | float) for n in numbers):
        return [f"{owner}: non-numeric duration {value!r}"]
    problems = []
    if any(n < 0 for n in numbers):
        problems.append(f"{owner}: negative duration {value!r}")
    if not numbers[0] <= numbers[1] <= numbers[2]:
        problems.append(f"{owner}: expected p25 <= p50 <= p75, got {value!r}")
    return problems


def test_c3_every_step_has_a_typical_duration_range(phases):
    """C3 "per step: a typical duration range (non-negative, min <= max)" (plan §2.1 A1 "typical
    duration ranges"; §4.2b `typical_duration_s {p25, p50, p75}` on phases and steps)."""
    problems = []
    for phase in phases:
        problems += _duration_problems(phase.get("id"), phase.get("typical_duration_s"))
        for step in phase.get("steps") or []:
            problems += _duration_problems(step.get("id"), step.get("typical_duration_s"))
    assert not problems, "\n".join(problems)


def test_c3_anatomy_and_instruments_are_vocabulary_terms_of_their_kind(steps, terms_by_id):
    """C3 "per step: … anatomy and instruments" (plan §2.1 A1 "anatomy and instruments per step").
    The rule book names them by vocabulary id, so each must be an A4 term of the right kind."""
    problems = []
    for _, step in steps:
        for field, kind in (("anatomy", "anatomy"), ("instruments", "instrument")):
            values = step.get(field)
            if not isinstance(values, list):
                problems.append(f"{step.get('id')}: `{field}` is not a list: {values!r}")
                continue
            for value in values:
                term = terms_by_id.get(value)
                if term is None:
                    problems.append(f"{step['id']}.{field}: {value!r} is not a vocabulary term")
                elif term.get("kind") != kind:
                    problems.append(
                        f"{step['id']}.{field}: {value!r} is a {term.get('kind')!r} term"
                    )
    assert not problems, "\n".join(problems)


def test_c3_every_step_and_phase_names_its_anatomy_and_instruments(phases):
    """C3 "per step: … anatomy and instruments" (plan §2.1 A1): every step names at least one
    anatomy or instrument term, and every phase at least one of each across its steps."""
    problems = []
    for phase in phases:
        anatomy = [a for s in phase.get("steps") or [] for a in s.get("anatomy") or []]
        instruments = [i for s in phase.get("steps") or [] for i in s.get("instruments") or []]
        if not anatomy:
            problems.append(f"{phase.get('id')}: no anatomy on any step")
        if not instruments:
            problems.append(f"{phase.get('id')}: no instrument on any step")
        for step in phase.get("steps") or []:
            if not (step.get("anatomy") or step.get("instruments")):
                problems.append(f"{step.get('id')}: neither anatomy nor instruments")
    assert not problems, "\n".join(problems)


def test_c3_known_obstacles_are_existing_a3_leaves(steps, leaves):
    """C3 "per step: … known obstacles … Every known obstacle names an existing A3 leaf" (plan
    §2.1 A1 "known obstacles per step"; leaves are `<family>.<slug>`, §4.2b)."""
    problems = []
    for _, step in steps:
        values = step.get("known_obstacles")
        if not isinstance(values, list):
            problems.append(f"{step.get('id')}: `known_obstacles` is not a list: {values!r}")
            continue
        problems += [
            f"{step['id']}: {v!r} is not a leaf of taxonomy/obstacles.yaml"
            for v in values
            if v not in leaves
        ]
    assert not problems, "\n".join(problems)


def test_c3_appendix_a_known_obstacles_are_linked_on_their_phase(
    appendix_a_obstacle, phases, leaves, helpers
):
    """C3 "known obstacles" per step (plan §2.1 A1 "known obstacles per step"): each obstacle
    Appendix A lists for a phase is a known obstacle of a step of that phase. Parametrized from
    Appendix A's "Known obstacles" column (conftest.py)."""
    number, obstacle, predicate = appendix_a_obstacle
    phase = _phase(phases, number)
    linked = [o for s in phase.get("steps") or [] for o in s.get("known_obstacles") or []]
    leaf_text = helpers["leaf_text"]
    hits = [
        leaf_id
        for leaf_id in linked
        if leaf_id in leaves
        and predicate(leaves[leaf_id][0], leaf_text(leaf_id, leaves[leaf_id][1]))
    ]
    assert hits, (
        f"Appendix A row {number} lists {obstacle!r}, but no step of {phase.get('id')} links a "
        f"leaf for it; its steps link {linked}"
    )


def test_c3_every_bilingual_field_has_both_halves(rulebook, helpers):
    """C3 "per step: … bilingual terms" (plan §2.1 A1) and plan §4.1 "Bilingual … both halves
    non-empty": every {ja, en} in the rule book (names, descriptions, cues, checkpoint texts)."""
    problems = helpers["bilingual_problems"](rulebook)
    assert not problems, "\n".join(problems)


def test_c3_step_terms_resolve_to_bilingual_vocabulary_entries(steps, terms_by_id):
    """C3 "per step: … bilingual terms" (plan §2.1 A1): the step's anatomy and instrument terms are
    A4 entries with a non-empty JA and EN form."""
    problems = []
    for _, step in steps:
        for value in (step.get("anatomy") or []) + (step.get("instruments") or []):
            term = terms_by_id.get(value)
            if term is None:
                continue  # reported by the kind test above
            if not (str(term.get("ja") or "").strip() and str(term.get("en") or "").strip()):
                problems.append(f"{step['id']}: term {value!r} lacks a JA or EN form")
    assert not problems, "\n".join(problems)


# ── Criterion 4: safety checkpoints ──────────────────────────────────────────


@pytest.mark.parametrize(
    ("number", "checkpoint", "groups"),
    APPENDIX_A_CHECKPOINTS,
    ids=[f"p{n:02d}-{c}" for n, c, _ in APPENDIX_A_CHECKPOINTS],
)
def test_c4_appendix_a_checkpoints_are_on_a_step_of_their_phase(
    number, checkpoint, groups, phases, helpers
):
    """C4 "every checkpoint Appendix A lists for a phase is present on a step of that phase, with
    a bilingual text" (plan Appendix A "Checkpoint(s)"; §4.2b "Checkpoints belong to steps")."""
    phase = _phase(phases, number)
    texts = [c.get("text") for s in phase.get("steps") or [] for c in s.get("checkpoints") or []]
    hits = [
        t for t in texts
        if helpers["is_bilingual"](t) and _matches(t["en"], groups, helpers["normalise"])
    ]  # fmt: skip
    assert hits, f"{phase.get('id')}: no checkpoint for {checkpoint!r}; found {texts}"


def test_c4_checkpoint_ids_and_texts(steps, const, helpers):
    """C4 "with a bilingual text and an id rarp.pNN.sNN.cN" (plan §4.2b `checkpoints[] {id
    (rarp.p06.s02.c1), text: Bilingual}`; ids unique)."""
    problems, ids = [], []
    for _, step in steps:
        checkpoints = step.get("checkpoints")
        if not isinstance(checkpoints, list):
            problems.append(f"{step.get('id')}: `checkpoints` is not a list: {checkpoints!r}")
            continue
        for checkpoint in checkpoints:
            cid = checkpoint.get("id")
            ids.append(cid)
            if not (isinstance(cid, str) and const.checkpoint_id_re.match(cid)):
                problems.append(f"{step['id']}: checkpoint id {cid!r} not rarp.pNN.sNN.cN")
            elif not cid.startswith(f"{step['id']}."):
                problems.append(f"{cid}: listed under {step['id']}")
            if not helpers["is_bilingual"](checkpoint.get("text")):
                problems.append(f"{cid}: text is not a non-empty {{ja, en}}")
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    assert not problems, "\n".join(problems)
    assert not duplicates, f"duplicate checkpoint ids: {duplicates}"


def test_c4_dash_phases_require_no_checkpoint(phases):
    """C4 "phases Appendix A gives '—' have none required" (Appendix A rows 1 and 11). Nothing is
    demanded of them; this pins that the required list above leaves them out, and that any
    checkpoint they do carry still sits in that phase."""
    required = {number for number, _, _ in APPENDIX_A_CHECKPOINTS}
    assert not required & set(DASH_PHASES)
    for number in DASH_PHASES:
        phase = _phase(phases, number)
        for step in phase.get("steps") or []:
            for checkpoint in step.get("checkpoints") or []:
                assert str(checkpoint.get("id", "")).startswith(f"{phase['id']}.")


# ── Criterion 5: expected order and optional phases ──────────────────────────


def test_c5_order_rules_reference_only_existing_steps_or_phases(rulebook, phases, steps):
    """C5 "order rules (if present) reference only existing steps or phases" (plan §2.1 A1
    "expected order"; knowledge/README.md)."""
    rules = rulebook.get("order_rules")
    if rules is None:
        pytest.skip("no order_rules in the rule book (the criterion applies only if present)")
    phase_or_step = {p["id"] for p in phases} | {s["id"] for _, s in steps}
    found = [
        (path, token)
        for path, text in _strings(rules)
        for token in re.findall(r"rarp\.[A-Za-z0-9_.]+", text)
    ]
    unknown = [f"{path}: {token}" for path, token in found if token not in phase_or_step]
    assert not unknown, "\n".join(unknown)


def _strings(node, path="order_rules"):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(key, f"{path}.<key>")
            yield from _strings(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _strings(value, f"{path}[{index}]")


def test_c5_optional_phases_are_marked_optional(phases, rulebook):
    """C5 "the optional phases of Appendix A (pelvic lymph node dissection; posterior
    reconstruction) are marked optional" (Appendix A rows 2 and 11 "(optional)"). Appendix A marks
    no other phase optional."""
    expected = {
        _phase(phases, number)["id"]: optional
        for number, _en, _ja, optional, _e, _j in APPENDIX_A_PHASES
    }
    actual = {phase["id"]: phase.get("optional", False) is True for phase in phases}
    assert actual == expected
    rules = rulebook.get("order_rules") or {}
    if "optional_phases" in rules:
        assert set(rules["optional_phases"]) == {i for i, opt in expected.items() if opt}


# ── Criterion 6: GraSP mapping ───────────────────────────────────────────────


def test_c6_grasp_crosswalk_references_existing_ids_and_is_unverified(rulebook, phases, steps):
    """C6 "Appendix A says the phases are 'to be mapped to GraSP's 11 phases / 21 steps in Block
    1'. Where a crosswalk is present, it references only existing phases/steps and is marked
    unverified (it hasn't been checked against GraSP data)."""
    keys = [k for k in rulebook if "grasp" in str(k).casefold()]
    if not keys:
        pytest.skip("no GraSP crosswalk in the rule book (the criterion applies only if present)")
    phase_or_step = {p["id"] for p in phases} | {s["id"] for _, s in steps}
    for key in keys:
        crosswalk = rulebook[key]
        marked = isinstance(crosswalk, dict) and (
            crosswalk.get("verified") is False
            or "unverified" in str(crosswalk.get("status", "")).casefold()
        )
        assert marked, f"`{key}` is not marked unverified (verified: false)"
        tokens = [
            (path, token)
            for path, text in _strings(crosswalk, key)
            for token in re.findall(r"rarp\.[A-Za-z0-9_.]+", text)
        ]
        unknown = [f"{p}: {t}" for p, t in tokens if t not in phase_or_step]
        assert not unknown, "\n".join(unknown)
        for part in ("phases", "steps"):
            ids = [e.get("grasp_id") for e in crosswalk.get(part) or [] if isinstance(e, dict)]
            assert len(ids) == len(set(ids)), f"duplicate GraSP ids in `{key}.{part}`: {ids}"
