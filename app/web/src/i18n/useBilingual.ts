import { useCallback } from "react";
import { useTranslation } from "react-i18next";

import type { Bilingual, Lang } from "@contracts/contracts";

import { isLang } from "./index";

/** The current UI language as a contract `Lang` (`ja` | `en`). */
export function useLang(): Lang {
  const { i18n } = useTranslation();
  const lang = i18n.resolvedLanguage ?? i18n.language;
  return isLang(lang) ? lang : "en";
}

/** A picker for bilingual content fields from the API: `(b) => b[currentLang]`. */
export function useBilingual(): (b: Bilingual) => string {
  const lang = useLang();
  return useCallback((b: Bilingual) => b[lang], [lang]);
}
