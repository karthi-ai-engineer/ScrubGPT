"""C3 Rule-book decoding: #14 acceptance criteria 4-7 (Team Lead answer; D-067; plan §2.3 C3,
§8.1 step 4; brain/README.md "C3 Rule-book decoding").

Expected behaviour, written from the spec before the code was opened:
- Input: `windows` [(t_start, t_end)] in float seconds and a probability matrix, one row per
  window and one column per `plan.step_ids` entry, with `plan = plan_from_rulebook(rulebook)`.
  Output: `Segment(step_id, t_start, t_end, confidence, n_windows)`.
- AC4: clean diagonal probabilities decode to exactly those steps, in rule-book order; segments
  are contiguous float-second spans with t_start < t_end, from the first window's start to the
  last window's end, no gap or overlap (README: "A gap between windows belongs to the segment
  before it"; "The recording may start and end at any step").
- AC5: a single out-of-order spike is smoothed away (no backward jump), and no output ever has a
  transition the rule book forbids. The README's rules: next step free; skipping forward allowed
  (each skipped required step costs `skip_penalty`, optional-phase steps free); a movable phase
  may appear at each place it `may_follow`; never backward (`default: sequential`); no repeat is
  documented, so a step never follows itself or comes back. So the segment sequence must be a
  strictly increasing subsequence of the "expanded order": the rule-book order with each movable
  phase placed after every phase it may follow.
- AC6: with weak or ambiguous evidence, segment lengths are pulled toward the typical durations
  (into p25..p75); with strong evidence, the evidence wins (an unusually short or long step keeps
  its evidence length). `use_durations=False` turns the priors off.
- AC7: bad input raises `ValueError` with a clear message: a wrong number of columns, negative
  values or NaN, zero windows, window times that aren't strictly increasing. Rows that don't sum
  to 1 are normalised (README), so scaling a row changes nothing and "a row of zeros = no
  information".

No step id is hard-coded: ids, order and durations come from the committed rule book (parsed
independently by the conftest fixtures, and loaded with `load_knowledge` for the plan).
"""

from __future__ import annotations

import math
import shutil

import numpy as np
import pytest
import yaml
from scrubgpt_brain.engines.decode import decode, plan_from_rulebook
from scrubgpt_brain.engines.rulebook import load_knowledge

W = 60.0  # C2's 1-minute windows (plan §8.1 step 2)
CLEAN = 0.97


# ── the rule book, read independently (conftest `rulebook` fixture) ──────────


class Book:
    """Order, durations and order rules of the committed rule book, from the raw YAML."""

    def __init__(self, raw: dict) -> None:
        rules = raw["order_rules"]
        self.phases = [p["id"] for p in raw["phases"]]
        self.steps_of = {p["id"]: [s["id"] for s in p.get("steps") or []] for p in raw["phases"]}
        self.order = [s for p in self.phases for s in self.steps_of[p]]
        self.phase_of = {s: p for p in self.phases for s in self.steps_of[p]}
        self.duration = {
            s["id"]: (s["typical_duration_s"]["p25"], s["typical_duration_s"]["p50"],
                      s["typical_duration_s"]["p75"])
            for p in raw["phases"] for s in p.get("steps") or []
        }  # fmt: skip
        self.optional = set(rules.get("optional_phases") or []) | {
            p["id"] for p in raw["phases"] if p.get("optional")
        }
        self.movable = {
            m["phase"]: list(m["may_follow"]) for m in rules.get("movable_phases") or []
        }
        expanded: list[str] = []
        for phase in self.phases:
            if phase not in self.movable:
                expanded += self.steps_of[phase]
            for moved, follows in self.movable.items():
                if phase in follows:
                    expanded += self.steps_of[moved]
        self.expanded = expanded
        # Steps outside optional and movable phases, in order: the "main line".
        self.required = [
            s for s in self.order
            if self.phase_of[s] not in self.optional and self.phase_of[s] not in self.movable
        ]  # fmt: skip

    def windows_for(self, step: str) -> int:
        return max(1, round(self.duration[step][1] / W))

    def typical_runs(self, steps: list[str]) -> list[tuple[str, int]]:
        return [(s, self.windows_for(s)) for s in steps]

    def forbidden(self, sequence: list[str]) -> str | None:
        """Why `sequence` breaks the order rules, or None (a strictly increasing subsequence of
        the expanded order)."""
        position = -1
        for index, step in enumerate(sequence):
            following = [j for j in range(position + 1, len(self.expanded))]
            nxt = next((j for j in following if self.expanded[j] == step), None)
            if nxt is None:
                before = sequence[index - 1] if index else "(start)"
                return f"{before} -> {step} at segment {index} is not allowed: {sequence}"
            position = nxt
        return None


