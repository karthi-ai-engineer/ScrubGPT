import { describe, expect, it } from "vitest";

import type { ProcedureReference } from "@contracts/contracts";

import { buildReplayIndex, replayStateAt } from "@/replay/sync";
import { fixtureDetail } from "@/test/fixtures";

import referenceJson from "../../../../contracts/fixtures/reference/rarp.json";

import { buildGraphElements, nodeId, shorten, viewpointOf, type GraphElements } from "./buildGraphElements";

const reference = referenceJson as ProcedureReference;
const records = fixtureDetail.seed_records.records;

/** The graph the Control Room shows at time `t` on the `track` step track. */
function graphAt(t: number, lang: "ja" | "en" = "en", track: "ai" | "dataset" = "ai", ref: ProcedureReference | null = reference) {
  const index = buildReplayIndex(fixtureDetail, track);
  const state = replayStateAt(index, t);
  return buildGraphElements(
    fixtureDetail,
    ref ?? undefined,
    { steps: index.steps.slice(0, state.steps), moments: index.moments.slice(0, state.moments) },
    lang,
  );
}

const ids = (g: GraphElements, kind?: string) => g.nodes.filter((n) => !kind || n.kind === kind).map((n) => n.id);
const node = (g: GraphElements, id: string) => {
  const found = g.nodes.find((n) => n.id === id);
  if (!found) throw new Error(`no node ${id}`);
  return found;
};
const hasEdge = (g: GraphElements, source: string, target: string) =>
  g.edges.some((e) => e.source === source && e.target === target);
const recordId = (questionOrMoment: string) => {
  const r = records.find((x) => x.question_id === questionOrMoment);
  if (!r) throw new Error(`no record for ${questionOrMoment}`);
  return nodeId.record(r.id);
};

