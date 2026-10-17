import { afterEach, describe, expect, it, vi } from "vitest";

import { VideoClock } from "./clock";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("VideoClock", () => {
  it("ticks once per animation frame while playing, and stops on pause", () => {
    const frames: FrameRequestCallback[] = [];
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => frames.push(cb));
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    const video = document.createElement("video");
    let paused = true;
    Object.defineProperty(video, "paused", { configurable: true, get: () => paused });

    const clock = new VideoClock();
    const listener = vi.fn();
    clock.subscribe(listener);
    clock.attach(video);
    expect(listener).toHaveBeenLastCalledWith(0, video, "other");

    paused = false;
    video.dispatchEvent(new Event("play"));
    expect(frames).toHaveLength(1);
    video.currentTime = 1.5;
    frames.shift()?.(0);
    expect(listener).toHaveBeenLastCalledWith(1.5, video, "frame");
    expect(frames).toHaveLength(1); // the next frame is scheduled

    paused = true;
    video.dispatchEvent(new Event("pause"));
    expect(cancelAnimationFrame).toHaveBeenCalled();
    clock.detach();
  });

  it("reports `ended` and `seeked` causes and stops after detach", () => {
    const video = document.createElement("video");
    const clock = new VideoClock();
    const listener = vi.fn();
    clock.attach(video);
    const unsubscribe = clock.subscribe(listener);
    video.dispatchEvent(new Event("seeked"));
    expect(listener).toHaveBeenLastCalledWith(0, video, "seeked");
    video.dispatchEvent(new Event("ended"));
    expect(listener).toHaveBeenLastCalledWith(0, video, "ended");

    const calls = listener.mock.calls.length;
    unsubscribe();
    video.dispatchEvent(new Event("timeupdate"));
    expect(listener.mock.calls.length).toBe(calls);

    const other = vi.fn();
    clock.subscribe(other);
    other.mockClear();
    clock.detach();
    video.dispatchEvent(new Event("timeupdate"));
    expect(other).not.toHaveBeenCalled();
  });
});
