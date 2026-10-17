/**
 * Disclaimer acceptance, J16 rule (brief criterion 11).
 *
 * Sources: plan §2.10 J16 ("Education/reference, not clinical advice"; "Demo data" badges),
 * app/web/CLAUDE.md rule 6 ("Disclaimer banner is always visible. Show 'Demo data' … badges"),
 * root CLAUDE.md product guardrails ("Education and reference only"), D-009 (JA + EN).
 */
import { act, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import i18n from "@/i18n";
import en from "@/i18n/en.json";
import ja from "@/i18n/ja.json";

import { fixture, flatten, json, mockServer, renderApp, standardRoutes } from "./harness";

const flat = { en: flatten(en), ja: flatten(ja) } as const;
const CJK = /[぀-ヿ㐀-鿿]/;

/** The resource values that carry the disclaimer and the badge, found by meaning (not by key). */
function disclaimerTexts(lang: "en" | "ja") {
  const values = Object.entries(flat[lang]).map(([k, v]) => [k, String(v)] as const);
  if (lang === "en") {
    const text = values.find(([, v]) => /not clinical advice/i.test(v) && /education/i.test(v) && /reference/i.test(v));
    const badge = values.find(([, v]) => /^demo data$/i.test(v.trim()));
    return { key: text?.[0], text: text?.[1], badgeKey: badge?.[0], badge: badge?.[1] };
  }
  return { key: undefined, text: undefined, badgeKey: undefined, badge: undefined };
}

const enTexts = disclaimerTexts("en");

describe("J16 disclaimer", () => {
  it("EN resources carry 'Education/reference, not clinical advice' and 'Demo data'; JA has both translated", () => {
    expect(enTexts.text, "an en string saying education/reference, not clinical advice").toBeDefined();
    expect(enTexts.badge, "an en string 'Demo data'").toBeDefined();
    const jaText = String(flat.ja[enTexts.key!]);
    const jaBadge = String(flat.ja[enTexts.badgeKey!]);
    expect(jaText).toMatch(CJK);
    expect(jaBadge).toMatch(CJK);
    // The Japanese text says "education/reference" and "not clinical advice".
    expect(jaText).toMatch(/教育/);
    expect(jaText).toMatch(/臨床/);
  });

  const pages: [string, () => void][] = [
    ["/", () => mockServer(standardRoutes())],
    ["/cases/case-fixture-01", () => mockServer(standardRoutes())],
    ["/cases/no-such-case", () => mockServer(standardRoutes())],
    ["/no/such/page", () => mockServer(standardRoutes())],
    [
      "/ (server unreachable)",
      () =>
        vi.stubGlobal(
          "fetch",
          vi.fn(async () => {
            throw new TypeError("Failed to fetch");
          }),
        ),
    ],
    ["/ (loading)", () => vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)))],
    ["/ (empty)", () => mockServer({ "/api/cases": () => json({ cases: [] }) })],
  ];

  it.each(pages)("is visible on %s in both languages", async (label, serve) => {
    serve();
    const path = label.split(" ")[0]!;
    renderApp(path);
    if (path === "/cases/case-fixture-01") {
      await screen.findByRole("heading", { level: 1, name: fixture.case.title.en });
    }
    for (const lang of ["en", "ja"] as const) {
      await act(() => i18n.changeLanguage(lang));
      const text = String(flat[lang][enTexts.key!]);
      const badge = String(flat[lang][enTexts.badgeKey!]);
      const textEls = await screen.findAllByText(
        (_, el) => el?.textContent?.trim().endsWith(text) === true && el.children.length <= 1,
      );
      expect(textEls[0]).toBeVisible();
      const badgeEls = screen.getAllByText(badge);
      expect(badgeEls[0]).toBeVisible();
    }
  });
});
