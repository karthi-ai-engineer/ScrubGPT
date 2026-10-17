/**
 * J2 Control Room acceptance (brief criteria 3, 4, 5, 6 and 9).
 *
 * Sources: plan §2.10 J2 ("Video at 1×/2×/4×/8×/16×; a live step bar and event markers; a JA/EN
 * transcript ticker; alerts"), §8.2 ("The browser `<video>` is the master clock … reveals each
 * timeline item when `currentTime ≥ item.t_start`. Speed changes and seeking can therefore never
 * put things out of sync"), §4.2 / §4.2b (timeline, moments, Reference names), §10 demo step 3,
 * app/web/CLAUDE.md rules 3–6, root CLAUDE.md (bilingual; provenance visible), app/web/README.md
 * (Control Room route, links from the case page and every home card), the test brief.
 *
 * Every expected value is computed from the committed synthetic fixture (contracts/fixtures).
 */
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { StepSegment } from "@contracts/contracts";

interface Timed {
  t_start: number;
}

import i18n from "@/i18n";

import {
  bilingualTexts,
  fixture,
  fixtureDetail,
  fixtureSummary,
  json,
  renderApp,
  secondSummary,
  stepName,
  visibleStrings,
} from "./harness";
import {
  CASE_ID,
  flat,
  hasTrustBadge,
  installEventSource,
  installReplayMedia,
  mockApi,
  playTo,
  region,
  renderControlRoom,
  seekTo,
  toggleButton,
  tr,
  video,
  type Lang,
} from "./replay-harness";

const tl = fixture.timeline;
const moments = fixture.moments.moments;

function upTo<T extends Timed>(items: readonly T[], t: number): T[] {
  return items.filter((i) => i.t_start <= t).sort((a, b) => a.t_start - b.t_start);
}
const aiSteps = tl.steps.filter((s) => s.track === "ai") as StepSegment[];
const datasetSteps = tl.steps.filter((s) => s.track === "dataset") as StepSegment[];
function currentStep(steps: readonly StepSegment[], t: number): StepSegment | undefined {
  return steps.find((s) => s.t_start <= t && t < s.t_end);
}

let restoreMedia: () => void;
beforeEach(() => {
  restoreMedia = installReplayMedia();
  installEventSource();
});
afterEach(() => restoreMedia());

// --- what is shown ------------------------------------------------------------------------

function tickerItems(lang: Lang = "en"): HTMLElement[] {
  return within(region(lang, "ticker.title")).queryAllByRole("listitem");
}
function eventMarkers(lang: Lang = "en"): HTMLElement[] {
  const list = within(region(lang, "events.title")).getByRole("list", { name: tr(lang, "events.stripLabel") });
  return within(list).queryAllByRole("button");
}
function alertItems(lang: Lang = "en"): HTMLElement[] {
  return within(region(lang, "alerts.title")).queryAllByRole("listitem");
}
function stepBar(lang: Lang = "en"): HTMLElement {
  return region(lang, "stepBar.title");
}
function reachedSegments(lang: Lang = "en"): HTMLElement[] {
  const bar = within(stepBar(lang)).getByRole("group", { name: tr(lang, "stepBar.barLabel") });
  return within(bar).queryAllByRole("button");
}
function currentStepLine(lang: Lang = "en"): HTMLElement {
  const label = within(stepBar(lang)).getByText(tr(lang, "stepBar.current"));
  return label.parentElement as HTMLElement;
}

/** The master clock rule at video time `t` (shown track = ai, the fixture's default). */
function expectRevealedAt(t: number, lang: Lang = "en") {
  const utterances = upTo(tl.utterances, t);
  const ticker = tickerItems(lang);
  expect(ticker.map((li) => li.textContent?.includes(utterances[ticker.indexOf(li)]!.text[lang]))).toEqual(
    utterances.map(() => true),
  );
  expect(ticker).toHaveLength(utterances.length);
  expect(eventMarkers(lang), `events at ${t}`).toHaveLength(upTo(tl.events, t).length);
  const shownMoments = upTo(moments, t);
  const alerts = alertItems(lang);
  expect(alerts, `alerts at ${t}`).toHaveLength(shownMoments.length);
  for (const m of shownMoments) {
    expect(alerts.some((li) => li.textContent?.includes(m.title[lang])), `${m.id} at ${t}`).toBe(true);
  }
  for (const m of moments.filter((x) => x.t_start > t)) {
    expect(alerts.some((li) => li.textContent?.includes(m.title[lang])), `${m.id} early at ${t}`).toBe(false);
  }
  expect(reachedSegments(lang), `steps at ${t}`).toHaveLength(upTo(aiSteps, t).length);
}

