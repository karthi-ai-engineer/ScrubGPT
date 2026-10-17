/**
 * J8 graph panel acceptance (brief criterion 8): the knowledge graph inside the Control Room
 * grows with the replay.
 *
 * Sources: plan §2.10 J2 ("a graph panel that grows") and J8 ("A panel inside the Control Room
 * is M"), §10 demo step 5, D-069 ("J8 shows only fixture records and reference nodes, with
 * provenance (trust label) and JA + EN labels, and keeps every viewpoint as its own node.
 * Nothing is invented"), D-059 (".qN" = "Operating surgeon's account", ".rN" = "Reviewer's
 * interpretation"; both viewpoints kept, never merged), root CLAUDE.md ("Keep every viewpoint";
 * provenance on every piece of knowledge), app/web/README.md (case → steps → moments → obstacle
 * leaves and records; Cytoscape isn't rendered in jsdom, so the panel shows its node list).
 *
 * The page tests read the panel's node list (the text form of the graph). The structure test
 * uses the pure `buildGraphElements` (an entry point named in the brief) to check the edges.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { DecisionRecord, Moment, StepSegment } from "@contracts/contracts";

import { buildGraphElements } from "@/graph/buildGraphElements";

import { bilingualTexts, fixture, fixtureDetail, stepName } from "./harness";
import {
  hasTrustBadge,
  installEventSource,
  installReplayMedia,
  mockApi,
  playTo,
  playToEnd,
  renderControlRoom,
  seekTo,
  toggleButton,
  tr,
  type Lang,
} from "./replay-harness";

const tl = fixture.timeline;
const moments = fixture.moments.moments;
const records = fixture.seedRecords.records;
const aiSteps = tl.steps.filter((s) => s.track === "ai") as StepSegment[];

function obstacleLeaf(id: string) {
  for (const fam of fixture.reference.obstacle_taxonomy) {
    for (const leaf of fam.leaves) if (leaf.id === id) return leaf;
  }
  return undefined;
}

/** Texts of a record that no other record has (so a node can be matched to exactly one). */
function uniqueTexts(record: DecisionRecord, lang: Lang): string[] {
  const others = new Set(records.filter((r) => r.id !== record.id).flatMap((r) => bilingualTexts(r, lang)));
  return bilingualTexts(record, lang).filter((t) => t.trim() && !others.has(t));
}

interface Expected {
  steps: string[];
  moments: Moment[];
  obstacles: string[];
  records: DecisionRecord[];
}

/** The spec's graph at video time t on the shown (ai) track. */
function expectedAt(t: number): Expected {
  const reachedSteps = new Set(aiSteps.filter((s) => s.t_start <= t).map((s) => s.step_id));
  const shown = moments.filter((m) => m.t_start <= t);
  const shownIds = new Set(shown.map((m) => m.id));
  for (const m of shown) reachedSteps.add(m.step_id);
  const obstacles = [...new Set(shown.flatMap((m) => (m.draft_obstacle ? [m.draft_obstacle] : [])))];
  const recs = records.filter((r) =>
    r.moment_id ? shownIds.has(r.moment_id) : aiSteps.some((s) => s.t_start <= t && s.step_id === r.step_id),
  );
  return { steps: [...reachedSteps], moments: shown, obstacles, records: recs };
}

function graphList(lang: Lang = "en"): HTMLElement {
  return screen.getByRole("list", { name: tr(lang, "graph.listLabel") });
}
function nodes(lang: Lang = "en"): HTMLElement[] {
  return within(graphList(lang)).queryAllByRole("listitem");
}
function nodesOfKind(kind: string, lang: Lang = "en"): HTMLElement[] {
  const label = tr(lang, `graph.kind.${kind}`);
  return nodes(lang).filter((li) => (li.textContent ?? "").startsWith(label) || within(li).queryAllByText(label).length > 0);
}

function recordNode(record: DecisionRecord, lang: Lang): HTMLElement {
  const unique = uniqueTexts(record, lang);
  const found = nodesOfKind("record", lang).filter((li) => unique.some((t) => li.textContent?.includes(t)));
  expect(found, `one node for record ${record.id} (${record.question_id ?? "no question"})`).toHaveLength(1);
  return found[0]!;
}

