import { act, render, screen, within } from "@testing-library/react";
import cytoscape from "cytoscape";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ProcedureReference } from "@contracts/contracts";

import { buildReplayIndex, replayStateAt } from "@/replay/sync";
import { fixtureDetail } from "@/test/fixtures";

import referenceJson from "../../../../contracts/fixtures/reference/rarp.json";

import { buildGraphElements } from "./buildGraphElements";
import { canvasSupported } from "./canvas";
import { GraphPanel } from "./GraphPanel";

// Cytoscape needs a real canvas; jsdom has none. Only the pure builder and the glue are tested.
vi.mock("cytoscape", () => ({ default: vi.fn() }));
vi.mock("./canvas", () => ({ canvasSupported: vi.fn(() => true) }));

interface FakeElement {
  group: "nodes" | "edges";
  data: Record<string, unknown>;
  position: { x: number; y: number };
}

/** Just enough of `cytoscape.Core` for `syncGraph`, the tap handler and teardown. */
function createFakeCy() {
  const els = new Map<string, FakeElement>();
  type Handler = (e: { target: unknown }) => void;
  const taps: { event: string; selector: string | null; handler: Handler }[] = [];
  const handle = (id: string) => ({
    id: () => id,
    nonempty: () => els.has(id),
    empty: () => !els.has(id),
    inside: () => els.has(id),
    isNode: () => els.get(id)?.group === "nodes",
    remove: () => els.delete(id),
    position: () => els.get(id)?.position ?? { x: 0, y: 0 },
    data: (d: Record<string, unknown>) => Object.assign(els.get(id)?.data ?? {}, d),
  });
  const run = vi.fn();
  const cy = {
    els,
    taps,
    run,
    batch: (fn: () => void) => fn(),
    elements: () => ({ forEach: (cb: (el: ReturnType<typeof handle>) => void) => [...els.keys()].forEach((id) => cb(handle(id))) }),
    getElementById: handle,
    add: (def: { group: "nodes" | "edges"; data: Record<string, unknown>; position?: { x: number; y: number } }) => {
      els.set(String(def.data.id), { group: def.group, data: { ...def.data }, position: def.position ?? { x: 0, y: 0 } });
    },
    layout: vi.fn<(options: unknown) => { run: typeof run }>(() => ({ run })),
    on: (event: string, selectorOrHandler: string | Handler, handler?: Handler) =>
      typeof selectorOrHandler === "string"
        ? taps.push({ event, selector: selectorOrHandler, handler: handler as Handler })
        : taps.push({ event, selector: null, handler: selectorOrHandler }),
    destroy: vi.fn(),
  };
  return cy;
}

const reference = referenceJson as ProcedureReference;
function graphAt(t: number, lang: "ja" | "en" = "en") {
  const index = buildReplayIndex(fixtureDetail, "ai");
  const s = replayStateAt(index, t);
  return buildGraphElements(fixtureDetail, reference, { steps: index.steps.slice(0, s.steps), moments: index.moments.slice(0, s.moments) }, lang);
}

let fake: ReturnType<typeof createFakeCy>;
beforeEach(() => {
  fake = createFakeCy();
  vi.mocked(cytoscape).mockImplementation(() => fake as unknown as cytoscape.Core);
  vi.mocked(canvasSupported).mockReturnValue(true);
});

const nodeCount = () => [...fake.els.values()].filter((e) => e.group === "nodes").length;

