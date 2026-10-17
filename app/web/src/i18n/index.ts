import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import type { Lang } from "@contracts/contracts";

import en from "./en.json";
import ja from "./ja.json";

export const SUPPORTED_LANGS: readonly Lang[] = ["ja", "en"];
export const LANG_STORAGE_KEY = "scrubgpt.lang";

export function isLang(value: unknown): value is Lang {
  return value === "ja" || value === "en";
}

function readStoredLang(): Lang | null {
  try {
    const stored = window.localStorage.getItem(LANG_STORAGE_KEY);
    return isLang(stored) ? stored : null;
  } catch {
    return null; // Storage blocked (private window, previews): fall through.
  }
}

function writeStoredLang(lang: Lang): void {
  try {
    window.localStorage.setItem(LANG_STORAGE_KEY, lang);
  } catch {
    // The toggle still works for this page view without storage.
  }
}

/** The stored choice, else Japanese for a Japanese browser, else English (J15). */
export function detectInitialLanguage(): Lang {
  const stored = readStoredLang();
  if (stored) return stored;
  const browser = typeof navigator === "undefined" ? "" : (navigator.language ?? "");
  return browser.toLowerCase().startsWith("ja") ? "ja" : "en";
}

function applyLang(lang: string): void {
  if (!isLang(lang)) return;
  document.documentElement.lang = lang;
  document.title = i18n.t("app.name", { lng: lang });
}

export const resources = {
  ja: { translation: ja },
  en: { translation: en },
} as const;

i18n.on("languageChanged", applyLang);

void i18n.use(initReactI18next).init({
  resources,
  lng: detectInitialLanguage(),
  fallbackLng: false,
  supportedLngs: [...SUPPORTED_LANGS],
  initAsync: false,
  interpolation: { escapeValue: false }, // React escapes already.
});

/** Switches the UI language instantly (no reload) and remembers the choice. */
export function setLanguage(lang: Lang): void {
  writeStoredLang(lang);
  void i18n.changeLanguage(lang);
}

export default i18n;
