/** The replay speeds (plan J2). The video element stays the master clock at every speed. */
export const PLAYBACK_RATES = [1, 2, 4, 8, 16] as const;
export type PlaybackRate = (typeof PLAYBACK_RATES)[number];