describe("GraphPanel", () => {
  it("mounts Cytoscape on its container with the built elements and lays them out once", () => {
    const elements = graphAt(60);
    render(<GraphPanel elements={elements} onSeek={vi.fn()} />);
    expect(cytoscape).toHaveBeenCalledTimes(1);
    // `cytoscape()` is overloaded; the panel uses the options form.
    const options = vi.mocked(cytoscape).mock.calls[0]?.[0] as unknown as cytoscape.CytoscapeOptions | undefined;
    expect(options?.container).toBe(screen.getByTestId("graph-canvas"));
    expect(nodeCount()).toBe(elements.nodes.length);
    expect(fake.els.size).toBe(elements.nodes.length + elements.edges.length);
    expect(fake.run).toHaveBeenCalledTimes(1);
  });

  it("re-lays out only when the node set changes; a language switch keeps positions", () => {
    const { rerender } = render(<GraphPanel elements={graphAt(60)} onSeek={vi.fn()} />);
    rerender(<GraphPanel elements={graphAt(60, "ja")} onSeek={vi.fn()} />);
    expect(fake.run).toHaveBeenCalledTimes(1);
    expect(fake.els.get("case:case-fixture-01")?.data.label).toBe(fixtureDetail.case.title.ja);

    rerender(<GraphPanel elements={graphAt(200, "ja")} onSeek={vi.fn()} />);
    expect(fake.run).toHaveBeenCalledTimes(2);

    // Seeking back removes nodes and closes the gaps in the tree.
    const earlier = graphAt(10, "ja");
    rerender(<GraphPanel elements={earlier} onSeek={vi.fn()} />);
    expect(nodeCount()).toBe(earlier.nodes.length);
    expect(fake.run).toHaveBeenCalledTimes(3);
  });

  it("uses the preset tree positions, fitted to the panel, without animation", () => {
    render(<GraphPanel elements={graphAt(60)} onSeek={vi.fn()} />);
    const options = fake.layout.mock.calls[0]?.[0] as { name: string; positions: Record<string, unknown>; fit: boolean; animate: boolean };
    expect(options).toMatchObject({ name: "preset", fit: true, animate: false });
    expect(Object.keys(options.positions).sort()).toEqual(graphAt(60).nodes.map((n) => n.id).sort());
  });

  it("seeks to a moment's start when its node is tapped", () => {
    const onSeek = vi.fn();
    render(<GraphPanel elements={graphAt(60)} onSeek={onSeek} />);
    const tap = fake.taps.find((h) => h.event === "tap" && h.selector?.includes("moment"));
    tap?.handler({ target: { data: (key: string) => (key === "tStart" ? 58 : undefined) } });
    expect(onSeek).toHaveBeenCalledWith(58);
  });

  it("shows a node's full text and trust label on hover or tap (records draw only emoji)", () => {
    const elements = graphAt(60);
    render(<GraphPanel elements={elements} onSeek={vi.fn()} />);
    const detail = screen.getByTestId("graph-detail");
    expect(detail).toHaveTextContent("Hover or tap a node to see its full text.");

    const record = elements.nodes.find((n) => n.kind === "record" && n.viewpoint === "reviewer");
    if (!record) throw new Error("no reviewer record");
    const focus = fake.taps.find((h) => h.event === "tap mouseover" && h.selector === "node");
    act(() => focus?.handler({ target: { id: () => record.id } }));
    expect(detail).toHaveTextContent(record.detail);
    expect(detail).toHaveTextContent("Reviewer's interpretation (.rN)");
    expect(within(detail).getByText("Simulated")).toBeInTheDocument();

    const background = fake.taps.find((h) => h.event === "tap" && h.selector === null);
    act(() => background?.handler({ target: fake }));
    expect(detail).toHaveTextContent("Hover or tap a node to see its full text.");
  });

  it("destroys Cytoscape on unmount", () => {
    const { unmount } = render(<GraphPanel elements={graphAt(60)} onSeek={vi.fn()} />);
    unmount();
    expect(fake.destroy).toHaveBeenCalled();
  });

  it("shows the counts, the viewpoint legend and a node list with trust badges", () => {
    render(<GraphPanel elements={graphAt(60)} onSeek={vi.fn()} />);
    expect(screen.getByTestId("graph-counts")).toHaveTextContent("Steps 3 · Moments 1 · Records 2");
    const legend = screen.getByLabelText("Legend");
    expect(within(legend).getByText("Operating surgeon's account (.qN)")).toBeInTheDocument();
    expect(within(legend).getByText("Reviewer's interpretation (.rN)")).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Nodes in the knowledge graph" });
    const records = within(list).getAllByText("Decision record");
    expect(records).toHaveLength(2);
    expect(within(list).getAllByText("Simulated")).toHaveLength(2);
  });

  it("without a canvas, shows the node list instead and never calls Cytoscape", () => {
    vi.mocked(canvasSupported).mockReturnValue(false);
    render(<GraphPanel elements={graphAt(60)} onSeek={vi.fn()} />);
    expect(cytoscape).not.toHaveBeenCalled();
    expect(screen.queryByTestId("graph-canvas")).not.toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Nodes in the knowledge graph" })).not.toHaveClass("sr-only");
  });
});
