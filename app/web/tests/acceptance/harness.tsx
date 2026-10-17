/**
 * Tester 2 harness for the Block 1 web acceptance tests (J1, J15, J16, video player).
 *
 * Responses are built from the committed synthetic fixtures (`contracts/fixtures`, D-026) in the
 * shapes documented in app/server/README.md (API table). `fetch` is mocked; nothing goes to a
 * network. Not a test file itself (no `.test.` in the name).
 */
import { QueryClient } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";

import type {
  Case,
  Metrics,
  Moments,
  ProcedureReference,
  Questions,
  SeedRecords,
  Timeline,
  TrustLabel,
} from "@contracts/contracts";

import { AppProviders, AppRoutes } from "@/app/App";

import caseJson from "../../../../contracts/fixtures/cases/case-fixture-01/case.json";
import metricsJson from "../../../../contracts/fixtures/cases/case-fixture-01/metrics.json";
import momentsJson from "../../../../contracts/fixtures/cases/case-fixture-01/moments.json";
import questionsJson from "../../../../contracts/fixtures/cases/case-fixture-01/questions.json";
import seedJson from "../../../../contracts/fixtures/cases/case-fixture-01/seed_records.json";
import timelineJson from "../../../../contracts/fixtures/cases/case-fixture-01/timeline.json";
import referenceJson from "../../../../contracts/fixtures/reference/rarp.json";

/** Plan §4.1 TrustLabel enum order and display emoji. */
export const TRUST_ORDER: readonly TrustLabel[] = [
  "ai_detected",
  "dataset_annotation",
  "narration_extracted",
  "operating_surgeon",
  "reviewer",
  "expert_validated",
  "simulated",
];
export const SPEC_EMOJI: Readonly<Record<TrustLabel, string>> = {
  ai_detected: "🤖",
  dataset_annotation: "📐",
  narration_extracted: "🎙️",
  operating_surgeon: "🩺",
  reviewer: "👁️",
  expert_validated: "✅",
  simulated: "🧪",
};

export const fixture = {
  case: caseJson as unknown as Case,
  timeline: timelineJson as unknown as Timeline,
  moments: momentsJson as unknown as Moments,
  questions: questionsJson as unknown as Questions,
  seedRecords: seedJson as unknown as SeedRecords,
  metrics: metricsJson as unknown as Metrics,
  reference: referenceJson as unknown as ProcedureReference,
};

export interface Summary {
  case: Case;
  media: { video: string; poster: string };
  counts: { moments: number; operating_questions: number; reviewer_questions: number; seed_records: number };
  trust_labels: TrustLabel[];
  has_metrics: boolean;
}

export interface Detail extends Summary {
  timeline: Timeline;
  moments: Moments;
  questions: Questions;
  seed_records: SeedRecords;
  metrics: Metrics | null;
}

function distinctLabels(): TrustLabel[] {
  const found = new Set<TrustLabel>();
  const t = fixture.timeline;
  for (const item of [...t.steps, ...t.events, ...t.instruments, ...t.utterances]) {
    found.add(item.provenance.trust_label);
  }
  for (const m of fixture.moments.moments) found.add(m.provenance.trust_label);
  for (const r of fixture.seedRecords.records) found.add(r.provenance.trust_label);
  return TRUST_ORDER.filter((label) => found.has(label));
}

export function fixtureSummary(): Summary {
  const id = fixture.case.id;
  return {
    case: fixture.case,
    media: { video: `/media/cases/${id}/video.mp4`, poster: `/media/cases/${id}/poster.jpg` },
    counts: {
      moments: fixture.moments.moments.length,
      operating_questions: fixture.questions.operating.length,
      reviewer_questions: fixture.questions.reviewer.length,
      seed_records: fixture.seedRecords.records.length,
    },
    trust_labels: distinctLabels(),
    has_metrics: true,
  };
}

/** A second, different case (English YouTube, full, not narrated, partial, all trust labels). */
export function secondSummary(): Summary {
  const id = "yt-en-03";
  return {
    case: {
      ...fixture.case,
      id,
      title: { ja: "第二症例（YouTube、英語）", en: "Second case (YouTube, English)" },
      source: "youtube",
      source_url: "https://example.invalid/watch",
      language: "en",
      video_type: "full",
      narrated: false,
      synthetic_speech: false,
      duration_s: 4512,
      status: "partial",
      data_note: { ja: "二番目の症例のデータ注記。", en: "Data note of the second case." },
    },
    media: { video: `/media/cases/${id}/video.mp4`, poster: `/media/cases/${id}/poster.jpg` },
    counts: { moments: 11, operating_questions: 13, reviewer_questions: 17, seed_records: 19 },
    trust_labels: [...TRUST_ORDER],
    has_metrics: false,
  };
}

