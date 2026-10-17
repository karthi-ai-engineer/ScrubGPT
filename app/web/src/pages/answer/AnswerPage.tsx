import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams, useSearchParams } from "react-router";

import { api, ApiRequestError, isBrainUnavailable } from "@/api/client";
import { useAnswerQueue, useCase } from "@/api/hooks";
import type { QueueRole } from "@/api/types";
import { ErrorState, LoadingState } from "@/components/QueryStatus";
import { TrustBadge } from "@/components/TrustBadge";
import { Button } from "@/components/ui/button";
import { useBilingual } from "@/i18n/useBilingual";
import { CaseNotFound } from "@/pages/CasePage";

import { AnswerDeck } from "./AnswerDeck";
import { DEFAULT_ROLE, ROLE_TRUST, type Answerer } from "./answerer";
import { AnswererSetup } from "./AnswererSetup";
import { BrainUnavailableBanner } from "./BrainUnavailableBanner";
import { forcedQueue, isQueueRole } from "./fields";

/**
 * The phone UI shown in a phone-sized frame (about 390×844) on the laptop, the default (plan §8.3,
 * app/web CLAUDE.md rule 7); on a real narrow screen the frame drops away.
 */
function PhoneFrame({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-center sm:py-2">
      <section
        aria-label={label}
        data-testid="phone-frame"
        className="flex w-full flex-col bg-background sm:h-[min(844px,calc(100dvh-11rem))] sm:min-h-[600px] sm:w-[390px] sm:overflow-hidden sm:rounded-[2.75rem] sm:border-[10px] sm:border-foreground sm:shadow-2xl"
      >
        <div aria-hidden="true" className="hidden h-6 shrink-0 items-center justify-center sm:flex">
          <span className="h-1.5 w-16 rounded-full bg-border" />
        </div>
        <div className="flex-1 sm:overflow-y-auto sm:px-4 sm:pb-6">{children}</div>
      </section>
    </div>
  );
}

/** J3: the Surgeon Answer app at `/cases/:caseId/answer?role=operating|reviewer`. */
export function AnswerPage() {
  const { caseId = "" } = useParams();
  const query = useCase(caseId);

  if (query.isPending) return <LoadingState />;
  if (query.isError) {
    if (query.error instanceof ApiRequestError && query.error.code === "not_found") {
      return <CaseNotFound caseId={caseId} />;
    }
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  }
  return <AnswerApp key={query.data.case.id} caseId={query.data.case.id} />;
}

function AnswerApp({ caseId }: { caseId: string }) {
  const { t } = useTranslation();
  const pick = useBilingual();
  const detail = useCase(caseId).data;
  const [params, setParams] = useSearchParams();
  const urlRole = params.get("role");
  const listRole: QueueRole = isQueueRole(urlRole) ? urlRole : "operating";

  const [answerer, setAnswerer] = useState<Answerer | null>(null);
  const [editingSetup, setEditingSetup] = useState(true);
  const [round, setRound] = useState(0);
  const queueRole = (answerer && forcedQueue(answerer.role)) ?? listRole;

  // Say early when the Brain is down, so the surgeon goes straight to tap or text.
  const brain = useQuery({
    queryKey: ["brain-health"],
    queryFn: ({ signal }) => api.brainHealth(signal),
    retry: false,
    staleTime: 30_000,
  });

  const caseLink = `/cases/${encodeURIComponent(caseId)}`;
  return (
    <article className="flex flex-col gap-3">
      <nav className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <Link to={`${caseLink}/control-room`} className="text-primary underline-offset-4 hover:underline">
          <span aria-hidden="true">← </span>
          {t("answer.backToControlRoom")}
        </Link>
        <Link to={caseLink} className="text-primary underline-offset-4 hover:underline">
          {t("answer.backToCase")}
        </Link>
      </nav>
      <h1 className="sr-only">{t("answer.title")}</h1>

      <PhoneFrame label={t("answer.frameLabel")}>
        <div className="flex flex-col gap-3 px-4 py-3 sm:px-0">
          <header className="flex flex-col gap-1">
            <p className="m-0 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{t("answer.title")}</p>
            {detail && <p className="m-0 text-sm font-medium">{pick(detail.case.title)}</p>}
            {answerer && !editingSetup && (
              <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="answerer">
                <TrustBadge label={ROLE_TRUST[answerer.role]} />
                <span className="min-w-0 flex-1 truncate">
                  {t("answer.who", { role: t(`answer.setup.roleOption.${answerer.role}`), name: answerer.name })}
                </span>
                <Button size="sm" variant="ghost" onClick={() => setEditingSetup(true)}>
                  {t("answer.change")}
                </Button>
              </div>
            )}
          </header>

          {isBrainUnavailable(brain.error) && <BrainUnavailableBanner />}

          {(editingSetup || !answerer) && (
            <AnswererSetup
              initial={answerer}
              defaultRole={DEFAULT_ROLE}
              queue={queueRole}
              onDone={(next, queue) => {
                setAnswerer(next);
                setEditingSetup(false);
                if (queue !== listRole) setParams({ role: queue }, { replace: true });
              }}
            />
          )}
          {answerer && (
            <div hidden={editingSetup}>
              <QueueView
                key={`${queueRole}:${answerer.role}:${round}`}
                caseId={caseId}
                role={queueRole}
                answerer={answerer}
                includeAnswered={round > 0}
                onAgain={() => setRound((r) => r + 1)}
              />
            </div>
          )}
        </div>
      </PhoneFrame>
    </article>
  );
}

function QueueView({
  caseId,
  role,
  answerer,
  includeAnswered,
  onAgain,
}: {
  caseId: string;
  role: QueueRole;
  answerer: Answerer;
  includeAnswered: boolean;
  onAgain: () => void;
}) {
  const queue = useAnswerQueue(caseId, role);
  // A fresh queue for each round: wait for this mount's fetch, not a cached copy.
  if (queue.isPending || (queue.isFetching && !queue.isFetchedAfterMount)) return <LoadingState />;
  if (queue.isError) return <ErrorState error={queue.error} onRetry={() => void queue.refetch()} />;
  return (
    <AnswerDeck caseId={caseId} queue={queue.data} answerer={answerer} includeAnswered={includeAnswered} onAgain={onAgain} />
  );
}
