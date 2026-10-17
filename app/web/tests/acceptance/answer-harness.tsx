/**
 * Tester 2 harness for the J3 Answer app and the live graph (Block 3 items pulled forward, D-071).
 * Not a test file itself (no `.test.` in the name).
 *
 * The app server is mocked at `fetch`, in the shapes of app/server/README.md (API table): the
 * answer queue is built from the fixture `questions.json` and `moments.json`; drafts are
 * contract-shaped `ExtractResponse`s (brain_api.md) built per test. Every call is recorded with
 * its method, path, query and body, so tests can check what the web app sent.
 */
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, vi } from "vitest";

import type { Bilingual, DecisionRecord, DecisionRecordDraft, Question, Role, TrustLabel } from "@contracts/contracts";

import en from "@/i18n/en.json";
import ja from "@/i18n/ja.json";

import { apiError, fixture, fixtureDetail, flatten, json, renderApp } from "./harness";

export const flat = { en: flatten(en), ja: flatten(ja) } as const;
export type Lang = "en" | "ja";
export const tr = (lang: Lang, key: string, vars: Record<string, string | number> = {}) => {
  const value = flat[lang][key];
  if (typeof value !== "string") throw new Error(`no i18n key ${key} (${lang})`);
  return value.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(vars[name] ?? `{{${name}}}`));
};

export const CASE_ID = fixture.case.id;
export const QUESTIONS = fixture.questions;
const MOMENTS = fixture.moments.moments;

/** plan §4.3: trust_label follows the answerer. */
export const ROLE_TRUST: Readonly<Record<string, TrustLabel>> = {
  operating_surgeon: "operating_surgeon",
  reviewer: "reviewer",
  dev_team_simulated: "simulated",
};

// --- The answer queue (README: answer-queue) --------------------------------------------------

export interface QueueItem {
  question: Question;
  moment: (typeof MOMENTS)[number];
  clip: string;
  poster: string;
  answered: boolean;
}

export function queueFor(role: "operating" | "reviewer", only?: string[]) {
  const list = QUESTIONS[role].filter((q) => !only || only.includes(q.id));
  const questions: QueueItem[] = list.map((question) => {
    const moment = MOMENTS.find((m) => m.id === question.moment_id)!;
    return {
      question,
      moment,
      clip: `/media/cases/${CASE_ID}/${moment.clip}`,
      poster: `/media/cases/${CASE_ID}/${moment.poster}`,
      answered: false,
    };
  });
  return {
    case_id: CASE_ID,
    role,
    est_seconds: list.reduce((s, q) => s + q.est_seconds, 0),
    questions,
  };
}

// --- Drafts (brain_api.md `/extract` response) ------------------------------------------------

export const ANSWER_ID = "01a1500a-0000-7000-8000-000000000001";

interface DraftOptions {
  questionId: string;
  role?: Role;
  cue?: Bilingual | null;
  action?: Bilingual | null;
  reason?: Bilingual | null;
  /** Override the order of `missing_fields` (the app must not rely on it, D-072 (c)). */
  missingOrder?: (missing: string[]) => string[];
  answerId?: string;
}

/**
 * A contract-shaped `{answer_id, extract}`: the fixture's first seed record as the base, with
 * the given cue / action / reason (null = not stated) and every other optional field null.
 */
