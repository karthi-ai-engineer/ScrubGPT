/**
 * J3 helpers (pure): draft field paths → localised labels, which fields the surgeon can fill in,
 * whether a draft can be confirmed, and who may answer which question (D-066).
 */
import type { DecisionRecordDraft, Lang, Role } from "@contracts/contracts";

import type { FieldEdit, QueueRole } from "@/api/types";

/** The i18n key suffix (`answer.field.<key>`) of each draft field the Answer app names. */
export type FieldKey =
  | "situation_cue"
  | "action"
  | "reason"
  | "alternatives"
  | "alternative_option"
  | "why_not"
  | "immediate_result"
  | "anticipation"
  | "preop_plan"
  | "patient_factors"
  | "obstacle"
  | "other";

/** `situation_cue.text` and `action.text`: a draft can't be confirmed while either is null (D-054). */
export const REQUIRED_TO_CONFIRM = ["situation_cue.text", "action.text"] as const;

/**
 * The fields the surgeon can fill in or correct with their own words: the app server turns each
 * into both languages with a `source: edit` grounding. `obstacle` (a taxonomy choice) and an empty
 * `alternatives` list are reported as "not stated" but can't be typed in here.
 */
const FILLABLE =
  /^(context\.preop_plan|context\.patient_factors\[\d+\]|situation_cue\.text|anticipation|action\.text|reason|immediate_result|alternatives\[\d+\]\.(option|why_not))$/;

export function isFillable(path: string): boolean {
  return FILLABLE.test(path);
}

/** The label key and (for list items after the first) the 1-based item number of a field path. */
export function fieldLabel(path: string): { key: FieldKey; n: number | null } {
  const index = /\[(\d+)\]/.exec(path);
  const n = index ? Number(index[1]) + 1 : null;
  const item = n !== null && n > 1 ? n : null;
  if (path === "situation_cue.text" || path === "situation_cue") return { key: "situation_cue", n: null };
  if (path === "action.text" || path === "action") return { key: "action", n: null };
  if (path === "reason") return { key: "reason", n: null };
  if (path === "alternatives") return { key: "alternatives", n: null };
  if (/^alternatives\[\d+\]\.why_not$/.test(path)) return { key: "why_not", n: item };
  if (/^alternatives\[\d+\](\.option)?$/.test(path)) return { key: "alternative_option", n: item };
  if (path === "immediate_result") return { key: "immediate_result", n: null };
  if (path === "anticipation") return { key: "anticipation", n: null };
  if (path === "context.preop_plan") return { key: "preop_plan", n: null };
  if (path === "context.patient_factors" || /^context\.patient_factors\[\d+\]$/.test(path)) {
    return { key: "patient_factors", n: item };
  }
  if (path === "obstacle" || path.startsWith("obstacle.")) return { key: "obstacle", n: null };
  return { key: "other", n: null };
}

/** The surgeon's words per field path (chip edits and filled missing fields), as typed. */
export type FieldTexts = Readonly<Record<string, string>>;

/** The edits to send on Confirm: every non-blank text, trimmed, in the language it was typed in. */
export function buildEdits(texts: FieldTexts, lang: Lang): FieldEdit[] {
  return Object.entries(texts)
    .map(([field, text]) => ({ field, text: text.trim(), lang }))
    .filter((edit) => edit.text !== "");
}

/** The required fields still empty: null in the draft and not filled in by the surgeon. */
export function missingToConfirm(draft: DecisionRecordDraft, texts: FieldTexts): string[] {
  const filled = (path: string) => (texts[path] ?? "").trim() !== "";
  const values: Record<(typeof REQUIRED_TO_CONFIRM)[number], unknown> = {
    "situation_cue.text": draft.situation_cue.text,
    "action.text": draft.action.text,
  };
  return REQUIRED_TO_CONFIRM.filter((path) => values[path] === null && !filled(path));
}

// ── Who answers (D-059, D-066) ────────────────────────────────────────────────────

/** The roles the Answer app offers. `expert` answers through the reviewer queue later (J10). */
export type AnswererRole = Extract<Role, "operating_surgeon" | "reviewer" | "dev_team_simulated">;

export const ANSWERER_ROLES: readonly AnswererRole[] = ["operating_surgeon", "reviewer", "dev_team_simulated"];

/** The question list a role must use; `null` when the role may answer either (role-play). */
export function forcedQueue(role: AnswererRole): QueueRole | null {
  if (role === "operating_surgeon") return "operating";
  if (role === "reviewer") return "reviewer";
  return null;
}

/** D-066: an operating surgeon answers only `.qN`, a reviewer only `.rN`; role-play and experts either. */
export function canAnswer(role: Role, questionId: string): boolean {
  const operating = /\.q\d+$/.test(questionId);
  const reviewer = /\.r\d+$/.test(questionId);
  if (role === "operating_surgeon") return operating;
  if (role === "reviewer") return reviewer;
  if (role === "dev_team_simulated" || role === "expert") return operating || reviewer;
  return false;
}

export function isQueueRole(value: unknown): value is QueueRole {
  return value === "operating" || value === "reviewer";
}

export function isAnswererRole(value: unknown): value is AnswererRole {
  return value === "operating_surgeon" || value === "reviewer" || value === "dev_team_simulated";
}