function expectGraphAt(t: number, lang: Lang = "en") {
  const exp = expectedAt(t);
  const all = nodes(lang);
  const caseNodes = nodesOfKind("case", lang);
  expect(caseNodes, `case node at ${t}`).toHaveLength(1);
  expect(caseNodes[0]!.textContent).toContain(fixture.case.title[lang]);

  const steps = nodesOfKind("step", lang);
  expect(steps, `steps at ${t}`).toHaveLength(exp.steps.length);
  for (const id of exp.steps) {
    const li = steps.find((x) => x.textContent?.includes(stepName(id)[lang]));
    expect(li, `step ${id} at ${t}`).toBeDefined();
    const seg = aiSteps.find((s) => s.step_id === id);
    const label = seg?.provenance.trust_label ?? moments.find((m) => m.step_id === id)!.provenance.trust_label;
    expect(hasTrustBadge(li!, label, lang), `trust of step ${id}`).toBe(true);
  }

  const ms = nodesOfKind("moment", lang);
  expect(ms, `moments at ${t}`).toHaveLength(exp.moments.length);
  for (const m of exp.moments) {
    const li = ms.find((x) => x.textContent?.includes(m.title[lang]));
    expect(li, `moment ${m.id} at ${t}`).toBeDefined();
    expect(hasTrustBadge(li!, m.provenance.trust_label, lang), `trust of ${m.id}`).toBe(true);
  }

  const obs = nodesOfKind("obstacle", lang);
  expect(obs, `obstacles at ${t}`).toHaveLength(exp.obstacles.length);
  for (const id of exp.obstacles) {
    const leaf = obstacleLeaf(id);
    expect(leaf, `${id} is a Reference leaf`).toBeDefined();
    expect(obs.some((x) => x.textContent?.includes(leaf!.name[lang])), `obstacle ${id} at ${t}`).toBe(true);
  }

  const recs = nodesOfKind("record", lang);
  expect(recs, `records at ${t}`).toHaveLength(exp.records.length);
  for (const r of exp.records) {
    const li = recordNode(r, lang);
    expect(hasTrustBadge(li, r.provenance.trust_label, lang), `trust of record ${r.id}`).toBe(true);
  }

  // Nothing invented: no node beyond the case, steps, moments, obstacles and records above.
  expect(all, `all nodes at ${t}`).toHaveLength(1 + exp.steps.length + exp.moments.length + exp.obstacles.length + exp.records.length);
}

let restoreMedia: () => void;
beforeEach(() => {
  restoreMedia = installReplayMedia();
  installEventSource();
});
afterEach(() => restoreMedia());

async function ready() {
  mockApi();
  await renderControlRoom();
  // The Reference is loaded once the first step has its name in the graph.
  await playTo(1);
  await waitFor(() => expect(graphList().textContent).toContain(stepName(aiSteps[0]!.step_id).en));
}

describe("J8 graph panel grows with the replay", () => {
  // 280–285 is left out on purpose: m06 starts at 280 but the ai track reaches its step only at
  // 285; how a step node appears in between is not specified (see the report).
  const times = [1, 30, 57.99, 58, 90, 119.99, 125, 150, 200, 224.99, 230, 270, 299.5];

  it("criterion 8: at each time the graph is case → reached steps → revealed moments → draft obstacle (Reference name) and the records tied to them", async () => {
    await ready();
    for (const t of times) {
      await playTo(t);
      await waitFor(() => expect(nodesOfKind("moment")).toHaveLength(expectedAt(t).moments.length));
      expectGraphAt(t);
    }
    await playToEnd();
    await waitFor(() => expect(nodesOfKind("moment")).toHaveLength(moments.length));
    expectGraphAt(300);
  });

  it("criterion 8: seeking back shrinks the graph again", async () => {
    await ready();
    await playTo(270);
    expectGraphAt(270);
    for (const t of [125, 58, 30]) {
      await seekTo(t);
      await waitFor(() => expect(nodesOfKind("moment")).toHaveLength(expectedAt(t).moments.length));
      expectGraphAt(t);
    }
  });

  it("criterion 8: every record is its own node, never merged: the two m01 records stay two nodes (.q1 operating surgeon's account, .r1 reviewer's interpretation)", async () => {
    await ready();
    await playTo(60);
    const m01 = records.filter((r) => r.moment_id === moments[0]!.id);
    expect(m01.map((r) => r.question_id).sort()).toEqual([`${moments[0]!.id}.q1`, `${moments[0]!.id}.r1`]);
    const q1 = recordNode(m01.find((r) => r.question_id!.endsWith(".q1"))!, "en");
    const r1 = recordNode(m01.find((r) => r.question_id!.endsWith(".r1"))!, "en");
    expect(q1).not.toBe(r1);
    // D-059 wording.
    expect(q1.textContent).toContain("Operating surgeon's account");
    expect(q1.textContent).not.toContain("Reviewer's interpretation");
    expect(r1.textContent).toContain("Reviewer's interpretation");
    expect(r1.textContent).not.toContain("Operating surgeon's account");
  });

  it("criterion 8: the m02 operating account and the narration record are two nodes; the narration one claims no viewpoint", async () => {
    await ready();
    await playTo(90);
    const m02 = records.filter((r) => r.moment_id === moments[1]!.id);
    expect(m02).toHaveLength(2);
    const narration = m02.find((r) => r.provenance.trust_label === "narration_extracted")!;
    const surgeon = m02.find((r) => r.question_id?.endsWith(".q1"))!;
    const n = recordNode(narration, "en");
    const s = recordNode(surgeon, "en");
    expect(n).not.toBe(s);
    expect(hasTrustBadge(n, "narration_extracted", "en")).toBe(true);
    expect(n.textContent).not.toContain("Operating surgeon's account");
    expect(n.textContent).not.toContain("Reviewer's interpretation");
    expect(s.textContent).toContain("Operating surgeon's account");
  });

  it("criterion 8: records without a moment appear once their step is reached (not before)", async () => {
    await ready();
    const momentless = records.filter((r) => !r.moment_id);
    expect(momentless.length).toBeGreaterThan(0);
    for (const r of momentless) {
      const reachedAt = Math.min(...aiSteps.filter((s) => s.step_id === r.step_id).map((s) => s.t_start));
      await seekTo(reachedAt - 0.01);
      await waitFor(() => expect(nodesOfKind("record")).toHaveLength(expectedAt(reachedAt - 0.01).records.length));
      const unique = uniqueTexts(r, "en");
      expect(nodesOfKind("record").some((li) => unique.some((x) => li.textContent?.includes(x))), `${r.id} early`).toBe(false);
      await playTo(reachedAt);
      await waitFor(() => expect(nodesOfKind("record")).toHaveLength(expectedAt(reachedAt).records.length));
      recordNode(r, "en");
    }
  });

  it("criterion 8: labels follow the JA/EN toggle (and viewpoint labels exist in both languages)", async () => {
    await ready();
    const user = userEvent.setup();
    await playTo(230);
    expectGraphAt(230, "en");
    await user.click(toggleButton("JA"));
    await waitFor(() => expect(graphList("ja").textContent).toContain(fixture.case.title.ja));
    expectGraphAt(230, "ja");
    const text = graphList("ja").textContent ?? "";
    for (const r of expectedAt(230).records) {
      for (const en of uniqueTexts(r, "en")) expect(text, `EN text of ${r.id} in JA`).not.toContain(en);
    }
    for (const m of expectedAt(230).moments) expect(text).not.toContain(m.title.en);
    const q1 = recordNode(records.find((r) => r.question_id?.endsWith("m01.q1"))!, "ja");
    expect(q1.textContent).toContain(tr("ja", "graph.operating"));
    const r1 = recordNode(records.find((r) => r.question_id?.endsWith("m01.r1"))!, "ja");
    expect(r1.textContent).toContain(tr("ja", "graph.reviewer"));
    await user.click(toggleButton("EN"));
    await waitFor(() => expect(graphList("en").textContent).toContain(fixture.case.title.en));
    expectGraphAt(230, "en");
  });
});

