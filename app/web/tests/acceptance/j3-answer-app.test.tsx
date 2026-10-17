/**
 * J3 Surgeon Answer app acceptance (brief criteria 5, 6, 7, 8, 9, 11; web side).
 *
 * Sources: plan §2.10 J3 ("Mobile layout. Question cards with the clip on loop; tap, voice and
 * text side by side; read-back; confirm/edit chips; skip or later; '2 of 4 · ~2 min'"), §8.3 (the
 * answer flow; "The phone is shown as a phone-sized frame on the laptop screen"), §4.1 ("The app
 * shows 'Brain unavailable' for 503 and 504"), §4.3 (trust label follows the answerer);
 * contracts/brain_api.md (`/extract`: "a chip on a null field is invalid"; `missing_fields` "is the
 * missing-field prompt: the app shows each entry as a fill-in input"); D-054 / D-056 (no chip for a
 * null field; Confirm disabled while cue or action is null and unfilled; the surgeon's text becomes
 * a `source: edit` grounding); D-066 (operating ⇒ .qN, reviewer ⇒ .rN); D-071 (guardrail list);
 * D-072 (c) (the app must not rely on the order of `missing_fields`); app/web/CLAUDE.md rules 1, 3,
 * 5, 6, 7, 10; app/web/README.md "Answer app (J3)".
 */
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import type { DecisionRecordDraft } from "@contracts/contracts";

import i18n from "@/i18n";
import { installFakeMic, removeFakeMic } from "@/test/fakes";

import {
  ANSWER_ID,
  answerByText,
  apiError,
  cardQuestionId,
  CASE_ID,
  confirmButton,
  confirmedRecord,
  draftResponse,
  escape,
  flat,
  json,
  mockAnswerServer,
  modeButton,
  modeButtons,
  openAnswerApp,
  QUESTIONS,
  queueFor,
  readback,
  startAs,
  tr,
  type Call,
  type Lang,
} from "./answer-harness";
import { renderApp, SPEC_EMOJI, visibleStrings } from "./harness";

const op = QUESTIONS.operating;
const DRAFT = "/api/answers/draft";
const CONFIRM = "/api/answers/confirm";
const AUDIO = "/api/answers/audio";
const RECORD_ID = "01a1500a-0000-7000-8000-0000000000aa";

function hasBadge(el: HTMLElement, label: keyof typeof SPEC_EMOJI, lang: Lang = "en") {
  const text = el.textContent ?? "";
  return text.includes(SPEC_EMOJI[label]) && text.includes(tr(lang, `trust.${label}`));
}

/** Routes for a draft that answers whatever question was asked, and a Confirm that stores it. */
function answerRoutes(options: Parameters<typeof draftResponse>[0] extends infer O ? Partial<O> : never = {}) {
  return {
    [DRAFT]: (call: Call) => {
      const body = call.body as { question_id: string; answerer_role: string };
      return json(
        draftResponse({
          questionId: body.question_id,
          role: body.answerer_role as never,
          ...options,
        }),
      );
    },
    [CONFIRM]: (call: Call) => {
      const body = call.body as { draft: DecisionRecordDraft; confirmed_by: string };
      return json({ record: confirmedRecord(body.draft, RECORD_ID, body.confirmed_by) }, 201);
    },
  };
}

function setLang(lang: Lang) {
  return act(async () => {
    await i18n.changeLanguage(lang);
  });
}

afterEach(() => removeFakeMic());

// --- criterion 8 -----------------------------------------------------------------------------------

