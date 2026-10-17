/**
 * J2 "surgery ends → N questions ready" acceptance (brief criterion 7).
 *
 * Sources: plan §2.10 J2 ("'surgery ends' → '4 questions ready'"), §8.2 ("When the video ends,
 * the app server raises a 'questions ready' event over SSE, and the phone frame shows its
 * notification"), §10 demo step 4 ("4 questions · ~3 min"), D-069 ("N questions ready" counts
 * `questions.json`, never fixed), app/server/README.md "SSE events" (`case.ended` payload),
 * app/web/README.md (POST `replay-ended` once per play-through when the video ends or comes
 * within 0.25 s of the end; banner and phone-frame notification from the event; the POST's reply
 * stands in while the stream is down), the test brief.
 */
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import i18n from "@/i18n";

import { json } from "./harness";
import {
  CASE_ID,
  emitAll,
  fixtureEnded,
  installEventSource,
  installReplayMedia,
  liveSources,
  mockApi,
  openStreams,
  playTo,
  playToEnd,
  renderControlRoom,
  seekTo,
  toggleButton,
  tr,
  video,
  type CaseEnded,
  type Lang,
} from "./replay-harness";

let restoreMedia: () => void;
beforeEach(() => {
  restoreMedia = installReplayMedia();
  installEventSource();
});
afterEach(() => restoreMedia());

function banner(lang: Lang = "en"): HTMLElement | null {
  const title = screen.queryByText(tr(lang, "ended.title"));
  return (title?.closest("section") as HTMLElement | null) ?? null;
}

function expectBanner(event: CaseEnded, lang: Lang = "en") {
  const b = banner(lang);
  expect(b, "the 'surgery ended' banner").not.toBeNull();
  const text = b!.textContent ?? "";
  const minutes = Math.ceil(event.est_seconds / 60);
  const t = i18n.getFixedT(lang);
  expect(text).toContain(t("ended.questionsReady", { count: event.questions.operating }));
  expect(text).toContain(t("ended.aboutMinutes", { count: minutes }));
  expect(text).toContain(t("ended.reviewer", { count: event.questions.reviewer }));
  if (lang === "en") {
    // The brief's wording: "Surgery ended · N questions ready · about M min".
    expect(text).toContain("Surgery ended");
    expect(text).toMatch(new RegExp(`(^|\\D)${event.questions.operating} questions? ready`));
    expect(text).toMatch(new RegExp(`about ${minutes} min`));
  }
  const phone = screen.getByRole("figure", { name: tr(lang, "ended.phoneLabel") });
  const phoneText = phone.textContent ?? "";
  expect(phoneText).toMatch(new RegExp(`(^|\\D)${event.questions.operating}(\\D|$)`));
  expect(phoneText).toMatch(new RegExp(`(^|\\D)${minutes}(\\D|$)`));
}

const settle = () =>
  act(async () => {
    await new Promise((r) => setTimeout(r, 20));
  });

describe("J2 surgery ends: the POST", () => {
  it("criterion 7: when the video ends, the client POSTs replay-ended exactly once", async () => {
    const api = mockApi();
    await renderControlRoom();
    await openStreams();
    await playTo(150);
    expect(api.replayPosts()).toHaveLength(0);
    await playToEnd();
    await waitFor(() => expect(api.replayPosts()).toHaveLength(1));
    expect(api.replayPosts()[0]!.path).toBe(`/api/cases/${CASE_ID}/replay-ended`);
    // More end-of-video ticks in the same play-through: no second POST.
    await act(async () => {
      video().dispatchEvent(new Event("timeupdate"));
      video().dispatchEvent(new Event("ended"));
      video().dispatchEvent(new Event("pause"));
    });
    await settle();
    expect(api.replayPosts()).toHaveLength(1);
  });

  it("criterion 7: within the documented tolerance of the end (0.25 s) also counts, once", async () => {
    const api = mockApi();
    await renderControlRoom();
    await openStreams();
    await playTo(299.5); // 0.5 s before the end: not yet
    await settle();
    expect(api.replayPosts()).toHaveLength(0);
    await playTo(299.8); // within 0.25 s
    await waitFor(() => expect(api.replayPosts()).toHaveLength(1));
    await playTo(299.9);
    await playToEnd();
    await settle();
    expect(api.replayPosts()).toHaveLength(1);
  });

  it("criterion 7: again after seeking back and replaying (once per play-through)", async () => {
    const api = mockApi();
    await renderControlRoom();
    await openStreams();
    await playToEnd();
    await waitFor(() => expect(api.replayPosts()).toHaveLength(1));
    await seekTo(10);
    await playTo(200);
    await settle();
    expect(api.replayPosts()).toHaveLength(1);
    await playToEnd();
    await waitFor(() => expect(api.replayPosts()).toHaveLength(2));
    // Play again from the end: the browser restarts from 0 (a new play-through).
    await act(async () => {
      await video().play();
      await new Promise((r) => setTimeout(r, 5));
    });
    await playTo(120);
    await playToEnd();
    await waitFor(() => expect(api.replayPosts()).toHaveLength(3));
    await settle();
    expect(api.replayPosts()).toHaveLength(3);
  });
});

