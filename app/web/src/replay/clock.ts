/**
 * A subscription hub for a `<video>` element's clock (the master clock, plan §8.2).
 *
 * While the video plays it ticks once per animation frame; it also ticks on `seeking`, `seeked`,
 * `ratechange`, `timeupdate`, `loadedmetadata`, `durationchange`, `pause` and `ended`, so a
 * paused seek, a speed change or a skipped frame at 16× is never missed. Listeners decide
 * themselves whether anything changed; the clock never touches React state.
 */
export type ClockCause = "frame" | "ended" | "seeked" | "other";

export type ClockListener = (t: number, video: HTMLVideoElement, cause: ClockCause) => void;

const TICK_EVENTS = [
  "timeupdate",
  "seeking",
  "seeked",
  "ratechange",
  "loadedmetadata",
  "durationchange",
  "pause",
  "ended",
  "emptied",
] as const;

export class VideoClock {
  private video: HTMLVideoElement | null = null;
  private readonly listeners = new Set<ClockListener>();
  private frame: number | null = null;

  /** Follows `video` (replacing any earlier element) and ticks once. */
  attach(video: HTMLVideoElement): void {
    if (this.video === video) return;
    this.detach();
    this.video = video;
    for (const name of TICK_EVENTS) video.addEventListener(name, this.onEvent);
    video.addEventListener("play", this.onPlay);
    video.addEventListener("playing", this.onPlay);
    if (!video.paused) this.onPlay();
    this.tick();
  }

  detach(): void {
    const video = this.video;
    if (!video) return;
    for (const name of TICK_EVENTS) video.removeEventListener(name, this.onEvent);
    video.removeEventListener("play", this.onPlay);
    video.removeEventListener("playing", this.onPlay);
    this.stopFrames();
    this.video = null;
  }

  /** Adds a listener (called at once when a video is attached); returns the unsubscribe. */
  subscribe(listener: ClockListener): () => void {
    this.listeners.add(listener);
    if (this.video) listener(this.video.currentTime, this.video, "other");
    return () => {
      this.listeners.delete(listener);
    };
  }

  /** Calls every listener with the current time. */
  tick(cause: ClockCause = "other"): void {
    const video = this.video;
    if (!video) return;
    const t = video.currentTime;
    for (const listener of [...this.listeners]) listener(t, video, cause);
  }

  private readonly onEvent = (event: Event) => {
    if (event.type === "pause" || event.type === "ended" || event.type === "emptied") this.stopFrames();
    this.tick(event.type === "ended" ? "ended" : event.type === "seeked" ? "seeked" : "other");
  };

  private readonly onPlay = () => {
    if (this.frame !== null || typeof requestAnimationFrame === "undefined") return;
    const loop = () => {
      this.tick("frame");
      const video = this.video;
      this.frame = video && !video.paused && !video.ended ? requestAnimationFrame(loop) : null;
    };
    this.frame = requestAnimationFrame(loop);
  };

  private stopFrames(): void {
    if (this.frame !== null && typeof cancelAnimationFrame !== "undefined") cancelAnimationFrame(this.frame);
    this.frame = null;
  }
}