// --- Criterion 3: route ------------------------------------------------------------------------

describe("J2 route", () => {
  it("criterion 3: /cases/:caseId/control-room shows the Control Room for the case", async () => {
    mockApi();
    await renderControlRoom();
    expect(screen.getAllByText(fixture.case.title.en).length).toBeGreaterThan(0);
    expect(video()).toBeInTheDocument();
  });

  it("criterion 3: reachable from each home card", async () => {
    mockApi({ cases: [fixtureSummary(), secondSummary()] });
    renderApp("/");
    await screen.findByRole("link", { name: fixture.case.title.en });
    const links = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    for (const id of [CASE_ID, secondSummary().case.id]) {
      expect(links, id).toContain(`/cases/${id}/control-room`);
    }
  });

  it("criterion 3: reachable from the case page (link opens it)", async () => {
    mockApi();
    const user = userEvent.setup();
    renderApp(`/cases/${CASE_ID}`);
    await screen.findByRole("heading", { level: 1, name: fixture.case.title.en });
    const link = screen
      .getAllByRole("link")
      .find((a) => a.getAttribute("href") === `/cases/${CASE_ID}/control-room`);
    expect(link).toBeDefined();
    await user.click(link!);
    expect(await screen.findByRole("heading", { level: 1, name: tr("en", "controlRoom.title") })).toBeInTheDocument();
  });

  it("criterion 3: an unknown case shows a localised not-found (EN and JA)", async () => {
    mockApi();
    renderApp("/cases/no-such-case/control-room");
    expect(await screen.findByText(tr("en", "errors.caseNotFound.title"))).toBeInTheDocument();
    await act(() => i18n.changeLanguage("ja"));
    expect(screen.getByText(tr("ja", "errors.caseNotFound.title"))).toBeInTheDocument();
  });
});

// --- Criterion 4: the master clock -------------------------------------------------------------

describe("J2 master clock (plan §8.2)", () => {
  const times = [0, 4.99, 5, 25, 51.99, 52, 57.99, 58, 60, 85, 100, 125, 150, 200, 230, 262, 280, 287, 299];

  it("criterion 4: at every video time t exactly the items with t_start <= t are shown (ticker, markers, alerts, steps)", async () => {
    mockApi();
    await renderControlRoom();
    expectRevealedAt(0);
    for (const t of times) {
      await playTo(t);
      expectRevealedAt(t);
    }
  });

  it("criterion 4: seeking backwards hides later items again (and forwards reveals them)", async () => {
    mockApi();
    await renderControlRoom();
    await playTo(299);
    expectRevealedAt(299);
    for (const t of [200, 60, 57.99, 4, 0, 130, 58]) {
      await seekTo(t);
      expectRevealedAt(t);
    }
  });

  it("criterion 4: at 1×, 2×, 4×, 8× and 16× nothing is shown early or late", async () => {
    mockApi();
    const user = userEvent.setup();
    await renderControlRoom();
    for (const rate of [1, 2, 4, 8, 16]) {
      await seekTo(0);
      await user.click(screen.getByRole("button", { name: tr("en", "player.speedOption").replace("{{rate}}", String(rate)) }));
      await waitFor(() => expect(video().playbackRate).toBe(rate));
      expectRevealedAt(0);
      // A browser's timeupdate comes every ~250 ms of wall time: 0.25 * rate seconds of video.
      const step = 0.25 * rate;
      for (let t = 0; t <= 300; t += step * 7.3) {
        await playTo(Math.min(t, 299.5));
        expectRevealedAt(Math.min(t, 299.5));
      }
      // Exact boundaries at this rate: just before and at t_start.
      for (const m of [moments[0]!, moments[2]!]) {
        await seekTo(m.t_start - 1);
        await playTo(m.t_start - 0.001);
        expectRevealedAt(m.t_start - 0.001);
        await playTo(m.t_start);
        expectRevealedAt(m.t_start);
      }
    }
  }, 60_000);

  it("criterion 4: a speed change alone reveals nothing", async () => {
    mockApi();
    const user = userEvent.setup();
    await renderControlRoom();
    await playTo(57);
    expectRevealedAt(57);
    await user.click(screen.getByRole("button", { name: tr("en", "player.speedOption").replace("{{rate}}", "16") }));
    await waitFor(() => expect(video().playbackRate).toBe(16));
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });
    expectRevealedAt(57);
  });

  it("criterion 4: items follow the video's currentTime, not wall time", async () => {
    mockApi();
    await renderControlRoom();
    await playTo(10); // playing, position 10 s
    expectRevealedAt(10);
    // Wall time passes (with the video "playing") but currentTime stays at 10 s: nothing new.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 400));
    });
    expectRevealedAt(10);
    // currentTime moves on: the items up to it appear.
    await playTo(130);
    expectRevealedAt(130);
  });
});