describe("criterion 8: tap, voice and text side by side in a phone frame; progress; skip and later; questions only from questions.json", () => {
  it("criterion 8: the answer app is shown in a phone-sized frame on the laptop (plan §8.3, rule 7)", async () => {
    mockAnswerServer();
    await openAnswerApp();
    const frame = screen.getByRole("region", { name: tr("en", "answer.frameLabel") });
    expect(frame).toBeInTheDocument();
    expect(frame).toContainElement(screen.getByRole("heading", { name: tr("en", "answer.setup.title") }));
  });

  it("criterion 8: Tap, Voice and Text are offered side by side with equal weight on every card", async () => {
    mockAnswerServer();
    await openAnswerApp();
    await startAs("dev_team_simulated");
    const frame = screen.getByRole("region", { name: tr("en", "answer.frameLabel") });
    for (let i = 0; i < 3; i++) {
      const buttons = modeButtons();
      expect(buttons.map((b) => b.textContent?.replace(/[^\p{L} ]/gu, "").trim())).toEqual([
        tr("en", "answer.mode.tap"),
        tr("en", "answer.mode.voice"),
        tr("en", "answer.mode.text"),
      ]);
      // Same element, same parent, same styling, all enabled: none is preferred over another.
      expect(new Set(buttons.map((b) => b.parentElement)).size).toBe(1);
      expect(new Set(buttons.map((b) => b.tagName)).size).toBe(1);
      expect(new Set(buttons.map((b) => b.className)).size).toBe(1);
      for (const b of buttons) {
        expect(b).toBeEnabled();
        expect(b).toHaveAttribute("aria-pressed", "false");
        expect(frame).toContainElement(b);
      }
      await userEvent.setup().click(screen.getByRole("button", { name: tr("en", "answer.skip") }));
    }
  });

  it("criterion 8: progress 'N of M · ~K min' comes from the queue (M questions, K = their est_seconds in minutes, rounded up)", async () => {
    mockAnswerServer();
    await openAnswerApp();
    await startAs("operating_surgeon");
    const total = op.length;
    const minutes = Math.ceil(op.reduce((s, q) => s + q.est_seconds, 0) / 60);
    expect(screen.getByText(tr("en", "answer.progress", { n: 1, total, minutes }))).toBeInTheDocument();
    await setLang("ja");
    expect(screen.getByText(tr("ja", "answer.progress", { n: 1, total, minutes }))).toBeInTheDocument();
  });

  it("criterion 8: Skip moves on to the next question (N + 1 of M)", async () => {
    mockAnswerServer();
    await openAnswerApp();
    const user = await startAs("operating_surgeon");
    expect(cardQuestionId()).toBe(op[0]!.id);
    expect(screen.getByRole("heading", { name: op[0]!.text.en })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: tr("en", "answer.skip") }));
    expect(cardQuestionId()).toBe(op[1]!.id);
    expect(screen.getByText(new RegExp(`^2 of ${op.length} · ~\\d+ min$`))).toBeInTheDocument();
  });

  it("criterion 8: Later moves the card to the end of the queue (it comes back last)", async () => {
    mockAnswerServer();
    await openAnswerApp();
    const user = await startAs("operating_surgeon");
    await user.click(screen.getByRole("button", { name: tr("en", "answer.later") }));
    expect(cardQuestionId()).toBe(op[1]!.id);
    expect(screen.getByText(new RegExp(`^1 of ${op.length} · `))).toBeInTheDocument();
    const seen: string[] = [cardQuestionId()!];
    for (let i = 1; i < op.length; i++) {
      await user.click(screen.getByRole("button", { name: tr("en", "answer.skip") }));
      if (cardQuestionId()) seen.push(cardQuestionId()!);
    }
    expect(seen).toEqual([...op.slice(1).map((q) => q.id), op[0]!.id]);
  });

  it("criterion 8: the cards are exactly the questions the server's queue gave (from questions.json); the app invents none", async () => {
    const only = [op[2]!.id, op[4]!.id];
    mockAnswerServer({
      [`/api/cases/${CASE_ID}/answer-queue`]: () => json(queueFor("operating", only)),
    });
    await openAnswerApp();
    const user = await startAs("operating_surgeon");
    const seen: string[] = [];
    while (cardQuestionId()) {
      seen.push(cardQuestionId()!);
      await user.click(screen.getByRole("button", { name: tr("en", "answer.skip") }));
    }
    expect(seen).toEqual(only);
    expect(screen.getByText(tr("en", "answer.done.title"))).toBeInTheDocument();
    // No other fixture question text appeared.
    const body = document.body.textContent ?? "";
    for (const q of [...QUESTIONS.operating, ...QUESTIONS.reviewer]) {
      if (!only.includes(q.id)) expect(body).not.toContain(q.text.en);
    }
  });

  it("criterion 8: each card loops the moment's clip (muted, inline)", async () => {
    mockAnswerServer();
    await openAnswerApp();
    await startAs("operating_surgeon");
    const video = document.querySelector<HTMLVideoElement>("[data-question-id] video");
    expect(video).not.toBeNull();
    expect(video!.getAttribute("src")).toContain(`${op[0]!.moment_id}.mp4`);
    expect(video!.loop).toBe(true);
    expect(video!.muted).toBe(true);
  });
});

