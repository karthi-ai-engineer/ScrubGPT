/**
 * J15 acceptance: JA/EN everywhere, switchable instantly (brief criterion 7).
 *
 * Sources: plan §2.10 J15 ("everywhere, switchable instantly"), app/web/CLAUDE.md rule 3 ("All UI
 * text goes through i18n keys, and both ja and en are required. The language toggle switches
 * instantly, with no reload"), root CLAUDE.md ("No English-only UI strings or content"; Bilingual
 * fields), app/web/README.md (toggle sets `<html lang>` and remembers the choice in localStorage;
 * content fields follow the language), D-009.
 */
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import i18n from "@/i18n";
import en from "@/i18n/en.json";
import ja from "@/i18n/ja.json";

import {
  bilingualTexts,
  fixture,
  fixtureDetail,
  flatten,
  mockServer,
  renderApp,
  secondSummary,
  fixtureSummary,
  standardRoutes,
  stepName,
  visibleStrings,
} from "./harness";

const enFlat = flatten(en);
const jaFlat = flatten(ja);
const CJK = /[぀-ヿ㐀-鿿＀-￯]/;

function toggleButton(lang: "JA" | "EN"): HTMLElement {
  const button = screen.getAllByRole("button").find((b) => b.textContent?.trim() === lang);
  if (!button) throw new Error(`no ${lang} toggle button`);
  return button;
}

function placeholders(value: string): string[] {
  return [...value.matchAll(/\{\{\s*([\w.]+)\s*\}\}/g)].map((m) => m[1] ?? "").sort();
}

describe("J15 resources", () => {
  it("ja and en resources have identical keys (CLAUDE.md rule 3: both ja and en are required)", () => {
    expect(Object.keys(jaFlat).sort()).toEqual(Object.keys(enFlat).sort());
  });

  it("every ja and en value is a non-empty string", () => {
    for (const [key, value] of [...Object.entries(jaFlat), ...Object.entries(enFlat)]) {
      expect(typeof value, key).toBe("string");
      expect((value as string).trim().length, key).toBeGreaterThan(0);
    }
  });

  it("ja and en values use the same interpolation placeholders", () => {
    for (const key of Object.keys(enFlat)) {
      expect(placeholders(String(jaFlat[key])), key).toEqual(placeholders(String(enFlat[key])));
    }
  });

  it("the ja resource is actually Japanese where the en text is a sentence", () => {
    // A Japanese UI string must not just copy the English one (D-009).
    const untranslated = Object.keys(enFlat).filter((key) => {
      const e = String(enFlat[key]);
      return e.split(" ").length >= 3 && e === String(jaFlat[key]);
    });
    expect(untranslated).toEqual([]);
  });
});

describe("J15 toggle", () => {
  it("switches instantly with no reload: same DOM, no refetch, <html lang> set", async () => {
    const fetchSpy = mockServer(standardRoutes());
    const user = userEvent.setup();
    renderApp("/");
    await screen.findByRole("link", { name: fixture.case.title.en });
    expect(document.documentElement.lang).toBe("en");
    const heading = screen.getByRole("heading", { level: 1 });
    const calls = fetchSpy.mock.calls.length;

    await user.click(toggleButton("JA"));

    expect(document.documentElement.lang).toBe("ja");
    expect(heading.isConnected).toBe(true); // the page was not reloaded or re-mounted
    expect(heading).toHaveTextContent(jaFlat["home.title"] as string);
    expect(screen.getByRole("link", { name: fixture.case.title.ja })).toBeInTheDocument();
    expect(screen.queryByText(fixture.case.title.en)).not.toBeInTheDocument();
    expect(fetchSpy.mock.calls.length).toBe(calls);
    expect(toggleButton("JA")).toHaveAttribute("aria-pressed", "true");
    expect(toggleButton("EN")).toHaveAttribute("aria-pressed", "false");

    await user.click(toggleButton("EN"));
    expect(document.documentElement.lang).toBe("en");
    expect(heading.isConnected).toBe(true);
    expect(heading).toHaveTextContent(enFlat["home.title"] as string);
    expect(screen.getByRole("link", { name: fixture.case.title.en })).toBeInTheDocument();
    expect(toggleButton("EN")).toHaveAttribute("aria-pressed", "true");
  });

  it("persists the choice across a reload (localStorage → the initial language)", async () => {
    mockServer(standardRoutes());
    const user = userEvent.setup();
    renderApp("/");
    await screen.findByRole("link", { name: fixture.case.title.en });
    await user.click(toggleButton("JA"));

    // A reload re-runs the i18n module from scratch with the same localStorage.
    vi.resetModules();
    const fresh = await import("@/i18n");
    expect(fresh.default.language).toBe("ja");
    expect(fresh.detectInitialLanguage()).toBe("ja");

    await user.click(toggleButton("EN"));
    vi.resetModules();
    const again = await import("@/i18n");
    expect(again.default.language).toBe("en");
  });

  it("content fields (Bilingual) follow the current language on the case page", async () => {
    mockServer(standardRoutes());
    const user = userEvent.setup();
    renderApp("/cases/case-fixture-01");
    await screen.findByRole("heading", { level: 1, name: fixture.case.title.en });
    const firstMoment = fixture.moments.moments[0]!;
    expect(screen.getByText(firstMoment.title.en)).toBeInTheDocument();
    expect(screen.getByText(fixture.case.data_note.en)).toBeInTheDocument();

    await user.click(toggleButton("JA"));

    expect(screen.getByRole("heading", { level: 1, name: fixture.case.title.ja })).toBeInTheDocument();
    expect(screen.getByText(firstMoment.title.ja)).toBeInTheDocument();
    expect(screen.queryByText(firstMoment.title.en)).not.toBeInTheDocument();
    expect(screen.getByText(fixture.case.data_note.ja)).toBeInTheDocument();
  });
});

