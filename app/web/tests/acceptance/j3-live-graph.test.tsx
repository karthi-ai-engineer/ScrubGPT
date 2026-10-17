/**
 * Confirmed answers update the Control Room's J8 graph through SSE (brief criterion 10, web side)
 * and the stored 🎙️ record shows "not confirmed" (brief criterion 2e).
 *
 * Sources: plan §8.3 ("Confirm → app server stores the record + provenance → SSE → graph and
 * library update live"), §10 demo step 5 ("new nodes appear in the graph; the new record shows its
 * 🩺 or 🧪 trust label"); D-071 ("one graph node per record"); D-073 ("The UI shows a stored 🎙️
 * record with null confirmation as 'not confirmed' (JA + EN) next to its 🎙️ label, never as
 * confirmed or surgeon-confirmed"); app/server/README.md "SSE events" (`record.created` carries the
 * stored record); app/web/README.md "Live graph" (`GET /api/cases/{id}/records`, then each
 * `record.created` of this case, one node per record, two answers on one moment stay two nodes);
 * app/web/CLAUDE.md rules 3 (JA + EN, toggle without reload) and 5 (trust labels everywhere).
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { DecisionRecord, TrustLabel } from "@contracts/contracts";

import { fixture, json } from "./harness";
import {
  emitAll,
  hasTrustBadge,
  installEventSource,
  installReplayMedia,
  mockApi,
  openStreams,
  playToEnd,
  renderControlRoom,
  toggleButton,
  tr,
  type Lang,
} from "./replay-harness";

const CASE_ID = fixture.case.id;
const seeds = fixture.seedRecords.records;
const NARRATION = seeds.find((r) => r.provenance.trust_label === "narration_extracted")!;
const m01 = fixture.moments.moments[0]!;

function graphList(lang: Lang = "en"): HTMLElement {
  return screen.getByRole("list", { name: tr(lang, "graph.listLabel") });
}
function recordNodes(lang: Lang = "en"): HTMLElement[] {
  const label = tr(lang, "graph.kind.record");
  return within(graphList(lang))
    .queryAllByRole("listitem")
    .filter((li) => (li.textContent ?? "").startsWith(label) || within(li).queryAllByText(label).length > 0);
}
function nodeWith(text: string, lang: Lang = "en"): HTMLElement[] {
  return recordNodes(lang).filter((li) => li.textContent?.includes(text));
}

/** A new confirmed answer on m01, as the server would send it in `record.created`. */
function answerRecord(n: number, label: TrustLabel, role: string, questionId = `${m01.id}.q1`): DecisionRecord {
  const base = structuredClone(seeds[0]!) as unknown as Record<string, unknown>;
  return {
    ...base,
    id: `01a1500a-0000-7000-8000-0000000001${String(n).padStart(2, "0")}`,
    moment_id: m01.id,
    question_id: questionId,
    action: { type: "act", text: { ja: `ライブ回答${n}の対応`, en: `Live answer ${n} action` }, actor: "surgeon" },
    provenance: {
      trust_label: label,
      attributed_to: role,
      generated_by: { model_tier: "TEXT_SMART", model: "mock", prompt_version: "extract.mock.v1" },
      confirmed_by: "Dr Live",
      confirmed_at: "2026-10-18T09:00:00Z",
    },
  } as unknown as DecisionRecord;
}

function storedRoute(records: readonly DecisionRecord[]) {
  return () =>
    json({
      records: records.map((record) => ({ record, source: "seed", answer_id: null, stored_at: "2026-10-18T00:00:00Z" })),
    });
}

let restoreMedia: () => void;
beforeEach(() => {
  restoreMedia = installReplayMedia();
  installEventSource();
});
afterEach(() => restoreMedia());

async function readyAtEnd(stored: readonly DecisionRecord[] = seeds) {
  mockApi({ extra: { [`/api/cases/${CASE_ID}/records`]: storedRoute(stored) } });
  await renderControlRoom();
  await openStreams();
  await playToEnd();
  await waitFor(() => expect(recordNodes()).toHaveLength(stored.length));
}