// --- criterion 5 (web) ---------------------------------------------------------------------------

describe("criterion 5 (web): answers reach the server in the documented shapes; the role decides the question list", () => {
  it("criterion 5: a typed answer is sent as mode text with the UI language, no audio, and the chosen role", async () => {
    const server = mockAnswerServer(answerRoutes());
    await openAnswerApp();
    const user = await startAs("operating_surgeon");
    await answerByText(user, "The view turned red");
    await screen.findByTestId("readback");
    const [call] = server.posts(DRAFT);
    expect(call!.body).toMatchObject({
      case_id: CASE_ID,
      question_id: op[0]!.id,
      answerer_role: "operating_surgeon",
      answer: { mode: "text", tap: null, text: "The view turned red", lang: "en", audio_uri: null },
    });
  });

  it("criterion 5: a tap answer sends the verdict and the tapped options in tap order (text null unless edit)", async () => {
    const server = mockAnswerServer(answerRoutes());
    await openAnswerApp();
    const user = await startAs("operating_surgeon");
    const q = op[0]!;
    expect(q.tap_options.length).toBeGreaterThan(1);
    await user.click(modeButton("tap"));
    const verdicts = screen.getByRole("group", { name: tr("en", "answer.tap.verdicts") });
    await user.click(within(verdicts).getByRole("button", { name: new RegExp(tr("en", "answer.tap.confirm")) }));
    await user.click(screen.getByRole("button", { name: q.tap_options[1]!.label.en }));
    await user.click(screen.getByRole("button", { name: q.tap_options[0]!.label.en }));
    await user.click(within(screen.getByTestId("tap-panel")).getByRole("button", { name: tr("en", "answer.tap.send") }));
    await screen.findByTestId("readback");
    const [call] = server.posts(DRAFT);
    expect((call!.body as { answer: unknown }).answer).toMatchObject({
      mode: "tap",
      tap: { verdict: "confirm", choice_ids: [q.tap_options[1]!.id, q.tap_options[0]!.id] },
      text: null,
      lang: "en",
      audio_uri: null,
    });
  });

  it("criterion 5: a voice answer is uploaded, then drafted with the server's answer_id, audio_uri and transcript", async () => {
    installFakeMic();
    const AUDIO_ID = "01a1500a-0000-7000-8000-0000000000b1";
    const server = mockAnswerServer({
      ...answerRoutes({ answerId: AUDIO_ID }),
      [AUDIO]: () => json({ answer_id: AUDIO_ID, audio_uri: `answers/${AUDIO_ID}.webm`, text: "出血が見えたので吸引した", lang: "ja" }),
    });
    await openAnswerApp();
    const user = await startAs("operating_surgeon");
    await user.click(modeButton("voice"));
    await user.click(screen.getByRole("button", { name: new RegExp(tr("en", "answer.voice.start")) }));
    await user.click(await screen.findByRole("button", { name: new RegExp(tr("en", "answer.voice.stop")) }));
    await screen.findByTestId("readback");
    const [upload] = server.posts(AUDIO);
    expect(upload!.body).toBeInstanceOf(FormData);
    const form = upload!.body as FormData;
    expect(form.get("audio")).toBeInstanceOf(Blob);
    expect(form.get("lang_hint")).toBe("en");
    const [draft] = server.posts(DRAFT);
    expect((draft!.body as { answer: unknown }).answer).toEqual({
      answer_id: AUDIO_ID,
      mode: "voice",
      tap: null,
      text: "出血が見えたので吸引した",
      lang: "ja",
      audio_uri: `answers/${AUDIO_ID}.webm`,
    });
  });

  it.each([
    ["operating_surgeon", "operating", ".q"],
    ["reviewer", "reviewer", ".r"],
  ] as const)("criterion 5 (D-066): a %s only gets the %s list, whatever the URL asks for", async (role, list, style) => {
    const server = mockAnswerServer();
    await openAnswerApp(`?role=${list === "operating" ? "reviewer" : "operating"}`);
    await startAs(role);
    const queueCalls = server.calls.filter((c) => c.path.endsWith("/answer-queue"));
    expect(queueCalls.at(-1)!.query.get("role")).toBe(list);
    expect(cardQuestionId()).toContain(style);
  });

  it("criterion 5 (D-066): a question of the other style is never asked of an operating surgeon, even if the server lists it", async () => {
    const mixed = queueFor("operating", [op[0]!.id]);
    const reviewerQ = queueFor("reviewer", [QUESTIONS.reviewer[0]!.id]).questions;
    mockAnswerServer({
      [`/api/cases/${CASE_ID}/answer-queue`]: () => json({ ...mixed, questions: [...reviewerQ, ...mixed.questions] }),
    });
    await openAnswerApp();
    const user = await startAs("operating_surgeon");
    const seen: string[] = [];
    while (cardQuestionId()) {
      seen.push(cardQuestionId()!);
      await user.click(screen.getByRole("button", { name: tr("en", "answer.skip") }));
    }
    expect(seen).toEqual([op[0]!.id]);
  });
});

