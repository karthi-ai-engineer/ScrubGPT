/**
 * J1 acceptance: Home / case list (brief criterion 8).
 *
 * Sources: plan §2.10 J1 ("Case list with source, language, status and trust badges"), §6 Dev2
 * Block 1 (milestone "Fixture case browsable in JA and EN"), app/web/CLAUDE.md rules 3 and 5
 * (i18n keys; every piece of knowledge shows its trust label), plan §4.1 TrustLabel (emoji),
 * app/web/README.md (Home lists the case cards; without the server a "can't reach the app server"
 * message with a retry button), the brief (source, language, video type, narration, status,
 * duration, counts, trust badges, data note; localised loading, empty and unreachable states).
 */
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { TrustLabel } from "@contracts/contracts";

import { AppProviders } from "@/app/App";
import { TrustBadge } from "@/components/TrustBadge";
import i18n from "@/i18n";
import en from "@/i18n/en.json";
import ja from "@/i18n/ja.json";

import {
  fixture,
  fixtureSummary,
  flatten,
  json,
  mockServer,
  renderApp,
  secondSummary,
  SPEC_EMOJI,
  standardRoutes,
  TRUST_ORDER,
  type Summary,
} from "./harness";

const flat = { en: flatten(en), ja: flatten(ja) } as const;
const tr = (lang: "en" | "ja", key: string) => {
  const value = flat[lang][key];
  if (typeof value !== "string") throw new Error(`no ${lang} resource ${key}`);
  return value;
};

/** The card (list item) of a case, found through its title link. */
async function cardOf(summary: Summary, lang: "en" | "ja"): Promise<HTMLElement> {
  const link = await screen.findByRole("link", { name: summary.case.title[lang] });
  const card = link.closest("li");
  if (!card) throw new Error("the case title is not inside a list item");
  return card;
}

function expectCardFacts(card: HTMLElement, summary: Summary, lang: "en" | "ja") {
  const c = within(card);
  const s = summary.case;
  // Source, language, video type, narration, status (localised enum names).
  expect(c.getAllByText(tr(lang, `source.${s.source}`)).length).toBeGreaterThan(0);
  expect(c.getAllByText(tr(lang, `caseLanguage.${s.language}`)).length).toBeGreaterThan(0);
  expect(c.getAllByText(tr(lang, `videoType.${s.video_type}`)).length).toBeGreaterThan(0);
  expect(c.getAllByText(tr(lang, s.narrated ? "case.narrated" : "case.notNarrated")).length).toBeGreaterThan(0);
  expect(c.getAllByText(tr(lang, `caseStatus.${s.status}`)).length).toBeGreaterThan(0);
  // Field labels are shown too.
  for (const key of ["case.source", "case.language", "case.videoType", "case.narration", "case.status", "case.duration"]) {
    expect(c.getAllByText(tr(lang, key)).length, key).toBeGreaterThan(0);
  }
  // Data note in the current language.
  expect(c.getByText(s.data_note[lang])).toBeInTheDocument();
}

