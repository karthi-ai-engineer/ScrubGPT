import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { Bilingual, DecisionRecord } from "@contracts/contracts";

import type { AnswerQueue } from "@/api/types";
import { TrustBadge } from "@/components/TrustBadge";
import { Button } from "@/components/ui/button";
import { useBilingual } from "@/i18n/useBilingual";
import { minutesUp } from "@/lib/format";

import { EMPTY_NOTES, type Answerer, type CardNotes } from "./answerer";
import { canAnswer } from "./fields";
import { QuestionCard } from "./QuestionCard";

interface AnswerDeckProps {
  caseId: string;
  queue: AnswerQueue;
  answerer: Answerer;
  /** Also ask questions the store already has an answer for ("Answer again"). */
  includeAnswered: boolean;
  onAgain: () => void;
}

type Outcome = "saved" | "skipped";

/**
 * The question cards, one at a time, with "2 of 4 · ~2 min" (counts and estimates from the queue),
 * skip, and later (moves the card to the end). Only questions this role may answer (D-066).
 */
export function AnswerDeck({ caseId, queue, answerer, includeAnswered, onAgain }: AnswerDeckProps) {
  const { t } = useTranslation();
  const pick = useBilingual();
  const byId = new Map(queue.questions.map((item) => [item.question.id, item]));

  const [order, setOrder] = useState<string[]>(() =>
    queue.questions
      .filter((item) => (includeAnswered || !item.answered) && canAnswer(answerer.role, item.question.id))
      .map((item) => item.question.id),
  );
  const [cursor, setCursor] = useState(0);
  const [outcomes, setOutcomes] = useState<Readonly<Record<string, Outcome>>>({});
  const [notes, setNotes] = useState<Readonly<Record<string, CardNotes>>>({});
  const [lastSaved, setLastSaved] = useState<{ record: DecisionRecord; question: Bilingual } | null>(null);

  const currentId = order[cursor];
  const current = currentId === undefined ? undefined : byId.get(currentId);
  const remainingSeconds = order.slice(cursor).reduce((sum, id) => sum + (byId.get(id)?.question.est_seconds ?? 0), 0);

  const advance = (id: string, outcome: Outcome) => {
    setOutcomes((all) => ({ ...all, [id]: outcome }));
    setCursor((c) => c + 1);
  };
  const later = () => {
    if (currentId === undefined) return;
    setOrder((all) => [...all.slice(0, cursor), ...all.slice(cursor + 1), currentId]);
    setLastSaved(null);
  };
  const skipped = order.filter((id) => outcomes[id] === "skipped");
  const savedCount = order.filter((id) => outcomes[id] === "saved").length;

  const savedNote = lastSaved && (
    <p
      role="status"
      data-testid="saved"
      className="m-0 flex flex-wrap items-center gap-2 rounded-lg border border-primary/40 bg-accent p-2.5 text-sm text-accent-foreground"
    >
      <span aria-hidden="true">✓</span>
      <span className="min-w-0 flex-1">{t("answer.saved", { question: pick(lastSaved.question) })}</span>
      <TrustBadge label={lastSaved.record.provenance.trust_label} />
    </p>
  );

  if (!current || currentId === undefined) {
    return (
      <div className="flex flex-col gap-3" data-testid="deck-done">
        {savedNote}
        <h2 className="m-0 text-lg font-semibold">{order.length === 0 ? t("answer.done.empty") : t("answer.done.title")}</h2>
        {order.length > 0 && (
          <p className="m-0 text-sm" data-testid="done-summary">
            {t("answer.done.summary", { saved: savedCount, skipped: skipped.length })}
          </p>
        )}
        {skipped.length > 0 && (
          <Button
            onClick={() => {
              setOrder(skipped);
              setCursor(0);
              setOutcomes({});
              setLastSaved(null);
            }}
          >
            {t("answer.done.skipped")}
          </Button>
        )}
        <Button variant="outline" onClick={onAgain}>
          {t("answer.done.again")}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <p className="m-0 text-sm font-semibold tabular-nums" data-testid="progress">
          {t("answer.progress", { n: cursor + 1, total: order.length, minutes: minutesUp(remainingSeconds) })}
        </p>
        <div className="flex gap-1">
          <Button size="sm" variant="ghost" onClick={later} disabled={order.length - cursor < 2}>
            {t("answer.later")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setLastSaved(null);
              advance(currentId, "skipped");
            }}
          >
            {t("answer.skip")}
          </Button>
        </div>
      </div>
      {savedNote}
      <QuestionCard
        key={currentId}
        caseId={caseId}
        item={current}
        answerer={answerer}
        notes={notes[currentId] ?? EMPTY_NOTES}
        onNotes={(next) => setNotes((all) => ({ ...all, [currentId]: next }))}
        onSaved={(record) => {
          setLastSaved({ record, question: current.question.text });
          advance(currentId, "saved");
        }}
      />
    </div>
  );
}
