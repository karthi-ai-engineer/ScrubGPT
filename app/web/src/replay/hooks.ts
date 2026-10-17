import { useEffect, useRef, useState } from "react";

import { type ClockListener, VideoClock } from "./clock";
import { EMPTY_REPLAY_STATE, isAtEnd, type ReplayIndex, replayStateAt, type ReplayState, sameReplayState } from "./sync";

/**
 * One clock per page, following the `<video>` that `getVideo` returns after mount.
 * `getVideo` must be stable (e.g. `useCallback(() => player.current?.getVideo() ?? null, [])`).
 */
export function useVideoClock(getVideo: () => HTMLVideoElement | null): VideoClock {
  const [clock] = useState(() => new VideoClock());
  useEffect(() => {
    const video = getVideo();
    if (video) clock.attach(video);
    return () => clock.detach();
  }, [clock, getVideo]);
  return clock;
}

/** Calls the latest `listener` on every clock tick, without re-subscribing on each render. */
export function useClockListener(clock: VideoClock, listener: ClockListener): void {
  const latest = useRef(listener);
  useEffect(() => {
    latest.current = listener;
  });
  useEffect(() => clock.subscribe((t, video, cause) => latest.current(t, video, cause)), [clock]);
}

/**
 * What the replay has revealed. React state changes only when a revealed set or the current
 * step changes, never 60 times a second.
 */
export function useReplayState(clock: VideoClock, index: ReplayIndex): ReplayState {
  const [state, setState] = useState<ReplayState>(EMPTY_REPLAY_STATE);
  useEffect(() => {
    // Compared here, not only in the updater: a bailed-out updater can still cost a render.
    let last: ReplayState | null = null;
    return clock.subscribe((t) => {
      const next = replayStateAt(index, t);
      if (last && sameReplayState(last, next)) return;
      last = next;
      setState((prev) => (sameReplayState(prev, next) ? prev : next));
    });
  }, [clock, index]);
  return state;
}

/** The video's duration once known, else `hint` (e.g. `case.duration_s`). */
export function useMediaDuration(clock: VideoClock, hint: number): number {
  const [duration, setDuration] = useState<number | null>(null);
  useEffect(() => {
    let last: number | null = null;
    return clock.subscribe((_t, video) => {
      const d = video.duration;
      if (Number.isFinite(d) && d > 0 && d !== last) {
        last = d;
        setDuration(d);
      }
    });
  }, [clock]);
  return duration ?? hint;
}

export interface ReplayEndHandlers {
  /** The play-through reached the end (called once per play-through). */
  onEnd: () => void;
  /** The user went back before the end after it had ended: a new play-through starts. */
  onRestart: () => void;
}

/**
 * "Surgery ends" detection: the `ended` event, or `currentTime >= duration - 0.25 s` (8–16× can
 * skip the last frames). Fires `onEnd` once per play-through; moving back before the end (a seek,
 * or replaying from the start) re-arms it and fires `onRestart`.
 */
export function useReplayEnd(clock: VideoClock, durationHint: number | null, handlers: ReplayEndHandlers): void {
  const latest = useRef(handlers);
  useEffect(() => {
    latest.current = handlers;
  });
  useEffect(() => {
    let endedAt: number | null = null;
    return clock.subscribe((t, video, cause) => {
      const duration = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : durationHint;
      const atEnd = cause === "ended" || isAtEnd(t, duration);
      if (atEnd) {
        if (endedAt === null) {
          endedAt = t;
          latest.current.onEnd();
        }
      } else if (endedAt !== null && t < endedAt) {
        endedAt = null;
        latest.current.onRestart();
      }
    });
  }, [clock, durationHint]);
}
