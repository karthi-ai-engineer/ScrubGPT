import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import type { CaseEndedEvent } from "@/api/types";
import { buttonVariants } from "@/components/ui/button";
import { minutesUp } from "@/lib/format";

/**
 * The "surgery ends" banner and a small phone-frame notification mock. Every number comes from
 * the `case.ended` event (counted by the server from `questions.json`), never from the UI.
 */
export function SurgeryEndedPanel({ event, caseTitle }: { event: CaseEndedEvent; caseTitle: string }) {
  const { t } = useTranslation();
  const operating = event.questions.operating;
  const minutes = minutesUp(event.est_seconds);

  return (
    <section
      role="status"
      aria-labelledby="ended-heading"
      data-testid="surgery-ended"
      className="flex flex-col gap-4 rounded-xl border border-primary/40 bg-accent p-4 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex min-w-0 flex-col gap-1">
        <h2 id="ended-heading" className="m-0 text-lg font-semibold text-accent-foreground">
          {t("ended.title")}
        </h2>
        <p className="m-0 text-base font-medium" data-testid="ended-summary">
          {t("ended.summary", {
            questions: t("ended.questionsReady", { count: operating }),
            minutes: t("ended.aboutMinutes", { count: minutes }),
          })}
        </p>
        <p className="m-0 text-sm text-muted-foreground" data-testid="ended-reviewer">
          {t("ended.reviewer", { count: event.questions.reviewer })}
        </p>
      </div>

      <figure aria-label={t("ended.phoneLabel")} className="m-0 shrink-0 self-center">
        <div className="w-56 rounded-[2rem] border-4 border-foreground bg-foreground p-1.5 shadow-lg">
          <div className="flex min-h-40 flex-col gap-2 rounded-[1.5rem] bg-background px-3 pt-5 pb-3">
            <div className="mx-auto h-1.5 w-12 rounded-full bg-border" aria-hidden="true" />
            <div className="flex flex-col gap-1 rounded-xl border border-border bg-card p-2.5 shadow-sm">
              <div className="flex items-center justify-between gap-2 text-[0.65rem] text-muted-foreground">
                <span className="truncate font-semibold">{t("ended.phoneApp")}</span>
                <span>{t("ended.phoneNow")}</span>
              </div>
              <p className="m-0 text-sm font-semibold" data-testid="phone-line">
                {t("ended.phoneLine", {
                  questions: t("ended.phoneQuestions", { count: operating }),
                  minutes: t("ended.phoneMinutes", { count: minutes }),
                })}
              </p>
              <p className="m-0 truncate text-xs text-muted-foreground">{caseTitle}</p>
              <Link
                to={`/cases/${encodeURIComponent(event.case_id)}/answer?role=operating`}
                className={buttonVariants({ size: "sm", className: "mt-1 w-full no-underline" })}
                data-testid="answer-now"
              >
                {t("ended.answerNow")}
              </Link>
            </div>
          </div>
        </div>
      </figure>
    </section>
  );
}
