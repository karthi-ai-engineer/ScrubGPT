import { describe, expect, it } from "vitest";

import { formatRange, formatTime } from "./format";

describe("formatTime", () => {
  it.each([
    [0, "0:00"],
    [5, "0:05"],
    [59.9, "0:59"],
    [60, "1:00"],
    [300, "5:00"],
    [3599, "59:59"],
    [3600, "1:00:00"],
    [3725.4, "1:02:05"],
    [36000, "10:00:00"],
  ])("formats %s s as %s", (seconds, expected) => {
    expect(formatTime(seconds)).toBe(expected);
  });

  it.each([-3, Number.NaN, Number.POSITIVE_INFINITY])("shows %s as 0:00", (seconds) => {
    expect(formatTime(seconds)).toBe("0:00");
  });
});

describe("formatRange", () => {
  it("joins start and end with an en dash", () => {
    expect(formatRange(58, 78)).toBe("0:58–1:18");
  });
});
