/**
 * Tester 2 harness for the Block 2 web acceptance tests (J2 Control Room, J8 graph panel, the
 * "surgery ends" flow over SSE). Not a test file itself (no `.test.` in the name).
 *
 * jsdom neither plays media nor has `EventSource`, so this file provides:
 * - a fake media element that behaves like a browser's for what the spec relies on (plan §8.2:
 *   the `<video>` is the master clock): `currentTime`, `duration`, `paused`, `ended`,
 *   `playbackRate`; setting `currentTime` is a seek (fires `seeking`, `timeupdate`, `seeked` as
 *   queued tasks, as in the HTML seek algorithm); `play()` on an ended video seeks to the start;
 *   playback progress is driven by the test (`playTo`), which fires `timeupdate` like a browser;
 * - a fake `EventSource` the test can open and push named events into;
 * - a `fetch` mock that records the method of each call (for `POST …/replay-ended`).
 */
import { act, screen, waitFor, within } from "@testing-library/react";
import { expect, vi } from "vitest";

import en from "@/i18n/en.json";
import ja from "@/i18n/ja.json";

import { apiError, fixture, flatten, json, renderApp, SPEC_EMOJI, standardRoutes, type Summary } from "./harness";

export const flat = { en: flatten(en), ja: flatten(ja) } as const;
export type Lang = "en" | "ja";
export const tr = (lang: Lang, key: string) => {
  const value = flat[lang][key];
  if (typeof value !== "string") throw new Error(`no i18n key ${key} (${lang})`);
  return value;
};

export const CASE_ID = fixture.case.id;
export const DURATION = fixture.case.duration_s;

// --- Fake media ---------------------------------------------------------------------------

interface MediaState {
  t: number;
  rate: number;
  def: number;
  paused: boolean;
  ended: boolean;
}

export function installReplayMedia(duration = DURATION) {
  const state = new WeakMap<HTMLMediaElement, MediaState>();
  const get = (el: HTMLMediaElement) => {
    let s = state.get(el);
    if (!s) {
      s = { t: 0, rate: 1, def: 1, paused: true, ended: false };
      state.set(el, s);
    }
    return s;
  };
  const fire = (el: HTMLMediaElement, name: string) => el.dispatchEvent(new Event(name));
  const proto = HTMLMediaElement.prototype;
  const saved = new Map<string, PropertyDescriptor | undefined>();
  const define = (name: string, desc: PropertyDescriptor) => {
    saved.set(name, Object.getOwnPropertyDescriptor(proto, name));
    Object.defineProperty(proto, name, { configurable: true, ...desc });
  };
  define("currentTime", {
    get(this: HTMLMediaElement) {
      return get(this).t;
    },
    // A seek: the position changes now; `seeking`, `timeupdate`, `seeked` follow as tasks.
    set(this: HTMLMediaElement, v: number) {
      const s = get(this);
      s.t = Math.max(0, Math.min(duration, v));
      if (s.t < duration) s.ended = false;
      setTimeout(() => {
        fire(this, "seeking");
        fire(this, "timeupdate");
        fire(this, "seeked");
      }, 0);
    },
  });
  define("playbackRate", {
    get(this: HTMLMediaElement) {
      return get(this).rate;
    },
    set(this: HTMLMediaElement, v: number) {
      const s = get(this);
      if (s.rate !== v) {
        s.rate = v;
        setTimeout(() => fire(this, "ratechange"), 0);
      }
    },
  });
  define("defaultPlaybackRate", {
    get(this: HTMLMediaElement) {
      return get(this).def;
    },
    set(this: HTMLMediaElement, v: number) {
      get(this).def = v;
    },
  });
  define("duration", { get: () => duration });
  define("paused", {
    get(this: HTMLMediaElement) {
      return get(this).paused;
    },
  });
  define("ended", {
    get(this: HTMLMediaElement) {
      return get(this).ended;
    },
  });
  define("load", {
    value(this: HTMLMediaElement) {
      const s = get(this);
      s.rate = s.def;
      s.t = 0;
      s.ended = false;
    },
  });
  define("play", {
    value(this: HTMLMediaElement) {
      const s = get(this);
      if (s.ended) {
        s.t = 0;
        s.ended = false;
        fire(this, "seeking");
        fire(this, "timeupdate");
        fire(this, "seeked");
      }
      s.paused = false;
      fire(this, "play");
      fire(this, "playing");
      return Promise.resolve();
    },
  });
  define("pause", {
    value(this: HTMLMediaElement) {
      const s = get(this);
      if (!s.paused) {
        s.paused = true;
        fire(this, "pause");
      }
    },
  });
  controller = {
    position(el, t) {
      get(el).t = t;
    },
    end(el) {
      const s = get(el);
      s.t = duration;
      s.ended = true;
      s.paused = true;
    },
  };
  return () => {
    controller = null;
    for (const [name, desc] of saved) {
      if (desc) Object.defineProperty(proto, name, desc);
      else delete (proto as unknown as Record<string, unknown>)[name];
    }
  };
}

interface MediaController {
  /** Playback progress (not a seek): the position moves without `seeking`/`seeked`. */
  position(el: HTMLMediaElement, t: number): void;
  /** The end of playback: position = duration, `ended` and `paused` become true. */
  end(el: HTMLMediaElement): void;
}
let controller: MediaController | null = null;
function media(): MediaController {
  if (!controller) throw new Error("installReplayMedia() first");
  return controller;
}

