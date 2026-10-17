import { useCallback, useRef } from "react";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { fixtureDetail } from "@/test/fixtures";

import { useMediaDuration, useReplayEnd, useReplayState, useVideoClock } from "./hooks";
import { buildReplayIndex } from "./sync";

const index = buildReplayIndex(fixtureDetail, "ai");

/** A fake video clock: sets `currentTime` and fires the media event the browser would. */
function at(video: HTMLVideoElement, t: number, type: "timeupdate" | "seeked" | "ended" = "timeupdate") {
  video.currentTime = t;
  fireEvent(video, new Event(type));
}

function Harness({ onRender, onEnd, onRestart }: { onRender: () => void; onEnd: () => void; onRestart: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const getVideo = useCallback(() => videoRef.current, []);
  const clock = useVideoClock(getVideo);
  const state = useReplayState(clock, index);
  const duration = useMediaDuration(clock, 123);
  useReplayEnd(clock, 300, { onEnd, onRestart });
  onRender();
  return (
    <div>
      <video ref={videoRef} />
      <output data-testid="state">{JSON.stringify(state)}</output>
      <output data-testid="duration">{duration}</output>
    </div>
  );
}

function setup() {
  const onRender = vi.fn();
  const onEnd = vi.fn();
  const onRestart = vi.fn();
  const view = render(<Harness onRender={onRender} onEnd={onEnd} onRestart={onRestart} />);
  const video = view.container.querySelector("video");
  if (!video) throw new Error("no video");
  const state = () => JSON.parse(screen.getByTestId("state").textContent ?? "{}") as Record<string, number>;
  return { video, onRender, onEnd, onRestart, state, view };
}

describe("replay hooks with a fake video clock", () => {
  it("follows currentTime on timeupdate and seeked, also backwards", () => {
    const { video, state } = setup();
    expect(state().utterances).toBe(0);
    at(video, 60);
    expect(state()).toMatchObject({ utterances: 3, moments: 1, events: 1, currentStep: 2 });
    at(video, 10, "seeked");
    expect(state()).toMatchObject({ utterances: 1, moments: 0, events: 0, currentStep: 0 });
  });

  it("re-renders only when the revealed sets or the current step change", () => {
    const { video, onRender } = setup();
    at(video, 61);
    const renders = onRender.mock.calls.length;
    for (const t of [61.1, 61.2, 61.5, 62, 63, 64, 65]) at(video, t); // nothing new until 66 s
    expect(onRender.mock.calls.length).toBe(renders);
    at(video, 66);
    expect(onRender.mock.calls.length).toBe(renders + 1);
  });

  it("ticks on ratechange too, so a speed change never desyncs", () => {
    const { video, state } = setup();
    video.currentTime = 90;
    video.playbackRate = 16;
    fireEvent(video, new Event("ratechange"));
    expect(state().moments).toBe(2); // m01 (58 s), m02 (85 s)
  });

  it("uses the media duration once known, else the hint", () => {
    const { video } = setup();
    expect(screen.getByTestId("duration")).toHaveTextContent("123");
    Object.defineProperty(video, "duration", { configurable: true, value: 300 });
    fireEvent.loadedMetadata(video);
    expect(screen.getByTestId("duration")).toHaveTextContent("300");
  });

  it("detects the end once per play-through, within 0.25 s of the duration or on `ended`", () => {
    const { video, onEnd, onRestart } = setup();
    at(video, 299.7);
    expect(onEnd).not.toHaveBeenCalled();
    at(video, 299.8); // 16× can skip the last frames
    at(video, 299.95);
    at(video, 300, "ended");
    expect(onEnd).toHaveBeenCalledTimes(1);

    at(video, 120, "seeked"); // back before the end: a new play-through
    expect(onRestart).toHaveBeenCalledTimes(1);
    at(video, 300, "ended");
    expect(onEnd).toHaveBeenCalledTimes(2);
  });

  it("counts the `ended` event as the end even without a known duration", () => {
    const { video, onEnd } = setup();
    // jsdom's duration is NaN; the hint (300) is used for the threshold, `ended` always counts.
    at(video, 42, "ended");
    expect(onEnd).toHaveBeenCalledTimes(1);
  });

  it("stops listening when unmounted", () => {
    const { video, onRender, view } = setup();
    view.unmount();
    const renders = onRender.mock.calls.length;
    act(() => at(video, 200));
    expect(onRender.mock.calls.length).toBe(renders);
  });
});