describe("J1 home", () => {
  it("lists every case from /api/cases (one card each)", async () => {
    const cases = [fixtureSummary(), secondSummary()];
    mockServer(standardRoutes(cases));
    renderApp("/");
    for (const summary of cases) {
      const card = await cardOf(summary, "en");
      expect(within(card).getByRole("link", { name: summary.case.title.en })).toHaveAttribute(
        "href",
        `/cases/${summary.case.id}`,
      );
    }
  });

  it("each card shows source, language, video type, narration, status and the data note (EN)", async () => {
    const cases = [fixtureSummary(), secondSummary()];
    mockServer(standardRoutes(cases));
    renderApp("/");
    for (const summary of cases) expectCardFacts(await cardOf(summary, "en"), summary, "en");
  });

  it("each card shows the same facts in Japanese after the toggle", async () => {
    const cases = [fixtureSummary(), secondSummary()];
    mockServer(standardRoutes(cases));
    renderApp("/");
    await cardOf(cases[0]!, "en");
    await act(() => i18n.changeLanguage("ja"));
    for (const summary of cases) expectCardFacts(await cardOf(summary, "ja"), summary, "ja");
  });

  it("each card shows the duration (300 s and 4512 s)", async () => {
    const cases = [fixtureSummary(), secondSummary()];
    mockServer(standardRoutes(cases));
    renderApp("/");
    expect((await cardOf(cases[0]!, "en")).textContent).toMatch(/(?<!\d)0?5:00(?!\d)|5\s*min/);
    expect((await cardOf(cases[1]!, "en")).textContent).toMatch(/1:15:12|75:12|1\s*h\s*15\s*min/);
  });

  it("each card shows the moment and question counts with their labels", async () => {
    const cases = [fixtureSummary(), secondSummary()];
    mockServer(standardRoutes(cases));
    renderApp("/");
    for (const summary of cases) {
      const card = await cardOf(summary, "en");
      const pairs: [string, number][] = [
        ["case.moments", summary.counts.moments],
        ["case.operatingQuestions", summary.counts.operating_questions],
        ["case.reviewerQuestions", summary.counts.reviewer_questions],
      ];
      for (const [key, count] of pairs) {
        const term = within(card).getByText(tr("en", key));
        // The number is shown next to its label (same small group).
        expect(term.parentElement?.textContent ?? "", key).toContain(String(count));
      }
    }
  });

  it("each card shows a trust badge (emoji + localised name) for every label in trust_labels", async () => {
    const cases = [fixtureSummary(), secondSummary()];
    mockServer(standardRoutes(cases));
    renderApp("/");
    for (const summary of cases) {
      const card = await cardOf(summary, "en");
      for (const label of summary.trust_labels) {
        const name = within(card).getByText(tr("en", `trust.${label}`));
        const badge = name.parentElement;
        expect(badge?.textContent ?? "", label).toContain(SPEC_EMOJI[label]);
      }
    }
  });

  it("loading state is localised", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
    renderApp("/");
    expect(await screen.findByText(tr("en", "status.loading"))).toBeInTheDocument();
    await act(() => i18n.changeLanguage("ja"));
    expect(screen.getByText(tr("ja", "status.loading"))).toBeInTheDocument();
  });

  it("empty state is localised", async () => {
    mockServer({ "/api/cases": () => json({ cases: [] }) });
    renderApp("/");
    expect(await screen.findByText(tr("en", "home.empty"))).toBeInTheDocument();
    await act(() => i18n.changeLanguage("ja"));
    expect(screen.getByText(tr("ja", "home.empty"))).toBeInTheDocument();
  });

  it("server unreachable: a localised message and a retry that recovers", async () => {
    let up = false;
    const spy = vi.fn(async (input: RequestInfo | URL) => {
      if (!up) throw new TypeError("Failed to fetch");
      const path = new URL(String(input), "http://localhost").pathname;
      return path === "/api/cases" ? json({ cases: [fixtureSummary()] }) : json({}, 404);
    });
    vi.stubGlobal("fetch", spy);
    const user = userEvent.setup();
    renderApp("/");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(tr("en", "errors.network.title"));
    await act(() => i18n.changeLanguage("ja"));
    expect(alert).toHaveTextContent(tr("ja", "errors.network.title"));
    await act(() => i18n.changeLanguage("en"));

    up = true;
    await user.click(within(alert).getByRole("button", { name: tr("en", "status.retry") }));
    expect(await screen.findByRole("link", { name: fixture.case.title.en })).toBeInTheDocument();
  });

  it("a 502 from the dev proxy (app server down) is shown as unreachable too", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("Bad Gateway", { status: 502 })));
    renderApp("/");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(tr("en", "errors.network.title"));
    expect(within(alert).getByRole("button", { name: tr("en", "status.retry") })).toBeInTheDocument();
  });
});

describe("Trust badges (plan §4.1, CLAUDE.md rule 5)", () => {
  it.each(TRUST_ORDER.map((label) => [label]))("%s: spec emoji + localised name in EN and JA", async (label) => {
    const view = render(
      <AppProviders>
        <TrustBadge label={label as TrustLabel} />
      </AppProviders>,
    );
    expect(view.container).toHaveTextContent(SPEC_EMOJI[label as TrustLabel]);
    expect(view.container).toHaveTextContent(tr("en", `trust.${label}`));
    await act(() => i18n.changeLanguage("ja"));
    expect(view.container).toHaveTextContent(SPEC_EMOJI[label as TrustLabel]);
    expect(view.container).toHaveTextContent(tr("ja", `trust.${label}`));
    expect(tr("ja", `trust.${label}`)).not.toBe(tr("en", `trust.${label}`));
  });
});