describe("criterion 10: confirmed answers grow the J8 graph live, one node per record", () => {
  it("criterion 10: the graph starts from the stored records (GET /api/cases/{id}/records), one node each", async () => {
    const stored = [...seeds, answerRecord(1, "operating_surgeon", "operating_surgeon")];
    await readyAtEnd(stored);
    expect(nodeWith("Live answer 1 action")).toHaveLength(1);
  });

  it("criterion 10: a record.created adds one node with its trust label, without a reload", async () => {
    await readyAtEnd();
    const before = recordNodes().length;
    const record = answerRecord(1, "operating_surgeon", "operating_surgeon");
    await emitAll("answer.confirmed", { case_id: CASE_ID, question_id: record.question_id, record_id: record.id, answer_id: "01a1500a-0000-7000-8000-000000000a01" });
    await emitAll("record.created", { record });
    await emitAll("graph.updated", { case_id: CASE_ID, nodes: [{ id: record.id, kind: "record" }], edges: [] });
    await waitFor(() => expect(recordNodes()).toHaveLength(before + 1));
    const [node] = nodeWith("Live answer 1 action");
    expect(node).toBeDefined();
    expect(hasTrustBadge(node!, "operating_surgeon", "en")).toBe(true);
    // Still the same page: the video and the earlier nodes are there.
    expect(document.querySelector("video")).not.toBeNull();
  });

  it("criterion 10: two answers on one moment stay two nodes (🩺 and 🧪), never merged", async () => {
    await readyAtEnd();
    const before = recordNodes().length;
    const a = answerRecord(1, "operating_surgeon", "operating_surgeon");
    const b = answerRecord(2, "simulated", "dev_team_simulated");
    await emitAll("record.created", { record: a });
    await emitAll("record.created", { record: b });
    await waitFor(() => expect(recordNodes()).toHaveLength(before + 2));
    const [na] = nodeWith("Live answer 1 action");
    const [nb] = nodeWith("Live answer 2 action");
    expect(na).toBeDefined();
    expect(nb).toBeDefined();
    expect(na).not.toBe(nb);
    expect(hasTrustBadge(na!, "operating_surgeon", "en")).toBe(true);
    expect(hasTrustBadge(nb!, "simulated", "en")).toBe(true);
  });

  it("criterion 10: the same record arriving twice is still one node; another case's record adds none", async () => {
    await readyAtEnd();
    const before = recordNodes().length;
    const a = answerRecord(1, "operating_surgeon", "operating_surgeon");
    await emitAll("record.created", { record: a });
    await emitAll("record.created", { record: a });
    const other = { ...answerRecord(3, "reviewer", "reviewer"), case_id: "yt-en-03" } as DecisionRecord;
    await emitAll("record.created", { record: other });
    await waitFor(() => expect(recordNodes()).toHaveLength(before + 1));
    expect(nodeWith("Live answer 1 action")).toHaveLength(1);
    expect(nodeWith("Live answer 3 action")).toHaveLength(0);
  });

  it("criterion 10: the new node is labelled in Japanese too (toggle, no reload)", async () => {
    await readyAtEnd();
    await emitAll("record.created", { record: answerRecord(1, "operating_surgeon", "operating_surgeon") });
    await waitFor(() => expect(nodeWith("Live answer 1 action")).toHaveLength(1));
    await userEvent.setup().click(toggleButton("JA"));
    await waitFor(() => expect(nodeWith("ライブ回答1の対応", "ja")).toHaveLength(1));
    expect(hasTrustBadge(nodeWith("ライブ回答1の対応", "ja")[0]!, "operating_surgeon", "ja")).toBe(true);
  });
});

describe("criterion 2e: a stored 🎙️ record with null confirmation shows 'not confirmed' (JA + EN) next to its 🎙️ label", () => {
  function narrationNode(lang: Lang): HTMLElement {
    const texts = [NARRATION.action.text[lang], NARRATION.situation_cue.text[lang]].filter(Boolean);
    const found = recordNodes(lang).filter((li) => texts.some((t) => li.textContent?.includes(t)));
    expect(found, "one node for the narration record").toHaveLength(1);
    return found[0]!;
  }

  it.each(["en", "ja"] as const)("criterion 2e: the narration record's node says 'not confirmed' with its 🎙️ label (%s)", async (lang) => {
    expect(NARRATION.provenance.confirmed_by).toBeNull();
    expect(NARRATION.provenance.confirmed_at).toBeNull();
    await readyAtEnd();
    if (lang === "ja") await userEvent.setup().click(toggleButton("JA"));
    await waitFor(() => expect(graphList(lang)).toBeInTheDocument());
    const node = narrationNode(lang);
    expect(hasTrustBadge(node, "narration_extracted", lang)).toBe(true);
    expect(node.textContent).toContain(tr(lang, "record.notConfirmed"));
  });

  it("criterion 2e: no confirmed record shows 'not confirmed', and the narration node claims no surgeon confirmation", async () => {
    await readyAtEnd();
    const notConfirmed = tr("en", "record.notConfirmed");
    for (const li of recordNodes()) {
      if (li === narrationNode("en")) continue;
      expect(li.textContent).not.toContain(notConfirmed);
    }
    const node = narrationNode("en");
    expect(node.textContent).not.toContain(tr("en", "trust.operating_surgeon"));
    expect(node.textContent).not.toContain(tr("en", "trust.expert_validated"));
  });

  it("criterion 2e: the JA and EN 'not confirmed' strings both exist and differ by language", () => {
    expect(tr("en", "record.notConfirmed").trim()).not.toBe("");
    expect(tr("ja", "record.notConfirmed")).toMatch(/[぀-ヿ㐀-鿿]/);
  });
});