export function draftResponse(o: DraftOptions) {
  const role = o.role ?? "dev_team_simulated";
  const question = [...QUESTIONS.operating, ...QUESTIONS.reviewer].find((q) => q.id === o.questionId)!;
  const base = structuredClone(fixture.seedRecords.records[0]!) as unknown as Record<string, unknown>;
  const answerId = o.answerId ?? ANSWER_ID;
  const cue = o.cue === undefined ? { ja: "視野が赤い", en: "The view is red" } : o.cue;
  const action = o.action === undefined ? null : o.action;
  const reason = o.reason === undefined ? null : o.reason;
  const grounding: { field: string; quote: string; source: string }[] = [];
  if (cue) grounding.push({ field: "situation_cue.text", quote: cue.ja, source: "answer" });
  if (action) grounding.push({ field: "action.text", quote: action.ja, source: "answer" });
  if (reason) grounding.push({ field: "reason", quote: reason.ja, source: "answer" });
  const draft = {
    ...base,
    id: null,
    moment_id: question.moment_id,
    question_id: question.id,
    step_id: MOMENTS.find((m) => m.id === question.moment_id)!.step_id,
    language: "ja",
    context: { patient_factors: [], preop_plan: null },
    situation_cue: { text: cue, cue_terms: [] },
    obstacle: null,
    anticipation: null,
    action: { type: "act", text: action, actor: "unknown" },
    alternatives: [],
    reason,
    immediate_result: null,
    delayed_outcome: { status: "pending", text: null, source: null },
    evidence: [{ kind: "answer_text", answer_id: answerId, quote: cue?.ja ?? "…" }],
    grounding,
    provenance: {
      trust_label: ROLE_TRUST[role],
      attributed_to: role,
      generated_by: { model_tier: "TEXT_SMART", model: "mock", prompt_version: "extract.mock.v1" },
      confirmed_by: null,
      confirmed_at: null,
    },
    new_terms: [],
  } as unknown as DecisionRecordDraft;
  const chips = [
    cue && { field: "situation_cue.text", value: cue, editable: true },
    action && { field: "action.text", value: action, editable: true },
    reason && { field: "reason", value: reason, editable: true },
  ].filter(Boolean);
  let missing = [
    "context.preop_plan",
    ...(cue ? [] : ["situation_cue.text"]),
    "obstacle",
    "anticipation",
    ...(action ? [] : ["action.text"]),
    ...(reason ? [] : ["reason"]),
    "immediate_result",
    "alternatives",
  ];
  if (o.missingOrder) missing = o.missingOrder(missing);
  return {
    answer_id: answerId,
    extract: {
      contract_version: "1.0",
      draft,
      readback: { ja: "読み上げ：視野が赤い。", en: "Read-back: the view is red." },
      chips,
      missing_fields: missing,
    },
  };
}

/** The record the server would return from Confirm (confirmation filled, new id). */
export function confirmedRecord(draft: DecisionRecordDraft, id: string, by = "Dr Test"): DecisionRecord {
  const record = structuredClone(draft) as unknown as Record<string, unknown> & { provenance: Record<string, unknown> };
  record.id = id;
  record.provenance = { ...record.provenance, confirmed_by: by, confirmed_at: "2026-10-18T09:00:00Z" };
  const action = record.action as { text: Bilingual | null };
  if (!action.text) action.text = { ja: "対応", en: "Action" };
  const cue = record.situation_cue as { text: Bilingual | null };
  if (!cue.text) cue.text = { ja: "手がかり", en: "Cue" };
  return record as unknown as DecisionRecord;
}

// --- fetch mock -------------------------------------------------------------------------------

export interface Call {
  method: string;
  path: string;
  query: URLSearchParams;
  body: unknown;
}

type Handler = (call: Call) => Response | Promise<Response>;

export interface AnswerServer {
  calls: Call[];
  posts: (path: string) => Call[];
  routes: Record<string, Handler>;
}

