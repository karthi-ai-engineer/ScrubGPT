import { useTranslation } from "react-i18next";

import type { TrustLabel } from "@contracts/contracts";

import { Badge } from "@/components/ui/badge";
import { TRUST_EMOJI } from "@/lib/trust";
import { cn } from "@/lib/utils";

interface TrustBadgeProps {
  label: TrustLabel;
  className?: string;
}

/** Emoji + localised name of a trust label. The emoji is decorative; the name is the text. */
export function TrustBadge({ label, className }: TrustBadgeProps) {
  const { t } = useTranslation();
  const name = t(`trust.${label}`);
  return (
    <Badge
      variant={label === "simulated" ? "notice" : "trust"}
      className={className}
      title={t("trust.label", { name })}
      data-trust-label={label}
    >
      <span aria-hidden="true">{TRUST_EMOJI[label]}</span>
      <span>{name}</span>
    </Badge>
  );
}

/** A wrapping row of trust badges. */
export function TrustBadgeList({ labels, className }: { labels: readonly TrustLabel[]; className?: string }) {
  const { t } = useTranslation();
  return (
    <ul className={cn("flex flex-wrap gap-1.5", className)} aria-label={t("case.trustLabels")}>
      {labels.map((label) => (
        <li key={label}>
          <TrustBadge label={label} />
        </li>
      ))}
    </ul>
  );
}
