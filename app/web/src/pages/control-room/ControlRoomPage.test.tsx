import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProcedureReference } from "@contracts/contracts";

import type { CaseEndedEvent } from "@/api/types";
import i18n from "@/i18n";
import { fixtureDetail, mockFetch } from "@/test/fixtures";
import { renderApp } from "@/test/render";

import referenceJson from "../../../../../contracts/fixtures/reference/rarp.json";

const reference = referenceJson as ProcedureReference;
const CASE = "case-fixture-01";
const ENDED_URL = `/api/cases/${CASE}/replay-ended`;
/** What the server would count from questions.json (8 operating, 131 s; 4 reviewer). */
const serverPayload: CaseEndedEvent = { case_id: CASE, questions: { operating: 8, reviewer: 4 }, est_seconds: 131 };

/** A stand-in for the browser's EventSource that the test drives by hand. */
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly url: string;
  readyState = 0;
  closed = false;
  onopen: ((e: Event) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  private listeners = new Map<string, Set<(e: MessageEvent<string>) => void>>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }
  addEventListener(name: string, fn: (e: MessageEvent<string>) => void) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set());
    this.listeners.get(name)?.add(fn);
  }
  removeEventListener(name: string, fn: (e: MessageEvent<string>) => void) {
    this.listeners.get(name)?.delete(fn);
  }
  close() {
    this.closed = true;
    this.readyState = 2;
  }
  open() {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }
  emit(name: string, data: unknown) {
    const event = new MessageEvent(name, { data: typeof data === "string" ? data : JSON.stringify(data) });
    for (const fn of this.listeners.get(name) ?? []) fn(event);
  }
}

function routes(url: string) {
  if (url === `/api/cases/${CASE}`) return { status: 200, body: fixtureDetail };
  if (url === "/api/references/rarp") return { status: 200, body: reference };
  if (url === ENDED_URL) return { status: 200, body: serverPayload };
  return undefined;
}

let fetchSpy: ReturnType<typeof mockFetch>;
const endedPosts = () =>
  fetchSpy.mock.calls.filter(([input, init]) => input === ENDED_URL && (init as RequestInit | undefined)?.method === "POST");

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  fetchSpy = mockFetch(routes);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function openControlRoom() {
  const view = renderApp(`/cases/${CASE}/control-room`);
  await screen.findByRole("heading", { level: 1, name: "Control Room" });
  const video = view.container.querySelector("video");
  if (!video) throw new Error("no video");
  Object.defineProperty(video, "duration", { configurable: true, value: 300 });
  fireEvent.loadedMetadata(video);
  // Wait for the Reference so names are resolved.
  await waitFor(() => expect(screen.getByTestId("current-step")).toHaveTextContent("Bladder drop"));
  return { view, video };
}

/** The fake video clock: move the playhead and fire the event the browser would. */
function at(video: HTMLVideoElement, t: number, type: "timeupdate" | "seeked" | "ended" = "timeupdate") {
  act(() => {
    video.currentTime = t;
    video.dispatchEvent(new Event(type));
  });
}

const section = (name: string) => {
  const heading = screen.getByRole("heading", { level: 2, name });
  const el = heading.closest("section");
  if (!el) throw new Error(`no section ${name}`);
  return el;
};
const tickerItems = () => within(section("Transcript")).queryAllByRole("listitem");
const alertItems = () => within(section("Alerts")).queryAllByRole("listitem");
const markers = () => within(screen.getByTestId("event-strip")).queryAllByRole("listitem");

