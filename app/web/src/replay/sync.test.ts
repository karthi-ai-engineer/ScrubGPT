import { describe, expect, it } from "vitest";

import type { StepSegment } from "@contracts/contracts";

import { fixtureDetail } from "@/test/fixtures";

import {
  availableTracks,
  buildReplayIndex,
  currentIndex,
  END_TOLERANCE_S,
  isAtEnd,
  replayStateAt,
  revealedAt,
  revealedCount,
  sameReplayState,
  selectTrack,
  sortByStart,
  type Timed,
} from "./sync";

const span = (t_start: number, t_end: number): Timed => ({ t_start, t_end });
// Contiguous segments with a gap between 30 and 40.
const segments = [span(0, 10), span(10, 30), span(40, 60)];

describe("revealedCount / revealedAt", () => {
  it("reveals an item exactly at its t_start, not just before", () => {
    expect(revealedCount(segments, 9.999)).toBe(1);
    expect(revealedCount(segments, 10)).toBe(2);
    expect(revealedCount(segments, 39.999)).toBe(2);
    expect(revealedCount(segments, 40)).toBe(3);
  });

  it("reveals nothing before the first item and everything after the last", () => {
    expect(revealedCount(segments, -1)).toBe(0);
    expect(revealedCount(segments, 0)).toBe(1);
    expect(revealedCount(segments, 1e6)).toBe(3);
  });

  it("handles empty lists and non-finite times", () => {
    expect(revealedCount([], 50)).toBe(0);
    expect(revealedAt([], 50)).toEqual([]);
    expect(revealedCount(segments, Number.NaN)).toBe(0);
  });

  it("hides items again when time moves backwards (a backwards seek)", () => {
    expect(revealedAt(segments, 45)).toHaveLength(3);
    expect(revealedAt(segments, 12)).toEqual([segments[0], segments[1]]);
    expect(revealedAt(segments, 0)).toEqual([segments[0]]);
  });

  it("matches a linear scan at every boundary (binary search)", () => {
    const items = sortByStart([span(5, 6), span(5, 7), span(1, 2), span(9, 9), span(3, 4)]);
    for (let t = 0; t <= 10; t += 0.5) {
      expect(revealedCount(items, t), `t=${t}`).toBe(items.filter((i) => i.t_start <= t).length);
    }
  });
});

describe("currentIndex", () => {
  it("is the segment with t_start <= t < t_end", () => {
    expect(currentIndex(segments, 0)).toBe(0);
    expect(currentIndex(segments, 9.99)).toBe(0);
    expect(currentIndex(segments, 10)).toBe(1); // a boundary belongs to the next segment
    expect(currentIndex(segments, 45)).toBe(2);
  });

  it("is -1 before the first segment, between segments and from the end of the last", () => {
    expect(currentIndex(segments, -0.1)).toBe(-1);
    expect(currentIndex(segments, 30)).toBe(-1);
    expect(currentIndex(segments, 35)).toBe(-1);
    expect(currentIndex(segments, 60)).toBe(-1);
    expect(currentIndex([], 5)).toBe(-1);
  });

  it("finds an earlier, longer segment that still contains t (overlap)", () => {
    const overlapping = [span(0, 100), span(10, 20)];
    expect(currentIndex(overlapping, 15)).toBe(1);
    expect(currentIndex(overlapping, 50)).toBe(0);
  });
});

describe("sortByStart", () => {
  it("sorts by t_start and keeps file order for equal starts", () => {
    const a = { ...span(5, 6), id: "a" };
    const b = { ...span(1, 2), id: "b" };
    const c = { ...span(5, 9), id: "c" };
    expect(sortByStart([a, b, c]).map((x) => x.id)).toEqual(["b", "a", "c"]);
  });
});

describe("step track selection", () => {
  const steps = fixtureDetail.timeline.steps;
  const only = (track: "ai" | "dataset"): StepSegment[] => steps.filter((s) => s.track === track);

  it("lists the tracks present, ai first", () => {
    expect(availableTracks(steps)).toEqual(["ai", "dataset"]);
    expect(availableTracks(only("dataset"))).toEqual(["dataset"]);
    expect(availableTracks([])).toEqual([]);
  });

  it("uses the case's default_step_track unless the user chose another existing track", () => {
    expect(selectTrack(steps, "ai", null)).toBe("ai");
    expect(selectTrack(steps, "dataset", null)).toBe("dataset");
    expect(selectTrack(steps, "ai", "dataset")).toBe("dataset");
  });

  it("falls back to a track that exists", () => {
    expect(selectTrack(only("dataset"), "ai", null)).toBe("dataset");
    expect(selectTrack(only("ai"), "ai", "dataset")).toBe("ai");
    expect(selectTrack([], "ai", null)).toBeNull();
  });

  it("builds the index from the selected track only, every list sorted by start", () => {
    const ai = buildReplayIndex(fixtureDetail, "ai");
    expect(ai.steps.every((s) => s.track === "ai")).toBe(true);
    expect(ai.steps).toHaveLength(only("ai").length);
    const dataset = buildReplayIndex(fixtureDetail, "dataset");
    expect(dataset.steps.every((s) => s.track === "dataset")).toBe(true);
    for (const list of [ai.steps, ai.events, ai.utterances, ai.moments]) {
      const starts = list.map((x) => x.t_start);
      expect(starts).toEqual([...starts].sort((x, y) => x - y));
    }
    // moments.json is in rank order, not time order: m05 (148 s) comes after m04 (195 s) in the file.
    expect(ai.moments.map((m) => m.id.split(".").pop())).toEqual(["m01", "m02", "m03", "m05", "m04", "m06"]);
  });
});

describe("replayStateAt", () => {
  const index = buildReplayIndex(fixtureDetail, "ai");

  it("counts what the fixture reveals at 60 s", () => {
    // ai steps at 0, 25, 50; events at 58; utterances at 5, 52, 60; moment m01 at 58.
    expect(replayStateAt(index, 60)).toEqual({ steps: 3, events: 1, utterances: 3, moments: 1, currentStep: 2 });
  });

  it("is empty-ish at 0 and complete at the end", () => {
    expect(replayStateAt(index, 0)).toEqual({ steps: 1, events: 0, utterances: 0, moments: 0, currentStep: 0 });
    const end = replayStateAt(index, fixtureDetail.case.duration_s);
    expect(end.moments).toBe(fixtureDetail.moments.moments.length);
    expect(end.utterances).toBe(fixtureDetail.timeline.utterances.length);
    expect(end.currentStep).toBe(-1); // the last segment ends at the duration (t < t_end)
  });

  it("only changes at reveal boundaries (so React state changes rarely)", () => {
    expect(sameReplayState(replayStateAt(index, 61), replayStateAt(index, 61.9))).toBe(true);
    expect(sameReplayState(replayStateAt(index, 65.9), replayStateAt(index, 66))).toBe(false); // u0004 at 66
  });
});

describe("isAtEnd", () => {
  it(`counts the last ${END_TOLERANCE_S} s as the end`, () => {
    expect(isAtEnd(299.74, 300)).toBe(false);
    expect(isAtEnd(299.75, 300)).toBe(true);
    expect(isAtEnd(300, 300)).toBe(true);
  });

  it("never ends without a known duration", () => {
    expect(isAtEnd(1000, null)).toBe(false);
    expect(isAtEnd(1000, Number.NaN)).toBe(false);
    expect(isAtEnd(0, 0)).toBe(false);
  });
});
