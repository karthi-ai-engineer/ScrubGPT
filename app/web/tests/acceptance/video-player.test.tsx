/**
 * Video player acceptance (brief criterion 10).
 *
 * Sources: plan §2.10 J2 (video at 1×/2×/4×/8×/16×), §6 Dev2 Block 1 ("Video player component with
 * speed control"), app/server/CLAUDE.md rule 7 (8–16× play), app/web/CLAUDE.md rules 3 and 4 (i18n;
 * the video element is the master clock, so speed changes and seeking never desync), the brief
 * (each speed sets `playbackRate`, the active one has `aria-pressed`, the rate survives seeking and
 * a source change; current time / duration shown). HTML Living Standard: loading a new source
 * resets `playbackRate` to `defaultPlaybackRate`.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { AppProviders } from "@/app/App";
import { VideoPlayer, type VideoPlayerHandle } from "@/components/VideoPlayer";
import i18n from "@/i18n";

import { installFakeMedia } from "./harness";

const RATES = [1, 2, 4, 8, 16] as const;

let restoreMedia: () => void;
beforeEach(() => {
  restoreMedia = installFakeMedia(120);
});
afterEach(() => restoreMedia());

function speedButtons(): Map<number, HTMLElement> {
  const map = new Map<number, HTMLElement>();
  for (const b of screen.getAllByRole("button")) {
    const m = /^(\d+)\s*[×x]$/.exec(b.textContent?.trim() ?? "");
    if (m) map.set(Number(m[1]), b);
  }
  return map;
}

function setup(src = "/media/cases/case-fixture-01/video.mp4") {
  const ref = createRef<VideoPlayerHandle>();
  const view = render(
    <AppProviders>
      <VideoPlayer ref={ref} src={src} title="Fixture" durationHint={300} />
    </AppProviders>,
  );
  const video = view.container.querySelector("video") as HTMLVideoElement;
  const rerender = (next: string) =>
    view.rerender(
      <AppProviders>
        <VideoPlayer ref={ref} src={next} title="Fixture" durationHint={300} />
      </AppProviders>,
    );
  return { ref, view, video, rerender };
}

describe("Video player", () => {
  it("offers exactly 1×, 2×, 4×, 8×, 16× and starts at 1× (aria-pressed)", () => {
    const { video } = setup();
    const buttons = speedButtons();
    expect([...buttons.keys()]).toEqual([...RATES]);
    expect(video.playbackRate).toBe(1);
    expect(buttons.get(1)).toHaveAttribute("aria-pressed", "true");
    for (const r of RATES.slice(1)) expect(buttons.get(r)).toHaveAttribute("aria-pressed", "false");
  });

  it.each(RATES.map((r) => [r]))("%s× sets playbackRate and is the only pressed speed", async (rate) => {
    const user = userEvent.setup();
    const { video } = setup();
    await user.click(speedButtons().get(rate)!);
    expect(video.playbackRate).toBe(rate);
    for (const [r, b] of speedButtons()) expect(b).toHaveAttribute("aria-pressed", String(r === rate));
  });

  it("the speed buttons have localised accessible names", async () => {
    setup();
    const names = () => [...speedButtons().values()].map((b) => b.getAttribute("aria-label") ?? b.textContent ?? "");
    const enNames = names();
    await act(() => i18n.changeLanguage("ja"));
    const jaNames = names();
    expect(jaNames).toHaveLength(5);
    jaNames.forEach((name, i) => expect(name).not.toBe(enNames[i]));
  });

  it("the rate survives seeking (seekTo and a user seek on the element)", async () => {
    const user = userEvent.setup();
    const { video, ref } = setup();
    await user.click(speedButtons().get(16)!);
    act(() => ref.current?.seekTo(42));
    expect(video.currentTime).toBe(42);
    expect(video.playbackRate).toBe(16);
    // A seek from the native controls.
    video.currentTime = 80;
    fireEvent.seeking(video);
    fireEvent.seeked(video);
    expect(video.playbackRate).toBe(16);
    expect(speedButtons().get(16)).toHaveAttribute("aria-pressed", "true");
  });

  it("the rate survives a source change (the media load resets playbackRate)", async () => {
    const user = userEvent.setup();
    const { video, rerender } = setup();
    await user.click(speedButtons().get(4)!);
    rerender("/media/cases/case-fixture-01/clips/case-fixture-01.m01.mp4");
    // What a browser does on a new source: run the load algorithm, then report metadata.
    video.load();
    fireEvent.loadStart(video);
    fireEvent.loadedMetadata(video);
    expect(video.playbackRate).toBe(4);
    expect(speedButtons().get(4)).toHaveAttribute("aria-pressed", "true");
  });

  it("shows current time and duration", async () => {
    const { video } = setup();
    // Before metadata: the duration hint (300 s).
    expect(document.body.textContent).toMatch(/0?0:00\s*\/\s*0?5:00/);
    fireEvent.loadedMetadata(video); // the fake media reports 120 s
    fireEvent.durationChange(video);
    video.currentTime = 65;
    fireEvent.timeUpdate(video);
    expect(document.body.textContent).toMatch(/0?1:05\s*\/\s*0?2:00/);
  });
});
