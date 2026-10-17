import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";

/** Always-visible disclaimer (J16): education and reference only, plus the demo-data badge. */
export function DisclaimerBanner() {
  const { t } = useTranslation();
  return (
    <section
      aria-label={t("disclaimer.label")}
      className="border-b border-notice-border bg-notice text-notice-foreground"
    >
      <div className="mx-auto flex max-w-screen-2xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-sm sm:px-6">
        <p className="m-0 font-medium" data-testid="disclaimer-text">
          <span aria-hidden="true">⚠️ </span>
          {t("disclaimer.text")}
        </p>
        <Badge variant="notice" className="bg-card">
          {t("disclaimer.demoData")}
        </Badge>
      </div>
    </section>
  );
}
