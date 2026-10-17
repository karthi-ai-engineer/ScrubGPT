/**
 * Formats seconds from the start of the video as `m:ss`, or `h:mm:ss` from one hour on.
 * Fractions are dropped (floor); negative or non-finite input shows as `0:00`.
 */
export function formatTime(seconds: number): string {
  const total = Number.isFinite(seconds) && seconds > 0 ? Math.floor(seconds) : 0;
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const ss = String(s).padStart(2, "0");
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${ss}`;
  }
  return `${m}:${ss}`;
}

/** A time range as `m:ss–m:ss` (en dash). */
export function formatRange(tStart: number, tEnd: number): string {
  return `${formatTime(tStart)}–${formatTime(tEnd)}`;
}

/** Whole minutes for an estimate in seconds, rounded up ("about M min"); never negative. */
export function minutesUp(seconds: number): number {
  return Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds / 60) : 0;
}