// --- criterion 6 ---------------------------------------------------------------------------------

describe("criterion 6: no chip for a null field; missing fields as empty fill-in inputs; Confirm gated on cue and action", () => {
  async function toReadback(options: Partial<Parameters<typeof draftResponse>[0]> = {}) {
    const server = mockAnswerServer(answerRoutes(options));
    await openAnswerApp();
    const user = await startAs("dev_team_simulated");
    await answerByText(user, "The view turned red");
    await screen.findByTestId("readback");
    return { server, user };
  }

  function chipFields() {
    const list = within(readback()).queryByTestId("chips");
    return list ? Array.from(list.querySelectorAll("[data-field]")).map((li) => li.getAttribute("data-field")) : [];
  }

  it("criterion 6: chips are exactly the response's chips; a null field (action, reason …) has no chip", async () => {
    await toReadback({ cue: { ja: "視野が赤い", en: "The view is red" }, action: null });
    expect(chipFields()).toEqual(["situation_cue.text"]);
    expect(within(readback()).getByText("The view is red")).toBeInTheDocument();
  });

  it.each([
    ["chip order", undefined],
    ["reversed order", (m: string[]) => [...m].reverse()],
  ] as const)("criterion 6: every fillable missing_fields entry is an empty fill-in input, never pre-filled (%s; D-072 (c))", async (_n, order) => {
    await toReadback({ cue: null, action: null, missingOrder: order });
    const missing = within(readback()).getByTestId("missing-fields");
    const fillable = ["context.preop_plan", "situation_cue.text", "anticipation", "action.text", "reason", "immediate_result"];
    for (const path of fillable) {
      const li = missing.querySelector(`[data-field="${path}"]`);
      expect(li, path).not.toBeNull();
      const input = li!.querySelector("input, textarea") as HTMLInputElement | null;
      expect(input, `${path} is a fill-in input`).not.toBeNull();
      expect(input!.value, `${path} is not pre-filled`).toBe("");
    }
    // Nothing from the question, the AI draft or the moment title is put in for the surgeon.
    const values = Array.from(readback().querySelectorAll<HTMLInputElement>("input, textarea")).map((i) => i.value);
    expect(values.every((v) => v === "")).toBe(true);
    expect(chipFields()).toEqual([]);
  });

  it("criterion 6: Confirm stays disabled while action.text is null and unfilled; filling it enables Confirm; clearing it disables it again", async () => {
    const { user } = await toReadback({ action: null });
    expect(confirmButton()).toBeDisabled();
    const input = within(readback()).getByLabelText(tr("en", "answer.readback.fillLabel", { field: tr("en", "answer.field.action") }));
    await user.type(input, "Suctioned, then clipped");
    expect(confirmButton()).toBeEnabled();
    await user.clear(input);
    expect(confirmButton()).toBeDisabled();
    await user.type(input, "   ");
    expect(confirmButton()).toBeDisabled();
  });

  it("criterion 6: with both cue and action unstated, Confirm needs both", async () => {
    const { user } = await toReadback({ cue: null, action: null });
    const cue = within(readback()).getByLabelText(tr("en", "answer.readback.fillLabel", { field: tr("en", "answer.field.situation_cue") }));
    const action = within(readback()).getByLabelText(tr("en", "answer.readback.fillLabel", { field: tr("en", "answer.field.action") }));
    expect(confirmButton()).toBeDisabled();
    await user.type(cue, "Blood pooling");
    expect(confirmButton()).toBeDisabled();
    await user.type(action, "Suctioned");
    expect(confirmButton()).toBeEnabled();
  });

  it("criterion 6: Confirm is enabled straight away when cue and action are both stated", async () => {
    await toReadback({ action: { ja: "吸引した", en: "Suctioned" } });
    expect(confirmButton()).toBeEnabled();
  });

  it("criterion 6: nothing is filled for the surgeon: Confirm sends the draft unchanged and only the surgeon's words as edits", async () => {
    const { server, user } = await toReadback({ action: null });
    const drafted = draftResponse({ questionId: op[0]!.id, role: "dev_team_simulated", action: null });
    const input = within(readback()).getByLabelText(tr("en", "answer.readback.fillLabel", { field: tr("en", "answer.field.action") }));
    await user.type(input, "Suctioned, then clipped");
    await user.click(confirmButton());
    await waitFor(() => expect(server.posts(CONFIRM)).toHaveLength(1));
    const body = server.posts(CONFIRM)[0]!.body as { answer_id: string; draft: unknown; edits: unknown[]; confirmed_by: string };
    expect(body.answer_id).toBe(ANSWER_ID);
    expect(body.draft).toEqual(drafted.extract.draft);
    expect(body.edits).toEqual([{ field: "action.text", text: "Suctioned, then clipped", lang: "en" }]);
    expect(body.confirmed_by).toBe("Dr Test");
  });
});

