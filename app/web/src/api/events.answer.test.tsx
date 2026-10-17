import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fixtureDetail } from "@/test/fixtures";
import { FakeEventSource } from "@/test/fakes";

import { parseServerEvent, useServerEvent } from "./events";

const record = fixtureDetail.seed_records.records[0];

describe("parseServerEvent: the answer events (app/server README)", () => {
  it("accepts record.created with a stored record", () => {
    expect(parseServerEvent("record.created", JSON.stringify({ record }))).toEqual({ record });
  });

  it.each([
    ["no record", {}],
    ["a record without an id", { record: { ...record, id: 1 } }],
    ["a record without an action text", { record: { ...record, action: { type: "act", text: null, actor: "surgeon" } } }],
    ["a record without a trust label", { record: { ...record, provenance: {} } }],
  ])("rejects record.created with %s", (_name, payload) => {
    expect(parseServerEvent("record.created", JSON.stringify(payload))).toBeNull();
  });

  it("checks answer.confirmed and graph.updated", () => {
    const confirmed = { case_id: "c", question_id: "c.m01.q1", record_id: "r", answer_id: "a" };
    expect(parseServerEvent("answer.confirmed", JSON.stringify(confirmed))).toEqual(confirmed);
    expect(parseServerEvent("answer.confirmed", JSON.stringify({ ...confirmed, record_id: null }))).toBeNull();
    const graph = { case_id: "c", nodes: [{ id: "record:r", kind: "record" }], edges: [] };
    expect(parseServerEvent("graph.updated", JSON.stringify(graph))).toEqual(graph);
    expect(parseServerEvent("graph.updated", JSON.stringify({ case_id: "c" }))).toBeNull();
  });
});

function Listener({ name, onEvent }: { name: "case.ended" | "record.created"; onEvent: (d: unknown) => void }) {
  useServerEvent(name, onEvent);
  return null;
}

describe("useServerEvent: one shared EventSource", () => {
  beforeEach(() => FakeEventSource.install());
  afterEach(() => vi.unstubAllGlobals());

  it("opens one connection for many subscribers and closes it with the last one", () => {
    const a = vi.fn();
    const b = vi.fn();
    const first = render(<Listener name="case.ended" onEvent={a} />);
    const second = render(<Listener name="record.created" onEvent={b} />);
    expect(FakeEventSource.live()).toHaveLength(1);
    const source = FakeEventSource.live()[0] as FakeEventSource;

    act(() => source.emit("record.created", { record }));
    expect(b).toHaveBeenCalledWith({ record });
    expect(a).not.toHaveBeenCalled();

    first.unmount();
    expect(source.closed).toBe(false);
    second.unmount();
    expect(source.closed).toBe(true);
    expect(FakeEventSource.live()).toHaveLength(0);
  });
});
