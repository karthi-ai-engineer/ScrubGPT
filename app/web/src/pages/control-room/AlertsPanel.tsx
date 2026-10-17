import { useTranslation } from "react-i18next";

import type { Moment } from "@contracts/contracts";

import { TrustBadge } from "@/components/TrustBadge";
import { Badge } from "@/components/ui/badge";
import { useBilingual } from "@/i18n/useBilingual";
import { formatRange, formatTime } from "@/lib/format";
import type { ReferenceLookup } from "@/lib/reference";
import { cn } from "@/lib/utils";

interface AlertsPanelProps {
  /** Revealed moments (`t >= t_start`), sorted by start; shown newest first. */
  moments: readonly Moment[];
  lookup: ReferenceLookup;
  onSeek: (seconds: number) => void;
  className?: string;
}

/** Each flagged moment becomes an alert card once the replay reaches it. Clicking seeks. */
export function AlertsPanel({ moments, lookup, onSeek, className }: AlertsPanelProps) {
  const { t, i18n } = useTranslation();
  const pick = useBilingual();
  const newestFirst = [...moments].reverse();
  const score = new Intl.NumberFormat(i18n.language, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <section aria-labelledby="alerts-heading" className={cn("flex min-w-0 flex-col gap-2 rounded-xl border border-border bg-card p-3", className)}>
      <h2 id="alerts-heading" className="m-0 text-base font-semibold">
        {t("alerts.title")}
      </h2>
      {newestFirst.length === 0 ? (
        <p className="m-0 text-sm text-muted-foreground">{t("alerts.empty")}</p>
      ) : (
        <ol
          aria-label={t("alerts.listLabel")}
          aria-live="polite"
          aria-relevant="additions"
          className="m-0 flex max-h-[26rem] list-none flex-col gap-2 overflow-y-auto p-0 pr-1"
        >
          {newestFirst.map((moment) => {
            const title = pick(moment.title);
            const stepName = lookup.stepName(moment.step_id);
            const checkpoint = moment.checkpoint_id ? lookup.checkpoint(moment.checkpoint_id) : undefined;
            // The Reference names the checkpoint; without it the id is shown.
            const checkpointText = checkpoint ? pick(checkpoint.text) : moment.checkpoint_id;
            return (
              <li key={moment.id} data-moment-id={moment.id}>
                <button
                  type="button"
                  onClick={() => onSeek(moment.t_start)}
                  aria-label={t("moments.jumpTo", { time: formatTime(moment.t_start), title })}
                  className={cn(
                    "flex w-full cursor-pointer flex-col gap-1.5 rounded-lg border border-l-4 bg-card p-2.5 text-left text-sm transition-colors hover:bg-accent/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                    moment.kind === "event" && "border-l-red-700",
                    moment.kind === "deviation" && "border-l-amber-600",
                    moment.kind === "checkpoint" && "border-l-teal-700",
                    moment.kind === "speech" && "border-l-sky-700",
                  )}
                >
                  <span className="flex flex-wrap items-center gap-1.5">
                    <span className="font-mono text-xs font-semibold tabular-nums text-primary">
                      {formatRange(moment.t_start, moment.t_end)}
                    </span>
                    <Badge variant="outline">{t(`momentKind.${moment.kind}`)}</Badge>
                    <TrustBadge label={moment.provenance.trust_label} />
                    <span className="ml-auto text-xs text-muted-foreground tabular-nums">
                      {t("alerts.score", { score: score.format(moment.score) })}
                    </span>
                  </span>
                  <span className="font-semibold">{title}</span>
                  {checkpointText && (
                    <span className="text-xs font-medium text-teal-900">
                      {t("alerts.checkpoint", { text: checkpointText })}
                    </span>
                  )}
                  {moment.why_flagged.length > 0 && (
                    <span className="flex flex-col gap-0.5 text-xs text-muted-foreground">
                      {moment.why_flagged.map((reason, i) => (
                        <span key={`${reason.signal}-${i}`}>· {pick(reason.detail)}</span>
                      ))}
                    </span>
                  )}
                  <span className="text-xs text-muted-foreground">
                    {t("moments.step", { name: stepName ? pick(stepName) : moment.step_id })}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
