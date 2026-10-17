"""C3 Rule-book decoding (plan §2.3, §8.1): noisy per-window step guesses → clean step segments.

C2 will have GPT look at each 1-minute window of frames and give a probability for every
rule-book step. Those guesses flicker: one window says "DVC ligation", the next "bladder neck",
the next "DVC ligation" again. Real surgery doesn't jump like that. This decoder finds the single
most likely sequence of steps for the whole video (a segmental Viterbi, i.e. a hidden semi-Markov
model), scoring three things:

- **Evidence:** how well each window fits the step it's assigned to (the log of its probability).
- **Order** (from the rule book's `order_rules`): see *Allowed transitions* below.
- **Duration:** how plausible each segment's length is for its step, from the rule book's
  typical durations (p25/p50/p75 → a log-normal prior). The first and the last segment may be cut
  off by the start or end of the recording, so they are scored as "lasts at least this long". For
  edited videos (`video_type: edited`) the durations mean nothing, so `use_durations=False`
  switches this term off.

**Allowed transitions** (a segment is followed by a later state in the expanded rule-book order):
- to the next step: free;
- skipping steps forward: each skipped step of a required phase costs `skip_penalty`, steps of an
  optional phase (`order_rules.optional_phases`) are skipped free. A required step can be
  skipped, at a price, so E2 can still report a "missing step". When the evidence against a
  required step is only moderate, a one-window "phantom" of it can cost about as much as the skip,
  so E2 should read a required step of one window as possibly skipped;
- a movable phase (`order_rules.movable_phases`, e.g. lymph node dissection after the prostate is
  freed) appears at each place it `may_follow`, and every copy is optional;
- **never backward**: the rule book's `default: sequential` allows no return to an earlier
  step. (Rule-book changes, e.g. interleaving phases after the urologist review, would come in
  through `order_rules`.)
- The recording may start and end at any step, free: videos often begin after docking or stop
  before closure.

**Input rows are normalised**: each row is divided by its sum (a row of zeros counts as "no
information", i.e. uniform). Negative values, NaN or infinity, a wrong number of columns, zero
windows, or window times that aren't strictly increasing raise `ValueError`.

**Output:** contiguous segments in float seconds that cover the first window's start to the last
window's end, with no gaps or overlaps. Boundaries fall on window starts; a gap between two windows
belongs to the segment before it. These are internal results: after `contracts-v1.0` they are
mapped onto the timeline's step segments.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from scrubgpt_brain.engines.rulebook import RuleBook

SKIP_PENALTY = math.log(0.02)
"""Log-cost of skipping one step of a required phase (≈ "2 % of videos really skip it")."""
EVIDENCE_FLOOR = 1e-4
"""Probabilities are floored here before taking logs, so one confident "0" can't veto a step."""
MIN_SIGMA = 0.15
"""Smallest log-normal spread, so a step with p25 ≈ p75 still allows some variation."""
_Z75 = 0.6744897501960817
"""The 75th percentile of the standard normal."""


@dataclass(frozen=True)
class State:
    """One step as the decoder sees it."""

    step_id: str
    p50_s: float
    sigma: float
    """Spread of log(duration)."""
    free_skip: bool
    """Skipping it costs nothing (optional or movable phase)."""


@dataclass(frozen=True)
class DecodePlan:
    """The states in expanded rule-book order, and which column of the probabilities each uses."""

    states: tuple[State, ...]
    columns: tuple[int, ...]
    """For each state, its column in the probability matrix (a movable step appears twice)."""
    step_ids: tuple[str, ...]
    """The probability matrix's columns: the rule-book steps, in order."""


@dataclass(frozen=True)
class Segment:
    """A decoded step segment."""

    step_id: str
    t_start: float
    t_end: float
    confidence: float
    """Mean normalised probability of this step over its windows."""
    n_windows: int


def _sigma(p25: float, p75: float) -> float:
    return max(MIN_SIGMA, (math.log(p75) - math.log(p25)) / (2 * _Z75))


def plan_from_rulebook(rulebook: RuleBook) -> DecodePlan:
    """The decoding plan for a rule book: its steps in order, a movable phase also at each later
    place it may follow, optional phases free to skip."""
    steps = rulebook.steps()
    step_ids = tuple(step.id for step in steps)
    column = {step_id: i for i, step_id in enumerate(step_ids)}
    rules = rulebook.order_rules
    optional = set(rules.optional_phases) | {p.id for p in rulebook.phases if p.optional}
    movable = {m.phase: m.may_follow for m in rules.movable_phases}

    def states_of(phase_id: str, *, free: bool) -> list[tuple[State, int]]:
        phase = rulebook.phase(phase_id)
        return [
            (
                State(
                    step_id=step.id,
                    p50_s=step.duration.p50,
                    sigma=_sigma(step.duration.p25, step.duration.p75),
                    free_skip=free,
                ),
                column[step.id],
            )
            for step in phase.steps
        ]

    expanded: list[tuple[State, int]] = []
    for phase in rulebook.phases:
        if phase.id in movable:
            continue  # placed after each phase it may follow, below
        expanded += states_of(phase.id, free=phase.id in optional)
        for moved, follows in movable.items():
            if phase.id in follows:
                expanded += states_of(moved, free=True)
    return DecodePlan(
        states=tuple(state for state, _ in expanded),
        columns=tuple(col for _, col in expanded),
        step_ids=step_ids,
    )


