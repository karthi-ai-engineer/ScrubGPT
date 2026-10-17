import { describe, expect, it } from "vitest";

import { mockFetch } from "@/test/fixtures";

import { api } from "./client";
import { parseServerEvent } from "./events";

const payload = { case_id: "case-fixture-01", questions: { operating: 8, reviewer: 4 }, est_seconds: 131 };

describe("parseServerEvent", () => {
  it("accepts a well-formed case.ended payload", () => {
    expect(parseServerEvent("case.ended", JSON.stringify(payload))).toEqual(payload);
  });

  it.each([
    ["not JSON", "{oops"],
    ["no case id", JSON.stringify({ ...payload, case_id: 1 })],
    ["no counts", JSON.stringify({ case_id: "x", est_seconds: 1 })],
    ["a negative count", JSON.stringify({ ...payload, questions: { operating: -1, reviewer: 0 } })],
    ["a fractional count", JSON.stringify({ ...payload, questions: { operating: 1.5, reviewer: 0 } })],
    ["no estimate", JSON.stringify({ ...payload, est_seconds: "131" })],
    ["null", "null"],
  ])("rejects %s (the UI never shows a made-up number)", (_name, raw) => {
    expect(parseServerEvent("case.ended", raw)).toBeNull();
  });
});

describe("api.replayEnded", () => {
  it("POSTs to the case's replay-ended path and returns the payload", async () => {
    const spy = mockFetch((url) => (url === "/api/cases/case-fixture-01/replay-ended" ? { status: 200, body: payload } : undefined));
    await expect(api.replayEnded("case-fixture-01")).resolves.toEqual(payload);
    expect(spy).toHaveBeenCalledWith(
      "/api/cases/case-fixture-01/replay-ended",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
