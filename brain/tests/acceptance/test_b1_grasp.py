"""B1 GraSP importer, labels: criteria B1-1 to B1-5 of the T1 brief at 5a89091 (plan §2.2 B1,
§4.1 ids and provenance, §4.2 timeline steps; D-049; brain/README.md "B1 GraSP importer, labels";
the A1 crosswalk in knowledge/rulebooks/rarp.yaml).

Expected behaviour, written from the spec before the code was opened:
- Input: a GraSP long-term annotation file. Its `phases_categories` / `steps_categories` are
  `{id, name, description}` where (rarp.yaml crosswalk comment) "Our `name` is the files'
  `description` …, `code` is their `name`"; `images` and `annotations` (one phase + one step per
  keyframe, keyframes 1 s apart). `import_grasp_steps(path, grasp_case, case_id, video_fps=…)`
  returns `(segments, report)`.
- B1-1: contract `StepSegment`s on track `dataset`, confidence 1.0, provenance
  `dataset_annotation` / `dataset` (no model), ids `<case_id>.sNNN`, times `frame_num / fps`; they
  fit a contract `Timeline` of the case.
- B1-2: a given `video_fps` is used; without it the rate is estimated from the 1 s keyframe
  spacing.
- B1-3: Idle gives no segment. A pause inside one step (the same step before and after) is
  bridged; a gap remains only where the step changes. Without idle, one segment ends where the
  next begins.
- B1-4: the crosswalk as documented: `maps_to` (a phase target expands to its steps), `by_phase`
  overrides, `phase` (a generic act uses its GraSP phase's mapping), and among several candidates
  the current step is kept if possible, else the first one not earlier in rule-book order (and the
  first in rule-book order with no current step).
- B1-5: category lists that don't match the crosswalk raise `GraspError`, as does a missing case
  (and an unreadable file). The report gives seconds per rule-book step and idle seconds (and the
  unmapped labels).

All annotation files are synthetic, built in `tmp_path` from the committed crosswalk; no real
GraSP data. GraSP and rule-book ids are taken from the loaded crosswalk by their properties, never
hard-coded. The README doesn't describe `images` / `annotations`; the GraSP layout is used
(`images[].{id, file_name, video_name, frame_num}`, `annotations[].{id, image_id, phases,
steps}`).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from scrubgpt_brain.engines.rulebook import load_knowledge
from scrubgpt_brain.pipeline.grasp import GraspError, import_grasp_steps
from scrubgpt_contracts.models.case_package import StepSegment, Timeline

CASE = "CASE042"
CASE_ID = "grasp-42"
FPS = 30


@pytest.fixture(scope="module")
def book():
    return load_knowledge().rulebook


@pytest.fixture(scope="module")
def raw_crosswalk(rulebook) -> dict:
    return rulebook["grasp"]


class Crosswalk:
    """The A1 crosswalk, read from the loaded rule book, and the rule-book step order."""

    def __init__(self, book) -> None:
        self.order = [s.id for p in book.phases for s in p.steps]
        self.steps_of = {p.id: [s.id for s in p.steps] for p in book.phases}
        self.phases = {label.grasp_id: label for label in book.grasp.phases}
        self.steps = {label.grasp_id: label for label in book.grasp.steps}

    def expand(self, targets) -> list[str]:
        """README "phase targets expand to their steps", in rule-book order."""
        found = []
        for target in targets:
            for step in self.steps_of.get(target, [target]):
                if step not in found:
                    found.append(step)
        return sorted(found, key=self.order.index)

    def phase_targets(self, grasp_phase: int) -> list[str]:
        label = self.phases[grasp_phase]
        return [] if label.maps_to == "phase" else self.expand(label.maps_to)

    def idle_step(self) -> int:
        return next(g for g, lab in self.steps.items() if lab.maps_to == () and not lab.by_phase)

    def idle_phase(self) -> int:
        return next(g for g, lab in self.phases.items() if lab.maps_to == ())

    def a_phase_for(self, step_id: str) -> int:
        """A GraSP phase whose targets include `step_id` (else any non-idle phase)."""
        for g, lab in self.phases.items():
            if lab.maps_to != "phase" and step_id in self.expand(lab.maps_to):
                return g
        return next(g for g, lab in self.phases.items() if lab.maps_to)

    def direct(self) -> list[tuple[int, str]]:
        """(GraSP step, rule-book step) for labels that map to exactly one rule-book step."""
        found = []
        for g, lab in self.steps.items():
            if lab.by_phase or lab.maps_to == "phase" or len(lab.maps_to) != 1:
                continue
            target = lab.maps_to[0]
            if target in self.order:
                found.append((g, target))
        return found

    def label_for(self, step_id: str) -> int:
        """A GraSP step label that maps straight to `step_id`."""
        return next(g for g, target in self.direct() if target == step_id)


@pytest.fixture(scope="module")
def cw(book) -> Crosswalk:
    return Crosswalk(book)


def annotation_file(path: Path, raw_crosswalk: dict, cases: dict, *, spacing: int = FPS,
                    start: int = 0) -> Path:  # fmt: skip
    """A GraSP-shaped long-term file: the crosswalk's categories, then one image + annotation per
    label of each case, `spacing` frames apart from frame `start`."""
    data = {
        "phases_categories": [
            {"id": c["grasp_id"], "name": c["code"], "description": c["name"]}
            for c in raw_crosswalk["phases"]
        ],
        "steps_categories": [
            {"id": c["grasp_id"], "name": c["code"], "description": c["name"]}
            for c in raw_crosswalk["steps"]
        ],
        "images": [],
        "annotations": [],
    }
    for case, labels in cases.items():
        for k, (phase, step) in enumerate(labels):
            image_id = len(data["images"]) + 1
            frame = start + k * spacing
            data["images"].append({
                "id": image_id, "file_name": f"{case}/{frame:09d}.jpg", "width": 1280,
                "height": 800, "video_name": case, "frame_num": frame,
            })  # fmt: skip
            data["annotations"].append(
                {"id": image_id, "image_id": image_id, "phases": phase, "steps": step}
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def run(tmp_path, raw_crosswalk, labels, **kw):
    spacing = kw.pop("spacing", FPS)
    start = kw.pop("start", 0)
    path = annotation_file(
        tmp_path / "grasp_long-term_t1.json", raw_crosswalk,
        {CASE: labels, "CASE099": labels[:2]}, spacing=spacing, start=start,
    )  # fmt: skip
    kw.setdefault("video_fps", FPS)
    return import_grasp_steps(path, CASE, CASE_ID, **kw)


def spans(segments):
    return [(s.step_id, round(s.t_start, 6), round(s.t_end, 6)) for s in segments]


def labelled(cw: Crosswalk, step_id: str, n: int) -> list[tuple[int, int]]:
    """`n` keyframes of a direct label for `step_id`, in a GraSP phase that maps to it."""
    return [(cw.a_phase_for(step_id), cw.label_for(step_id))] * n


def two_direct_steps(cw: Crosswalk) -> tuple[str, str]:
    """Two different rule-book steps with direct labels, the first earlier in rule-book order."""
    direct = sorted({t for _, t in cw.direct()}, key=cw.order.index)
    return direct[0], direct[1]


# ── B1-1 ─────────────────────────────────────────────────────────────────────


def test_b1_1_labels_become_contract_dataset_step_segments(tmp_path, raw_crosswalk, cw):
    """B1-1 "The labels become contract `StepSegment`s with track `dataset`, confidence 1.0,
    provenance `dataset_annotation` / `dataset`, ids `<case_id>.sNNN`, and times
    `frame_num / fps`" (README: "rule-book step segments on the dataset track (📐
    `dataset_annotation`)"). Two direct labels, 5 and 4 keyframes from frame 60 at 30 fps: 2-7 s
    and 7-11 s; they also make a valid contract `Timeline` for the case."""
    a, b = two_direct_steps(cw)
    segments, _ = run(tmp_path, raw_crosswalk, labelled(cw, a, 5) + labelled(cw, b, 4), start=60)
    assert [s.step_id for s in segments] == [a, b]
    assert spans(segments)[0] == (a, 2.0, 7.0)
    assert spans(segments)[1][:2] == (b, 7.0)
    assert 10.0 < segments[1].t_end <= 11.0 + 1e-9, segments[1]
    numbers = []
    for seg in segments:
        StepSegment.model_validate(seg.model_dump(mode="json"))
        assert seg.id.startswith(f"{CASE_ID}.s") and len(seg.id.split(".s")[1]) >= 3, seg.id
        numbers.append(int(seg.id.split(".s")[1]))
        assert seg.track.value == "dataset"
        assert seg.confidence == 1.0
        assert seg.provenance.trust_label.value == "dataset_annotation"
        assert seg.provenance.attributed_to.value == "dataset"
        assert seg.provenance.generated_by is None
    assert numbers == sorted(set(numbers)), "segment ids not unique and in time order"
    Timeline.model_validate({
        "contract_version": "1.0", "case_id": CASE_ID,
        "steps": [s.model_dump(mode="json") for s in segments],
        "events": [], "instruments": [], "utterances": [],
    })  # fmt: skip


def test_b1_1_only_the_given_case_is_imported(tmp_path, raw_crosswalk, cw):
    """README: one GraSP case's labels: keyframes of another case in the same file are left out
    (the file holds two cases here)."""
    a, _ = two_direct_steps(cw)
    segments, report = run(tmp_path, raw_crosswalk, labelled(cw, a, 6))
    assert spans(segments)[0][:2] == (a, 0.0)
    assert len(segments) == 1
    assert report.seconds_by_step.get(a) == pytest.approx(6.0)


# ── B1-2 ─────────────────────────────────────────────────────────────────────


def test_b1_2_a_given_video_fps_is_used(tmp_path, raw_crosswalk, cw):
    """B1-2 "A given `video_fps` is used" (README: "a keyframe's time is `frame_num / fps`. Pass
    the source video's `video_fps`"): keyframes 30 frames apart with `video_fps=29.97` start at
    `frame / 29.97`."""
    a, b = two_direct_steps(cw)
    segments, _ = run(
        tmp_path, raw_crosswalk, labelled(cw, a, 3) + labelled(cw, b, 3), start=300,
        video_fps=29.97,
    )  # fmt: skip
    assert segments[0].t_start == pytest.approx(300 / 29.97)
    assert segments[1].t_start == pytest.approx((300 + 3 * 30) / 29.97)


@pytest.mark.parametrize("spacing", [25, 30, 60])
def test_b1_2_without_video_fps_the_rate_comes_from_the_1_s_spacing(
    tmp_path, raw_crosswalk, cw, spacing
):
    """B1-2 "Without it, the rate is estimated from the 1 s keyframe spacing": keyframes `spacing`
    frames apart give `spacing` fps, so each keyframe is 1 s."""
    a, b = two_direct_steps(cw)
    segments, _ = run(
        tmp_path, raw_crosswalk, labelled(cw, a, 4) + labelled(cw, b, 2), spacing=spacing,
        start=10 * spacing, video_fps=None,
    )  # fmt: skip
    assert spans(segments)[0] == (a, 10.0, 14.0)
    assert spans(segments)[1][:2] == (b, 14.0)


# ── B1-3 ─────────────────────────────────────────────────────────────────────


def test_b1_3_idle_inside_one_step_is_bridged(tmp_path, raw_crosswalk, cw):
    """B1-3 "Idle gives no segment. A pause inside the same step is bridged": A A A idle idle A A
    B B gives A over 0-7 s (the pause bridged) and B from 7 s."""
    a, b = two_direct_steps(cw)
    idle = [(cw.idle_phase(), cw.idle_step())]
    labels = labelled(cw, a, 3) + idle * 2 + labelled(cw, a, 2) + labelled(cw, b, 2)
    segments, _ = run(tmp_path, raw_crosswalk, labels)
    assert [s.step_id for s in segments] == [a, b]
    assert spans(segments)[0] == (a, 0.0, 7.0)
    assert spans(segments)[1][:2] == (b, 7.0)


def test_b1_3_a_gap_remains_only_at_a_step_change(tmp_path, raw_crosswalk, cw):
    """B1-3 "… and a gap remains only at a step change": A A idle idle B B B gives A 0-2 s and B
    from 4 s (the idle 2-4 s is no segment); idle at the start and end gives none either. The
    report counts 2 s of A, 3 s of B and 4 s of idle."""
    a, b = two_direct_steps(cw)
    idle = [(cw.idle_phase(), cw.idle_step())]
    labels = idle + labelled(cw, a, 2) + idle * 2 + labelled(cw, b, 3) + idle
    segments, report = run(tmp_path, raw_crosswalk, labels)
    assert spans(segments) == [(a, 1.0, 3.0), (b, 5.0, 8.0)]
    assert report.seconds_by_step.get(a) == pytest.approx(2.0)
    assert report.seconds_by_step.get(b) == pytest.approx(3.0)
    assert report.idle_seconds == pytest.approx(4.0)


def test_b1_3_without_idle_segments_are_contiguous(tmp_path, raw_crosswalk, cw):
    """B1-3, "a gap remains only at a step change" with an idle: without one, each segment ends
    where the next begins (A B A: three segments, a surgeon may go back, README)."""
    a, b = two_direct_steps(cw)
    labels = labelled(cw, a, 2) + labelled(cw, b, 3) + labelled(cw, a, 2)
    segments, _ = run(tmp_path, raw_crosswalk, labels)
    assert [s.step_id for s in segments] == [a, b, a]
    for first, second in zip(segments, segments[1:], strict=False):
        assert first.t_end == pytest.approx(second.t_start)
    assert spans(segments)[:2] == [(a, 0.0, 2.0), (b, 2.0, 5.0)]


# ── B1-4 ─────────────────────────────────────────────────────────────────────


def test_b1_4_maps_to_a_step_gives_that_step(tmp_path, raw_crosswalk, cw):
    """B1-4 "`maps_to`": every label that maps to one rule-book step gives exactly that step."""
    for grasp_step, step_id in cw.direct():
        segments, _ = run(tmp_path, raw_crosswalk, [(cw.a_phase_for(step_id), grasp_step)] * 3)
        assert [s.step_id for s in segments] == [step_id], (grasp_step, step_id)


def _phase_target_label(cw: Crosswalk) -> tuple[int, str, list[str]]:
    """A label whose `maps_to` is one rule-book phase with two or more steps."""
    for g, lab in cw.steps.items():
        if lab.by_phase or lab.maps_to == "phase" or len(lab.maps_to) != 1:
            continue
        target = lab.maps_to[0]
        if target in cw.steps_of and len(cw.steps_of[target]) >= 2:
            return g, target, cw.steps_of[target]
    pytest.fail("the crosswalk has no label that maps to a multi-step phase")


def test_b1_4_a_phase_target_expands_to_its_steps(tmp_path, raw_crosswalk, cw):
    """B1-4 "`maps_to` (phase targets expand to their steps)" and README "With several candidate
    steps …": alone, a label that maps to a phase gives that phase's first step; after a label for
    the phase's second step, it keeps that step (continuity)."""
    grasp_step, phase, steps = _phase_target_label(cw)
    gphase = cw.a_phase_for(steps[0])
    alone, _ = run(tmp_path, raw_crosswalk, [(gphase, grasp_step)] * 3)
    assert [s.step_id for s in alone] == [steps[0]]
    second = steps[1]
    try:
        lead = cw.label_for(second)
    except StopIteration:
        pytest.skip(f"no direct label for {second}")
    kept, _ = run(tmp_path, raw_crosswalk, [(gphase, lead)] * 2 + [(gphase, grasp_step)] * 3)
    assert [s.step_id for s in kept] == [second], spans(kept)


def test_b1_4_by_phase_overrides_maps_to(tmp_path, raw_crosswalk, cw):
    """B1-4 "`by_phase` overrides": for each label with `by_phase`, in each listed GraSP phase it
    gives that phase's target; a label with a `maps_to` list gives `maps_to` in another phase."""
    checked = 0
    for g, lab in cw.steps.items():
        for gphase, targets in lab.by_phase.items():
            want = cw.expand(targets)
            segments, _ = run(tmp_path, raw_crosswalk, [(gphase, g)] * 3)
            assert [s.step_id for s in segments] == want[:1], (g, gphase, spans(segments))
            checked += 1
        if lab.by_phase and lab.maps_to != "phase" and lab.maps_to:
            other = next(p for p, pl in cw.phases.items() if p not in lab.by_phase and pl.maps_to)
            segments, _ = run(tmp_path, raw_crosswalk, [(other, g)] * 3)
            assert [s.step_id for s in segments] == cw.expand(lab.maps_to)[:1], (g, other)
    assert checked, "the crosswalk has no by_phase entry"


def test_b1_4_a_generic_act_uses_its_grasp_phase_mapping(tmp_path, raw_crosswalk, cw):
    """B1-4 "`phase` (generic acts use their GraSP phase's mapping)": a `maps_to: phase` label
    without `by_phase`, in every GraSP phase whose mapping is one rule-book step, gives that
    step."""
    generic = [g for g, lab in cw.steps.items() if lab.maps_to == "phase" and not lab.by_phase]
    assert generic, "the crosswalk has no generic act"
    checked = 0
    for gphase in cw.phases:
        targets = cw.phase_targets(gphase)
        if len(targets) != 1:
            continue
        for g in generic:
            segments, _ = run(tmp_path, raw_crosswalk, [(gphase, g)] * 3)
            assert [s.step_id for s in segments] == targets, (g, gphase, spans(segments))
            checked += 1
    assert checked


def test_b1_4_continuity_keeps_the_current_step_else_the_next_not_earlier(
    tmp_path, raw_crosswalk, cw
):
    """B1-4 "continuity among several candidates" (README: "the current step is kept if possible,
    else the first one not earlier in rule-book order"): a generic act in a GraSP phase with
    several candidates keeps the current step when it is one of them, and otherwise, after a step
    that lies between the candidates, goes to the first candidate not earlier than it."""
    generic = next(g for g, lab in cw.steps.items() if lab.maps_to == "phase" and not lab.by_phase)
    direct = dict((t, g) for g, t in cw.direct())
    kept = moved = 0
    for gphase in cw.phases:
        candidates = cw.phase_targets(gphase)
        if len(candidates) < 2:
            continue
        for step in candidates[1:]:
            if step in direct:
                segments, _ = run(
                    tmp_path, raw_crosswalk, [(gphase, direct[step])] * 2 + [(gphase, generic)] * 3
                )
                assert [s.step_id for s in segments] == [step], (gphase, step, spans(segments))
                kept += 1
        first, last = cw.order.index(candidates[0]), cw.order.index(candidates[-1])
        between = [s for s in cw.order[first + 1 : last] if s not in candidates and s in direct]
        for current in between:
            want = next(c for c in candidates if cw.order.index(c) >= cw.order.index(current))
            segments, _ = run(
                tmp_path, raw_crosswalk,
                [(cw.a_phase_for(current), direct[current])] * 2 + [(gphase, generic)] * 3,
            )  # fmt: skip
            assert [s.step_id for s in segments] == [current, want], (gphase, spans(segments))
            moved += 1
    assert kept and moved, (kept, moved)


def test_b1_4_unmapped_labels_give_no_segment_and_are_reported(tmp_path, raw_crosswalk, cw):
    """README "`report` gives … any unmapped labels": a generic act in the Idle GraSP phase has no
    target, so it gives no segment, and the report lists it with its seconds."""
    generic = next(g for g, lab in cw.steps.items() if lab.maps_to == "phase" and not lab.by_phase)
    a, _ = two_direct_steps(cw)
    labels = labelled(cw, a, 2) + [(cw.idle_phase(), generic)] * 3
    segments, report = run(tmp_path, raw_crosswalk, labels)
    assert [s.step_id for s in segments] == [a]
    code = cw.steps[generic].code or cw.steps[generic].name
    assert report.unmapped_seconds, report
    assert any(code in str(key) for key in report.unmapped_seconds), report.unmapped_seconds
    assert sum(report.unmapped_seconds.values()) == pytest.approx(3.0)


# ── B1-5 ─────────────────────────────────────────────────────────────────────


def _mismatch(raw_crosswalk: dict, how: str) -> dict:
    changed = copy.deepcopy(raw_crosswalk)
    if how == "step-name-changed":
        changed["steps"][3]["name"] += " (v2)"
    elif how == "step-code-changed":
        changed["steps"][4]["code"] = "T1_Renamed"
    elif how == "phase-missing":
        del changed["phases"][-1]
    elif how == "extra-step":
        changed["steps"].append({"grasp_id": 99, "code": "T1_Extra", "name": "T1 extra step"})
    elif how == "ids-shifted":
        changed["phases"][2]["grasp_id"] = 77
    else:
        raise ValueError(how)
    return changed


@pytest.mark.parametrize(
    "how", ["step-name-changed", "step-code-changed", "phase-missing", "extra-step", "ids-shifted"]
)
def test_b1_5_categories_that_dont_match_the_crosswalk_raise(tmp_path, raw_crosswalk, cw, how):
    """B1-5 "Category lists that don't match the crosswalk raise `GraspError`" (README: "the
    file's category lists must equal the A1 crosswalk (ids, codes, names), or the import
    stops")."""
    a, _ = two_direct_steps(cw)
    path = annotation_file(
        tmp_path / "grasp_long-term_t1.json", _mismatch(raw_crosswalk, how),
        {CASE: labelled(cw, a, 3)},
    )  # fmt: skip
    with pytest.raises(GraspError):
        import_grasp_steps(path, CASE, CASE_ID, video_fps=FPS)


def test_b1_5_a_missing_case_raises(tmp_path, raw_crosswalk, cw):
    """B1-5 "… and so does a missing case": the file has no keyframes for the GraSP case asked
    for."""
    a, _ = two_direct_steps(cw)
    path = annotation_file(tmp_path / "g.json", raw_crosswalk, {"CASE001": labelled(cw, a, 3)})
    with pytest.raises(GraspError) as caught:
        import_grasp_steps(path, CASE, CASE_ID, video_fps=FPS)
    assert CASE in str(caught.value)


@pytest.mark.parametrize("bad", ["missing", "not-json"])
def test_b1_5_an_unreadable_file_raises(tmp_path, bad):
    """B1-5 / README "or the import stops": a missing file or one that isn't JSON raises
    `GraspError` (not a crash)."""
    path = tmp_path / "grasp_long-term_t1.json"
    if bad == "not-json":
        path.write_text("{not json", encoding="utf-8")
    with pytest.raises(GraspError):
        import_grasp_steps(path, CASE, CASE_ID, video_fps=FPS)


def test_b1_5_the_report_gives_seconds_per_step_and_idle(tmp_path, raw_crosswalk, cw):
    """B1-5 "The report gives seconds per step and idle seconds" (README "`report` gives seconds
    per rule-book step, idle seconds …"): A ×4, idle ×3, B ×5, at 1 s per keyframe."""
    a, b = two_direct_steps(cw)
    idle = [(cw.idle_phase(), cw.idle_step())]
    _, report = run(tmp_path, raw_crosswalk, labelled(cw, a, 4) + idle * 3 + labelled(cw, b, 5))
    assert {k: round(v, 6) for k, v in report.seconds_by_step.items() if v} == {a: 4.0, b: 5.0}
    assert report.idle_seconds == pytest.approx(3.0)
    assert not report.unmapped_seconds


# ── README gaps (T1 brief round 3, narrow re-test) ───────────────────────────


def test_gap_only_the_documented_file_keys_are_needed(tmp_path, raw_crosswalk, cw):
    """Gap re-test: README "Input: … `phases_categories` and `steps_categories` hold `id`, `name`
    (the code) and `description` (the name); `images` hold `id`, `video_name` … and
    `frame_num`; `annotations` hold `image_id`, `phases` and `steps`": a file with exactly those
    keys (no file name, size or annotation id) imports like the full one."""
    a, b = two_direct_steps(cw)
    labels = labelled(cw, a, 4) + labelled(cw, b, 3)
    full, _ = run(tmp_path / "full", raw_crosswalk, labels)
    data = {
        "phases_categories": [{"id": c["grasp_id"], "name": c["code"], "description": c["name"]}
                              for c in raw_crosswalk["phases"]],
        "steps_categories": [{"id": c["grasp_id"], "name": c["code"], "description": c["name"]}
                             for c in raw_crosswalk["steps"]],
        "images": [{"id": k + 1, "video_name": CASE, "frame_num": k * FPS}
                   for k in range(len(labels))],
        "annotations": [{"image_id": k + 1, "phases": p, "steps": s}
                        for k, (p, s) in enumerate(labels)],
    }  # fmt: skip
    path = tmp_path / "minimal.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    minimal, _ = import_grasp_steps(path, CASE, CASE_ID, video_fps=FPS)
    assert spans(minimal) == spans(full)


def test_gap_the_last_keyframe_stands_for_1_s(tmp_path, raw_crosswalk, cw):
    """Gap re-test: README "Each keyframe stands for the time up to the next one; the last one
    stands for 1 s": keyframes 2 s apart (60 frames at 30 fps) give A 0-6 s and B 6-11 s (the
    last of B's keyframes, at 10 s, stands for 1 s)."""
    a, b = two_direct_steps(cw)
    segments, report = run(
        tmp_path, raw_crosswalk, labelled(cw, a, 3) + labelled(cw, b, 3), spacing=60
    )
    assert spans(segments) == [(a, 0.0, 6.0), (b, 6.0, 11.0)]
    assert report.seconds_by_step.get(b) == pytest.approx(5.0)


def test_gap_when_every_candidate_is_earlier_the_first_is_taken(tmp_path, raw_crosswalk, cw):
    """Gap re-test: README "if all of them are earlier (the surgeon went back), the first
    candidate": after a direct label for a step later than all of a GraSP phase's candidates, a
    generic act in that phase takes the phase's first candidate."""
    generic = next(g for g, lab in cw.steps.items() if lab.maps_to == "phase" and not lab.by_phase)
    direct = dict((t, g) for g, t in cw.direct())
    checked = 0
    for gphase in cw.phases:
        candidates = cw.phase_targets(gphase)
        if len(candidates) < 2:
            continue
        later = [s for s in direct if cw.order.index(s) > cw.order.index(candidates[-1])]
        if not later:
            continue
        current = later[0]
        segments, _ = run(
            tmp_path, raw_crosswalk,
            [(cw.a_phase_for(current), direct[current])] * 2 + [(gphase, generic)] * 3,
        )  # fmt: skip
        assert [s.step_id for s in segments] == [current, candidates[0]], spans(segments)
        checked += 1
    assert checked
