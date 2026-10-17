/** Display helpers for timeline items (icons, colours, localisable names). Display-only. */
import type { EventType } from "@contracts/contracts";

/** Icon and colour per event type (J2 event markers). The icon is decorative; the name is text. */
export const EVENT_STYLE: Readonly<Record<EventType, { icon: string; className: string }>> = {
  bleeding: { icon: "🩸", className: "border-red-700 bg-red-50 text-red-900" },
  smoke: { icon: "💨", className: "border-slate-500 bg-slate-100 text-slate-900" },
  out_of_body: { icon: "📷", className: "border-amber-600 bg-amber-50 text-amber-900" },
  idle: { icon: "⏸️", className: "border-sky-700 bg-sky-50 text-sky-900" },
  suction: { icon: "💧", className: "border-teal-700 bg-teal-50 text-teal-900" },
  other: { icon: "◆", className: "border-violet-700 bg-violet-50 text-violet-900" },
};

export const EVENT_TYPES = Object.keys(EVENT_STYLE) as EventType[];

/** Signal names with a localised label (`signal.<name>`); any other signal is shown verbatim. */
export const KNOWN_SIGNALS = [
  "red_pixel_ratio",
  "dark_frame_ratio",
  "low_motion",
  "gpt_check",
  "speech",
  "teaching",
  "checkpoint",
  "step_order",
  "out_of_body",
] as const;
export type KnownSignal = (typeof KNOWN_SIGNALS)[number];

export function isKnownSignal(signal: string): signal is KnownSignal {
  return (KNOWN_SIGNALS as readonly string[]).includes(signal);
}

/** `speaker_0` → 1 (shown as "Speaker 1"); `null` for any other label (shown verbatim). */
export function speakerNumber(speaker: string): number | null {
  const match = /^speaker_(\d+)$/.exec(speaker);
  return match ? Number(match[1]) + 1 : null;
}

/** Position of `t` on a bar of `duration` seconds, in percent (0–100). */
export function percentOf(t: number, duration: number): number {
  if (!(duration > 0) || !Number.isFinite(t)) return 0;
  return Math.min(100, Math.max(0, (t / duration) * 100));
}
