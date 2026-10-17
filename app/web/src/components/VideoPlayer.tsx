import { useCallback, useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { useTranslation } from "react-i18next";

import { formatTime } from "@/lib/format";
import { PLAYBACK_RATES, type PlaybackRate } from "@/lib/playback";
import { cn } from "@/lib/utils";

export interface VideoPlayerHandle {
  /** Moves the playhead to `seconds` (clamped to the video), keeping the chosen speed. */
  seekTo: (seconds: number) => void;
  /** The underlying element, for components that follow `currentTime`. */
  getVideo: () => HTMLVideoElement | null;
}

interface VideoPlayerProps {
  src: string;
  poster?: string;
  /** Accessible name of the player (e.g. the case title in the current language). */
  title: string;
  /** Shown as the duration until the video's metadata has loaded (e.g. `case.duration_s`). */
  durationHint?: number;
  ref?: Ref<VideoPlayerHandle>;
  className?: string;
}

export function VideoPlayer({ src, poster, title, durationHint, ref, className }: VideoPlayerProps) {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [rate, setRate] = useState<PlaybackRate>(1);
  const [currentTime, setCurrentTime] = useState(0);
  const [mediaDuration, setMediaDuration] = useState<number | null>(null);

  // A new `src` resets the element to `defaultPlaybackRate`, so both are set.
  const applyRate = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    video.defaultPlaybackRate = rate;
    if (video.playbackRate !== rate) video.playbackRate = rate;
  }, [rate]);

  useEffect(applyRate, [applyRate, src]);

  useImperativeHandle(
    ref,
    () => ({
      seekTo: (seconds: number) => {
        const video = videoRef.current;
        if (!video) return;
        const end = Number.isFinite(video.duration) ? video.duration : Infinity;
        const target = Math.min(Math.max(0, seconds), end);
        video.currentTime = target;
        setCurrentTime(target);
        applyRate();
      },
      getVideo: () => videoRef.current,
    }),
    [applyRate],
  );

  const duration = mediaDuration ?? durationHint ?? 0;

  return (
    <figure className={cn("m-0 flex min-w-0 flex-col gap-3", className)} aria-label={t("player.label", { title })}>
      <video
        ref={videoRef}
        src={src}
        poster={poster}
        controls
        preload="metadata"
        playsInline
        className="aspect-video w-full rounded-lg bg-black"
        onLoadedMetadata={(e) => {
          const d = e.currentTarget.duration;
          setMediaDuration(Number.isFinite(d) ? d : null);
          applyRate();
        }}
        onDurationChange={(e) => {
          const d = e.currentTarget.duration;
          if (Number.isFinite(d)) setMediaDuration(d);
        }}
        onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
        onSeeked={(e) => {
          setCurrentTime(e.currentTarget.currentTime);
          applyRate();
        }}
      />
      <figcaption className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label={t("player.speed")} className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-muted-foreground" aria-hidden="true">
            {t("player.speed")}
          </span>
          <div className="inline-flex overflow-hidden rounded-md border border-border bg-card">
            {PLAYBACK_RATES.map((r, i) => {
              const active = r === rate;
              return (
                <button
                  key={r}
                  type="button"
                  aria-pressed={active}
                  aria-label={t("player.speedOption", { rate: r })}
                  onClick={() => setRate(r)}
                  className={cn(
                    "min-w-11 cursor-pointer px-2.5 py-1.5 font-mono text-sm tabular-nums transition-colors focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring",
                    i > 0 && "border-l border-border",
                    active ? "bg-primary font-semibold text-primary-foreground" : "text-foreground hover:bg-muted",
                  )}
                >
                  {t("player.rate", { rate: r })}
                </button>
              );
            })}
          </div>
        </div>
        <p className="m-0 font-mono text-sm tabular-nums text-muted-foreground">
          <span className="sr-only">{t("player.position")} </span>
          <span data-testid="player-time">{`${formatTime(currentTime)} / ${formatTime(duration)}`}</span>
        </p>
      </figcaption>
    </figure>
  );
}