// --- criterion 7 (web) ---------------------------------------------------------------------------

describe("criterion 7 (web): edited chips go to the server as edits; trust label follows the role", () => {
  it.each(["en", "ja"] as const)("criterion 7: an edited chip is sent as an edit in the language it was typed in (%s)", async (lang) => {
    const server = mockAnswerServer(answerRoutes({ action: { ja: "吸引した", en: "Suctioned" } }));
    await setLang(lang);
    await openAnswerAppIn(lang);
    const user = await startAs("dev_team_simulated", "Dr Test", lang);
    await answerByText(user, "赤い", lang);
    await screen.findByTestId("readback");
    const cueName = tr(lang, "answer.field.situation_cue");
    await user.click(within(readback()).getByRole("button", { name: tr(lang, "answer.readback.editLabel", { field: cueName }) }));
    const box = within(readback()).getByRole("textbox", { name: tr(lang, "answer.readback.editLabel", { field: cueName }) });
    await user.clear(box);
    await user.type(box, lang === "ja" ? "出血がたまっていた" : "Blood was pooling");
    await user.click(within(readback()).getByRole("button", { name: tr(lang, "answer.readback.save") }));
    await user.click(confirmButton(lang));
    await waitFor(() => expect(server.posts(CONFIRM)).toHaveLength(1));
    const body = server.posts(CONFIRM)[0]!.body as { edits: unknown[] };
    expect(body.edits).toEqual([{ field: "situation_cue.text", text: lang === "ja" ? "出血がたまっていた" : "Blood was pooling", lang }]);
  });

  it.each([
    ["operating_surgeon", "operating_surgeon"],
    ["reviewer", "reviewer"],
    ["dev_team_simulated", "simulated"],
  ] as const)("criterion 7: answering as %s shows and saves the %s trust label", async (role, label) => {
    const server = mockAnswerServer(answerRoutes({ action: { ja: "吸引した", en: "Suctioned" } }));
    await openAnswerApp();
    const user = await startAs(role);
    // The chosen role and its trust label are shown on the card.
    expect(hasBadge(screen.getByTestId("answerer"), label)).toBe(true);
    await answerByText(user, "Answer");
    await screen.findByTestId("readback");
    expect((server.posts(DRAFT)[0]!.body as { answerer_role: string }).answerer_role).toBe(role);
    expect(hasBadge(readback(), label)).toBe(true);
    await user.click(confirmButton());
    const saved = await screen.findByTestId("saved");
    expect(hasBadge(saved, label)).toBe(true);
  });
});

// --- criterion 9 ---------------------------------------------------------------------------------