describe("J2 surgery ends: the case.ended event", () => {
  it("criterion 7: on case.ended for this case shows 'Surgery ended · N questions ready · about M min', the reviewer count and a phone-frame notification", async () => {
    mockApi();
    await renderControlRoom();
    await openStreams();
    await playToEnd();
    const event = fixtureEnded();
    expect(event).toEqual({ case_id: CASE_ID, questions: { operating: 8, reviewer: 4 }, est_seconds: 131 });
    await emitAll("case.ended", event);
    await waitFor(() => expect(banner()).not.toBeNull());
    expectBanner(event); // 8 questions ready · about 3 min (131 s rounded up)
  });

  it("criterion 7: N is the event's questions.operating, never fixed (a different questions.json → a different N)", async () => {
    // The server counted a reduced questions.json: 3 operating (65 s), 1 reviewer.
    const reduced: CaseEnded = { case_id: CASE_ID, questions: { operating: 3, reviewer: 1 }, est_seconds: 65 };
    mockApi({ replayEnded: () => json(reduced) });
    await renderControlRoom();
    await openStreams();
    await playToEnd();
    await emitAll("case.ended", reduced);
    await waitFor(() => expect(banner()).not.toBeNull());
    expectBanner(reduced); // 3 questions ready · about 2 min
    expect(banner()!.textContent).not.toMatch(/(^|\D)8 questions/);
    expect(banner()!.textContent).not.toMatch(/(^|\D)4 questions/);
  });

  it("criterion 7: the banner shows the SSE event's numbers (not the POST reply's) while the stream is connected", async () => {
    mockApi(); // the POST answers 8 / 4 / 131
    await renderControlRoom();
    await openStreams();
    await playToEnd();
    const fromEvent: CaseEnded = { case_id: CASE_ID, questions: { operating: 5, reviewer: 2 }, est_seconds: 200 };
    await emitAll("case.ended", fromEvent);
    await waitFor(() => expect(banner()).not.toBeNull());
    expectBanner(fromEvent); // 5 · about 4 min
  });

  it("criterion 7: M is est_seconds rounded up to whole minutes", async () => {
    mockApi();
    await renderControlRoom();
    await openStreams();
    await playToEnd();
    for (const [est, minutes] of [
      [131, 3],
      [120, 2],
      [121, 3],
      [61, 2],
      [59, 1],
    ] as const) {
      const ev: CaseEnded = { case_id: CASE_ID, questions: { operating: 4, reviewer: 0 }, est_seconds: est };
      await emitAll("case.ended", ev);
      await waitFor(() => expect(banner()?.textContent).toMatch(new RegExp(`about ${minutes} min`)));
      expectBanner(ev);
    }
  });

  it("criterion 7: events for other cases and malformed payloads are ignored", async () => {
    mockApi();
    await renderControlRoom();
    await openStreams();
    await playToEnd();
    const good = fixtureEnded();
    const bad: unknown[] = [
      { ...good, case_id: "another-case" },
      "not json at all {",
      JSON.stringify(null),
      { case_id: CASE_ID },
      { ...good, questions: { operating: "8", reviewer: 4 } },
      { ...good, questions: { operating: -1, reviewer: 4 } },
      { ...good, questions: { operating: 2.5, reviewer: 4 } },
      { ...good, questions: { reviewer: 4 } },
      { ...good, est_seconds: "131" },
      { ...good, est_seconds: -5 },
    ];
    for (const payload of bad) {
      await emitAll("case.ended", payload);
      await settle();
      expect(banner(), JSON.stringify(payload)).toBeNull();
    }
    await emitAll("case.ended", good);
    await waitFor(() => expect(banner()).not.toBeNull());
    expectBanner(good);
  });

  it("criterion 7: the banner follows the JA/EN toggle", async () => {
    mockApi();
    const user = userEvent.setup();
    await renderControlRoom();
    await openStreams();
    await playToEnd();
    await emitAll("case.ended", fixtureEnded());
    await waitFor(() => expect(banner()).not.toBeNull());
    await user.click(toggleButton("JA"));
    expectBanner(fixtureEnded(), "ja");
  });

  it("criterion 7 (README): if the event stream is down, the POST's reply (same payload) is shown", async () => {
    mockApi();
    await renderControlRoom();
    // The EventSource never opens.
    await waitFor(() => expect(liveSources().length).toBeGreaterThan(0));
    await playToEnd();
    await waitFor(() => expect(banner()).not.toBeNull());
    expectBanner(fixtureEnded());
  });

  it("criterion 7: the client listens on GET /api/events (EventSource)", async () => {
    mockApi();
    await renderControlRoom();
    await waitFor(() => expect(liveSources()).toHaveLength(1));
  });
});
