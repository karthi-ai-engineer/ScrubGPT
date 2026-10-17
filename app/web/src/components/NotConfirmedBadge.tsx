import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/**
 * "Not confirmed" next to the trust label of a stored record nobody has confirmed yet (a
 * narration-mined 🎙️ record, D-073). Such a record never looks confirmed or surgeon-confirmed.
 */
export function NotConfirmedBadge({ className }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <Badge variant="outline" className={cn("border-dashed", className)} data-testid="not-confirmed" title={t("record.notConfirmedHint")}>
      {t("record.notConfirmed")}
    </Badge>
  );
}