export function fixtureDetail(): Detail {
  return {
    ...fixtureSummary(),
    timeline: fixture.timeline,
    moments: fixture.moments,
    questions: fixture.questions,
    seed_records: fixture.seedRecords,
    metrics: fixture.metrics,
  };
}

export function apiError(code: string, status: number): Response {
  return json(
    { contract_version: "1.0", error: { code, message: `${code} (test)`, retryable: status >= 500 } },
    status,
  );
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Handler = () => Response | Promise<Response>;

/** Mocks `fetch`: `routes` maps a path (no query) to a handler; anything else is a 404 ApiError. */
export function mockServer(routes: Record<string, Handler>) {
  const spy = vi.fn(async (input: RequestInfo | URL) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const path = new URL(raw, "http://localhost").pathname;
    const handler = routes[path];
    return handler ? handler() : apiError("not_found", 404);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

/** The standard app server: one fixture case (or the given list), its detail and the reference. */
export function standardRoutes(cases: Summary[] = [fixtureSummary()]): Record<string, Handler> {
  return {
    "/api/health": () =>
      json({ status: "ok", contract_version: "1.0", brain_mode: "mock", cases: { loaded: cases.length, rejected: 0 } }),
    "/api/cases": () => json({ cases }),
    "/api/cases/case-fixture-01": () => json(fixtureDetail()),
    "/api/references/rarp": () => json(fixture.reference),
  };
}

export function renderApp(path: string): RenderResult {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity, staleTime: Infinity } },
  });
  return render(
    <AppProviders queryClient={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </AppProviders>,
  );
}

/** Flattens an i18n resource object into `{ "a.b": "value" }`. */
export function flatten(obj: unknown, prefix = ""): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  if (obj !== null && typeof obj === "object" && !Array.isArray(obj)) {
    for (const [k, v] of Object.entries(obj)) {
      const key = prefix ? `${prefix}.${k}` : k;
      if (v !== null && typeof v === "object" && !Array.isArray(v)) Object.assign(out, flatten(v, key));
      else out[key] = v;
    }
  }
  return out;
}

/** Every string under a `ja` or `en` key of a Bilingual anywhere in `value`. */
export function bilingualTexts(value: unknown, lang: "ja" | "en"): string[] {
  const out: string[] = [];
  const walk = (v: unknown) => {
    if (Array.isArray(v)) v.forEach(walk);
    else if (v !== null && typeof v === "object") {
      const o = v as Record<string, unknown>;
      if (typeof o.ja === "string" && typeof o.en === "string") out.push(o[lang] as string);
      Object.values(o).forEach(walk);
    }
  };
  walk(value);
  return out;
}

/** Visible text nodes plus user-facing attributes (aria-label, title, alt, placeholder). */
export function visibleStrings(root: HTMLElement): string[] {
  const out: string[] = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const text = n.textContent?.trim();
    if (text) out.push(text);
  }
  root.querySelectorAll("*").forEach((el) => {
    for (const attr of ["aria-label", "title", "alt", "placeholder"]) {
      const v = el.getAttribute(attr)?.trim();
      if (v) out.push(v);
    }
  });
  return out;
}

/**
 * A fake media element state, because jsdom doesn't play media. Setting `src` or calling `load()`
 * runs the part of the HTML media load algorithm that matters here: `playbackRate` is reset to
 * `defaultPlaybackRate` (HTML Living Standard, "media element load algorithm").
 */
export function installFakeMedia(duration = 300) {
  const state = new WeakMap<HTMLMediaElement, { t: number; rate: number; def: number }>();
  const get = (el: HTMLMediaElement) => {
    let s = state.get(el);
    if (!s) {
      s = { t: 0, rate: 1, def: 1 };
      state.set(el, s);
    }
    return s;
  };
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
    set(this: HTMLMediaElement, v: number) {
      get(this).t = v;
    },
  });
  define("playbackRate", {
    get(this: HTMLMediaElement) {
      return get(this).rate;
    },
    set(this: HTMLMediaElement, v: number) {
      get(this).rate = v;
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
  define("duration", {
    get() {
      return duration;
    },
  });
  define("load", {
    value(this: HTMLMediaElement) {
      const s = get(this);
      s.rate = s.def;
      s.t = 0;
    },
  });
  define("play", { value: () => Promise.resolve() });
  define("pause", { value: () => undefined });
  return () => {
    for (const [name, desc] of saved) {
      if (desc) Object.defineProperty(proto, name, desc);
      else delete (proto as unknown as Record<string, unknown>)[name];
    }
  };
}

/** The Procedure Reference name of a step id (plan §4.2b). */
export function stepName(stepId: string) {
  for (const phase of fixture.reference.phases) {
    for (const step of phase.steps) if (step.id === stepId) return step.name;
  }
  throw new Error(`step ${stepId} is not in the fixture reference`);
}
