import { describe, expect, it, vi } from "vitest";

import { fixtureSummary, mockFetch } from "@/test/fixtures";

import { api, ApiRequestError } from "./client";

async function caught(promise: Promise<unknown>): Promise<ApiRequestError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiRequestError) return error;
    throw error;
  }
  throw new Error("expected the call to fail");
}

describe("api client", () => {
  it("returns the parsed JSON body", async () => {
    mockFetch((url) => (url === "/api/cases" ? { status: 200, body: { cases: [fixtureSummary] } } : undefined));
    await expect(api.cases()).resolves.toEqual({ cases: [fixtureSummary] });
  });

  it("encodes the case id in the path", async () => {
    const spy = mockFetch(() => ({ status: 200, body: {} }));
    await api.case("a b/c");
    expect(spy).toHaveBeenCalledWith("/api/cases/a%20b%2Fc", expect.anything());
  });

  it("throws the ApiError code, message and retryable flag", async () => {
    mockFetch(() => undefined); // → 404 not_found ApiError
    const error = await caught(api.case("nope"));
    expect(error.code).toBe("not_found");
    expect(error.status).toBe(404);
    expect(error.retryable).toBe(false);
  });

  it("reports an unreachable server as `network`", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const error = await caught(api.cases());
    expect(error.code).toBe("network");
    expect(error.retryable).toBe(true);
  });

  it("reports a proxy 502 without an ApiError body as `network`", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 502 }));
    expect((await caught(api.cases())).code).toBe("network");
  });

  it("reports any other non-ApiError failure as `http`", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("<html>", { status: 500 }));
    expect((await caught(api.cases())).code).toBe("http");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("not json", { status: 200 }));
    expect((await caught(api.cases())).code).toBe("http");
  });
});