@pytest.fixture(scope="module")
def book(rulebook) -> Book:
    return Book(rulebook)


@pytest.fixture(scope="module")
def plan():
    return plan_from_rulebook(load_knowledge().rulebook)


# ── synthetic inputs ─────────────────────────────────────────────────────────


def build(plan, runs, *, p_on=CLEAN, gap=0.0, start=0.0):
    """Windows of `W` s (minus `gap`), and rows confident (`p_on`) in each run's step."""
    column = {sid: k for k, sid in enumerate(plan.step_ids)}
    n = len(plan.step_ids)
    windows, rows, spans = [], [], []
    t = start
    for step, count in runs:
        first = len(windows)
        for _ in range(count):
            windows.append((float(t), float(t + W - gap)))
            row = [(1.0 - p_on) / (n - 1)] * n
            row[column[step]] = p_on
            rows.append(row)
            t += W
        spans.append((step, first, len(windows) - 1))
    return windows, rows, spans


def expected_segments(windows, spans):
    """(step, t_start, t_end, n_windows) of each run: a gap belongs to the segment before."""
    out = []
    for i, (step, first, last) in enumerate(spans):
        t_start = windows[first][0]
        t_end = windows[spans[i + 1][1]][0] if i + 1 < len(spans) else windows[last][1]
        out.append((step, t_start, t_end, last - first + 1))
    return out


def got(segments):
    return [(s.step_id, s.t_start, s.t_end, s.n_windows) for s in segments]


def steps_of(segments):
    return [s.step_id for s in segments]


def assert_well_formed(segments, windows):
    """AC4: contiguous float-second segments with t_start < t_end covering the windows."""
    assert segments, "no segment"
    assert segments[0].t_start == pytest.approx(windows[0][0], abs=1e-9)
    assert segments[-1].t_end == pytest.approx(windows[-1][1], abs=1e-9)
    for seg in segments:
        assert isinstance(seg.t_start, float) and isinstance(seg.t_end, float), seg
        assert seg.t_start < seg.t_end, seg
        assert math.isfinite(seg.confidence), seg
    for a, b in zip(segments, segments[1:], strict=False):
        assert a.t_end == pytest.approx(b.t_start, abs=1e-9), f"gap or overlap: {a} | {b}"
    assert sum(s.n_windows for s in segments) == len(windows)


def window_labels(segments, windows):
    """The decoded step of each window (by its midpoint)."""
    labels = []
    for t0, t1 in windows:
        mid = (t0 + t1) / 2
        labels.append(next(s.step_id for s in segments if s.t_start <= mid < s.t_end))
    return labels


def _middle(book: Book) -> list[str]:
    """A slice of the main line that starts and ends mid-procedure."""
    return book.required[2:-2]


# ── AC4 ──────────────────────────────────────────────────────────────────────


def test_ac4_plan_columns_are_the_rule_book_steps(plan, book):
    """README "`plan = plan_from_rulebook(knowledge.rulebook)  # columns = plan.step_ids`": one
    column per rule-book step, each exactly once."""
    assert sorted(plan.step_ids) == sorted(book.order)
    assert len(set(plan.step_ids)) == len(plan.step_ids)


@pytest.mark.parametrize("which", ["full", "middle-slice", "without-optional-phases"])
def test_ac4_clean_diagonal_decodes_to_exactly_those_steps(plan, book, which):
    """#14 AC4 "Clean diagonal probabilities (each window confident in the next step in order)
    decode to exactly those steps, in rule-book order. Segments are contiguous, have float-second
    `t_start` < `t_end`, and cover the input time range from the first window's start to the last
    window's end with no gaps or overlaps." Each step gets its typical (p50) number of windows;
    "middle-slice" starts and ends mid-procedure (README "The recording may start and end at any
    step")."""
    steps = {
        "full": book.order,
        "middle-slice": _middle(book),
        "without-optional-phases": [s for s in book.order if book.phase_of[s] not in book.optional],
    }[which]
    windows, rows, spans = build(plan, book.typical_runs(steps), start=12.5)
    segments = decode(windows, rows, plan)
    assert_well_formed(segments, windows)
    assert steps_of(segments) == steps
    assert got(segments) == expected_segments(windows, spans)


