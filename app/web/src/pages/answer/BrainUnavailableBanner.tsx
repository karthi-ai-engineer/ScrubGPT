import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

/** "Brain unavailable" (503 `unavailable` / 504 `timeout`, D-071), with the tap and text fallback. */
export function BrainUnavailableBanner({ className }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <p
      role="alert"
      data-testid="brain-unavailable"
      className={cn("m-0 rounded-lg border border-notice-border bg-notice p-2.5 text-sm text-notice-foreground", className)}
    >
      {t("answer.brainUnavailable")}
    </p>
  );
}
