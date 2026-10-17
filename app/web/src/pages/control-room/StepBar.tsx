import { useRef, type MouseEvent } from "react";
import { useTranslation } from "react-i18next";

import type { StepTrack } from "@contracts/contracts";

import { TrustBadge } from "@/components/TrustBadge";
import { useBilingual } from "@/i18n/useBilingual";
import { formatTime } from "@/lib/format";
import { phaseColor, type ReferenceLookup } from "@/lib/reference";
import { percentOf } from "@/lib/timelineDisplay";
import { cn } from "@/lib/utils";
import type { VideoClock } from "@/replay/clock";
import { useClockListener } from "@/replay/hooks";
import type { ReplayIndex, ReplayState } from "@/replay/sync";

interface StepBarProps {
  index: ReplayIndex;
  state: ReplayState;
  duration: number;
  lookup: ReferenceLookup;
  tracks: readonly StepTrack[];
  onTrackChange: (track: StepTrack) => void;
  onSeek: (seconds: number) => void;
  clock: VideoClock;
}

/**
 * The live step bar: one segment per step of the shown track over the full duration. Reached
 * segments take their phase colour, unreached ones stay neutral (no spoilers); the current step
 * is highlighted and named from the Reference with its trust badge. Clicking the bar seeks.
 */
export function StepBar({ index, state, duration, lookup, tracks, onTrackChange, onSeek, clock }: StepBarProps) {
  const { t } = useTranslation();
  const pick = useBilingual();
  const playhead = useRef<HTMLDivElement>(null);

  useClockListener(clock, (time) => {
    if (playhead.current) playhead.current.style.left = `${percentOf(time, duration)}%`;
  });

  const stepName = (stepId: string) => {
    const name = lookup.stepName(stepId);
    return name ? pick(name) : stepId;
  };
  const current = state.currentStep >= 0 ? index.steps[state.currentStep] : undefined;

  const seekToPointer = (event: MouseEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width <= 0) return;
    onSeek(((event.clientX - rect.left) / rect.width) * duration);
  };

  return (
    <section aria-labelledby="step-bar-heading" className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="step-bar-heading" className="m-0 text-base font-semibold">
          {t("stepBar.title")}
        </h2>
        {tracks.length > 1 && (
          <div role="group" aria-label={t("stepBar.track")} className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground" aria-hidden="true">
              {t("stepBar.track")}
            </span>
            <div className="inline-flex overflow-hidden rounded-md border border-border">
              {tracks.map((track, i) => {
                const active = track === index.track;
                return (
                  <button
                    key={track}
                    type="button"
                    aria-pressed={active}
                    onClick={() => onTrackChange(track)}
                    className={cn(
                      "cursor-pointer px-2.5 py-1 text-xs font-medium focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring",
                      i > 0 && "border-l border-border",
                      active ? "bg-primary text-primary-foreground" : "bg-card hover:bg-muted",
                    )}
                  >
                    {t(`stepBar.trackOption.${track}`)}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <p className="m-0 flex min-h-7 flex-wrap items-center gap-2 text-sm" aria-live="polite" data-testid="current-step">
        <span className="text-muted-foreground">{t("stepBar.current")}</span>
        {current ? (
          <>
            <span className="font-semibold">{stepName(current.step_id)}</span>
            <TrustBadge label={current.provenance.trust_label} />
          </>
        ) : (
          <span className="text-muted-foreground">
            {state.steps === 0 ? t("stepBar.notStarted") : t("stepBar.between")}
          </span>
        )}
      </p>

      {index.steps.length === 0 ? (
        <p className="m-0 text-sm text-muted-foreground">{t("stepBar.empty")}</p>
      ) : (
        // The bar is a pointer shortcut; keyboard users use the reached segments' buttons.
        <div
          className="relative h-7 w-full cursor-pointer overflow-hidden rounded-md bg-muted"
          onClick={seekToPointer}
          aria-label={t("stepBar.barLabel")}
          role="group"
        >
          {index.steps.map((segment, i) => {
            const left = percentOf(segment.t_start, duration);
            const width = Math.max(0, percentOf(segment.t_end, duration) - left);
            const reached = i < state.steps;
            const isCurrent = i === state.currentStep;
            const style = { left: `${left}%`, width: `${width}%` };
            if (!reached) {
              return (
                <div
                  key={segment.id}
                  data-step-state="upcoming"
                  className="absolute inset-y-1 border-r border-card bg-border/70"
                  style={style}
                />
              );
            }
            const name = stepName(segment.step_id);
            return (
              <button
                key={segment.id}
                type="button"
                data-step-state={isCurrent ? "current" : "reached"}
                aria-current={isCurrent ? "step" : undefined}
                aria-label={t("stepBar.jumpTo", { time: formatTime(segment.t_start), name })}
                title={name}
                onClick={(event) => {
                  event.stopPropagation();
                  onSeek(segment.t_start);
                }}
                className={cn(
                  "absolute cursor-pointer border-r border-card focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring",
                  isCurrent ? "inset-y-0 z-[1] ring-2 ring-foreground ring-inset" : "inset-y-1 opacity-80 hover:opacity-100",
                )}
                style={{ ...style, backgroundColor: phaseColor(lookup.phaseOrder(segment.step_id)) }}
              />
            );
          })}
          <div
            ref={playhead}
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 z-[2] w-0.5 -translate-x-1/2 bg-foreground"
            style={{ left: "0%" }}
          />
        </div>
      )}
    </section>
  );
}