def test_ac4_one_window_per_step_without_duration_priors(plan, book):
    """#14 AC4 with one window per step ("each window confident in the next step in order") and
    `use_durations=False` (README: "turns durations off for edited videos"): every window is its
    own segment, in rule-book order."""
    windows, rows, spans = build(plan, [(s, 1) for s in book.order])
    segments = decode(windows, rows, plan, use_durations=False)
    assert_well_formed(segments, windows)
    assert got(segments) == expected_segments(windows, spans)


def test_ac4_a_single_window_is_one_segment(plan, book):
    """#14 AC4 at its smallest: one window decodes to one segment spanning exactly that window."""
    windows, rows, spans = build(plan, [(book.required[3], 1)], start=7.0)
    segments = decode(windows, rows, plan)
    assert_well_formed(segments, windows)
    assert got(segments) == expected_segments(windows, spans)


def test_ac4_gaps_between_windows_belong_to_the_segment_before(plan, book):
    """#14 AC4 "… with no gaps or overlaps" when the windows themselves have gaps (55 s windows
    every 60 s): README "A gap between windows belongs to the segment before it"."""
    windows, rows, spans = build(plan, book.typical_runs(_middle(book)), gap=5.0)
    segments = decode(windows, rows, plan)
    assert_well_formed(segments, windows)
    assert got(segments) == expected_segments(windows, spans)


def test_ac4_numpy_and_list_inputs_decode_alike(plan, book):
    """#14 AC4 "It takes the probability matrix as input" (Team Lead answer, item 2): a numpy
    array and nested lists give the same segments."""
    windows, rows, _ = build(plan, book.typical_runs(_middle(book)))
    assert got(decode(np.array(windows), np.array(rows), plan)) == got(decode(windows, rows, plan))


# ── AC5 ──────────────────────────────────────────────────────────────────────


def _spike_case(book: Book):
    """A main-line step with >= 5 windows that has 3 more main-line steps after it, and the step
    3 places later (the spike)."""
    for i, step in enumerate(book.required):
        if i >= 1 and book.windows_for(step) >= 5 and i + 3 < len(book.required):
            return step, book.required[i + 3]
    raise AssertionError("no step fits the spike case")


@pytest.mark.parametrize("spike", [(0.6, 0.3), (0.95, 0.02)], ids=["moderate", "strong"])
def test_ac5_a_single_out_of_order_spike_is_smoothed(plan, book, spike):
    """#14 AC5 "Noise is smoothed. A single window whose highest probability is an out-of-order
    step (for example, a later step spiking inside an earlier one) doesn't produce a backward
    jump." The middle window of a long step peaks on the step three places later; the output is
    the clean decoding, the spike window stays inside its step."""
    host, later = _spike_case(book)
    windows, rows, spans = build(plan, book.typical_runs(book.order))
    clean = got(decode(windows, rows, plan))
    _, first, last = next(span for span in spans if span[0] == host)
    middle = (first + last) // 2
    column = {sid: k for k, sid in enumerate(plan.step_ids)}
    high, own = spike
    n = len(plan.step_ids)
    row = [(1.0 - high - own) / (n - 2)] * n
    row[column[later]], row[column[host]] = high, own
    rows[middle] = row
    assert max(range(n), key=row.__getitem__) == column[later]  # the spike is the argmax
    segments = decode(windows, rows, plan)
    assert book.forbidden(steps_of(segments)) is None, book.forbidden(steps_of(segments))
    assert got(segments) == clean
    assert window_labels(segments, windows)[middle] == host


