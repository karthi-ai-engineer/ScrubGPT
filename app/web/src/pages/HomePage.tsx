import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { useCases } from "@/api/hooks";
import type { CaseSummary } from "@/api/types";
import { CaseCountsList, CaseFacts } from "@/components/CaseFacts";
import { ErrorState, LoadingState } from "@/components/QueryStatus";
import { TrustBadgeList } from "@/components/TrustBadge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useBilingual } from "@/i18n/useBilingual";

/** J1: the case list, one card per case. */
export function HomePage() {
  const { t } = useTranslation();
  const cases = useCases();

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="m-0 text-2xl font-semibold tracking-tight">{t("home.title")}</h1>
        <p className="m-0 text-muted-foreground">{t("home.subtitle")}</p>
      </header>

      {cases.isPending ? (
        <LoadingState />
      ) : cases.isError ? (
        <ErrorState error={cases.error} onRetry={() => void cases.refetch()} />
      ) : cases.data.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border bg-card p-8 text-center text-muted-foreground">
          {t("home.empty")}
        </p>
      ) : (
        <ul className="m-0 grid list-none grid-cols-1 gap-5 p-0 md:grid-cols-2 xl:grid-cols-3" aria-label={t("home.count", { count: cases.data.length })}>
          {cases.data.map((summary) => (
            <li key={summary.case.id} className="min-w-0">
              <CaseCard summary={summary} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CaseCard({ summary }: { summary: CaseSummary }) {
  const { t } = useTranslation();
  const pick = useBilingual();
  const title = pick(summary.case.title);

  return (
    <Card className="group relative h-full overflow-hidden transition-shadow focus-within:ring-2 focus-within:ring-ring hover:shadow-md">
      <img
        src={summary.media.poster}
        alt={t("case.posterAlt", { title })}
        loading="lazy"
        decoding="async"
        className="aspect-video w-full bg-muted object-cover"
      />
      <CardHeader>
        <CardTitle>
          {/* The stretched link makes the whole card clickable while the title stays the link text. */}
          <Link
            to={`/cases/${encodeURIComponent(summary.case.id)}`}
            className="text-foreground no-underline after:absolute after:inset-0 after:content-[''] hover:underline focus-visible:outline-none"
          >
            {title}
          </Link>
        </CardTitle>
        <p className="m-0 font-mono text-xs text-muted-foreground">{summary.case.id}</p>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3">
        <CaseFacts caseInfo={summary.case} />
        <CaseCountsList counts={summary.counts} />
        <TrustBadgeList labels={summary.trust_labels} />
        {/* Above the card's stretched title link, so it stays separately clickable. */}
        <Link
          to={`/cases/${encodeURIComponent(summary.case.id)}/control-room`}
          aria-label={t("controlRoom.openFor", { title })}
          className={buttonVariants({ variant: "outline", size: "sm", className: "relative z-10 self-start no-underline" })}
        >
          {t("controlRoom.open")}
        </Link>
        <div className="mt-auto rounded-md bg-muted p-3 text-sm">
          <p className="m-0 mb-1 font-medium">{t("case.dataNote")}</p>
          <p className="m-0 text-muted-foreground">{pick(summary.case.data_note)}</p>
        </div>
      </CardContent>
    </Card>
  );
}
