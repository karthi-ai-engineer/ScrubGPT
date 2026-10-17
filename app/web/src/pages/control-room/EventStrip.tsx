import { useId, useRef } from "react";
import { useTranslation } from "react-i18next";

import type { TimelineEvent } from "@contracts/contracts";

import { TrustBadge } from "@/components/TrustBadge";
import { formatRange, formatTime } from "@/lib/format";
import { EVENT_STYLE, EVENT_TYPES, isKnownSignal, percentOf } from "@/lib/timelineDisplay";
import { cn } from "@/lib/utils";
import type { VideoClock } from "@/replay/clock";
import { useClockListener } from "@/replay/hooks";

interface EventStripProps {
  /** Revealed events (`t >= t_start`), sorted by start. */
  events: readonly TimelineEvent[];
  duration: number;
  onSeek: (seconds: number) => void;
  clock: VideoClock;
}

/** Event markers on a time strip: each appears when reached and seeks the video on click. */
export function EventStrip({ events, duration, onSeek, clock }: EventStripProps) {
  const { t } = useTranslation();
  const playhead = useRef<HTMLLIElement>(null);
  useClockListener(clock, (time) => {
    if (playhead.current) playhead.current.style.left = `${percentOf(time, duration)}%`;
  });

  return (
    <section aria-labelledby="events-heading" className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="events-heading" className="m-0 text-base font-semibold">
          {t("events.title")}
        </h2>
        <span className="text-xs text-muted-foreground tabular-nums">{t("events.count", { count: events.length })}</span>
      </div>
      <ul
        aria-label={t("events.stripLabel")}
        className="relative m-0 h-10 w-full list-none rounded-md bg-muted p-0"
        data-testid="event-strip"
      >
        {events.map((event) => (
          <EventMarker key={event.id} event={event} left={percentOf(event.t_start, duration)} onSeek={onSeek} />
        ))}
        <li
          ref={playhead}
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 w-0.5 -translate-x-1/2 bg-foreground/60"
          style={{ left: "0%" }}
        />
      </ul>
      <ul aria-label={t("events.legend")} className="m-0 flex list-none flex-wrap gap-x-3 gap-y-1 p-0 text-xs text-muted-foreground">
        {EVENT_TYPES.map((type) => (
          <li key={type} className="flex items-center gap-1">
            <span aria-hidden="true">{EVENT_STYLE[type].icon}</span>
            {t(`eventType.${type}`)}
          </li>
        ))}
      </ul>
    </section>
  );
}

function EventMarker({ event, left, onSeek }: { event: TimelineEvent; left: number; onSeek: (s: number) => void }) {
  const { t } = useTranslation();
  const tooltipId = useId();
  const style = EVENT_STYLE[event.type];
  const typeName = t(`eventType.${event.type}`);
  const signals = event.signals
    .map((signal) => (isKnownSignal(signal) ? t(`signal.${signal}`) : signal))
    .join(t("signal.listSeparator"));
  // Markers near the right edge open their tooltip leftwards so it stays on screen.
  const alignRight = left > 50;

  return (
    <li className="group absolute top-1/2 -translate-x-1/2 -translate-y-1/2" style={{ left: `${left}%` }} data-event-type={event.type}>
      <button
        type="button"
        onClick={() => onSeek(event.t_start)}
        aria-label={t("events.jumpTo", { type: typeName, time: formatTime(event.t_start) })}
        aria-describedby={tooltipId}
        className={cn(
          "flex size-8 cursor-pointer items-center justify-center rounded-full border-2 text-sm shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
          style.className,
        )}
      >
        <span aria-hidden="true">{style.icon}</span>
      </button>
      <div
        id={tooltipId}
        role="tooltip"
        className={cn(
          "pointer-events-none absolute top-full z-30 mt-2 hidden w-48 flex-col gap-1 rounded-md border border-border bg-popover p-2 text-xs text-popover-foreground shadow-md group-focus-within:flex group-hover:flex",
          alignRight ? "right-0" : "left-0",
        )}
      >
        <span className="font-semibold">
          {typeName} <span className="font-mono font-normal tabular-nums">{formatRange(event.t_start, event.t_end)}</span>
        </span>
        <span>{t("events.signals", { list: signals })}</span>
        <TrustBadge label={event.provenance.trust_label} className="self-start" />
      </div>
    </li>
  );
}