@pytest.mark.parametrize("use_durations", [True, False], ids=["durations", "no-durations"])
@pytest.mark.parametrize("seed", range(6))
def test_ac5_random_noise_never_gives_a_forbidden_transition(plan, book, seed, use_durations):
    """#14 AC5 "The output never has a step transition the rule book forbids." Pure noise (rows
    from a sparse Dirichlet, 150 windows) decodes to a sequence allowed by the README's rules
    (forward only, skips allowed, the movable phase only where it `may_follow`, no repeat)."""
    rng = np.random.default_rng(seed)
    rows = rng.dirichlet(np.full(len(plan.step_ids), 0.3), size=150)
    windows = [(i * W, (i + 1) * W) for i in range(len(rows))]
    segments = decode(windows, rows, plan, use_durations=use_durations)
    assert_well_formed(segments, windows)
    assert book.forbidden(steps_of(segments)) is None, book.forbidden(steps_of(segments))


def test_ac5_reversed_evidence_never_goes_backward(plan, book):
    """#14 AC5 "never has a step transition the rule book forbids" (README "Never backward"):
    clean evidence for the whole procedure in reverse order still decodes forward only."""
    windows, rows, _ = build(plan, book.typical_runs(list(reversed(book.order))))
    segments = decode(windows, rows, plan)
    assert_well_formed(segments, windows)
    assert book.forbidden(steps_of(segments)) is None, book.forbidden(steps_of(segments))


def test_ac5_evidence_for_a_repeat_does_not_go_back(plan, book):
    """#14 AC5 "The rules for skips and repeats come from the rule book and are documented in the
    module README": the README allows no repeat ("Never backward"), so clean evidence A, B, A for
    two consecutive steps never decodes to B -> A."""
    a, b = _middle(book)[:2]
    windows, rows, _ = build(plan, [(a, 6), (b, 6), (a, 6)])
    segments = decode(windows, rows, plan)
    assert_well_formed(segments, windows)
    assert book.forbidden(steps_of(segments)) is None, book.forbidden(steps_of(segments))


def test_ac5_an_optional_phase_can_be_skipped(plan, book):
    """README "Steps of an optional phase (`order_rules.optional_phases`) are skipped free": clean
    evidence that leaves out each optional, non-movable phase decodes to exactly what's there."""
    optional = [p for p in book.phases if p in book.optional and p not in book.movable]
    assert optional, "the rule book has no optional, non-movable phase"
    for phase in optional:
        steps = [s for s in book.order if book.phase_of[s] != phase]
        windows, rows, spans = build(plan, book.typical_runs(steps))
        assert got(decode(windows, rows, plan)) == expected_segments(windows, spans), phase


def test_ac5_a_movable_phase_decodes_at_each_place_it_may_follow(plan, book):
    """README "A movable phase (`order_rules.movable_phases`) can appear at each place it
    `may_follow`, free to skip at either": clean evidence with the movable phase moved after each
    phase it may follow decodes to exactly that order."""
    assert book.movable, "the rule book has no movable phase"
    for moved, follows in book.movable.items():
        rest = [p for p in book.phases if p != moved]
        for after in follows:
            phases = []
            for phase in rest:
                phases.append(phase)
                if phase == after:
                    phases.append(moved)
            steps = [s for p in phases for s in book.steps_of[p]]
            windows, rows, spans = build(plan, book.typical_runs(steps))
            segments = decode(windows, rows, plan)
            assert got(segments) == expected_segments(windows, spans), f"{moved} after {after}"


