import { useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Utterance } from "@contracts/contracts";

import { TrustBadge } from "@/components/TrustBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useBilingual, useLang } from "@/i18n/useBilingual";
import { formatTime } from "@/lib/format";
import { speakerNumber } from "@/lib/timelineDisplay";
import { cn } from "@/lib/utils";

/** How close to the bottom (px) still counts as "following" the newest line. */
const FOLLOW_SLACK_PX = 24;

interface TranscriptTickerProps {
  /** Revealed utterances (`t >= t_start`), sorted by start: newest last. */
  utterances: readonly Utterance[];
  onSeek: (seconds: number) => void;
  className?: string;
}

/**
 * The JA/EN transcript ticker. It follows the newest line unless the user has scrolled up;
 * scrolling back to the bottom (or "Show latest") resumes following.
 */
export function TranscriptTicker({ utterances, onSeek, className }: TranscriptTickerProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const pick = useBilingual();
  const scroller = useRef<HTMLOListElement>(null);
  const [following, setFollowing] = useState(true);

  // After new lines render, keep the newest in view while following.
  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && following) el.scrollTop = el.scrollHeight;
  }, [utterances.length, following, lang]);

  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= FOLLOW_SLACK_PX;
    if (atBottom !== following) setFollowing(atBottom);
  };

  const speakerLabel = (speaker: string) => {
    const n = speakerNumber(speaker);
    return n === null ? speaker : t("ticker.speaker", { n });
  };

  return (
    <section aria-labelledby="ticker-heading" className={cn("flex min-w-0 flex-col gap-2 rounded-xl border border-border bg-card p-3", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="ticker-heading" className="m-0 text-base font-semibold">
          {t("ticker.title")}
        </h2>
        {!following && utterances.length > 0 && (
          <Button size="sm" variant="outline" onClick={() => setFollowing(true)}>
            {t("ticker.jumpToLatest")}
          </Button>
        )}
      </div>
      {utterances.length === 0 ? (
        <p className="m-0 text-sm text-muted-foreground">{t("ticker.empty")}</p>
      ) : (
        <ol
          ref={scroller}
          onScroll={onScroll}
          aria-label={t("ticker.listLabel")}
          aria-live="polite"
          aria-relevant="additions"
          tabIndex={0}
          className="m-0 flex max-h-60 list-none flex-col gap-1.5 overflow-y-auto p-0 pr-1"
          data-following={following}
        >
          {utterances.map((u) => (
            <li
              key={u.id}
              data-utterance-id={u.id}
              className={cn(
                "flex flex-col gap-1 rounded-md border border-border px-2.5 py-1.5 text-sm",
                u.class === "irrelevant" ? "bg-muted/50 text-muted-foreground" : "bg-card",
              )}
            >
              <span className="flex flex-wrap items-center gap-1.5 text-xs">
                <button
                  type="button"
                  onClick={() => onSeek(u.t_start)}
                  className="cursor-pointer font-mono font-semibold tabular-nums text-primary hover:underline"
                >
                  {formatTime(u.t_start)}
                </button>
                {u.speaker && <span className="font-medium">{speakerLabel(u.speaker)}</span>}
                <Badge variant="outline" data-utterance-class={u.class}>
                  {t(`utteranceClass.${u.class}`)}
                </Badge>
                {u.original_lang !== lang && (
                  <Badge variant="secondary" data-original-lang={u.original_lang}>
                    {t("ticker.original", { lang: t(`caseLanguage.${u.original_lang}`) })}
                  </Badge>
                )}
                <TrustBadge label={u.provenance.trust_label} />
              </span>
              <span lang={lang}>{pick(u.text)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