describe("criterion 9: Brain 503/504 → 'Brain unavailable' (JA + EN), tap or text as the fallback, nothing typed is lost", () => {
  it.each([
    ["unavailable", 503, "en"],
    ["timeout", 504, "en"],
    ["unavailable", 503, "ja"],
    ["timeout", 504, "ja"],
  ] as const)("criterion 9: a %s (%i) on the draft shows 'Brain unavailable' (%s) and keeps the typed answer", async (code, status, lang) => {
    mockAnswerServer({ [DRAFT]: () => apiError(code, status) });
    await setLang(lang);
    await openAnswerAppIn(lang);
    const user = await startAs("dev_team_simulated", "Dr Test", lang);
    await answerByText(user, "Typed words stay", lang);
    const banner = await screen.findByTestId("brain-unavailable");
    expect(banner).toHaveTextContent(tr(lang, "answer.brainUnavailable"));
    expect(screen.getByLabelText(tr(lang, "answer.text.label"))).toHaveValue("Typed words stay");
    expect(modeButton("tap", lang)).toBeEnabled();
    expect(modeButton("text", lang)).toBeEnabled();
    // The banner's text names the fallback in both languages.
    expect(tr("en", "answer.brainUnavailable")).toMatch(/Brain/);
    expect(tr("ja", "answer.brainUnavailable")).toMatch(/Brain/);
  });

  it("criterion 9: the other language is shown when the language is toggled while the banner is up (no reload)", async () => {
    mockAnswerServer({ [DRAFT]: () => apiError("unavailable", 503) });
    await openAnswerApp();
    const user = await startAs("dev_team_simulated");
    await answerByText(user, "Typed words stay");
    await screen.findByTestId("brain-unavailable");
    await setLang("ja");
    expect(screen.getByTestId("brain-unavailable")).toHaveTextContent(tr("ja", "answer.brainUnavailable"));
    expect(screen.getByLabelText(tr("ja", "answer.text.label"))).toHaveValue("Typed words stay");
  });

  it("criterion 9: a Brain that is down before answering is announced up front (GET /api/brain/health 503)", async () => {
    mockAnswerServer({ "/api/brain/health": () => apiError("unavailable", 503) });
    await openAnswerApp();
    await startAs("dev_team_simulated");
    expect(await screen.findByTestId("brain-unavailable")).toHaveTextContent(tr("en", "answer.brainUnavailable"));
    expect(modeButton("tap")).toBeEnabled();
    expect(modeButton("text")).toBeEnabled();
  });

  it("criterion 9: a 503 on Confirm (translation) keeps the read-back and the surgeon's fill-ins", async () => {
    mockAnswerServer({ ...answerRoutes({ action: null }), [CONFIRM]: () => apiError("unavailable", 503) });
    await openAnswerApp();
    const user = await startAs("dev_team_simulated");
    await answerByText(user, "Answer");
    await screen.findByTestId("readback");
    const input = within(readback()).getByLabelText(tr("en", "answer.readback.fillLabel", { field: tr("en", "answer.field.action") }));
    await user.type(input, "My own action words");
    await user.click(confirmButton());
    expect(await screen.findByTestId("brain-unavailable")).toHaveTextContent(tr("en", "answer.brainUnavailable"));
    expect(readback()).toBeInTheDocument();
    expect(input).toHaveValue("My own action words");
    expect(confirmButton()).toBeEnabled();
  });

  it("criterion 9: a 504 on the voice upload shows 'Brain unavailable' and offers text instead", async () => {
    installFakeMic();
    mockAnswerServer({ [AUDIO]: () => apiError("timeout", 504) });
    await openAnswerApp();
    const user = await startAs("dev_team_simulated");
    await user.click(modeButton("voice"));
    await user.click(screen.getByRole("button", { name: new RegExp(tr("en", "answer.voice.start")) }));
    await user.click(await screen.findByRole("button", { name: new RegExp(tr("en", "answer.voice.stop")) }));
    expect(await screen.findByTestId("brain-unavailable")).toHaveTextContent(tr("en", "answer.brainUnavailable"));
    expect(screen.getByLabelText(tr("en", "answer.text.label"))).toBeInTheDocument();
    expect(modeButton("tap")).toBeEnabled();
  });
});

// --- criterion 11 --------------------------------------------------------------------------------

async function openAnswerAppIn(lang: Lang) {
  const view = renderApp(`/cases/${CASE_ID}/answer`);
  await screen.findByRole("heading", { name: tr(lang, "answer.setup.title") });
  return view;
}