def test_ac5_a_movable_phase_elsewhere_is_not_decoded_there(plan, book):
    """#14 AC5 "never has a step transition the rule book forbids": clean evidence for the movable
    phase at a place it may not follow (after a middle main-line phase) still decodes to an
    allowed sequence."""
    for moved, follows in book.movable.items():
        candidates = [
            p for p in book.phases if p not in follows and p != moved and p not in book.optional
        ]
        after = candidates[len(candidates) // 2]
        phases = []
        for phase in (p for p in book.phases if p != moved):
            phases.append(phase)
            if phase == after:
                phases.append(moved)
        steps = [s for p in phases for s in book.steps_of[p]]
        windows, rows, _ = build(plan, book.typical_runs(steps))
        segments = decode(windows, rows, plan)
        assert book.forbidden(steps_of(segments)) is None, book.forbidden(steps_of(segments))


def test_ac5_a_required_step_with_no_evidence_is_skipped(plan, book):
    """README "Skipping forward: each skipped step of a required phase costs `skip_penalty`" and
    "A required step that the evidence argues against only moderately can come out as a
    one-window phantom": with strong clean evidence that leaves out one required step (each in
    turn, mid-procedure), the decoder skips it, giving exactly the steps that are there."""
    for step in book.required[1:-1]:
        steps = [s for s in book.order if s != step]
        windows, rows, spans = build(plan, book.typical_runs(steps))
        segments = decode(windows, rows, plan)
        assert got(segments) == expected_segments(windows, spans), f"skipping {step}"


def _with_moved_phase(book: Book, moved: str, after: str) -> list[str]:
    phases = []
    for phase in (p for p in book.phases if p != moved):
        phases.append(phase)
        if phase == after:
            phases.append(moved)
    return [s for p in phases for s in book.steps_of[p]]


def test_ac5_the_order_rules_come_from_the_rule_book(const, tmp_path, plan, book):
    """#14 AC5 "The rules for skips and repeats come from the rule book": a copy of knowledge/
    whose movable phase may follow a different main-line phase (instead of its second place) gives
    a plan that decodes the phase at the new place exactly, and no longer at the old one; the
    committed plan doesn't decode it at the new place."""
    root = tmp_path / "knowledge"
    shutil.copytree(const.knowledge, root)
    path = root / "rulebooks" / "rarp.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    rule = raw["order_rules"]["movable_phases"][0]
    moved, follows = rule["phase"], list(rule["may_follow"])
    assert len(follows) >= 2, "test setup: the movable phase has one place only"
    others = [p for p in book.phases if p not in follows and p != moved and p not in book.optional]
    new_place = others[len(others) // 2]
    rule["may_follow"] = [follows[0], new_place]
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    changed = Book(raw)
    new_plan = plan_from_rulebook(load_knowledge(root).rulebook)

    steps = _with_moved_phase(book, moved, new_place)
    windows, rows, spans = build(new_plan, changed.typical_runs(steps))
    assert got(decode(windows, rows, new_plan)) == expected_segments(windows, spans)
    windows, rows, _ = build(plan, book.typical_runs(steps))
    committed = steps_of(decode(windows, rows, plan))
    assert committed != steps and book.forbidden(committed) is None, committed

    old = _with_moved_phase(book, moved, follows[1])
    windows, rows, _ = build(new_plan, changed.typical_runs(old))
    decoded = steps_of(decode(windows, rows, new_plan))
    assert decoded != old and changed.forbidden(decoded) is None, decoded


def test_ac5_heavy_independent_noise_is_smoothed(plan, book):
    """#14 AC5 "Noise is smoothed" (README: on independent synthetic noise the decoder lifts
    window accuracy well above the raw argmax): each window gives its true step only 0.15 plus a
    share of Dirichlet noise; the decoded window labels beat the raw argmax by 20 points and reach
    85 %, over three seeds."""
    runs = book.typical_runs(book.order)
    truth = [s for s, n in runs for _ in range(n)]
    column = {sid: k for k, sid in enumerate(plan.step_ids)}
    n = len(plan.step_ids)
    raw_scores, decoded_scores = [], []
    for seed in range(3):
        rng = np.random.default_rng(100 + seed)
        rows = 0.85 * rng.dirichlet(np.full(n, 0.5), size=len(truth))
        rows[np.arange(len(truth)), [column[s] for s in truth]] += 0.15
        windows = [(i * W, (i + 1) * W) for i in range(len(truth))]
        segments = decode(windows, rows, plan)
        assert_well_formed(segments, windows)
        assert book.forbidden(steps_of(segments)) is None
        argmax = [plan.step_ids[k] for k in rows.argmax(axis=1)]
        raw_scores.append(np.mean([a == t for a, t in zip(argmax, truth, strict=True)]))
        labels = window_labels(segments, windows)
        decoded_scores.append(np.mean([a == t for a, t in zip(labels, truth, strict=True)]))
    raw, decoded = float(np.mean(raw_scores)), float(np.mean(decoded_scores))
    assert decoded >= max(0.85, raw + 0.20), f"raw argmax {raw:.2f}, decoded {decoded:.2f}"


# ── AC6 ──────────────────────────────────────────────────────────────────────


def _duration_case(book: Book):
    """(X, A, B, Y): four consecutive main-line steps, mid-procedure, with p25 of A and B >= 240 s
    (so 2 windows are clearly short) and X, Y as clean neighbours."""
    line = book.required
    for i in range(1, len(line) - 2):
        a, b = line[i], line[i + 1]
        if book.duration[a][0] >= 240 and book.duration[b][0] >= 240:
            return line[i - 1], a, b, line[i + 2]
    raise AssertionError("no pair of steps fits the duration case")


def _two_step_region(plan, book, x, y, region):
    """Clean X, then the A/B `region` rows ([(p_a, p_b)] per window), then clean Y."""
    windows, rows, _ = build(plan, [(x, book.windows_for(x))])
    column = {sid: k for k, sid in enumerate(plan.step_ids)}
    n = len(plan.step_ids)
    t = windows[-1][1]
    a, b = region["steps"]
    for p_a, p_b in region["rows"]:
        row = [0.0] * n
        row[column[a]], row[column[b]] = p_a, p_b
        windows.append((t, t + W))
        rows.append(row)
        t += W
    y_windows, y_rows, _ = build(plan, [(y, book.windows_for(y))], start=t)
    return windows + y_windows, rows + y_rows


def _length_of(segments, step):
    found = [s for s in segments if s.step_id == step]
    assert len(found) == 1, f"{step}: {len(found)} segments in {steps_of(segments)}"
    return found[0].t_end - found[0].t_start


def test_ac6_ambiguous_evidence_is_pulled_to_the_typical_durations(plan, book):
    """#14 AC6 "With weak or ambiguous evidence, the segment lengths are pulled toward the rule
    book's typical durations." Between two clean neighbours, a region as long as A's and B's
    typical durations together has 50/50 evidence for A and B: A and B each come out within
    their p25..p75."""
    x, a, b, y = _duration_case(book)
    n_region = book.windows_for(a) + book.windows_for(b)
    region = {"steps": (a, b), "rows": [(0.5, 0.5)] * n_region}
    windows, rows = _two_step_region(plan, book, x, y, region)
    segments = decode(windows, rows, plan)
    assert steps_of(segments) == [x, a, b, y]
    for step in (a, b):
        p25, _, p75 = book.duration[step]
        assert p25 <= _length_of(segments, step) <= p75, (step, got(segments))


def test_ac6_weak_evidence_is_pulled_toward_the_typical_duration(plan, book):
    """#14 AC6 "With weak or ambiguous evidence, the segment lengths are pulled toward the rule
    book's typical durations." The region's evidence weakly (52/48) puts the A/B boundary after
    one window: without priors (`use_durations=False`) A lasts that one window; with them, A is
    pulled into its p25..p75, closer to p50."""
    x, a, b, y = _duration_case(book)
    n_region = book.windows_for(a) + book.windows_for(b)
    region = {"steps": (a, b), "rows": [(0.52, 0.48)] + [(0.48, 0.52)] * (n_region - 1)}
    windows, rows = _two_step_region(plan, book, x, y, region)
    without = decode(windows, rows, plan, use_durations=False)
    assert steps_of(without) == [x, a, b, y]
    assert _length_of(without, a) == pytest.approx(W)
    with_priors = decode(windows, rows, plan)
    assert steps_of(with_priors) == [x, a, b, y]
    p25, p50, p75 = book.duration[a]
    length = _length_of(with_priors, a)
    assert p25 <= length <= p75, got(with_priors)
    assert abs(length - p50) < abs(W - p50)


@pytest.mark.parametrize("kind", ["short", "long"])
def test_ac6_strong_evidence_wins_over_the_priors(plan, book, kind):
    """#14 AC6 "With strong evidence, the evidence wins." Clean one-hot evidence makes A unusually
    short (2 windows, below its p25) or long (1.5 x its p75): A keeps exactly its evidence length
    with the duration priors on."""
    x, a, b, y = _duration_case(book)
    p25, _, p75 = book.duration[a]
    n_a = 2 if kind == "short" else math.ceil(1.5 * p75 / W)
    assert (n_a * W < p25) if kind == "short" else (n_a * W > p75)
    n_b = book.windows_for(b)
    region = {"steps": (a, b), "rows": [(1.0, 0.0)] * n_a + [(0.0, 1.0)] * n_b}
    windows, rows = _two_step_region(plan, book, x, y, region)
    segments = decode(windows, rows, plan)
    assert steps_of(segments) == [x, a, b, y]
    assert _length_of(segments, a) == pytest.approx(n_a * W)
    assert _length_of(segments, b) == pytest.approx(n_b * W)


# ── AC7 ──────────────────────────────────────────────────────────────────────


def _bad(plan, book):
    windows, rows, _ = build(plan, book.typical_runs(_middle(book)[:3]))
    return windows, rows


def _raises_clearly(windows, rows, plan, keywords):
    with pytest.raises(ValueError) as caught:
        decode(windows, rows, plan)
    message = str(caught.value).lower()
    assert message.strip(), "the ValueError has no message"
    assert any(k in message for k in keywords), f"unclear message: {caught.value}"


@pytest.mark.parametrize("delta", [-1, 1], ids=["one-column-short", "one-column-extra"])
def test_ac7_rows_that_dont_match_the_step_count_are_rejected(plan, book, delta):
    """#14 AC7 "probability rows that don't match the step count" raise a clear error (README:
    "Bad input raises `ValueError`: … a wrong number of columns")."""
    windows, rows = _bad(plan, book)
    n = len(plan.step_ids)
    rows = [row[:-1] if delta < 0 else [*row, 0.0] for row in rows]
    _raises_clearly(windows, rows, plan, [str(n), str(n + delta), "column", "step"])


def test_ac7_a_ragged_matrix_is_rejected(plan, book):
    """#14 AC7 "probability rows that don't match the step count": one short row among full ones."""
    windows, rows = _bad(plan, book)
    rows[1] = rows[1][:-2]
    with pytest.raises(ValueError):
        decode(windows, rows, plan)


@pytest.mark.parametrize("value", [-0.1, float("nan")], ids=["negative", "nan"])
def test_ac7_negative_values_or_nan_are_rejected(plan, book, value):
    """#14 AC7 "negative values, or NaN" raise a clear error (README "negative values or NaN")."""
    windows, rows = _bad(plan, book)
    rows[2][3] = value
    _raises_clearly(windows, rows, plan, ["negative", "nan", "finite", "invalid", "≥ 0", ">= 0"])


def test_ac7_zero_windows_are_rejected(plan):
    """#14 AC7 "zero windows" raise a clear error (README "no windows")."""
    _raises_clearly([], [], plan, ["window", "empty"])
    _raises_clearly([], np.zeros((0, len(plan.step_ids))), plan, ["window", "empty"])


@pytest.mark.parametrize("case", ["backward", "same-start", "end-before-start", "zero-length"])
def test_ac7_window_times_that_arent_increasing_are_rejected(plan, book, case):
    """#14 AC7 "window times that aren't increasing" raise a clear error (README "window times
    that aren't strictly increasing"): a window that starts before the one before it, two that
    start at the same time, and a window whose end isn't after its start."""
    windows, rows = _bad(plan, book)
    windows = list(windows)
    if case == "backward":
        windows[2], windows[3] = windows[3], windows[2]
    elif case == "same-start":
        windows[3] = (windows[2][0], windows[3][1])
    elif case == "end-before-start":
        windows[3] = (windows[3][0], windows[3][0] - 10.0)
    else:
        windows[3] = (windows[3][0], windows[3][0])
    _raises_clearly(windows, rows, plan, ["increas", "order", "time", "sort", "start", "end"])


def test_ac7_rows_that_dont_sum_to_one_are_normalised(plan, book):
    """#14 AC7 "Rows that don't sum to 1 are either normalised or rejected, and the README says
    which." The README says "Rows are **normalised**": scaling each row by its own factor gives
    the same segments as the rows that sum to 1."""
    windows, rows, _ = build(plan, book.typical_runs(_middle(book)))
    rng = np.random.default_rng(7)
    scaled = np.array(rows) * rng.uniform(0.05, 20.0, size=(len(rows), 1))
    assert not np.allclose(scaled.sum(axis=1), 1.0)
    assert got(decode(windows, scaled, plan)) == got(decode(windows, rows, plan))


def test_ac7_a_row_of_zeros_is_no_information(plan, book):
    """README "Rows are normalised (a row of zeros = no information)": a zero row inside a step's
    run is accepted, and the clean segments are unchanged."""
    windows, rows, spans = build(plan, book.typical_runs(_middle(book)))
    step, first, last = next(span for span in spans if span[2] - span[1] >= 2)
    rows[(first + last) // 2] = [0.0] * len(plan.step_ids)
    assert got(decode(windows, rows, plan)) == expected_segments(windows, spans)
