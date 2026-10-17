/**
 * Criterion 14 (new at 00ce6e4, from Tester 2's spec gap): "The J1 card and the case page show the
 * seed-record count (`counts.seed_records`), localised in JA and EN."
 *
 * Sources: the re-test brief (criterion 14), plan §2.10 J1, app/server/README.md (`CaseSummary.counts`
 * has `seed_records`), app/web/CLAUDE.md rule 3 (all UI text through i18n keys, both ja and en;
 * the toggle switches instantly, with no reload).
 */
import { act, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import i18n from "@/i18n";
import en from "@/i18n/en.json";
import ja from "@/i18n/ja.json";

import {
  fixture,
  fixtureSummary,
  flatten,
  installFakeMedia,
  mockServer,
  renderApp,
  secondSummary,
  standardRoutes,
  type Summary,
} from "./harness";

const flat = { en: flatten(en), ja: flatten(ja) } as const;
const tr = (lang: "en" | "ja", key: string) => {
  const value = flat[lang][key];
  if (typeof value !== "string" || value.trim() === "") throw new Error(`no ${lang} resource ${key}`);
  return value;
};
const KEY = "case.seedRecords";

async function cardOf(summary: Summary, lang: "en" | "ja"): Promise<HTMLElement> {
  const link = await screen.findByRole("link", { name: summary.case.title[lang] });
  const card = link.closest("li");
  if (!card) throw new Error("the case title is not inside a list item");
  return card;
}

/** The seed-record label is shown in `root`, with the count next to it (same small group). */
function expectSeedCount(root: HTMLElement, count: number, lang: "en" | "ja") {
  const terms = within(root).getAllByText(tr(lang, KEY));
  const withCount = terms.filter((term) =>
    new RegExp(`(?<!\\d)${count}(?!\\d)`).test(term.parentElement?.textContent ?? ""),
  );
  expect(withCount.length, `${lang}: "${tr(lang, KEY)}" next to ${count}`).toBeGreaterThan(0);
  const other = lang === "en" ? "ja" : "en";
  if (tr(other, KEY) !== tr(lang, KEY)) {
    expect(within(root).queryAllByText(tr(other, KEY)), `no ${other} label in ${lang}`).toHaveLength(0);
  }
}

let restoreMedia: () => void;
beforeEach(() => {
  restoreMedia = installFakeMedia(fixture.case.duration_s);
});
afterEach(() => restoreMedia());

describe("Criterion 14: seed-record count", () => {
  it("the label exists in both languages and differs (localised, not English-only)", () => {
    expect(tr("ja", KEY)).not.toBe(tr("en", KEY));
  });

  it("each J1 card shows counts.seed_records with its label (EN)", async () => {
    const cases = [fixtureSummary(), secondSummary()];
    mockServer(standardRoutes(cases));
    renderApp("/");
    for (const summary of cases) {
      expectSeedCount(await cardOf(summary, "en"), summary.counts.seed_records, "en");
    }
  });

  it("each J1 card shows counts.seed_records with its Japanese label after the toggle", async () => {
    const cases = [fixtureSummary(), secondSummary()];
    mockServer(standardRoutes(cases));
    renderApp("/");
    await cardOf(cases[0]!, "en");
    await act(() => i18n.changeLanguage("ja"));
    for (const summary of cases) {
      expectSeedCount(await cardOf(summary, "ja"), summary.counts.seed_records, "ja");
    }
  });

  it("the J1 card shows the count the server sends (not a count of its own)", async () => {
    const summary = { ...secondSummary(), counts: { ...secondSummary().counts, seed_records: 37 } };
    mockServer(standardRoutes([summary]));
    renderApp("/");
    expectSeedCount(await cardOf(summary, "en"), 37, "en");
  });

  it("the case page shows counts.seed_records with its label (EN)", async () => {
    mockServer(standardRoutes());
    const view = renderApp("/cases/case-fixture-01");
    await screen.findByRole("heading", { level: 1, name: fixture.case.title.en });
    expectSeedCount(view.container, fixtureSummary().counts.seed_records, "en");
  });

  it("the case page shows counts.seed_records with its Japanese label after the toggle", async () => {
    mockServer(standardRoutes());
    const view = renderApp("/cases/case-fixture-01");
    await screen.findByRole("heading", { level: 1, name: fixture.case.title.en });
    await act(() => i18n.changeLanguage("ja"));
    await screen.findByRole("heading", { level: 1, name: fixture.case.title.ja });
    expectSeedCount(view.container, fixtureSummary().counts.seed_records, "ja");
  });
});