describe("J8 graph structure (buildGraphElements)", () => {
  it("criterion 8: edges are case → step → moment → obstacle / record; moment-less records hang on their step", () => {
    const detail = fixtureDetail();
    for (const t of [60, 125, 230, 299.5]) {
      const exp = expectedAt(t);
      const g = buildGraphElements(
        detail as never,
        fixture.reference,
        { steps: aiSteps.filter((s) => s.t_start <= t), moments: exp.moments },
        "en",
      );
      const byId = new Map(g.nodes.map((n) => [n.id, n]));
      const find = (kind: string, text: string) => {
        const hits = g.nodes.filter((n) => n.kind === kind && (n.detail.includes(text) || n.label.includes(text)));
        expect(hits, `${kind} "${text}" at ${t}`).toHaveLength(1);
        return hits[0]!;
      };
      const edge = (a: { id: string }, b: { id: string }) =>
        g.edges.some((e) => (e.source === a.id && e.target === b.id) || (e.source === b.id && e.target === a.id));

      const caseNode = find("case", fixture.case.title.en);
      for (const id of exp.steps) expect(edge(caseNode, find("step", stepName(id).en)), `case–${id}`).toBe(true);
      for (const m of exp.moments) {
        const mn = find("moment", m.title.en);
        expect(edge(find("step", stepName(m.step_id).en), mn), `step–${m.id}`).toBe(true);
        if (m.draft_obstacle) expect(edge(mn, find("obstacle", obstacleLeaf(m.draft_obstacle)!.name.en)), `${m.id}–obstacle`).toBe(true);
      }
      for (const r of exp.records) {
        const rn = g.nodes.filter((n) => n.kind === "record" && uniqueTexts(r, "en").some((x) => n.detail.includes(x)));
        expect(rn, `record ${r.id}`).toHaveLength(1);
        expect(rn[0]!.trust).toBe(r.provenance.trust_label);
        const parent = r.moment_id
          ? find("moment", moments.find((m) => m.id === r.moment_id)!.title.en)
          : find("step", stepName(r.step_id).en);
        expect(edge(parent, rn[0]!), `${r.id} attached`).toBe(true);
      }
      // Every edge joins two existing nodes.
      for (const e of g.edges) expect(byId.has(e.source) && byId.has(e.target), e.id).toBe(true);
    }
  });
});
