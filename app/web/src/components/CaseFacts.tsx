import { useTranslation } from "react-i18next";

import type { Case } from "@contracts/contracts";

import type { CaseCounts } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Localised facts about a case: source, language, video type, narration, status, duration. */
export function CaseFacts({ caseInfo, className }: { caseInfo: Case; className?: string }) {
  const { t } = useTranslation();
  const facts: { key: string; term: string; value: string }[] = [
    { key: "source", term: t("case.source"), value: t(`source.${caseInfo.source}`) },
    { key: "language", term: t("case.language"), value: t(`caseLanguage.${caseInfo.language}`) },
    { key: "videoType", term: t("case.videoType"), value: t(`videoType.${caseInfo.video_type}`) },
    {
      key: "narration",
      term: t("case.narration"),
      value: caseInfo.narrated ? t("case.narrated") : t("case.notNarrated"),
    },
    { key: "status", term: t("case.status"), value: t(`caseStatus.${caseInfo.status}`) },
    { key: "duration", term: t("case.duration"), value: formatTime(caseInfo.duration_s) },
  ];
  return (
    <dl className={cn("m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm", className)}>
      {facts.map((f) => (
        <div key={f.key} className="contents" data-fact={f.key}>
          <dt className="text-muted-foreground">{f.term}</dt>
          <dd className="m-0 font-medium">
            {f.value}
            {f.key === "narration" && caseInfo.synthetic_speech && (
              <Badge variant="notice" className="ml-2 align-middle">
                <span aria-hidden="true">🧪</span>
                {t("case.syntheticSpeech")}
              </Badge>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** The case's content counts. */
export function CaseCountsList({
  counts,
  className,
}: {
  counts: CaseCounts;
  className?: string;
}) {
  const { t } = useTranslation();
  const items = [
    { key: "moments", term: t("case.moments"), value: counts.moments },
    { key: "operating", term: t("case.operatingQuestions"), value: counts.operating_questions },
    { key: "reviewer", term: t("case.reviewerQuestions"), value: counts.reviewer_questions },
    { key: "records", term: t("case.seedRecords"), value: counts.seed_records },
  ];
  return (
    <dl className={cn("m-0 flex flex-wrap gap-2", className)}>
      {items.map((item) => (
        <div key={item.key} className="flex items-baseline gap-1.5 rounded-md bg-muted px-2.5 py-1 text-sm">
          <dt className="text-muted-foreground">{item.term}</dt>
          <dd className="m-0 font-semibold tabular-nums" data-count={item.key}>
            {item.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
