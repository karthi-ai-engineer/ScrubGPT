import { useTranslation } from "react-i18next";
import { NavLink, Outlet } from "react-router";

import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import { LanguageToggle } from "@/components/LanguageToggle";
import { cn } from "@/lib/utils";

/** The app shell: header (product, nav, JA | EN), the always-visible disclaimer, the page. */
export function Layout() {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2"
      >
        {t("app.skipToContent")}
      </a>
      <div className="sticky top-0 z-40">
        <header className="bg-header text-header-foreground">
          <div className="mx-auto flex max-w-screen-2xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
            <div className="flex min-w-0 flex-col leading-tight">
              <span className="text-[0.7rem] font-semibold tracking-[0.18em] text-header-foreground/75 uppercase">
                {t("app.org")}
              </span>
              <span className="text-lg font-semibold">{t("app.name")}</span>
            </div>
            <nav aria-label={t("nav.label")} className="flex items-center gap-1">
              <NavLink
                to="/"
                end
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-3 py-1.5 text-sm font-medium text-header-foreground no-underline hover:bg-header-foreground/15",
                    isActive && "bg-header-foreground/15",
                  )
                }
              >
                {t("nav.home")}
              </NavLink>
            </nav>
            <LanguageToggle className="ml-auto" />
          </div>
        </header>
        <DisclaimerBanner />
      </div>
      <main id="main" className="mx-auto w-full max-w-screen-2xl flex-1 px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
