import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DecisionRecord, ProcedureReference } from "@contracts/contracts";

import type { StoredRecord } from "@/api/types";
import { CASE, confirmedRecord, draftFor } from "@/test/answerFixtures";
import { FakeEventSource } from "@/test/fakes";
import { fixtureDetail, mockFetch } from "@/test/fixtures";
import { renderApp } from "@/test/render";

import referenceJson from "../../../../../contracts/fixtures/reference/rarp.json";

const reference = referenceJson as ProcedureReference;
const seeds = fixtureDetail.seed_records.records;
const stored = (record: DecisionRecord, source: "seed" | "answer" = "seed"): StoredRecord => ({
  record,
  source,
  answer_id: null,
  stored_at: "2026-10-18T09:00:00Z",
});

/** A confirmed answer to m01.q1: a second operating-surgeon viewpoint on m01, next to the seed one. */
const answer = confirmedRecord(
  {
    ...draftFor("case-fixture-01.m01.q1", { trust: "operating_surgeon" }),
    action: { type: "act", text: { ja: "新しい回答の対応", en: "The new answer's action" }, actor: "surgeon" },
  },
  "01a1436a-aaaa-7000-8000-00000000000a",
  "Dr Live",
);

function serve(records: StoredRecord[] | null) {
  return mockFetch((url) => {
    if (url === `/api/cases/${CASE}`) return { status: 200, body: fixtureDetail };
    if (url === "/api/references/rarp") return { status: 200, body: reference };
    if (url === `/api/cases/${CASE}/records` && records) return { status: 200, body: { records } };
    return undefined;
  });
}

async function openAt(t: number) {
  const view = renderApp(`/cases/${CASE}/control-room`);
  await screen.findByRole("heading", { level: 1, name: "Control Room" });
  const video = view.container.querySelector("video");
  if (!video) throw new Error("no video");
  Object.defineProperty(video, "duration", { configurable: true, value: 300 });
  fireEvent.loadedMetadata(video);
  await waitFor(() => expect(screen.getByTestId("current-step")).toHaveTextContent("Bladder drop"));
  act(() => {
    video.currentTime = t;
    video.dispatchEvent(new Event("timeupdate"));
  });
}

const counts = () => screen.getByTestId("graph-counts").textContent;
const recordItems = () =>
  [...document.querySelectorAll<HTMLElement>('[data-node-kind="record"]')].map((el) => el.getAttribute("data-node-id"));

beforeEach(() => {
  FakeEventSource.install();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Control Room: the graph grows with confirmed answers (D-071)", () => {
  it("draws the stored records (seed + answers) from GET /records, one node each", async () => {
    serve([...seeds.map((r) => stored(r)), stored(answer, "answer")]);
    await openAt(60);
    await waitFor(() => expect(counts()).toBe("Steps 3 · Moments 1 · Records 3"));
    const q1Seed = seeds.find((r) => r.question_id === "case-fixture-01.m01.q1");
    expect(recordItems()).toEqual(expect.arrayContaining([`record:${q1Seed?.id}`, `record:${answer.id}`]));
  });

  it("falls back to the package's seed records when the store can't be read", async () => {
    serve(null); // GET /records → 404
    await openAt(60);
    expect(counts()).toBe("Steps 3 · Moments 1 · Records 2");
  });

  it("adds a record.created as its own node, live; two records on one moment stay two nodes", async () => {
    serve(seeds.map((r) => stored(r)));
    await openAt(60);
    await waitFor(() => expect(counts()).toBe("Steps 3 · Moments 1 · Records 2"));

    // Every subscriber (case.ended, record.created) shares one EventSource on /api/events.
    const live = FakeEventSource.live();
    expect(live).toHaveLength(1);
    const source = live[0] as FakeEventSource;
    expect(source.url).toBe("/api/events");
    expect(source.listenerCount("record.created")).toBe(1);
    expect(source.listenerCount("case.ended")).toBe(1);

    act(() => source.emit("record.created", { record: answer }));
    expect(counts()).toBe("Steps 3 · Moments 1 · Records 3");
    const node = document.querySelector<HTMLElement>(`[data-node-id="record:${answer.id}"]`);
    expect(node).toHaveTextContent("The new answer's action");
    expect(node).toHaveTextContent("Operating surgeon"); // its trust label 🩺
    expect(node).toHaveTextContent("Operating surgeon's account (.qN)");
    const q1Seed = seeds.find((r) => r.question_id === "case-fixture-01.m01.q1");
    expect(document.querySelector(`[data-node-id="record:${q1Seed?.id}"]`)).not.toBeNull();

    // The same record again, another case's record, or a malformed payload add nothing.
    act(() => source.emit("record.created", { record: answer }));
    act(() => source.emit("record.created", { record: { ...answer, id: "other", case_id: "other-case" } }));
    act(() => source.emit("record.created", { record: { id: "x" } }));
    act(() => source.emit("record.created", "{not json"));
    expect(counts()).toBe("Steps 3 · Moments 1 · Records 3");
  });

  it("a record on a moment the replay hasn't reached shows once the moment is revealed", async () => {
    serve(seeds.map((r) => stored(r)));
    await openAt(0);
    const source = FakeEventSource.live()[0] as FakeEventSource;
    act(() => source.emit("record.created", { record: answer }));
    expect(counts()).toBe("Steps 1 · Moments 0 · Records 0");
    const video = document.querySelector("video") as HTMLVideoElement;
    act(() => {
      video.currentTime = 60;
      video.dispatchEvent(new Event("timeupdate"));
    });
    expect(counts()).toBe("Steps 3 · Moments 1 · Records 3");
  });
});
