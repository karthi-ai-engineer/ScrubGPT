/**
 * The replay sync engine (plan §8.2): pure functions over timeline items sorted by `t_start`.
 *
 * The `<video>` element is the master clock (app/web CLAUDE.md rule 4): an item is revealed when
 * `t >= item.t_start`, so speed changes and seeking (also backwards) can never desync the view.
 * Nothing here knows about React or the DOM.
 */
import type { Moment, StepSegment, StepTrack, TimelineEvent, Utterance } from "@contracts/contracts";

import type { CaseDetail } from "@/api/types";

/** Anything on the video's timeline. */
export interface Timed {
  t_start: number;
  t_end: number;
}

/** A copy of `items` sorted by `t_start` (stable: equal starts keep their file order). */
export function sortByStart<T extends Timed>(items: readonly T[]): T[] {
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => a.item.t_start - b.item.t_start || a.index - b.index)
    .map(({ item }) => item);
}

/**
 * How many of the `sorted` items are revealed at time `t`: the number with `t_start <= t`
 * (binary search, O(log n)). A non-finite `t` reveals nothing.
 */
export function revealedCount(sorted: readonly Timed[], t: number): number {
  if (!Number.isFinite(t)) return 0;
  let lo = 0;
  let hi = sorted.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if ((sorted[mid] as Timed).t_start <= t) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** The revealed prefix of `sorted` at time `t`. */
export function revealedAt<T extends Timed>(sorted: readonly T[], t: number): T[] {
  return sorted.slice(0, revealedCount(sorted, t));
}

/**
 * The index of the segment that contains `t` (`t_start <= t < t_end`), or -1 between segments,
 * before the first and from the end of the last. For overlapping segments the latest-starting
 * one that still contains `t` wins.
 */
export function currentIndex(sorted: readonly Timed[], t: number): number {
  // Every candidate starts at or before `t`; walk back from the latest start (a track has a few
  // dozen segments, so the linear tail is cheap even at 60 frames a second).
  for (let i = revealedCount(sorted, t) - 1; i >= 0; i--) {
    if (t < (sorted[i] as Timed).t_end) return i;
  }
  return -1;
}

/** The step tracks present in a timeline, in a fixed order (`ai`, then `dataset`). */
export function availableTracks(steps: readonly StepSegment[]): StepTrack[] {
  const order: StepTrack[] = ["ai", "dataset"];
  return order.filter((track) => steps.some((s) => s.track === track));
}

/**
 * The step track to show: the user's choice when that track exists, else the case's
 * `default_step_track` when it exists, else the first track present; `null` without steps.
 */
export function selectTrack(
  steps: readonly StepSegment[],
  defaultTrack: StepTrack,
  chosen: StepTrack | null,
): StepTrack | null {
  const tracks = availableTracks(steps);
  if (chosen && tracks.includes(chosen)) return chosen;
  if (tracks.includes(defaultTrack)) return defaultTrack;
  return tracks[0] ?? null;
}

/** Everything the Control Room reveals, each list sorted by `t_start`. */
export interface ReplayIndex {
  track: StepTrack | null;
  steps: StepSegment[];
  events: TimelineEvent[];
  utterances: Utterance[];
  moments: Moment[];
}

export function buildReplayIndex(detail: CaseDetail, track: StepTrack | null): ReplayIndex {
  return {
    track,
    steps: sortByStart(detail.timeline.steps.filter((s) => s.track === track)),
    events: sortByStart(detail.timeline.events),
    utterances: sortByStart(detail.timeline.utterances),
    moments: sortByStart(detail.moments.moments),
  };
}

/**
 * What is revealed at one instant, as counts of each sorted list plus the current step. Small
 * and comparable, so the UI re-renders only when it changes (not on every animation frame).
 */
export interface ReplayState {
  steps: number;
  events: number;
  utterances: number;
  moments: number;
  /** Index into `ReplayIndex.steps`, or -1. */
  currentStep: number;
}

export const EMPTY_REPLAY_STATE: ReplayState = { steps: 0, events: 0, utterances: 0, moments: 0, currentStep: -1 };

export function replayStateAt(index: ReplayIndex, t: number): ReplayState {
  return {
    steps: revealedCount(index.steps, t),
    events: revealedCount(index.events, t),
    utterances: revealedCount(index.utterances, t),
    moments: revealedCount(index.moments, t),
    currentStep: currentIndex(index.steps, t),
  };
}

export function sameReplayState(a: ReplayState, b: ReplayState): boolean {
  return (
    a.steps === b.steps &&
    a.events === b.events &&
    a.utterances === b.utterances &&
    a.moments === b.moments &&
    a.currentStep === b.currentStep
  );
}

/** Seconds before the end at which a replay counts as finished (8–16× can skip the last frames). */
export const END_TOLERANCE_S = 0.25;

/** Whether `t` is at the end of a video of `duration` seconds (an unknown duration never is). */
export function isAtEnd(t: number, duration: number | null): boolean {
  return duration !== null && Number.isFinite(duration) && duration > 0 && t >= duration - END_TOLERANCE_S;
}