/** The app server for the Answer app: case detail, reference, brain health, queue, and the given extra routes. */
export function mockAnswerServer(extra: Record<string, Handler> = {}): AnswerServer {
  const routes: Record<string, Handler> = {
    "/api/health": () =>
      json({ status: "ok", contract_version: "1.0", brain_mode: "mock", cases: { loaded: 1, rejected: 0 } }),
    [`/api/cases/${CASE_ID}`]: () => json(fixtureDetail()),
    "/api/references/rarp": () => json(fixture.reference),
    "/api/brain/health": () =>
      json({ contract_version: "1.0", status: "ok", mode: "mock", model_tiers: {}, cache_mode: "off" }),
    [`/api/cases/${CASE_ID}/answer-queue`]: (call) =>
      json(queueFor(call.query.get("role") === "reviewer" ? "reviewer" : "operating")),
    [`/api/cases/${CASE_ID}/records`]: () =>
      json({
        records: fixture.seedRecords.records.map((record) => ({ record, source: "seed", answer_id: null, stored_at: "2026-10-18T00:00:00Z" })),
      }),
    ...extra,
  };
  const calls: Call[] = [];
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(raw, "http://localhost");
    const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    let body: unknown = init?.body ?? null;
    if (typeof body === "string") {
      try {
        body = JSON.parse(body);
      } catch {
        // keep the raw string
      }
    }
    const call: Call = { method, path: url.pathname, query: url.searchParams, body };
    calls.push(call);
    const handler = routes[url.pathname];
    return handler ? handler(call) : apiError("not_found", 404);
  });
  vi.stubGlobal("fetch", spy);
  return {
    calls,
    routes,
    posts: (path: string) => calls.filter((c) => c.method === "POST" && c.path === path),
  };
}

export { apiError, json };

// --- Page helpers ------------------------------------------------------------------------------

export async function openAnswerApp(query = "") {
  const view = renderApp(`/cases/${CASE_ID}/answer${query}`);
  await screen.findByRole("heading", { name: tr("en", "answer.setup.title") });
  return view;
}

/** Fills the "who is answering" screen and starts. `roleKey` is an answerer role. */
export async function startAs(role: "operating_surgeon" | "reviewer" | "dev_team_simulated", name = "Dr Test", lang: Lang = "en") {
  const user = userEvent.setup();
  const roles = screen.getByRole("group", { name: tr(lang, "answer.setup.role") });
  await user.click(within(roles).getByRole("radio", { name: new RegExp(`^${escape(tr(lang, `answer.setup.roleOption.${role}`))}`) }));
  const input = screen.getByLabelText(tr(lang, "answer.setup.name"));
  await user.clear(input);
  await user.type(input, name);
  await user.click(screen.getByRole("button", { name: tr(lang, "answer.setup.start") }));
  await waitFor(() => expect(currentCard()).not.toBeNull());
  return user;
}

export function escape(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The question card on screen (it carries `data-question-id`), or null. */
export function currentCard(): HTMLElement | null {
  return document.querySelector<HTMLElement>("[data-question-id]");
}

export function cardQuestionId(): string | null {
  return currentCard()?.getAttribute("data-question-id") ?? null;
}

export function modeButtons(lang: Lang = "en"): HTMLElement[] {
  const group = screen.getByRole("group", { name: tr(lang, "answer.modes") });
  return within(group).getAllByRole("button");
}

export function modeButton(mode: "tap" | "voice" | "text", lang: Lang = "en"): HTMLElement {
  const group = screen.getByRole("group", { name: tr(lang, "answer.modes") });
  return within(group).getByRole("button", { name: new RegExp(escape(tr(lang, `answer.mode.${mode}`))) });
}

/** Answers the current card by text and waits for the read-back. */
export async function answerByText(user: ReturnType<typeof userEvent.setup>, text: string, lang: Lang = "en") {
  await user.click(modeButton("text", lang));
  const box = screen.getByLabelText(tr(lang, "answer.text.label"));
  await user.type(box, text);
  const panel = screen.getByTestId("text-panel");
  await user.click(within(panel).getByRole("button", { name: tr(lang, "answer.text.send") }));
}

export function readback(): HTMLElement {
  return screen.getByTestId("readback");
}

export function confirmButton(lang: Lang = "en"): HTMLElement {
  return within(readback()).getByRole("button", { name: tr(lang, "answer.readback.confirm") });
}

export async function flush() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
}