describe("Control Room", () => {
  it("is linked from the case page and the home cards", async () => {
    mockFetch((url) =>
      url === "/api/cases" ? { status: 200, body: { cases: [fixtureDetail] } } : routes(url),
    );
    const home = renderApp("/");
    const link = await screen.findByRole("link", { name: `Open Control Room: ${fixtureDetail.case.title.en}` });
    expect(link).toHaveAttribute("href", `/cases/${CASE}/control-room`);
    home.unmount();

    renderApp(`/cases/${CASE}`);
    expect(await screen.findByRole("link", { name: "Open Control Room" })).toHaveAttribute(
      "href",
      `/cases/${CASE}/control-room`,
    );
  });

  it("reveals transcript, alerts and event markers as the video clock advances, and hides them on a backwards seek", async () => {
    const { video } = await openControlRoom();
    expect(screen.getByText("No speech yet.")).toBeInTheDocument();
    expect(screen.getByText("No alerts yet.")).toBeInTheDocument();
    expect(markers()).toHaveLength(0);

    at(video, 57.9);
    expect(tickerItems()).toHaveLength(2); // 5 s, 52 s
    expect(alertItems()).toHaveLength(0);
    expect(markers()).toHaveLength(0);

    at(video, 58); // m01 and e001 start exactly here
    expect(alertItems()).toHaveLength(1);
    expect(markers()).toHaveLength(1);

    at(video, 90);
    expect(tickerItems().map((li) => li.getAttribute("data-utterance-id"))).toEqual([
      "case-fixture-01.u0001",
      "case-fixture-01.u0002",
      "case-fixture-01.u0003",
      "case-fixture-01.u0004",
      "case-fixture-01.u0005",
    ]); // newest last
    expect(alertItems().map((li) => li.getAttribute("data-moment-id"))).toEqual([
      "case-fixture-01.m02",
      "case-fixture-01.m01",
    ]); // newest first

    at(video, 30, "seeked");
    expect(tickerItems()).toHaveLength(1);
    expect(alertItems()).toHaveLength(0);
    expect(markers()).toHaveLength(0);
  });

  it("shows each utterance in the current language with its original language, class, speaker and trust label", async () => {
    const { video } = await openControlRoom();
    at(video, 61);
    const item = tickerItems()[2];
    if (!item) throw new Error("no third utterance");
    expect(item).toHaveTextContent("There's some bleeding. Raise the insufflation pressure, please.");
    expect(within(item).getByText("Original: Japanese")).toBeInTheDocument();
    expect(within(item).getByText("Instruction")).toBeInTheDocument();
    expect(within(item).getByText("Speaker 1")).toBeInTheDocument();
    expect(within(item).getByText("AI-detected")).toBeInTheDocument();

    await act(() => i18n.changeLanguage("ja"));
    expect(item).toHaveTextContent("少し出血しています。気腹圧を上げてください。");
    expect(within(item).queryByText(/原文/)).not.toBeInTheDocument(); // same as the original
    expect(within(item).getByText("指示")).toBeInTheDocument();
    expect(within(item).getByText("話者1")).toBeInTheDocument();
  });

  it("shows alert cards with kind, title, why-flagged, checkpoint name, score and trust; clicking seeks", async () => {
    const user = userEvent.setup();
    const { video } = await openControlRoom();
    at(video, 125);
    const newest = alertItems()[0];
    if (!newest) throw new Error("no alert");
    expect(newest).toHaveTextContent("Ureteral orifices check");
    expect(newest).toHaveTextContent("Checkpoint");
    expect(newest).toHaveTextContent("Checkpoint: ureteral orifices identified");
    expect(newest).toHaveTextContent("Score 0.80");
    expect(within(newest).getByText("AI-detected")).toBeInTheDocument();
    const checkpoint = reference.phases
      .flatMap((p) => p.steps)
      .flatMap((s) => s.checkpoints)
      .find((c) => c.id === "rarp.p06.s01.c1");
    expect(newest).toHaveTextContent(`Checkpoint: ${checkpoint?.text.en}`);

    await user.click(within(alertItems()[1] as HTMLElement).getByRole("button"));
    expect(video.currentTime).toBe(85); // m02
  });

  it("event markers have a tooltip with signals and the trust label, and seek on click", async () => {
    const user = userEvent.setup();
    const { video } = await openControlRoom();
    at(video, 101);
    expect(markers()).toHaveLength(2);
    const smoke = screen.getByRole("button", { name: "Smoke at 1:40" });
    expect(screen.getAllByRole("tooltip", { hidden: true })).toHaveLength(2);
    const bleeding = screen.getByRole("button", { name: "Bleeding at 0:58" });
    const description = document.getElementById(bleeding.getAttribute("aria-describedby") ?? "");
    expect(description).toHaveTextContent("Signals: Red area, AI image check");
    expect(description).toHaveTextContent("AI-detected");
    await user.click(smoke);
    expect(video.currentTime).toBe(100);
  });

  it("step bar: colours reached segments only, names the current step with its trust badge, toggles tracks, seeks", async () => {
    const user = userEvent.setup();
    const { video, view } = await openControlRoom();
    at(video, 60);
    const states = () => [...view.container.querySelectorAll("[data-step-state]")].map((el) => el.getAttribute("data-step-state"));
    expect(states()).toEqual(["reached", "reached", "current", ...Array(9).fill("upcoming")]);
    const current = screen.getByTestId("current-step");
    expect(current).toHaveTextContent("DVC ligation");
    expect(within(current).getByText("AI-detected")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Dataset" }));
    expect(screen.getByRole("button", { name: "Dataset" })).toHaveAttribute("aria-pressed", "true");
    expect(states()).toHaveLength(fixtureDetail.timeline.steps.filter((s) => s.track === "dataset").length);
    expect(within(screen.getByTestId("current-step")).getByText("Dataset annotation")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Jump to 0:27: Endopelvic fascia incision" }));
    expect(video.currentTime).toBe(27);
  });

  it("the graph grows with the replay (one node per record)", async () => {
    const { video } = await openControlRoom();
    const counts = () => screen.getByTestId("graph-counts").textContent;
    expect(counts()).toBe("Steps 1 · Moments 0 · Records 0");
    at(video, 60);
    expect(counts()).toBe("Steps 3 · Moments 1 · Records 2");
    at(video, 300);
    expect(counts()).toContain(`Records ${fixtureDetail.seed_records.records.length}`);
  });

  describe("surgery ends", () => {
    it("POSTs replay-ended exactly once and shows N from the SSE event, not a fixed number", async () => {
      const { video } = await openControlRoom();
      const source = FakeEventSource.instances.at(-1);
      expect(source?.url).toBe("/api/events");
      act(() => source?.open());

      at(video, 299.7);
      expect(endedPosts()).toHaveLength(0);
      at(video, 299.8); // within 0.25 s of the end: 16× may never reach the last frame
      at(video, 299.9);
      at(video, 300, "ended");
      await waitFor(() => expect(endedPosts()).toHaveLength(1));
      expect(screen.queryByTestId("surgery-ended")).not.toBeInTheDocument(); // waits for the event

      // Another case's event is ignored; a malformed one too.
      act(() => source?.emit("case.ended", { ...serverPayload, case_id: "other-case" }));
      act(() => source?.emit("case.ended", "{not json"));
      expect(screen.queryByTestId("surgery-ended")).not.toBeInTheDocument();

      act(() => source?.emit("case.ended", { case_id: CASE, questions: { operating: 5, reviewer: 2 }, est_seconds: 61 }));
      const banner = await screen.findByTestId("surgery-ended");
      expect(within(banner).getByRole("heading", { name: "Surgery ended" })).toBeInTheDocument();
      expect(within(banner).getByTestId("ended-summary")).toHaveTextContent("5 questions ready · about 2 min");
      expect(within(banner).getByTestId("ended-reviewer")).toHaveTextContent("2 reviewer questions");
      expect(within(banner).getByTestId("phone-line")).toHaveTextContent("5 questions · ~2 min");
      const answer = within(banner).getByRole("button", { name: "Answer now" });
      expect(answer).toBeDisabled();
      expect(answer).toHaveAccessibleDescription("The Answer app comes in Block 3.");

      await act(() => i18n.changeLanguage("ja"));
      expect(within(banner).getByTestId("ended-summary")).toHaveTextContent("質問5件の準備ができました");
      expect(within(banner).getByTestId("ended-summary")).toHaveTextContent("約2分");
      expect(within(banner).getByRole("button", { name: "今すぐ回答" })).toBeDisabled();
    });

    it("re-arms after seeking back before the end: a new play-through POSTs again", async () => {
      const { video } = await openControlRoom();
      const source = FakeEventSource.instances.at(-1);
      act(() => source?.open());
      at(video, 300, "ended");
      await waitFor(() => expect(endedPosts()).toHaveLength(1));
      act(() => source?.emit("case.ended", serverPayload));
      expect(await screen.findByTestId("surgery-ended")).toBeInTheDocument();

      at(video, 300); // more ticks at the end: still one POST
      expect(endedPosts()).toHaveLength(1);

      at(video, 120, "seeked");
      expect(screen.queryByTestId("surgery-ended")).not.toBeInTheDocument();
      at(video, 299.9);
      await waitFor(() => expect(endedPosts()).toHaveLength(2));
    });

    it("uses the POST reply while the event stream is not connected", async () => {
      const { video } = await openControlRoom();
      at(video, 300, "ended");
      const banner = await screen.findByTestId("surgery-ended");
      expect(within(banner).getByTestId("ended-summary")).toHaveTextContent("8 questions ready · about 3 min");
      expect(within(banner).getByTestId("ended-reviewer")).toHaveTextContent("4 reviewer questions");
    });

    it("shows a retry when the POST fails", async () => {
      const user = userEvent.setup();
      fetchSpy.mockRestore();
      fetchSpy = mockFetch((url) => (url === ENDED_URL ? { status: 503, body: {} } : routes(url)));
      const { video } = await openControlRoom();
      at(video, 300, "ended");
      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent("Couldn't tell the app server that the replay ended.");
      fetchSpy.mockRestore();
      fetchSpy = mockFetch(routes);
      await user.click(within(alert).getByRole("button", { name: "Try again" }));
      await waitFor(() => expect(endedPosts()).toHaveLength(1));
      expect(await screen.findByTestId("surgery-ended")).toBeInTheDocument();
    });

    it("closes the event stream when the page unmounts", async () => {
      const { view } = await openControlRoom();
      const source = FakeEventSource.instances.at(-1);
      view.unmount();
      expect(source?.closed).toBe(true);
    });
  });
});
