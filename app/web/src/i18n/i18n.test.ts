import { afterEach, describe, expect, it, vi } from "vitest";

import en from "./en.json";
import i18n, { detectInitialLanguage, LANG_STORAGE_KEY, setLanguage } from "./index";
import ja from "./ja.json";

/** Flattens nested resources to `a.b.c` → value. */
function flatten(obj: object, prefix = ""): Map<string, unknown> {
  const out = new Map<string, unknown>();
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === "object") {
      for (const [k, v] of flatten(value as object, path)) out.set(k, v);
    } else {
      out.set(path, value);
    }
  }
  return out;
}

describe("i18n resources", () => {
  const jaKeys = flatten(ja);
  const enKeys = flatten(en);

  it("ja and en have identical key sets", () => {
    expect([...jaKeys.keys()].sort()).toEqual([...enKeys.keys()].sort());
    expect(jaKeys.size).toBeGreaterThan(0);
  });

  it.each([
    ["ja", jaKeys],
    ["en", enKeys],
  ] as const)("every %s value is a non-empty string", (_lang, keys) => {
    for (const [key, value] of keys) {
      expect(typeof value, key).toBe("string");
      expect((value as string).trim(), key).not.toBe("");
    }
  });

  it("uses the same interpolation variables in both languages", () => {
    const vars = (s: unknown) => [...String(s).matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort();
    for (const [key, value] of enKeys) {
      expect(vars(jaKeys.get(key)), key).toEqual(vars(value));
    }
  });

  it("has the J16 disclaimer in both languages", () => {
    expect(ja.disclaimer.text).toBe("教育・参考用です。臨床上の助言ではありません。");
    expect(en.disclaimer.text).toBe("Education and reference only — not clinical advice.");
  });
});

describe("detectInitialLanguage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("prefers the stored language", () => {
    window.localStorage.setItem(LANG_STORAGE_KEY, "ja");
    expect(detectInitialLanguage()).toBe("ja");
    window.localStorage.setItem(LANG_STORAGE_KEY, "en");
    expect(detectInitialLanguage()).toBe("en");
  });

  it("ignores an invalid stored value and falls back to the browser language", () => {
    window.localStorage.setItem(LANG_STORAGE_KEY, "fr");
    vi.spyOn(navigator, "language", "get").mockReturnValue("ja-JP");
    expect(detectInitialLanguage()).toBe("ja");
  });

  it("uses Japanese for a Japanese browser and English otherwise", () => {
    const spy = vi.spyOn(navigator, "language", "get");
    spy.mockReturnValue("ja");
    expect(detectInitialLanguage()).toBe("ja");
    spy.mockReturnValue("en-GB");
    expect(detectInitialLanguage()).toBe("en");
    spy.mockReturnValue("de-DE");
    expect(detectInitialLanguage()).toBe("en");
  });

  it("works when storage throws", async () => {
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
      clear: () => undefined,
    };
    vi.stubGlobal("localStorage", broken);
    vi.spyOn(navigator, "language", "get").mockReturnValue("ja-JP");
    expect(detectInitialLanguage()).toBe("ja");
    expect(() => setLanguage("ja")).not.toThrow();
    await vi.waitFor(() => expect(i18n.language).toBe("ja"));
    expect(document.documentElement.lang).toBe("ja");
  });
});