describe("buildGraphElements", () => {
  it("starts with the case and the first reached step", () => {
    const g = graphAt(0);
    expect(ids(g)).toEqual(["case:case-fixture-01", "step:rarp.p03.s01"]);
    expect(hasEdge(g, "case:case-fixture-01", "step:rarp.p03.s01")).toBe(true);
    const step = node(g, "step:rarp.p03.s01");
    expect(step.label).toBe("🤖 Bladder drop"); // trust emoji + Reference name
    expect(step.trust).toBe("ai_detected");
  });

  it("adds a revealed moment under its step, its obstacle leaf, and one node per record", () => {
    const g = graphAt(60);
    expect(ids(g, "step")).toEqual(["step:rarp.p03.s01", "step:rarp.p04.s01", "step:rarp.p04.s02"]);
    expect(ids(g, "moment")).toEqual(["moment:case-fixture-01.m01"]);
    expect(hasEdge(g, "step:rarp.p04.s02", "moment:case-fixture-01.m01")).toBe(true);

    expect(node(g, "obstacle:bleeding.dvc_santorini").trust).toBeNull(); // a Reference node
    expect(hasEdge(g, "moment:case-fixture-01.m01", "obstacle:bleeding.dvc_santorini")).toBe(true);

    // m01 has two viewpoints (.q1 the operating surgeon, .r1 a reviewer): two separate nodes.
    const q1 = recordId("case-fixture-01.m01.q1");
    const r1 = recordId("case-fixture-01.m01.r1");
    expect(ids(g, "record")).toEqual([q1, r1]);
    expect(hasEdge(g, "moment:case-fixture-01.m01", q1)).toBe(true);
    expect(hasEdge(g, "moment:case-fixture-01.m01", r1)).toBe(true);
    expect(node(g, q1).viewpoint).toBe("operating");
    expect(node(g, r1).viewpoint).toBe("reviewer");
    // On the canvas a record shows only its trust + viewpoint emoji; the action text is the detail.
    expect(node(g, q1).label).toBe("🧪 🩺");
    expect(node(g, r1).label).toBe("🧪 👁️");
    const q1Record = records.find((r) => r.question_id === "case-fixture-01.m01.q1");
    expect(node(g, q1).detail).toBe(q1Record?.action.text.en);
    expect(node(g, q1).trust).toBe("simulated");
  });

  it("names the obstacle leaf from the Reference", () => {
    const leafName = reference.obstacle_taxonomy
      .flatMap((f) => f.leaves)
      .find((l) => l.id === "bleeding.dvc_santorini")?.name;
    const g = graphAt(60);
    expect(node(g, "obstacle:bleeding.dvc_santorini").detail).toBe(leafName?.en);
    expect(node(g, "obstacle:bleeding.dvc_santorini").label).toBe(shorten(leafName?.en ?? "", 30));
    expect(node(graphAt(60, "ja"), "obstacle:bleeding.dvc_santorini").detail).toBe(leafName?.ja);
  });

  it("keeps every viewpoint separate: never fewer record nodes than records", () => {
    const g = graphAt(fixtureDetail.case.duration_s);
    expect(ids(g, "record")).toHaveLength(records.length);
    expect(new Set(ids(g, "record")).size).toBe(records.length);
  });

  it("puts a narration record (no question) on its moment, with its own trust emoji", () => {
    const narration = records.find((r) => r.provenance.trust_label === "narration_extracted");
    if (!narration) throw new Error("fixture has no narration record");
    const g = graphAt(90); // m02 at 85 s
    const n = node(g, nodeId.record(narration.id));
    expect(n.viewpoint).toBeNull();
    expect(n.label).toBe("🎙️");
    expect(n.detail).toBe(narration.action.text.en);
    expect(hasEdge(g, `moment:${narration.moment_id}`, n.id)).toBe(true);
  });

  it("attaches a record without a moment to its step once that step is reached", () => {
    const loose = records.find((r) => r.moment_id === null && r.step_id === "rarp.p06.s01");
    if (!loose) throw new Error("fixture has no moment-less record on rarp.p06.s01");
    expect(ids(graphAt(109.9))).not.toContain(nodeId.record(loose.id));
    const g = graphAt(110); // ai step rarp.p06.s01 starts at 110 s
    expect(hasEdge(g, "step:rarp.p06.s01", nodeId.record(loose.id))).toBe(true);
  });

  it("shrinks again for an earlier time (a backwards seek)", () => {
    const later = graphAt(200);
    const earlier = graphAt(60);
    expect(earlier.nodes.length).toBeLessThan(later.nodes.length);
    expect(graphAt(60)).toEqual(earlier); // deterministic
  });

  it("labels nodes in the current language", () => {
    const en = graphAt(60, "en");
    const ja = graphAt(60, "ja");
    expect(node(en, "case:case-fixture-01").detail).toBe(fixtureDetail.case.title.en);
    expect(node(ja, "case:case-fixture-01").detail).toBe(fixtureDetail.case.title.ja);
    expect(node(en, "case:case-fixture-01").label).toBe(shorten(fixtureDetail.case.title.en, 30));
    expect(node(ja, "step:rarp.p04.s02").label).toContain("DVC");
    const m01 = fixtureDetail.moments.moments[0];
    expect(node(ja, "moment:case-fixture-01.m01").label).toBe(`🤖 ${m01?.title.ja}`);
    const q1 = records.find((r) => r.question_id === "case-fixture-01.m01.q1");
    expect(node(ja, recordId("case-fixture-01.m01.q1")).detail).toBe(q1?.action.text.ja);
  });

  it("adds a moment's step even when the shown track has not reached it yet", () => {
    // Dataset track: rarp.p09.s02 starts at 205 s, but moment m04 (on that step) starts at 195 s.
    const g = graphAt(196, "en", "dataset");
    expect(hasEdge(g, "step:rarp.p09.s02", "moment:case-fixture-01.m04")).toBe(true);
    expect(node(g, "step:rarp.p09.s02").trust).toBe("ai_detected"); // from the moment
  });

  it("falls back to raw ids without a Reference and skips unknown obstacle leaves", () => {
    const g = graphAt(60, "en", "ai", null);
    expect(node(g, "step:rarp.p04.s02").label).toBe("🤖 rarp.p04.s02");
    expect(ids(g, "obstacle")).toEqual([]);
  });
});

describe("helpers", () => {
  it("reads the viewpoint from the question id", () => {
    expect(viewpointOf({ question_id: "case-x.m01.q2" })).toBe("operating");
    expect(viewpointOf({ question_id: "case-x.m01.r1" })).toBe("reviewer");
    expect(viewpointOf({ question_id: null })).toBeNull();
  });

  it("shortens long text with an ellipsis, by code point", () => {
    expect(shorten("short")).toBe("short");
    expect(shorten("abcdefghij", 5)).toBe("abcd…");
    expect([...shorten("気腹圧を15に上げ、圧で止まるかを見た", 6)]).toHaveLength(6);
  });
});
