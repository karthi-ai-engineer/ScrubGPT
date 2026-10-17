import { createRef } from "react";

import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { PLAYBACK_RATES } from "@/lib/playback";

import { VideoPlayer, type VideoPlayerHandle } from "./VideoPlayer";

function getVideo(container: HTMLElement): HTMLVideoElement {
  const video = container.querySelector("video");
  if (!video) throw new Error("no <video>");
  return video;
}

describe("VideoPlayer", () => {
  it("renders a native video with controls, poster and metadata preload", () => {
    const { container } = render(<VideoPlayer src="/media/a.mp4" poster="/media/a.jpg" title="Case A" />);
    const video = getVideo(container);
    expect(video).toHaveAttribute("src", "/media/a.mp4");
    expect(video).toHaveAttribute("poster", "/media/a.jpg");
    expect(video).toHaveAttribute("preload", "metadata");
    expect(video).toHaveAttribute("controls");
  });

  it("offers 1× 2× 4× 8× 16×, starting at 1×", () => {
    render(<VideoPlayer src="/media/a.mp4" title="Case A" />);
    expect(PLAYBACK_RATES).toEqual([1, 2, 4, 8, 16]);
    for (const rate of PLAYBACK_RATES) {
      const button = screen.getByRole("button", { name: `${rate}× speed` });
      expect(button).toHaveAttribute("aria-pressed", rate === 1 ? "true" : "false");
    }
  });

  it.each(PLAYBACK_RATES)("sets playbackRate to %s× and marks that button pressed", async (rate) => {
    const user = userEvent.setup();
    const { container } = render(<VideoPlayer src="/media/a.mp4" title="Case A" />);
    const video = getVideo(container);

    await user.click(screen.getByRole("button", { name: `${rate}× speed` }));

    expect(video.playbackRate).toBe(rate);
    expect(video.defaultPlaybackRate).toBe(rate);
    for (const other of PLAYBACK_RATES) {
      expect(screen.getByRole("button", { name: `${other}× speed` })).toHaveAttribute(
        "aria-pressed",
        other === rate ? "true" : "false",
      );
    }
  });

  it("keeps the chosen rate when the src changes (the browser resets it on load)", async () => {
    const user = userEvent.setup();
    const { container, rerender } = render(<VideoPlayer src="/media/a.mp4" title="Case A" />);
    await user.click(screen.getByRole("button", { name: "8× speed" }));

    rerender(<VideoPlayer src="/media/b.mp4" title="Case B" />);
    const video = getVideo(container);
    expect(video).toHaveAttribute("src", "/media/b.mp4");
    // Simulate the media element resetting playbackRate when the new source loads.
    video.playbackRate = 1;
    fireEvent.loadedMetadata(video);
    expect(video.playbackRate).toBe(8);
    expect(screen.getByRole("button", { name: "8× speed" })).toHaveAttribute("aria-pressed", "true");
  });

  it("seekTo sets currentTime, keeps the rate, and updates the time display", async () => {
    const user = userEvent.setup();
    const ref = createRef<VideoPlayerHandle>();
    const { container } = render(<VideoPlayer ref={ref} src="/media/a.mp4" title="Case A" durationHint={300} />);
    const video = getVideo(container);
    await user.click(screen.getByRole("button", { name: "4× speed" }));

    act(() => ref.current?.seekTo(85));
    expect(video.currentTime).toBe(85);
    expect(video.playbackRate).toBe(4);
    expect(screen.getByTestId("player-time")).toHaveTextContent("1:25 / 5:00");

    act(() => ref.current?.seekTo(-10));
    expect(video.currentTime).toBe(0);
  });

  it("shows the media duration once metadata has loaded", () => {
    const { container } = render(<VideoPlayer src="/media/a.mp4" title="Case A" durationHint={300} />);
    const video = getVideo(container);
    Object.defineProperty(video, "duration", { configurable: true, value: 3725 });
    fireEvent.loadedMetadata(video);
    expect(screen.getByTestId("player-time")).toHaveTextContent("0:00 / 1:02:05");
  });
});
