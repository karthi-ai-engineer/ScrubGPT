import type { TrustLabel } from "@contracts/contracts";

import type { AnswererRole } from "./fields";

/** Who is answering: their role (sent as `answerer_role`) and the "confirmed by" name. */
export interface Answerer {
  role: AnswererRole;
  name: string;
}

/**
 * The demo default is role-play 🧪 (`dev_team_simulated`): the surgeon joins later (D-005), so
 * nothing looks surgeon-confirmed by accident.
 */
export const DEFAULT_ROLE: AnswererRole = "dev_team_simulated";

export const NAME_STORAGE_KEY = "scrubgpt.answer.confirmedBy";

/** The remembered "confirmed by" name; `""` when there is none or storage is blocked. */
export function readStoredName(): string {
  try {
    return window.localStorage.getItem(NAME_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function writeStoredName(name: string): void {
  try {
    window.localStorage.setItem(NAME_STORAGE_KEY, name);
  } catch {
    // The name still works for this page view without storage.
  }
}

/** The trust label each role's records get (brain_api.md `/extract`: `provenance.trust_label`). */
export const ROLE_TRUST: Readonly<Record<AnswererRole, TrustLabel>> = {
  operating_surgeon: "operating_surgeon",
  reviewer: "reviewer",
  dev_team_simulated: "simulated",
};

/** What the surgeon typed on a card; kept by the deck so it survives "later" and failures. */
export interface CardNotes {
  text: string;
  tapEdit: string;
}

export const EMPTY_NOTES: CardNotes = { text: "", tapEdit: "" };
