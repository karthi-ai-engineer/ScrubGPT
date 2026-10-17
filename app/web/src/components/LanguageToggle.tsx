import { useTranslation } from "react-i18next";

import type { Lang } from "@contracts/contracts";

import { setLanguage } from "@/i18n";
import { useLang } from "@/i18n/useBilingual";
import { cn } from "@/lib/utils";

const OPTIONS = [
  { lang: "ja", short: "lang.jaShort", name: "lang.jaName" },
  { lang: "en", short: "lang.enShort", name: "lang.enName" },
] as const satisfies readonly { lang: Lang; short: string; name: string }[];

/** JA | EN toggle (J15): switches instantly, no reload, and remembers the choice. */
export function LanguageToggle({ className }: { className?: string }) {
  const { t } = useTranslation();
  const current = useLang();
  return (
    <div
      role="group"
      aria-label={t("lang.groupLabel")}
      className={cn("inline-flex overflow-hidden rounded-md border border-header-foreground/40", className)}
    >
      {OPTIONS.map(({ lang, short, name }, i) => {
        const active = lang === current;
        return (
          <button
            key={lang}
            type="button"
            lang={lang}
            aria-pressed={active}
            aria-label={t(name)}
            onClick={() => setLanguage(lang)}
            className={cn(
              "min-w-11 cursor-pointer px-3 py-1.5 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-header-foreground",
              i > 0 && "border-l border-header-foreground/40",
              active
                ? "bg-header-foreground text-header"
                : "bg-transparent text-header-foreground hover:bg-header-foreground/15",
            )}
          >
            {t(short)}
          </button>
        );
      })}
    </div>
  );
}
