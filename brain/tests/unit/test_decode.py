"""Dev1's unit tests for C3 rule-book decoding (engines/decode.py). No hard-coded step ids: the
plans are synthetic or come from the committed rule book."""

import math

import numpy as np
import pytest
from scrubgpt_brain.engines import decode as d
from scrubgpt_brain.engines.rulebook import load_knowledge

WINDOW_S = 60.0


def plan_of(p50s: list[float], *, free: set[int] | None = None) -> d.DecodePlan:
    """A synthetic plan: steps s0, s1, … with these typical durations (p25 = p50/2, p75 = 2·p50)."""
    states = tuple(
        d.State(f"s{i}", p50, d._sigma(p50 / 2, p50 * 2), i in (free or set()))
        for i, p50 in enumerate(p50s)
    )
    return d.DecodePlan(states, tuple(range(len(states))), tuple(s.step_id for s in states))


def windows_of(n: int) -> list[tuple[float, float]]:
    return [(i * WINDOW_S, (i + 1) * WINDOW_S) for i in range(n)]


def confident(labels: list[int], n_steps: int, p: float = 0.9) -> np.ndarray:
    probs = np.full((len(labels), n_steps), (1 - p) / (n_steps - 1))
    probs[np.arange(len(labels)), labels] = p
    return probs


def test_clean_evidence_decodes_in_order_and_covers_the_range():
    plan = plan_of([180, 240, 180, 300])
    labels = [0] * 3 + [1] * 4 + [2] * 3 + [3] * 5
    segments = d.decode(windows_of(len(labels)), confident(labels, 4), plan)
    assert [s.step_id for s in segments] == ["s0", "s1", "s2", "s3"]
    assert segments[0].t_start == 0.0 and segments[-1].t_end == len(labels) * WINDOW_S
    for before, after in zip(segments, segments[1:], strict=False):
        assert before.t_end == after.t_start  # contiguous, no gaps or overlaps
    assert all(isinstance(s.t_start, float) and s.t_start < s.t_end for s in segments)
    assert [s.n_windows for s in segments] == [3, 4, 3, 5]


def test_an_out_of_order_spike_does_not_jump_backward():
    plan = plan_of([240] * 5)
    labels = [0] * 4 + [1] * 4 + [2] * 4 + [3] * 4 + [4] * 4
    probs = confident(labels, 5)
    probs[13] = confident([0], 5, p=0.97)[0]  # step 0 spikes inside step 3
    probs[5] = confident([4], 5, p=0.97)[0]  # and step 4 spikes inside step 1
    order = [s.step_id for s in d.decode(windows_of(len(labels)), probs, plan)]
    assert order == ["s0", "s1", "s2", "s3", "s4"]


def test_skips_cost_unless_the_step_is_optional():
    labels = [0] * 4 + [2] * 4  # step 1 never shows, and the evidence is clear about it
    probs = confident(labels, 3, p=0.98)
    required = d.decode(windows_of(8), probs, plan_of([240] * 3))
    optional = d.decode(windows_of(8), probs, plan_of([240] * 3, free={1}))
    assert [s.step_id for s in required] == [s.step_id for s in optional] == ["s0", "s2"]
    # A huge skip penalty makes the decoder keep a required step instead of skipping it.
    kept = d.decode(windows_of(8), probs, plan_of([240] * 3), skip_penalty=-1e6)
    assert "s1" in [s.step_id for s in kept]


def test_duration_priors_pull_weak_evidence_and_lose_to_strong_evidence():
    # Steps s1 and s2 sit in the middle (fully observed: the first and last segments may be cut
    # off by the recording, so their priors are deliberately weak). Their 12 windows are
    # ambiguous between them.
    ambiguous = np.vstack(
        [confident([0, 0], 4), np.tile([0.02, 0.48, 0.48, 0.02], (12, 1)), confident([3, 3], 4)]
    )
    ambiguous[2] = [0.02, 0.9, 0.06, 0.02]  # s1 starts here
    ambiguous[13] = [0.02, 0.06, 0.9, 0.02]  # s2 ends here

    def middle(p50s: list[float], probs: np.ndarray, **kw) -> list[int]:
        segments = d.decode(windows_of(len(probs)), probs, plan_of(p50s), **kw)
        return [s.n_windows for s in segments if s.step_id in ("s1", "s2")]

    short_long = middle([120, 180, 540, 120], ambiguous)
    long_short = middle([120, 540, 180, 120], ambiguous)
    assert sum(short_long) == sum(long_short) == 12
    assert short_long[0] < short_long[1] and long_short[0] > long_short[1]  # the priors decide
    # Strong evidence for a 9 / 3 split wins against priors that want 3 / 9.
    strong = confident([0, 0] + [1] * 9 + [2] * 3 + [3, 3], 4, p=0.99)
    assert middle([120, 180, 540, 120], strong) == [9, 3]
    # Without priors (edited video) the ambiguous middle is left to the evidence alone.
    assert sum(middle([120, 180, 540, 120], ambiguous, use_durations=False)) == 12


def test_the_real_rule_book_plan_and_its_movable_phase():
    book = load_knowledge().rulebook
    plan = d.plan_from_rulebook(book)
    assert set(plan.step_ids) == {s.id for s in book.steps()}
    movable = book.order_rules.movable_phases[0].phase
    movable_steps = [s.id for s in book.phase(movable).steps]
    copies = [i for i, s in enumerate(plan.states) if s.step_id in movable_steps]
    assert len(copies) == 2 * len(movable_steps) and all(plan.states[i].free_skip for i in copies)
    # Evidence: the late copy of the movable phase, after the phase it may follow last.
    late_after = book.phase(book.order_rules.movable_phases[0].may_follow[-1]).steps[-1].id
    a, b = plan.step_ids.index(late_after), plan.step_ids.index(movable_steps[0])
    labels = [a] * 5 + [b] * 5
    segments = d.decode(windows_of(10), confident(labels, len(plan.step_ids)), plan)
    assert [s.step_id for s in segments] == [late_after, movable_steps[0]]


@pytest.mark.parametrize(
    ("windows", "probs", "message"),
    [
        ([], np.zeros((0, 3)), "no windows"),
        (windows_of(2), np.ones((2, 2)), "rows × 3 steps"),
        (windows_of(2), np.array([[0.5, -0.1, 0.6]] * 2), "non-negative"),
        (windows_of(2), np.array([[math.nan, 0.5, 0.5]] * 2), "finite"),
        ([(60.0, 120.0), (0.0, 60.0)], np.ones((2, 3)), "strictly increasing"),
        ([(0.0, 0.0), (60.0, 120.0)], np.ones((2, 3)), "t_start < t_end"),
    ],
)
def test_bad_input_raises(windows, probs, message):
    with pytest.raises(ValueError, match=message):
        d.decode(windows, probs, plan_of([60, 60, 60]))


def test_rows_are_normalised_and_zero_rows_mean_no_information():
    plan = plan_of([120, 120])
    scaled = confident([0, 0, 1, 1], 2) * 7.5  # rows summing to 7.5
    assert [s.step_id for s in d.decode(windows_of(4), scaled, plan)] == ["s0", "s1"]
    with_blank = confident([0, 0, 1, 1], 2)
    with_blank[1] = 0.0
    segments = d.decode(windows_of(4), with_blank, plan)
    assert segments[-1].t_end == 240.0 and segments[0].confidence <= 0.9