export function video(): HTMLVideoElement {
  const el = document.querySelector("video");
  if (!el) throw new Error("no <video> on the page");
  return el;
}

/** Normal playback reached `t` (paused = false); fires `timeupdate` as a browser does. */
export async function playTo(t: number) {
  const el = video();
  await act(async () => {
    if (el.paused) await el.play();
    media().position(el, t);
    el.dispatchEvent(new Event("timeupdate"));
  });
}

/** A user seek (sets `currentTime`), then waits for the queued `seeked`. */
export async function seekTo(t: number) {
  const el = video();
  await act(async () => {
    el.currentTime = t;
    await new Promise((r) => setTimeout(r, 5));
  });
}

/** The video plays to its end: position = duration, then `timeupdate`, `pause`, `ended`. */
export async function playToEnd() {
  const el = video();
  await act(async () => {
    if (el.paused) await el.play();
    media().position(el, el.duration);
    el.dispatchEvent(new Event("timeupdate"));
    media().end(el);
    el.dispatchEvent(new Event("pause"));
    el.dispatchEvent(new Event("ended"));
  });
}

// --- Fake EventSource ---------------------------------------------------------------------

export class FakeEventSource extends EventTarget {
  static instances: FakeEventSource[] = [];
  readonly url: string;
  readyState = 0;
  onopen: ((ev: Event) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  closed = false;

  constructor(url: string | URL) {
    super();
    this.url = String(url);
    FakeEventSource.instances.push(this);
  }

  open() {
    this.readyState = 1;
    const ev = new Event("open");
    this.onopen?.(ev);
    this.dispatchEvent(ev);
  }

  emit(name: string, data: unknown) {
    const ev = new MessageEvent(name, { data: typeof data === "string" ? data : JSON.stringify(data) });
    if (name === "message") this.onmessage?.(ev);
    this.dispatchEvent(ev);
  }

  close() {
    this.closed = true;
    this.readyState = 2;
  }
}

export function installEventSource() {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
}

/** Every open (not closed) EventSource on `/api/events`. */
export function liveSources(): FakeEventSource[] {
  return FakeEventSource.instances.filter((s) => !s.closed && new URL(s.url, "http://localhost").pathname === "/api/events");
}

export async function openStreams() {
  await waitFor(() => expect(liveSources().length).toBeGreaterThan(0));
  await act(async () => {
    for (const s of liveSources()) s.open();
  });
}

export async function emitAll(name: string, data: unknown) {
  await act(async () => {
    for (const s of liveSources()) s.emit(name, data);
  });
}

// --- fetch mock ---------------------------------------------------------------------------

export interface Call {
  method: string;
  path: string;
}

export interface CaseEnded {
  case_id: string;
  questions: { operating: number; reviewer: number };
  est_seconds: number;
}

/** What the real server would answer for the fixture (counted from questions.json). */
export function fixtureEnded(): CaseEnded {
  const q = fixture.questions;
  return {
    case_id: CASE_ID,
    questions: { operating: q.operating.length, reviewer: q.reviewer.length },
    est_seconds: q.operating.reduce((sum, x) => sum + x.est_seconds, 0),
  };
}

export function mockApi(
  options: { replayEnded?: () => Response | Promise<Response>; cases?: Summary[]; extra?: Record<string, () => Response> } = {},
) {
  const routes: Record<string, () => Response | Promise<Response>> = {
    ...standardRoutes(options.cases),
    [`/api/cases/${CASE_ID}/replay-ended`]: options.replayEnded ?? (() => json(fixtureEnded())),
    ...options.extra,
  };
  const calls: Call[] = [];
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const path = new URL(raw, "http://localhost").pathname;
    const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    calls.push({ method, path });
    const handler = routes[path];
    return handler ? handler() : apiError("not_found", 404);
  });
  vi.stubGlobal("fetch", spy);
  return {
    calls,
    replayPosts: () => calls.filter((c) => c.method === "POST" && c.path.endsWith("/replay-ended")),
  };
}

// --- Page helpers -------------------------------------------------------------------------

export async function renderControlRoom(caseId = CASE_ID) {
  const view = renderApp(`/cases/${caseId}/control-room`);
  await screen.findByRole("heading", { level: 1, name: tr("en", "controlRoom.title") });
  await waitFor(() => expect(document.querySelector("video")).not.toBeNull());
  // The Reference (step names) has loaded once a step name can be resolved; give it a tick.
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
  return view;
}

export function region(lang: Lang, key: string): HTMLElement {
  return screen.getByRole("region", { name: tr(lang, key) });
}

/** Text of a trust badge as the spec describes it: the emoji and the localised name. */
export function hasTrustBadge(el: HTMLElement, label: keyof typeof SPEC_EMOJI, lang: Lang): boolean {
  const text = el.textContent ?? "";
  return text.includes(SPEC_EMOJI[label]) && text.includes(tr(lang, `trust.${label}`));
}

export function toggleButton(lang: "JA" | "EN"): HTMLElement {
  const button = screen.getAllByRole("button").find((b) => b.textContent?.trim() === lang);
  if (!button) throw new Error(`no ${lang} toggle button`);
  return button;
}

export { within };