describe("J15 no hard-coded UI strings", () => {
  const jaLatin = new Set<string>();
  const addLatin = (text: string) => {
    for (const w of text.match(/[A-Za-z]{3,}/g) ?? []) jaLatin.add(w.toLowerCase());
  };
  Object.values(jaFlat).forEach((v) => addLatin(String(v)));
  const jaContent = [
    ...bilingualTexts(fixtureDetail(), "ja"),
    ...bilingualTexts(fixture.reference, "ja"),
    ...bilingualTexts(secondSummary(), "ja"),
  ];
  jaContent.forEach(addLatin);
  // Identifiers shown verbatim (case ids, also an unknown id from the URL) are data, not UI text.
  ["case-fixture-01", "yt-en-03", "unknown-case"].forEach(addLatin);

  const enCjk = new Set<string>();
  Object.values(enFlat).forEach((v) => {
    for (const c of String(v)) if (CJK.test(c)) enCjk.add(c);
  });

  async function pagesIn(lang: "ja" | "en", check: (strings: string[], page: string) => void) {
    await act(() => i18n.changeLanguage(lang));
    const pages: [string, () => Promise<unknown>][] = [
      ["/", () => screen.findByRole("link", { name: fixture.case.title[lang] })],
      ["/cases/case-fixture-01", () => screen.findAllByText(fixture.moments.moments[0]!.title[lang])],
      ["/no/such/page", () => screen.findByRole("heading", { level: 1 })],
      ["/cases/unknown-case", () => screen.findByRole("alert")],
    ];
    for (const [path, ready] of pages) {
      mockServer(standardRoutes([fixtureSummary(), secondSummary()]));
      const view = renderApp(path);
      await ready();
      if (path === "/cases/case-fixture-01") {
        // Wait for the reference so step names are rendered.
        const name = stepName(fixture.moments.moments[0]!.step_id)[lang];
        await waitFor(() => expect(view.container.textContent).toContain(name));
      }
      check(visibleStrings(view.container), path);
      view.unmount();
    }
  }

  it("in Japanese, no English UI text appears (every Latin word comes from ja resources or data)", async () => {
    await pagesIn("ja", (strings, page) => {
      const offenders = strings.filter((s) =>
        (s.match(/[A-Za-z]{3,}/g) ?? []).some((w) => !jaLatin.has(w.toLowerCase())),
      );
      expect(offenders, page).toEqual([]);
    });
  });

  it("in English, no Japanese UI text appears (except what the en resources themselves contain)", async () => {
    await pagesIn("en", (strings, page) => {
      const offenders = strings.filter((s) => [...s].some((c) => CJK.test(c) && !enCjk.has(c)));
      expect(offenders, page).toEqual([]);
    });
  });

  it("the error state is localised in both languages", async () => {
    for (const lang of ["en", "ja"] as const) {
      await act(() => i18n.changeLanguage(lang));
      const flat = lang === "en" ? enFlat : jaFlat;
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => {
          throw new TypeError("Failed to fetch");
        }),
      );
      const view = renderApp("/");
      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(flat["errors.network.title"] as string);
      expect(within(alert).getByRole("button", { name: flat["status.retry"] as string })).toBeInTheDocument();
      view.unmount();
    }
  });
});