def _log_duration(state: State, seconds: float, *, truncated: bool) -> float:
    """How plausible a segment of this length is for the step, as a log score ≤ 0.

    The step's durations are log-normal (from p25/p50/p75), so log(duration) is normal with mean
    log(p50). A fully observed segment scores `-z²/2`, with z its distance from the median in
    spreads, on the log scale: 0 at the median, growing for unusually short or long segments. A
    density in seconds would instead charge every extra segment a constant (its unit is "per
    second"), and the decoder would prefer fewer, longer segments against the evidence. A
    segment that may be cut off by the start or end of the recording scores the log of the chance
    that the step lasts at least this long.
    """
    if seconds <= 0:
        return -math.inf
    z = (math.log(seconds) - math.log(state.p50_s)) / state.sigma
    if truncated:
        return math.log(max(0.5 * math.erfc(z / math.sqrt(2)), 1e-300))
    return -0.5 * z * z


def _validated(
    windows: Sequence[tuple[float, float]], probabilities: Sequence[Sequence[float]], n_steps: int
) -> tuple[np.ndarray, np.ndarray]:
    if len(windows) == 0:
        raise ValueError("no windows to decode")
    times = np.asarray(windows, dtype=float)
    if times.ndim != 2 or times.shape[1] != 2:
        raise ValueError("windows must be (t_start, t_end) pairs")
    if not np.all(np.isfinite(times)) or np.any(times[:, 1] <= times[:, 0]):
        raise ValueError("every window needs finite times with t_start < t_end")
    if np.any(np.diff(times[:, 0]) <= 0) or np.any(times[1:, 0] < times[:-1, 1]):
        raise ValueError("windows must be strictly increasing and must not overlap")
    probs = np.asarray(probabilities, dtype=float)
    if probs.ndim != 2 or probs.shape != (len(times), n_steps):
        raise ValueError(
            f"probabilities must be {len(times)} rows × {n_steps} steps, not {probs.shape}"
        )
    if not np.all(np.isfinite(probs)) or np.any(probs < 0):
        raise ValueError("probabilities must be finite and non-negative")
    sums = probs.sum(axis=1, keepdims=True)
    probs = np.where(sums > 0, probs / np.where(sums > 0, sums, 1), 1.0 / n_steps)
    return times, probs


def decode(
    windows: Sequence[tuple[float, float]],
    probabilities: Sequence[Sequence[float]],
    plan: DecodePlan,
    *,
    use_durations: bool = True,
    skip_penalty: float = SKIP_PENALTY,
    duration_weight: float = 1.0,
) -> list[Segment]:
    """Decode per-window step probabilities into ordered step segments.

    `windows[i]` is `(t_start, t_end)` of window i, in seconds; `probabilities[i][k]` is window i's
    probability for `plan.step_ids[k]`. See the module docstring for the rules.
    """
    times, probs = _validated(windows, probabilities, len(plan.step_ids))
    n_windows, n_states = len(times), len(plan.states)
    # Segment boundaries: the start of each window, then the end of the last one.
    bounds = np.append(times[:, 0], times[-1, 1])
    log_p = np.log(np.maximum(probs, EVIDENCE_FLOOR))[:, list(plan.columns)]  # windows × states
    cum = np.vstack([np.zeros(n_states), np.cumsum(log_p, axis=0)])  # (n_windows+1) × states

    # Transition costs between states i → j (j later than i): skipped required steps.
    skip_cost = np.array([0.0 if s.free_skip else skip_penalty for s in plan.states])
    prefix = np.concatenate([[0.0], np.cumsum(skip_cost)])
    trans = np.full((n_states, n_states), -math.inf)
    for i in range(n_states):
        for j in range(i + 1, n_states):
            trans[i, j] = prefix[j] - prefix[i + 1]

    best = np.full((n_windows + 1, n_states), -math.inf)  # best[t, j]: windows [0, t) end in j
    back_start = np.zeros((n_windows + 1, n_states), dtype=int)
    back_prev = np.full((n_windows + 1, n_states), -1, dtype=int)
    entry = np.zeros((n_windows + 1, n_states))  # best score of entering j at boundary u
    entry_prev = np.full((n_windows + 1, n_states), -1, dtype=int)

    for t in range(1, n_windows + 1):
        # Entering states at boundary t-1 (a new segment starting with window t-1).
        u = t - 1
        if u > 0:
            scores = best[u][:, None] + trans  # i × j
            entry_prev[u] = np.argmax(scores, axis=0)
            entry[u] = scores[entry_prev[u], np.arange(n_states)]
        # Score every segment [u, t) for every state, keep the best start.
        starts = np.arange(t)
        lengths = bounds[t] - bounds[starts]
        evidence = cum[t][None, :] - cum[starts]  # starts × states
        totals = entry[starts] + evidence
        if use_durations:
            durations = np.array(
                [
                    [
                        _log_duration(
                            state, float(length), truncated=(start == 0 or t == n_windows)
                        )
                        for state in plan.states
                    ]
                    for start, length in zip(starts, lengths, strict=True)
                ]
            )
            totals = totals + duration_weight * durations
        best_start = np.argmax(totals, axis=0)
        best[t] = totals[best_start, np.arange(n_states)]
        back_start[t] = best_start
        back_prev[t] = [
            entry_prev[best_start[j], j] if best_start[j] > 0 else -1 for j in range(n_states)
        ]

    # Backtrack from the best final state (the recording may end at any step).
    segments: list[Segment] = []
    t, j = n_windows, int(np.argmax(best[n_windows]))
    while t > 0:
        u = int(back_start[t, j])
        column = plan.columns[j]
        segments.append(
            Segment(
                step_id=plan.states[j].step_id,
                t_start=float(bounds[u]),
                t_end=float(bounds[t]),
                confidence=float(np.mean(probs[u:t, column])),
                n_windows=t - u,
            )
        )
        t, j = u, int(back_prev[t, j])
    segments.reverse()
    return segments
