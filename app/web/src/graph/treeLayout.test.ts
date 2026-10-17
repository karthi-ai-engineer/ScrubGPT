import { describe, expect, it } from "vitest";

import type { ProcedureReference } from "@contracts/contracts";

import { buildReplayIndex, replayStateAt } from "@/replay/sync";
import { fixtureDetail } from "@/test/fixtures";

import referenceJson from "../../../../contracts/fixtures/reference/rarp.json";

import { buildGraphElements, type GraphElements } from "./buildGraphElements";
import { TREE_LAYOUT, treePositions } from "./treeLayout";

function graphAt(t: number): GraphElements {
  const index = buildReplayIndex(fixtureDetail, "ai");
  const s = replayStateAt(index, t);
  return buildGraphElements(
    fixtureDetail,
    referenceJson as ProcedureReference,
    { steps: index.steps.slice(0, s.steps), moments: index.moments.slice(0, s.moments) },
    "en",
  );
}

const { firstColumn, columnWidth, rowHeight } = TREE_LAYOUT;

describe("treePositions", () => {
  it("places every node, one column per depth: case, steps, moments, then leaves and records", () => {
    const g = graphAt(60);
    const p = treePositions(g);
    expect(Object.keys(p).sort()).toEqual(g.nodes.map((n) => n.id).sort());
    expect(p["case:case-fixture-01"]?.x).toBe(0);
    expect(p["step:rarp.p04.s02"]?.x).toBe(firstColumn);
    expect(p["moment:case-fixture-01.m01"]?.x).toBe(firstColumn + columnWidth);
    expect(p["obstacle:bleeding.dvc_santorini"]?.x).toBe(firstColumn + 2 * columnWidth);
  });

  it("gives each leaf its own row, so no two nodes in a column share a row", () => {
    const p = treePositions(graphAt(fixtureDetail.case.duration_s));
    const byColumn = new Map<number, number[]>();
    for (const { x, y } of Object.values(p)) byColumn.set(x, [...(byColumn.get(x) ?? []), y]);
    for (const ys of byColumn.values()) {
      const sorted = [...ys].sort((a, b) => a - b);
      for (let i = 1; i < sorted.length; i++) {
        expect((sorted[i] as number) - (sorted[i - 1] as number)).toBeGreaterThanOrEqual(rowHeight - 1e-9);
      }
    }
  });

  it("centres a parent on its children", () => {
    const g = graphAt(60);
    const p = treePositions(g);
    const kids = g.edges.filter((e) => e.source === "moment:case-fixture-01.m01").map((e) => p[e.target]?.y ?? NaN);
    expect(p["moment:case-fixture-01.m01"]?.y).toBe((Math.min(...kids) + Math.max(...kids)) / 2);
  });

  it("is deterministic and keeps earlier rows when the graph grows at the bottom", () => {
    expect(treePositions(graphAt(60))).toEqual(treePositions(graphAt(60)));
    const before = treePositions(graphAt(26)); // two steps
    const after = treePositions(graphAt(51)); // a third step appended below
    expect(after["step:rarp.p03.s01"]).toEqual(before["step:rarp.p03.s01"]);
  });
});
