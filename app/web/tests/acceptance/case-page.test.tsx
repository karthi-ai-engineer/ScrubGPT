/**
 * Case page acceptance (brief criterion 9): the case, the video player and the flagged moments.
 *
 * Sources: plan §6 Dev2 Block 1 (web skeleton, video player; milestone "Fixture case browsable in
 * JA and EN"), plan §4.2 (moments: `t_start`, `t_end`, `kind`, `step_id`, `provenance`), §4.2b
 * (step names come from the Procedure Reference), app/web/CLAUDE.md rules 3, 4 and 5 (the video is
 * the master clock; every piece of knowledge shows its trust label), app/web/README.md
 * (`/cases/:caseId`: video player with 1×–16× speeds, flagged moments that seek the video), the
 * brief (unknown case → localised "not found" with a way home).
 */
import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import i18n from "@/i18n";
import en from "@/i18n/en.json";
import ja from "@/i18n/ja.json";

import {
  fixture,
  flatten,
  installFakeMedia,
  mockServer,
  renderApp,
  SPEC_EMOJI,
  standardRoutes,
  stepName,
} from "./harness";

const flat = { en: flatten(en), ja: flatten(ja) } as const;
const tr = (lang: "en" | "ja", key: string) => String(flat[lang][key]);
const moments = fixture.moments.moments;

/** `m:ss` (or `0m:ss`) for a time in seconds; the spec fixes no format, so both are accepted. */
function timeRe(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = String(Math.floor(seconds % 60)).padStart(2, "0");
  return `0?${m}:${s}`;
}

let restoreMedia: () => void;
beforeEach(() => {
  restoreMedia = installFakeMedia(fixture.case.duration_s);
});
afterEach(() => restoreMedia());

/** The list item of a moment, found by its title. */
function momentItem(title: string): HTMLElement {
  const item = screen.getByText(title).closest("li");
  if (!item) throw new Error(`moment "${title}" is not in a list item`);
  return item;
}

describe("Case page", () => {
  it("shows the case title, facts, data note and trust badges", async () => {
    mockServer(standardRoutes());
    renderApp("/cases/case-fixture-01");
    expect(await screen.findByRole("heading", { level: 1, name: fixture.case.title.en })).toBeInTheDocument();
    expect(screen.getAllByText(tr("en", `source.${fixture.case.source}`)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(tr("en", `caseStatus.${fixture.case.status}`)).length).toBeGreaterThan(0);
    expect(screen.getByText(fixture.case.data_note.en)).toBeInTheDocument();
  });

  it("shows the video player with the case video and poster", async () => {
    mockServer(standardRoutes());
    const view = renderApp("/cases/case-fixture-01");
    await screen.findByRole("heading", { level: 1, name: fixture.case.title.en });
    const video = view.container.querySelector("video");
    expect(video).not.toBeNull();
    expect(video?.getAttribute("src")).toBe("/media/cases/case-fixture-01/video.mp4");
    expect(video?.getAttribute("poster")).toBe("/media/cases/case-fixture-01/poster.jpg");
  });

  it("lists every moment with time range, kind, trust badge and the Reference step name", async () => {
    mockServer(standardRoutes());
    renderApp("/cases/case-fixture-01");
    await screen.findByRole("heading", { level: 1, name: fixture.case.title.en });
    // The step names arrive with the reference.
    await screen.findAllByText(new RegExp(escape(stepName(moments[0]!.step_id).en)));
    for (const moment of moments) {
      const item = momentItem(moment.title.en);
      const text = item.textContent ?? "";
      expect(text, moment.id).toMatch(new RegExp(`${timeRe(moment.t_start)}\\s*[–—-]\\s*${timeRe(moment.t_end)}`));
      expect(text, moment.id).toContain(tr("en", `momentKind.${moment.kind}`));
      expect(text, moment.id).toContain(tr("en", `trust.${moment.provenance.trust_label}`));
      expect(text, moment.id).toContain(SPEC_EMOJI[moment.provenance.trust_label]);
      expect(text, moment.id).toContain(stepName(moment.step_id).en);
      expect(text, moment.id).not.toContain(moment.step_id); // a name, not the raw id
    }
  });

  it("the moments list follows the language (titles, kinds, step names)", async () => {
    mockServer(standardRoutes());
    renderApp("/cases/case-fixture-01");
    await screen.findAllByText(new RegExp(escape(stepName(moments[0]!.step_id).en)));
    await act(() => i18n.changeLanguage("ja"));
    for (const moment of moments) {
      const text = momentItem(moment.title.ja).textContent ?? "";
      expect(text).toContain(tr("ja", `momentKind.${moment.kind}`));
      expect(text).toContain(tr("ja", `trust.${moment.provenance.trust_label}`));
      expect(text).toContain(stepName(moment.step_id).ja);
    }
  });

  it("selecting a moment seeks the video to its t_start (the video is the master clock)", async () => {
    mockServer(standardRoutes());
    const user = userEvent.setup();
    const view = renderApp("/cases/case-fixture-01");
    await screen.findByRole("heading", { level: 1, name: fixture.case.title.en });
    const video = view.container.querySelector("video") as HTMLVideoElement;
    for (const moment of [moments[3]!, moments[0]!, moments[5]!]) {
      const item = momentItem(moment.title.en);
      const control = within(item).queryByRole("button") ?? within(item).getByRole("link");
      await user.click(control);
      expect(video.currentTime, moment.id).toBe(moment.t_start);
    }
  });

  it("selecting a moment keeps the chosen playback speed", async () => {
    mockServer(standardRoutes());
    const user = userEvent.setup();
    const view = renderApp("/cases/case-fixture-01");
    await screen.findByRole("heading", { level: 1, name: fixture.case.title.en });
    const video = view.container.querySelector("video") as HTMLVideoElement;
    const eight = screen.getAllByRole("button").find((b) => /^8\s*[×x]$/.test(b.textContent?.trim() ?? ""));
    if (!eight) throw new Error("no 8× button");
    await user.click(eight);
    await user.click(within(momentItem(moments[2]!.title.en)).getByRole("button"));
    expect(video.currentTime).toBe(moments[2]!.t_start);
    expect(video.playbackRate).toBe(8);
  });

  it("an unknown case shows a localised 'not found' with a way home (EN and JA)", async () => {
    mockServer(standardRoutes());
    const user = userEvent.setup();
    renderApp("/cases/no-such-case");
    expect(await screen.findByText(tr("en", "errors.caseNotFound.title"))).toBeInTheDocument();
    await act(() => i18n.changeLanguage("ja"));
    expect(screen.getByText(tr("ja", "errors.caseNotFound.title"))).toBeInTheDocument();
    const home = screen.getByRole("link", { name: tr("ja", "status.backHome") });
    expect(home).toHaveAttribute("href", "/");
    await user.click(home);
    expect(await screen.findByRole("heading", { level: 1, name: tr("ja", "home.title") })).toBeInTheDocument();
  });

  it("an unknown page shows a localised 'page not found' with a way home", async () => {
    mockServer(standardRoutes());
    renderApp("/no/such/page");
    expect(await screen.findByText(tr("en", "errors.pageNotFound.title"))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: tr("en", "status.backHome") })).toHaveAttribute("href", "/");
  });
});

function escape(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
