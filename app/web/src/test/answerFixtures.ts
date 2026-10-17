/**
 * Answer-app test data built from the contract fixture case (`case-fixture-01`), in the app
 * server's shapes (app/server README, API table) and the contract's `ExtractResponse`.
 */
import type { Bilingual, Chip, DecisionRecord, DecisionRecordDraft, ExtractResponse } from "@contracts/contracts";

import type { AnswerQueue, DraftResponse, QueueRole } from "@/api/types";

import { fixtureDetail } from "./fixtures";

export const CASE = fixtureDetail.case.id;
export const ANSWER_ID = "01a1436a-0000-7000-8000-000000000001";

/** `GET /api/cases/{id}/answer-queue?role=` for the fixture (nothing answered yet). */
export function fixtureQueue(role: QueueRole, answered: readonly string[] = []): AnswerQueue {
  const questions = role === "operating" ? fixtureDetail.questions.operating : fixtureDetail.questions.reviewer;
  const moments = new Map(fixtureDetail.moments.moments.map((m) => [m.id, m]));
  return {
    case_id: CASE,
    role,
    est_seconds: questions.filter((q) => !answered.includes(q.id)).reduce((sum, q) => sum + q.est_seconds, 0),
    questions: questions.map((question) => {
      const moment = moments.get(question.moment_id);
      if (!moment) throw new Error(`no moment ${question.moment_id}`);
      return {
        question,
        moment,
        clip: `/media/cases/${CASE}/${moment.clip}`,
        poster: `/media/cases/${CASE}/${moment.poster}`,
        answered: answered.includes(question.id),
      };
    }),
  };
}

const seed = fixtureDetail.seed_records.records[0] as DecisionRecord;

/**
 * A `DecisionRecordDraft` for `questionId`, based on the m01.q1 seed record. `only` keeps just the
 * named Bilingual fields filled (the rest null / empty), like the fake Brain's generic draft.
 */
export function draftFor(
  questionId: string,
  options: { only?: readonly ("situation_cue.text" | "action.text" | "reason")[]; trust?: DecisionRecordDraft["provenance"]["trust_label"] } = {},
): DecisionRecordDraft {
  const keep = (path: "situation_cue.text" | "action.text" | "reason") => !options.only || options.only.includes(path);
  const momentId = questionId.replace(/\.[qr]\d+$/, "");
  const trust = options.trust ?? "simulated";
  return {
    ...seed,
    id: null,
    moment_id: momentId,
    question_id: questionId,
    situation_cue: keep("situation_cue.text") ? seed.situation_cue : { text: null, cue_terms: [] },
    action: keep("action.text") ? seed.action : { type: "act", text: null, actor: "unknown" },
    reason: keep("reason") ? seed.reason : null,
    alternatives: options.only ? [] : seed.alternatives,
    immediate_result: options.only ? null : seed.immediate_result,
    obstacle: options.only ? null : seed.obstacle,
    grounding: seed.grounding.filter((g) => !options.only || options.only.some((p) => g.field === p)),
    provenance: {
      trust_label: trust,
      attributed_to: trust === "simulated" ? "dev_team_simulated" : trust === "reviewer" ? "reviewer" : "operating_surgeon",
      generated_by: seed.provenance.generated_by,
      confirmed_by: null,
      confirmed_at: null,
    },
  };
}

const CHIP_PATHS = ["situation_cue.text", "action.text", "reason", "immediate_result"] as const;

/** The `ExtractResponse` for a draft: a chip per filled field, the null ones in `missing_fields`. */
export function extractFor(draft: DecisionRecordDraft, extraMissing: readonly string[] = []): ExtractResponse {
  const values: Record<(typeof CHIP_PATHS)[number], Bilingual | null> = {
    "situation_cue.text": draft.situation_cue.text,
    "action.text": draft.action.text,
    reason: draft.reason,
    immediate_result: draft.immediate_result,
  };
  const chips: Chip[] = CHIP_PATHS.flatMap((field) => {
    const value = values[field];
    return value ? [{ field, value, editable: true }] : [];
  });
  draft.alternatives.forEach((alt, i) => {
    chips.push({ field: `alternatives[${i}].option`, value: alt.option, editable: true });
    if (alt.why_not) chips.push({ field: `alternatives[${i}].why_not`, value: alt.why_not, editable: true });
  });
  const missing = [
    ...CHIP_PATHS.filter((field) => values[field] === null),
    ...(draft.obstacle === null ? ["obstacle"] : []),
    ...(draft.alternatives.length === 0 ? ["alternatives"] : []),
    ...extraMissing,
  ];
  return {
    contract_version: "1.0",
    draft,
    readback: {
      ja: draft.action.text ? `対応：${draft.action.text.ja}。` : "（模擬）回答から記録できる内容はまだありません。",
      en: draft.action.text ? `Action: ${draft.action.text.en}.` : "(Mock) Nothing to record from the answer yet.",
    },
    chips,
    missing_fields: missing,
  };
}

export function draftResponse(extract: ExtractResponse, answerId = ANSWER_ID): DraftResponse {
  return { answer_id: answerId, extract };
}

/** The stored record the server returns on Confirm. */
export function confirmedRecord(draft: DecisionRecordDraft, id: string, confirmedBy: string): DecisionRecord {
  return {
    ...draft,
    id,
    situation_cue: { text: draft.situation_cue.text ?? { ja: "手がかり", en: "Cue" }, cue_terms: draft.situation_cue.cue_terms },
    action: { ...draft.action, text: draft.action.text ?? { ja: "対応", en: "Action" } },
    provenance: { ...draft.provenance, confirmed_by: confirmedBy, confirmed_at: "2026-10-18T09:00:00Z" },
  };
}

export const brainError = (code: "unavailable" | "timeout") => ({
  status: code === "unavailable" ? 503 : 504,
  body: { contract_version: "1.0", error: { code, message: `${code} (test)`, retryable: true } },
});
