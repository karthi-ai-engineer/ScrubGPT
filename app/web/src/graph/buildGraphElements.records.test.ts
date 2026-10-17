import { describe, expect, it } from "vitest";

import type { DecisionRecord, ProcedureReference } from "@contracts/contracts";

import { buildReplayIndex, replayStateAt } from "@/replay/sync";
import { confirmedRecord, draftFor } from "@/test/answerFixtures";
import { fixtureDetail } from "@/test/fixtures";

import referenceJson from "../../../../contracts/fixtures/reference/rarp.json";

import { buildGraphElements, nodeId } from "./buildGraphElements";

const reference = referenceJson as ProcedureReference;
const seeds = fixtureDetail.seed_records.records;

function graphAt(t: number, records?: readonly DecisionRecord[]) {
  const index = buildReplayIndex(fixtureDetail, "ai");
  const s = replayStateAt(index, t);
  return buildGraphElements(
    fixtureDetail,
    reference,
    { steps: index.steps.slice(0, s.steps), moments: index.moments.slice(0, s.moments) },
    "en",
    records,
  );
}

const reviewerAnswer = confirmedRecord(
  { ...draftFor("case-fixture-01.m01.r1", { trust: "reviewer" }), action: { type: "act", text: { ja: "別の見方", en: "Another view" }, actor: "surgeon" } },
  "01a1436a-bbbb-7000-8000-00000000000b",
  "Dr Reviewer",
);

describe("buildGraphElements with stored records (J3 → J8)", () => {
  it("defaults to the package's seed records", () => {
    expect(graphAt(60)).toEqual(graphAt(60, seeds));
  });

  it("adds a confirmed answer as its own node under its moment, never merged with the seed viewpoints", () => {
    const g = graphAt(60, [...seeds, reviewerAnswer]);
    const m01 = nodeId.moment("case-fixture-01.m01");
    const onM01 = g.edges.filter((e) => e.source === m01 && e.target.startsWith("record:")).map((e) => e.target);
    expect(onM01).toHaveLength(3);
    const node = g.nodes.find((n) => n.id === nodeId.record(reviewerAnswer.id));
    expect(node).toMatchObject({ kind: "record", trust: "reviewer", viewpoint: "reviewer", label: "👁️ 👁️", detail: "Another view", unconfirmed: false });
  });

  it("ignores another case's records", () => {
    const other = { ...reviewerAnswer, id: "other", case_id: "case-other" };
    expect(graphAt(60, [...seeds, other]).nodes.some((n) => n.id === nodeId.record("other"))).toBe(false);
  });

  it("marks a stored record nobody confirmed (🎙️ narration, D-073) as unconfirmed; confirmed ones are not", () => {
    const g = graphAt(300);
    const records = g.nodes.filter((n) => n.kind === "record");
    const narration = seeds.find((r) => r.provenance.trust_label === "narration_extracted");
    expect(records.filter((n) => n.unconfirmed).map((n) => n.id)).toEqual([nodeId.record(narration?.id ?? "")]);
    expect(g.nodes.filter((n) => n.kind !== "record").every((n) => !n.unconfirmed)).toBe(true);
  });
});
