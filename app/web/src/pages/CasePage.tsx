import { useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";

import type { Bilingual, Moment } from "@contracts/contracts";

import { ApiRequestError } from "@/api/client";
import { useCase, useReference } from "@/api/hooks";
import type { CaseDetail } from "@/api/types";
import { CaseCountsList, CaseFacts } from "@/components/CaseFacts";
import { ErrorState, LoadingState } from "@/components/QueryStatus";
import { TrustBadge, TrustBadgeList } from "@/components/TrustBadge";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { VideoPlayer, type VideoPlayerHandle } from "@/components/VideoPlayer";
import { useBilingual } from "@/i18n/useBilingual";
import { formatRange, formatTime } from "@/lib/format";

/** The case page: title, facts, the video player and the flagged moments (jump-to). */
export function CasePage() {
  const { caseId = "" } = useParams();
  const { t } = useTranslation();
  const query = useCase(caseId);

  if (query.isPending) return <LoadingState />;
  if (query.isError) {
    if (query.error instanceof ApiRequestError && query.error.code === "not_found") {
      return <CaseNotFound caseId={caseId} />;
    }
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  }
  return <CaseView detail={query.data} backLabel={t("case.backToCases")} />;
}

/** "Case not found" with a link home (also used by the Control Room). */
export function CaseNotFound({ caseId }: { caseId: string }) {
  const { t } = useTranslation();
  return (
    <div role="alert" className="mx-auto my-8 flex max-w-xl flex-col items-start gap-3 rounded-xl border border-border bg-card p-6">
      <h1 className="m-0 text-xl font-semibold">{t("errors.caseNotFound.title")}</h1>
      <p className="m-0 text-muted-foreground">{t("errors.caseNotFound.body", { id: caseId })}</p>
      <Link to="/" className={buttonVariants()}>
        {t("status.backHome")}
      </Link>
    </div>
  );
}

/** The procedure of a step id such as `rarp.p03.s01` (plan §4.1 id format). */
function procedureOf(moments: readonly Moment[]): string | null {
  const stepId = moments[0]?.step_id;
  return stepId ? (stepId.split(".")[0] ?? null) : null;
}

function CaseView({ detail, backLabel }: { detail: CaseDetail; backLabel: string }) {
  const { t } = useTranslation();
  const pick = useBilingual();
  const player = useRef<VideoPlayerHandle>(null);
  const title = pick(detail.case.title);
  const moments = detail.moments.moments;

  // Step names come from the Procedure Reference; the raw step id is the fallback.
  const reference = useReference(procedureOf(moments));
  const stepNames = useMemo(() => {
    const names = new Map<string, Bilingual>();
    for (const phase of reference.data?.phases ?? []) {
      for (const step of phase.steps) names.set(step.id, step.name);
    }
    return names;
  }, [reference.data]);

  return (
    <article className="flex flex-col gap-6">
      <Link to="/" className="self-start text-sm text-primary underline-offset-4 hover:underline">
        <span aria-hidden="true">← </span>
        {backLabel}
      </Link>

      <header className="flex flex-col gap-2">
        <h1 className="m-0 text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="m-0 font-mono text-xs text-muted-foreground">{detail.case.id}</p>
        <TrustBadgeList labels={detail.trust_labels} />
        <Link
          to={`/cases/${encodeURIComponent(detail.case.id)}/control-room`}
          className={buttonVariants({ className: "mt-1 self-start no-underline" })}
        >
          {t("controlRoom.open")}
        </Link>
      </header>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
        <section aria-label={t("case.video")} className="flex min-w-0 flex-col gap-4">
          <VideoPlayer
            ref={player}
            src={detail.media.video}
            poster={detail.media.poster}
            title={title}
            durationHint={detail.case.duration_s}
          />
          <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
            <CaseFacts caseInfo={detail.case} />
            <CaseCountsList counts={detail.counts} />
            <div className="text-sm">
              <p className="m-0 mb-1 font-medium">{t("case.dataNote")}</p>
              <p className="m-0 text-muted-foreground">{pick(detail.case.data_note)}</p>
            </div>
          </div>
        </section>

        <section aria-labelledby="moments-heading" className="flex min-w-0 flex-col gap-3">
          <div>
            <h2 id="moments-heading" className="m-0 text-lg font-semibold">
              {t("moments.title")}
            </h2>
            <p className="m-0 text-sm text-muted-foreground">{t("moments.hint")}</p>
          </div>
          {moments.length === 0 ? (
            <p className="text-muted-foreground">{t("moments.empty")}</p>
          ) : (
            <ol className="m-0 flex list-none flex-col gap-2 p-0">
              {moments.map((moment) => {
                const momentTitle = pick(moment.title);
                const stepName = stepNames.get(moment.step_id);
                return (
                  <li key={moment.id}>
                    <button
                      type="button"
                      onClick={() => player.current?.seekTo(moment.t_start)}
                      aria-label={t("moments.jumpTo", { time: formatTime(moment.t_start), title: momentTitle })}
                      className="flex w-full cursor-pointer flex-col gap-1.5 rounded-lg border border-border bg-card p-3 text-left transition-colors hover:border-primary hover:bg-accent/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                    >
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-sm font-semibold tabular-nums text-primary">
                          {formatRange(moment.t_start, moment.t_end)}
                        </span>
                        <Badge variant="outline">{t(`momentKind.${moment.kind}`)}</Badge>
                        <TrustBadge label={moment.provenance.trust_label} />
                      </span>
                      <span className="font-medium">{momentTitle}</span>
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
      </div>
    </article>
  );
}