describe("criterion 11: every J3 string in JA and EN; the disclaimer stays visible", () => {
  it("criterion 11: the answer.* and record.* keys are the same in ja.json and en.json, all non-empty", () => {
    for (const prefix of ["answer.", "record."]) {
      const enKeys = Object.keys(flat.en).filter((k) => k.startsWith(prefix)).sort();
      const jaKeys = Object.keys(flat.ja).filter((k) => k.startsWith(prefix)).sort();
      expect(enKeys.length).toBeGreaterThan(0);
      expect(jaKeys).toEqual(enKeys);
      for (const k of enKeys) {
        expect(String(flat.en[k]).trim(), k).not.toBe("");
        expect(String(flat.ja[k]).trim(), k).not.toBe("");
      }
    }
    // The whole resource files have identical key sets.
    expect(Object.keys(flat.ja).sort()).toEqual(Object.keys(flat.en).sort());
  });

  /** English-only UI strings (en ≠ ja) that would leak into the Japanese page. */
  function englishOnly(): Set<string> {
    const out = new Set<string>();
    for (const [k, v] of Object.entries(flat.en)) {
      const jaV = flat.ja[k];
      if (typeof v === "string" && typeof jaV === "string" && v !== jaV && !v.includes("{{") && /[A-Za-z]{3}/.test(v)) out.add(v.trim());
    }
    return out;
  }

  it("criterion 11: in Japanese, no English UI string shows on the setup screen, the card, or the read-back", async () => {
    mockAnswerServer(answerRoutes({ action: null }));
    await setLang("ja");
    await openAnswerAppIn("ja");
    const leaks = () => visibleStrings(document.body).filter((s) => englishOnly().has(s));
    expect(leaks()).toEqual([]);
    const user = await startAs("dev_team_simulated", "田中", "ja");
    expect(leaks()).toEqual([]);
    await user.click(modeButton("tap", "ja"));
    expect(leaks()).toEqual([]);
    await answerByText(user, "赤い", "ja");
    await screen.findByTestId("readback");
    expect(leaks()).toEqual([]);
    expect(within(readback()).getByText(tr("ja", "answer.readback.title"))).toBeInTheDocument();
  });

  it("criterion 11: the JA | EN toggle switches the answer app in place, without a reload, keeping what was typed", async () => {
    const server = mockAnswerServer();
    await openAnswerApp();
    const user = await startAs("dev_team_simulated");
    await user.click(modeButton("text"));
    await user.type(screen.getByLabelText(tr("en", "answer.text.label")), "Half-typed answer");
    const caseFetches = server.calls.filter((c) => c.path === `/api/cases/${CASE_ID}`).length;
    const toggle = screen.getAllByRole("button").find((b) => b.textContent?.trim() === "JA");
    expect(toggle).toBeDefined();
    await user.click(toggle!);
    expect(screen.getByLabelText(tr("ja", "answer.text.label"))).toHaveValue("Half-typed answer");
    expect(screen.getByRole("heading", { name: op[0]!.text.ja })).toBeInTheDocument();
    expect(server.calls.filter((c) => c.path === `/api/cases/${CASE_ID}`).length).toBe(caseFetches);
  });

  it.each(["en", "ja"] as const)("criterion 11: the disclaimer stays visible on the answer app at every step (%s)", async (lang) => {
    mockAnswerServer(answerRoutes({ action: { ja: "吸引した", en: "Suctioned" } }));
    await setLang(lang);
    await openAnswerAppIn(lang);
    const text = tr(lang, "disclaimer.text");
    expect(screen.getByText(new RegExp(escape(text)))).toBeVisible();
    const user = await startAs("dev_team_simulated", "Dr Test", lang);
    expect(screen.getByText(new RegExp(escape(text)))).toBeVisible();
    await answerByText(user, "Answer", lang);
    await screen.findByTestId("readback");
    expect(screen.getByText(new RegExp(escape(text)))).toBeVisible();
    await user.click(confirmButton(lang));
    await screen.findByTestId("saved");
    expect(screen.getByText(new RegExp(escape(text)))).toBeVisible();
  });

  it("criterion 11 / rule 5: the AI draft being checked carries its 🤖 trust label; a quote being confirmed its 🎙️ label", async () => {
    mockAnswerServer();
    await openAnswerApp();
    const user = await startAs("operating_surgeon");
    expect(op[0]!.ai_draft).not.toBeNull();
    expect(hasBadge(screen.getByTestId("ai-draft"), "ai_detected")).toBe(true);
    await user.click(screen.getByRole("button", { name: tr("en", "answer.skip") }));
    expect(op[1]!.quote).not.toBeNull();
    expect(hasBadge(screen.getByTestId("quote"), "narration_extracted")).toBe(true);
  });
});