// --- Criterion 5: step bar --------------------------------------------------------------------

describe("J2 step bar", () => {
  it("criterion 5: shows the current step (t_start <= t < t_end) with its Reference name and trust badge", async () => {
    mockApi();
    await renderControlRoom();
    for (const t of [0, 24.9, 25, 49.99, 50, 60, 112, 199, 286]) {
      await playTo(t);
      const step = currentStep(aiSteps, t)!;
      await waitFor(() => expect(currentStepLine().textContent).toContain(stepName(step.step_id).en));
      expect(hasTrustBadge(currentStepLine(), step.provenance.trust_label, "en")).toBe(true);
    }
  });

  it("criterion 5: the step name follows the language toggle", async () => {
    mockApi();
    const user = userEvent.setup();
    await renderControlRoom();
    await playTo(60);
    const step = currentStep(aiSteps, 60)!;
    await waitFor(() => expect(currentStepLine().textContent).toContain(stepName(step.step_id).en));
    await user.click(toggleButton("JA"));
    expect(currentStepLine("ja").textContent).toContain(stepName(step.step_id).ja);
    expect(hasTrustBadge(currentStepLine("ja"), "ai_detected", "ja")).toBe(true);
  });

  it("criterion 5: the track follows case.default_step_track; a toggle switches to the other track", async () => {
    mockApi();
    const user = userEvent.setup();
    await renderControlRoom();
    expect(fixture.case.default_step_track).toBe("ai");
    // t = 49: the ai track is in rarp.p04.s01, the dataset track already in rarp.p04.s02.
    await playTo(49);
    const ai = currentStep(aiSteps, 49)!;
    const ds = currentStep(datasetSteps, 49)!;
    expect(ai.step_id).not.toBe(ds.step_id);
    await waitFor(() => expect(currentStepLine().textContent).toContain(stepName(ai.step_id).en));
    expect(reachedSegments()).toHaveLength(upTo(aiSteps, 49).length);

    const toggle = within(stepBar()).getByRole("group", { name: tr("en", "stepBar.track") });
    const buttons = within(toggle).getAllByRole("button");
    expect(buttons).toHaveLength(2);
    const datasetButton = buttons.find((b) => b.getAttribute("aria-pressed") === "false")!;
    await user.click(datasetButton);
    await waitFor(() => expect(currentStepLine().textContent).toContain(stepName(ds.step_id).en));
    expect(hasTrustBadge(currentStepLine(), "dataset_annotation", "en")).toBe(true);
    expect(reachedSegments()).toHaveLength(upTo(datasetSteps, 49).length);
  });

  it("criterion 5: a case whose default_step_track is dataset starts on the dataset track", async () => {
    const detail = fixtureDetail();
    detail.case = { ...detail.case, default_step_track: "dataset" };
    mockApi({ extra: { [`/api/cases/${CASE_ID}`]: () => json(detail) } });
    await renderControlRoom();
    await playTo(49);
    const ds = currentStep(datasetSteps, 49)!;
    await waitFor(() => expect(currentStepLine().textContent).toContain(stepName(ds.step_id).en));
    expect(hasTrustBadge(currentStepLine(), "dataset_annotation", "en")).toBe(true);
  });

  it("criterion 5: no track toggle when only one track exists", async () => {
    const detail = fixtureDetail();
    detail.timeline = { ...detail.timeline, steps: aiSteps };
    mockApi({ extra: { [`/api/cases/${CASE_ID}`]: () => json(detail) } });
    await renderControlRoom();
    await playTo(60);
    expect(within(stepBar()).queryByRole("group", { name: tr("en", "stepBar.track") })).toBeNull();
  });

  it("criterion 5: unreached segments reveal no step names (EN and JA, text and labels)", async () => {
    mockApi();
    const user = userEvent.setup();
    await renderControlRoom();
    await playTo(30);
    const reached = new Set(upTo(aiSteps, 30).map((s) => s.step_id));
    const unreached = [...new Set(aiSteps.map((s) => s.step_id))].filter((id) => !reached.has(id));
    expect(unreached.length).toBeGreaterThan(5);
    for (const lang of ["en", "ja"] as const) {
      if (lang === "ja") await user.click(toggleButton("JA"));
      const strings = visibleStrings(stepBar(lang)).join("\n");
      for (const id of unreached) expect(strings, `${id} leaked (${lang})`).not.toContain(stepName(id)[lang]);
    }
  });

  it("criterion 5: clicking the bar seeks the video (a reached segment, and a point on the bar)", async () => {
    mockApi();
    const user = userEvent.setup();
    await renderControlRoom();
    await playTo(100);
    const segments = reachedSegments();
    const second = upTo(aiSteps, 100)[1]!;
    await user.click(segments[1]!);
    await waitFor(() => expect(video().currentTime).toBe(second.t_start));

    const bar = within(stepBar()).getByRole("group", { name: tr("en", "stepBar.barLabel") });
    bar.getBoundingClientRect = () =>
      ({ left: 0, top: 0, right: 1000, bottom: 20, width: 1000, height: 20, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
    fireEvent.click(bar, { clientX: 500, clientY: 10 });
    await waitFor(() => expect(video().currentTime).toBeCloseTo(150, 1));
  });
});

// --- Criterion 6: ticker and alerts -------------------------------------------------------------

describe("J2 transcript ticker", () => {
  it("criterion 6: each revealed utterance shows its text, localised class tag, speaker, original-language marker and trust badge (EN UI)", async () => {
    mockApi();
    await renderControlRoom();
    await playTo(70);
    const shown = upTo(tl.utterances, 70);
    const items = tickerItems();
    expect(items).toHaveLength(shown.length);
    const speakerRe = new RegExp(tr("en", "ticker.speaker").replace("{{n}}", "(\\d+)"));
    const speakerOf = new Map<string, string>();
    shown.forEach((u, i) => {
      const text = items[i]!.textContent ?? "";
      expect(text).toContain(u.text.en);
      expect(text).toContain(tr("en", `utteranceClass.${u.class}`));
      // original ja ≠ UI en → a marker naming the original language
      expect(u.original_lang).toBe("ja");
      expect(text).toContain(tr("en", "caseLanguage.ja"));
      expect(hasTrustBadge(items[i]!, u.provenance.trust_label, "en")).toBe(true);
      const m = speakerRe.exec(text) ?? (text.includes(u.speaker ?? "\u0000") ? [u.speaker, u.speaker] : null);
      expect(m, `speaker of ${u.id}`).not.toBeNull();
      speakerOf.set(u.speaker ?? "", m![1]!);
    });
    // Two different speakers are told apart.
    expect(new Set(speakerOf.values()).size).toBe(new Set(shown.map((u) => u.speaker)).size);
  });

  it("criterion 6: in the JA UI the ticker shows Japanese text and tags, and no original-language marker for Japanese speech", async () => {
    mockApi();
    const user = userEvent.setup();
    await renderControlRoom();
    await playTo(100);
    await user.click(toggleButton("JA"));
    const shown = upTo(tl.utterances, 100);
    const items = tickerItems("ja");
    expect(items).toHaveLength(shown.length);
    shown.forEach((u, i) => {
      const text = items[i]!.textContent ?? "";
      expect(text).toContain(u.text.ja);
      expect(text).not.toContain(u.text.en);
      expect(text).toContain(tr("ja", `utteranceClass.${u.class}`));
      expect(text).not.toContain(tr("ja", "caseLanguage.ja"));
      expect(hasTrustBadge(items[i]!, u.provenance.trust_label, "ja")).toBe(true);
    });
  });
});

describe("J2 alerts", () => {
  it("criterion 6: each revealed moment shows kind, title, why_flagged details, checkpoint name, score and trust badge", async () => {
    mockApi();
    await renderControlRoom();
    await playTo(130);
    const shown = upTo(moments, 130);
    const items = alertItems();
    expect(items).toHaveLength(shown.length);
    for (const m of shown) {
      const li = items.find((x) => x.textContent?.includes(m.title.en))!;
      expect(li, m.id).toBeDefined();
      const text = li.textContent ?? "";
      expect(text).toContain(tr("en", `momentKind.${m.kind}`));
      for (const why of m.why_flagged) expect(text).toContain(why.detail.en);
      expect(text).toContain(m.score.toFixed(2));
      expect(hasTrustBadge(li, m.provenance.trust_label, "en")).toBe(true);
      if (m.checkpoint_id) {
        const cp = fixture.reference.phases
          .flatMap((p) => p.steps)
          .flatMap((s) => s.checkpoints)
          .find((c) => c.id === m.checkpoint_id)!;
        expect(text, `checkpoint of ${m.id}`).toContain(cp.text.en);
      }
    }
  });

  it("criterion 6: alerts follow the language toggle (kind, title, details, checkpoint)", async () => {
    mockApi();
    const user = userEvent.setup();
    await renderControlRoom();
    await playTo(130);
    await user.click(toggleButton("JA"));
    const items = alertItems("ja");
    const m03 = moments.find((m) => m.kind === "checkpoint" && m.t_start <= 130)!;
    const li = items.find((x) => x.textContent?.includes(m03.title.ja))!;
    expect(li).toBeDefined();
    expect(li.textContent).toContain(tr("ja", "momentKind.checkpoint"));
    for (const why of m03.why_flagged) expect(li.textContent).toContain(why.detail.ja);
    const cp = fixture.reference.phases.flatMap((p) => p.steps).flatMap((s) => s.checkpoints).find((c) => c.id === m03.checkpoint_id)!;
    expect(li.textContent).toContain(cp.text.ja);
    expect(hasTrustBadge(li, "ai_detected", "ja")).toBe(true);
  });

  it("criterion 6: selecting an alert seeks the video to its t_start", async () => {
    mockApi();
    const user = userEvent.setup();
    await renderControlRoom();
    await playTo(130);
    // Newest first: seeking to an earlier moment hides the later ones again (criterion 4).
    for (const m of upTo(moments, 130).reverse()) {
      const li = alertItems().find((x) => x.textContent?.includes(m.title.en))!;
      await user.click(within(li).getAllByRole("button")[0]!);
      await waitFor(() => expect(video().currentTime).toBe(m.t_start));
    }
  });
});

// --- Criterion 9: i18n and disclaimer ------------------------------------------------------------

describe("J2 / J8 i18n and disclaimer", () => {
  it("criterion 9: ja and en have identical key sets, every value non-empty, same placeholders", () => {
    expect(Object.keys(flat.ja).sort()).toEqual(Object.keys(flat.en).sort());
    const ph = (v: string) => [...v.matchAll(/\{\{\s*([\w.]+)\s*\}\}/g)].map((m) => m[1]).sort();
    for (const key of Object.keys(flat.en)) {
      const e = String(flat.en[key]);
      const j = String(flat.ja[key]);
      expect(e.trim(), key).not.toBe("");
      expect(j.trim(), key).not.toBe("");
      expect(ph(j), key).toEqual(ph(e));
    }
  });

  it("criterion 9: the disclaimer stays visible on the Control Room in both languages", async () => {
    mockApi();
    const user = userEvent.setup();
    await renderControlRoom();
    expect(screen.getByText(tr("en", "disclaimer.text"))).toBeVisible();
    await playTo(299);
    expect(screen.getByText(tr("en", "disclaimer.text"))).toBeVisible();
    await user.click(toggleButton("JA"));
    expect(screen.getByText(tr("ja", "disclaimer.text"))).toBeVisible();
  });

  const CJK = /[぀-ヿ㐀-鿿＀-￯]/;
  const jaLatin = new Set<string>();
  const addLatin = (text: string) => {
    for (const w of text.match(/[A-Za-z]{3,}/g) ?? []) jaLatin.add(w.toLowerCase());
  };
  Object.values(flat.ja).forEach((v) => addLatin(String(v)));
  [...bilingualTexts(fixtureDetail(), "ja"), ...bilingualTexts(fixture.reference, "ja")].forEach(addLatin);
  [CASE_ID].forEach(addLatin);
  // Data shown verbatim: speaker ids, signal names, ids from the contracts.
  const enCjk = new Set<string>();
  Object.values(flat.en).forEach((v) => {
    for (const c of String(v)) if (CJK.test(c)) enCjk.add(c);
  });

  async function controlRoomStrings(lang: Lang): Promise<string[]> {
    mockApi();
    await renderControlRoom();
    await act(() => i18n.changeLanguage(lang));
    const out: string[] = [];
    for (const t of [0, 70, 130, 230, 299]) {
      await playTo(t);
      await waitFor(() => expect(currentStepLine(lang).textContent).toContain(stepName(currentStep(aiSteps, t)!.step_id)[lang]));
      out.push(...visibleStrings(document.body));
    }
    return out;
  }

  it("criterion 9: in Japanese, no English UI text appears on the Control Room", async () => {
    const strings = await controlRoomStrings("ja");
    const offenders = strings.filter((s) => (s.match(/[A-Za-z]{3,}/g) ?? []).some((w) => !jaLatin.has(w.toLowerCase())));
    expect([...new Set(offenders)]).toEqual([]);
  });

  it("criterion 9: in English, no Japanese UI text appears on the Control Room", async () => {
    const strings = await controlRoomStrings("en");
    const offenders = strings.filter((s) => [...s].some((c) => CJK.test(c) && !enCjk.has(c)));
    expect([...new Set(offenders)]).toEqual([]);
  });
});
