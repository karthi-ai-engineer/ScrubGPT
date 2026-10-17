import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProcedureReference } from "@contracts/contracts";

import type { QueueRole } from "@/api/types";
import i18n from "@/i18n";
import {
  ANSWER_ID,
  brainError,
  CASE,
  confirmedRecord,
  draftFor,
  draftResponse,
  extractFor,
  fixtureQueue,
} from "@/test/answerFixtures";
import { installFakeMic, removeFakeMic } from "@/test/fakes";
import { fixtureDetail, mockFetch } from "@/test/fixtures";
import { renderApp } from "@/test/render";

import referenceJson from "../../../../../contracts/fixtures/reference/rarp.json";
import { NAME_STORAGE_KEY } from "./answerer";

const reference = referenceJson as ProcedureReference;
const operating = fixtureDetail.questions.operating;
const reviewer = fixtureDetail.questions.reviewer;
type Reply = { status: number; body: unknown };

interface Server {
  draft?: (body: Record<string, unknown>, n: number) => Reply;
  confirm?: (body: Record<string, unknown>, n: number) => Reply;
  audio?: (n: number) => Reply;
  brainHealth?: Reply;
  answered?: string[];
}

let fetchSpy: ReturnType<typeof mockFetch>;

/** The app server for the Answer app: case, queue (by `?role=`), Brain health, draft, audio, confirm. */
function serve(server: Server = {}) {
  const counts = { draft: 0, confirm: 0, audio: 0 };
  fetchSpy = mockFetch((url) => {
    if (url === `/api/cases/${CASE}`) return { status: 200, body: fixtureDetail };
    if (url === "/api/references/rarp") return { status: 200, body: reference };
    if (url === "/api/brain/health") return server.brainHealth ?? { status: 200, body: { status: "ok" } };
    const queue = /^\/api\/cases\/case-fixture-01\/answer-queue\?role=(\w+)$/.exec(url);
    if (queue) return { status: 200, body: fixtureQueue(queue[1] as QueueRole, server.answered) };
    return undefined;
  });
  // Bodies of POSTs: answer with the handlers above (draft/confirm need the request body).
  const routeGet = fetchSpy.getMockImplementation();
  fetchSpy.mockImplementation(async (input, init) => {
    const url = String(input);
    const json = (reply: Reply) =>
      new Response(JSON.stringify(reply.body), { status: reply.status, headers: { "Content-Type": "application/json" } });
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : {};
    if (url === "/api/answers/draft" && server.draft) return json(server.draft(body, counts.draft++));
    if (url === "/api/answers/confirm" && server.confirm) return json(server.confirm(body, counts.confirm++));
    if (url === "/api/answers/audio" && server.audio) return json(server.audio(counts.audio++));
    return routeGet ? routeGet(input, init) : json({ status: 404, body: {} });
  });
}

const posts = (path: string) =>
  fetchSpy.mock.calls.filter(([url, init]) => url === path && (init as RequestInit | undefined)?.method === "POST");
const jsonBodies = (path: string) => posts(path).map(([, init]) => JSON.parse(String((init as RequestInit).body)) as unknown);

/** Opens the Answer app and gets past the setup screen. */
async function start(options: { route?: string; role?: RegExp; name?: string } = {}) {
  const user = userEvent.setup();
  renderApp(options.route ?? `/cases/${CASE}/answer?role=operating`);
  await screen.findByRole("heading", { name: "Who is answering?" });
  if (options.role) await user.click(screen.getByRole("radio", { name: options.role }));
  const name = screen.getByLabelText("Confirmed by (your name)");
  await user.clear(name);
  await user.type(name, options.name ?? "Dr Test");
  await user.click(screen.getByRole("button", { name: "Start answering" }));
  await screen.findByTestId("progress");
  return user;
}

/** The role radio (its label also holds the trust badge and a hint). */
const roleRadio = (role: string) => {
  const radio = document.querySelector(`input[type="radio"][value="${role}"][name$="-role"]`);
  if (!(radio instanceof HTMLInputElement)) throw new Error(`no role ${role}`);
  return radio;
};
const progress = () => screen.getByTestId("progress").textContent;
const questionHeading = () => screen.getByRole("heading", { level: 2 }).textContent;

beforeEach(() => {
  serve();
});

afterEach(() => {
  vi.unstubAllGlobals();
  removeFakeMic();
});

describe("Answer app: setup and the queue", () => {
  it("shows the phone frame, role-play 🧪 by default, and needs a name (remembered)", async () => {
    const user = userEvent.setup();
    renderApp(`/cases/${CASE}/answer`);
    expect(await screen.findByRole("region", { name: "Answer app (phone view)" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Role-play/ })).toBeChecked();
    const startButton = screen.getByRole("button", { name: "Start answering" });
    expect(startButton).toBeDisabled();
    await user.type(screen.getByLabelText("Confirmed by (your name)"), "  Dr Sato ");
    await user.click(startButton);
    await screen.findByTestId("progress");
    expect(window.localStorage.getItem(NAME_STORAGE_KEY)).toBe("Dr Sato");
    expect(screen.getByTestId("answerer")).toHaveTextContent("Role-play (simulated) · Dr Sato");
    expect(within(screen.getByTestId("answerer")).getByText("Simulated")).toBeInTheDocument();
  });

  it("pre-fills the remembered name, and works when storage throws", async () => {
    window.localStorage.setItem(NAME_STORAGE_KEY, "Dr Kept");
    renderApp(`/cases/${CASE}/answer`);
    expect(await screen.findByLabelText("Confirmed by (your name)")).toHaveValue("Dr Kept");
  });

  it("works when storage is blocked", async () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
      clear: () => undefined,
    });
    await start();
    expect(progress()).toContain("1 of");
  });

  it("shows '1 of 8 · ~3 min' from the queue, then skip and later", async () => {
    const user = await start();
    const total = operating.length;
    const seconds = operating.reduce((s, q) => s + q.est_seconds, 0);
    expect(progress()).toBe(`1 of ${total} · ~${Math.ceil(seconds / 60)} min`);
    expect(questionHeading()).toBe(operating[0]?.text.en);
    expect(fetchSpy).toHaveBeenCalledWith(`/api/cases/${CASE}/answer-queue?role=operating`, expect.anything());

    // The clip loops, muted and inline, with its poster.
    const video = document.querySelector("video");
    expect(video).toHaveAttribute("src", `/media/cases/${CASE}/clips/case-fixture-01.m01.mp4`);
    expect(video).toHaveAttribute("poster", `/media/cases/${CASE}/clips/case-fixture-01.m01.jpg`);
    expect(video).toHaveAttribute("loop");
    expect(video).toHaveAttribute("playsinline");
    expect(video?.muted).toBe(true);
    // The AI draft being checked carries its 🤖 label.
    expect(within(screen.getByTestId("ai-draft")).getByText("AI-detected")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Skip" }));
    const left = seconds - (operating[0]?.est_seconds ?? 0);
    expect(progress()).toBe(`2 of ${total} · ~${Math.ceil(left / 60)} min`);
    expect(questionHeading()).toBe(operating[1]?.text.en);
    // A quote to confirm carries its 🎙️ label.
    expect(within(screen.getByTestId("quote")).getByText("From narration")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Later" }));
    expect(progress()).toBe(`2 of ${total} · ~${Math.ceil(left / 60)} min`);
    expect(questionHeading()).toBe(operating[2]?.text.en);

    // Skip to the end: the "later" question comes last.
    for (let i = 1; i < total - 1; i += 1) await user.click(screen.getByRole("button", { name: "Skip" }));
    expect(progress()).toBe(`${total} of ${total} · ~1 min`);
    expect(questionHeading()).toBe(operating[1]?.text.en);
    await user.click(screen.getByRole("button", { name: "Skip" }));
    expect(screen.getByTestId("done-summary")).toHaveTextContent(`Saved 0 · Skipped ${total}`);
    await user.click(screen.getByRole("button", { name: "Answer the skipped questions" }));
    expect(progress()).toContain(`1 of ${total}`);
  });

  it("asks only unanswered questions", async () => {
    serve({ answered: [operating[0]?.id ?? ""] });
    await start();
    expect(progress()).toContain(`1 of ${operating.length - 1}`);
    expect(questionHeading()).toBe(operating[1]?.text.en);
  });
});

describe("Answer app: who answers which question (D-066)", () => {
  it("an operating surgeon gets the operating list, even from a reviewer link", async () => {
    serve({ draft: () => ({ status: 200, body: draftResponse(extractFor(draftFor(operating[0]?.id ?? ""))) }) });
    const user = await start({ route: `/cases/${CASE}/answer?role=reviewer`, role: /Operating surgeon/ });
    expect(fetchSpy).toHaveBeenCalledWith(`/api/cases/${CASE}/answer-queue?role=operating`, expect.anything());
    expect(questionHeading()).toBe(operating[0]?.text.en);
    await user.click(screen.getByRole("button", { name: /Text/ }));
    await user.type(screen.getByLabelText("Your answer"), "Oozing");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(jsonBodies("/api/answers/draft")).toHaveLength(1));
    expect(jsonBodies("/api/answers/draft")[0]).toMatchObject({ answerer_role: "operating_surgeon", question_id: operating[0]?.id });
  });

  it("a reviewer gets the reviewer list and can't pick the surgeon's", async () => {
    const user = userEvent.setup();
    renderApp(`/cases/${CASE}/answer?role=operating`);
    await screen.findByRole("heading", { name: "Who is answering?" });
    await user.click(roleRadio("reviewer"));
    expect(screen.getByRole("radio", { name: "Surgeon questions" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "Reviewer questions" })).toBeChecked();
    await user.type(screen.getByLabelText("Confirmed by (your name)"), "Dr R");
    await user.click(screen.getByRole("button", { name: "Start answering" }));
    await screen.findByTestId("progress");
    expect(questionHeading()).toBe(reviewer[0]?.text.en);
    expect(progress()).toContain(`1 of ${reviewer.length}`);
  });

  it("role-play may choose either list", async () => {
    const user = userEvent.setup();
    renderApp(`/cases/${CASE}/answer`);
    await user.click(await screen.findByRole("radio", { name: "Reviewer questions" }));
    await user.type(screen.getByLabelText("Confirmed by (your name)"), "Dev");
    await user.click(screen.getByRole("button", { name: "Start answering" }));
    await screen.findByTestId("progress");
    expect(questionHeading()).toBe(reviewer[0]?.text.en);
  });
});

describe("Answer app: tap, voice and text", () => {
  const q1 = operating[0];
  if (!q1) throw new Error("no question");
  const okDraft = () => ({ status: 200, body: draftResponse(extractFor(draftFor(q1.id))) });

  it("offers the three modes side by side with equal weight", async () => {
    await start();
    const modes = within(screen.getByRole("group", { name: "How to answer" })).getAllByRole("button");
    expect(modes.map((b) => b.textContent)).toEqual(["👆Tap", "🎙Voice", "⌨Text"]);
    expect(new Set(modes.map((b) => b.className)).size).toBe(1);
    for (const b of modes) expect(b).toHaveAttribute("aria-pressed", "false");
  });

  it("tap: a verdict plus tap options in tap order → the contract's Answer", async () => {
    serve({ draft: okDraft });
    const user = await start();
    await user.click(screen.getByRole("button", { name: /Tap/ }));
    const send = screen.getByRole("button", { name: "Send" });
    expect(send).toBeDisabled();
    const verdicts = within(screen.getByRole("group", { name: "Your verdict" })).getAllByRole("button");
    expect(verdicts.map((b) => b.textContent)).toEqual(["✓Confirm", "✎Edit", "✗Reject"]);
    await user.click(screen.getByRole("button", { name: /Confirm/ }));
    const [first, second] = [q1.tap_options[1], q1.tap_options[0]];
    if (!first || !second) throw new Error("tap options");
    await user.click(screen.getByRole("button", { name: first.label.en }));
    await user.click(screen.getByRole("button", { name: second.label.en }));
    expect(screen.getByRole("button", { name: first.label.en })).toHaveAttribute("aria-pressed", "true");
    await user.click(send);
    await screen.findByTestId("readback");
    expect(jsonBodies("/api/answers/draft")).toEqual([
      {
        case_id: CASE,
        question_id: q1.id,
        answerer_role: "dev_team_simulated",
        answer: { mode: "tap", tap: { verdict: "confirm", choice_ids: [first.id, second.id] }, text: null, lang: "en", audio_uri: null },
      },
    ]);
  });

  it("tap: an edit needs the surgeon's words, which are sent as text", async () => {
    serve({ draft: okDraft });
    const user = await start();
    await user.click(screen.getByRole("button", { name: /Tap/ }));
    await user.click(screen.getByRole("button", { name: /Edit/ }));
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(screen.getByText("An edit needs your own words.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Your correction"), "Arterial, not venous");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByTestId("readback");
    expect(jsonBodies("/api/answers/draft")[0]).toMatchObject({
      answer: { mode: "tap", tap: { verdict: "edit", choice_ids: [] }, text: "Arterial, not venous", lang: "en", audio_uri: null },
    });
  });

  it("text: typed in the UI language (Japanese here)", async () => {
    serve({ draft: okDraft });
    await act(() => i18n.changeLanguage("ja"));
    const user = userEvent.setup();
    renderApp(`/cases/${CASE}/answer?role=operating`);
    await user.type(await screen.findByLabelText("確認者（お名前）"), "田中");
    await user.click(screen.getByRole("button", { name: "回答を始める" }));
    expect(await screen.findByTestId("progress")).toHaveTextContent(`1 / ${operating.length}・約3分`);
    await user.click(screen.getByRole("button", { name: /テキスト/ }));
    await user.type(screen.getByLabelText("回答"), "結紮部からのにじみ");
    await user.click(screen.getByRole("button", { name: "送信" }));
    await screen.findByTestId("readback");
    expect(jsonBodies("/api/answers/draft")[0]).toEqual({
      case_id: CASE,
      question_id: q1.id,
      answerer_role: "dev_team_simulated",
      answer: { mode: "text", tap: null, text: "結紮部からのにじみ", lang: "ja", audio_uri: null },
    });
  });

  it("voice: records webm/opus, uploads with lang_hint, shows the transcript, drafts with the server's answer_id", async () => {
    const mic = installFakeMic();
    serve({
      audio: () => ({
        status: 200,
        body: { answer_id: ANSWER_ID, audio_uri: `answers/${ANSWER_ID}.webm`, text: "にじみが見えた", lang: "ja" },
      }),
      draft: okDraft,
    });
    const user = await start();
    await user.click(screen.getByRole("button", { name: /Voice/ }));
    await user.click(screen.getByRole("button", { name: /Press to record/ }));
    await screen.findByRole("button", { name: /Press to stop/ });
    expect(mic.getUserMedia).toHaveBeenCalledWith({ audio: true });
    await user.click(screen.getByRole("button", { name: /Press to stop/ }));
    await screen.findByTestId("readback");
    expect(mic.stopTrack).toHaveBeenCalled();

    const [, init] = posts("/api/answers/audio")[0] ?? [];
    const form = (init as RequestInit).body as FormData;
    expect(form.get("lang_hint")).toBe("en");
    const file = form.get("audio") as File;
    expect(file.name).toBe("answer.webm");
    expect(file.type).toBe("audio/webm;codecs=opus");
    expect(jsonBodies("/api/answers/draft")[0]).toEqual({
      case_id: CASE,
      question_id: q1.id,
      answerer_role: "dev_team_simulated",
      answer: {
        answer_id: ANSWER_ID,
        mode: "voice",
        tap: null,
        text: "にじみが見えた",
        lang: "ja",
        audio_uri: `answers/${ANSWER_ID}.webm`,
      },
    });
  });

  it("voice: Safari records mp4/aac", async () => {
    installFakeMic({ supported: ["audio/mp4"] });
    serve({
      audio: () => ({ status: 200, body: { answer_id: ANSWER_ID, audio_uri: `answers/${ANSWER_ID}.m4a`, text: "Oozing", lang: "en" } }),
      draft: okDraft,
    });
    const user = await start();
    await user.click(screen.getByRole("button", { name: /Voice/ }));
    await user.click(screen.getByRole("button", { name: /Press to record/ }));
    await user.click(await screen.findByRole("button", { name: /Press to stop/ }));
    await screen.findByTestId("readback");
    const file = ((posts("/api/answers/audio")[0]?.[1] as RequestInit).body as FormData).get("audio") as File;
    expect(file.name).toBe("answer.m4a");
    expect(file.type).toBe("audio/mp4");
  });

  it("voice: no speech heard → says so and sends nothing to draft", async () => {
    installFakeMic();
    serve({ audio: () => ({ status: 200, body: { answer_id: ANSWER_ID, audio_uri: "answers/x.webm", text: " ", lang: "en" } }) });
    const user = await start();
    await user.click(screen.getByRole("button", { name: /Voice/ }));
    await user.click(screen.getByRole("button", { name: /Press to record/ }));
    await user.click(await screen.findByRole("button", { name: /Press to stop/ }));
    expect(await screen.findByText("No speech was heard. Try again, or answer by tap or text.")).toBeInTheDocument();
    expect(posts("/api/answers/draft")).toHaveLength(0);
  });

  it("voice: no microphone here → explains it and points to tap or text", async () => {
    removeFakeMic();
    const user = await start();
    await user.click(screen.getByRole("button", { name: /Voice/ }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The microphone isn't available here (it needs localhost or HTTPS). Answer by tap or text.",
    );
    expect(screen.queryByRole("button", { name: /Press to record/ })).not.toBeInTheDocument();
  });

  it("voice: microphone denied → explains it", async () => {
    installFakeMic({ deny: "NotAllowedError" });
    const user = await start();
    await user.click(screen.getByRole("button", { name: /Voice/ }));
    await user.click(screen.getByRole("button", { name: /Press to record/ }));
    expect(await screen.findByText(/Microphone access was denied/)).toBeInTheDocument();
  });
});

describe("Answer app: read-back, chips and Confirm", () => {
  const q1 = operating[0];
  if (!q1) throw new Error("no question");

  async function toReadback(server: Server) {
    serve(server);
    const user = await start({ name: "Dr Test" });
    await user.click(screen.getByRole("button", { name: /Text/ }));
    await user.type(screen.getByLabelText("Your answer"), "We raised the pressure");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByTestId("readback");
    return user;
  }

  it("one chip per filled field, none for a null field; missing fields are empty 'not stated' inputs", async () => {
    const draft = draftFor(q1.id, { only: ["action.text"] });
    await toReadback({ draft: () => ({ status: 200, body: draftResponse(extractFor(draft)) }) });
    expect(screen.getByTestId("readback-text")).toHaveTextContent(`Action: ${draft.action.text?.en}.`);

    const chips = within(screen.getByTestId("chips")).getAllByRole("listitem");
    expect(chips.map((c) => c.getAttribute("data-field"))).toEqual(["action.text"]);
    expect(chips[0]).toHaveTextContent("Action");
    expect(chips[0]).toHaveTextContent(draft.action.text?.en ?? "");

    const missing = screen.getByTestId("missing-fields");
    const cue = within(missing).getByLabelText("Situation cue (not stated)");
    expect(cue).toHaveValue("");
    expect(cue).toHaveAttribute("placeholder", "not stated");
    expect(within(missing).getByLabelText("Reason (not stated)")).toHaveValue("");
    expect(within(missing).getByText(/Obstacle/).closest("p")).toHaveTextContent("Obstacle: not stated (can't be filled in here)");

    // The record's trust label, and who the provenance will name.
    const readback = screen.getByTestId("readback");
    expect(within(readback).getByText("Simulated")).toBeInTheDocument();
    expect(readback).toHaveTextContent("Provenance will say it was confirmed by Dr Test.");
  });

  it("an alternative's missing why-not is a fill-in input too", async () => {
    const draft = { ...draftFor(q1.id), alternatives: [{ option: { ja: "追加の縫合", en: "An additional suture" }, why_not: null }] };
    await toReadback({ draft: () => ({ status: 200, body: draftResponse(extractFor(draft, ["alternatives[0].why_not"])) }) });
    expect(within(screen.getByTestId("missing-fields")).getByLabelText("Why not (not stated)")).toHaveValue("");
  });

  it("Confirm stays disabled until the cue and the action are filled; the edits are sent", async () => {
    const draft = draftFor(q1.id, { only: ["reason"] });
    const record = confirmedRecord(draft, "01a1436a-9999-7000-8000-000000000009", "Dr Test");
    const user = await toReadback({
      draft: () => ({ status: 200, body: draftResponse(extractFor(draft)) }),
      confirm: () => ({ status: 201, body: { record } }),
    });
    const confirm = screen.getByRole("button", { name: "Confirm" });
    expect(confirm).toBeDisabled();
    expect(screen.getByTestId("confirm-hint")).toHaveTextContent("To confirm, fill in: Situation cue, Action");

    await user.type(screen.getByLabelText("Situation cue (not stated)"), "Venous oozing");
    expect(confirm).toBeDisabled();
    expect(screen.getByTestId("confirm-hint")).toHaveTextContent("To confirm, fill in: Action");
    await user.type(screen.getByLabelText("Action (not stated)"), "Raised the pressure");
    expect(confirm).toBeEnabled();
    expect(screen.queryByTestId("confirm-hint")).not.toBeInTheDocument();

    // Edit the reason chip.
    await user.click(screen.getByRole("button", { name: "Edit: Reason" }));
    const editor = screen.getByRole("textbox", { name: "Edit: Reason" });
    expect(editor).toHaveValue(draft.reason?.en);
    expect(confirm).toBeDisabled(); // an open editor first
    await user.clear(editor);
    await user.type(editor, "It was venous");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(within(screen.getByTestId("chips")).getByText("Edited")).toBeInTheDocument();

    await user.click(confirm);
    await screen.findByTestId("saved");
    expect(jsonBodies("/api/answers/confirm")).toEqual([
      {
        answer_id: ANSWER_ID,
        draft,
        edits: [
          { field: "situation_cue.text", text: "Venous oozing", lang: "en" },
          { field: "action.text", text: "Raised the pressure", lang: "en" },
          { field: "reason", text: "It was venous", lang: "en" },
        ],
        confirmed_by: "Dr Test",
      },
    ]);
    // Saved, with the record's trust badge; the next card is up.
    const saved = screen.getByTestId("saved");
    expect(saved).toHaveTextContent(`Saved: ${q1.text.en}`);
    expect(within(saved).getByText("Simulated")).toBeInTheDocument();
    expect(progress()).toContain(`2 of ${operating.length}`);
  });

  it("an unchanged chip edit is not an edit; undo drops it; start over goes back to the modes", async () => {
    const draft = draftFor(q1.id);
    const user = await toReadback({ draft: () => ({ status: 200, body: draftResponse(extractFor(draft)) }) });
    await user.click(screen.getByRole("button", { name: "Edit: Reason" }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(within(screen.getByTestId("chips")).queryByText("Edited")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit: Reason" }));
    await user.type(screen.getByRole("textbox", { name: "Edit: Reason" }), "!");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(within(screen.getByTestId("chips")).queryByText("Edited")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start over" }));
    expect(screen.queryByTestId("readback")).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: "How to answer" })).toBeInTheDocument();
  });
});

describe("Answer app: Brain unavailable (503/504)", () => {
  const q1 = operating[0];
  if (!q1) throw new Error("no question");

  it("shows the banner, keeps the card and the typed text; trying again works", async () => {
    serve({
      draft: (_body, n) => (n === 0 ? brainError("unavailable") : { status: 200, body: draftResponse(extractFor(draftFor(q1.id))) }),
    });
    const user = await start();
    await user.click(screen.getByRole("button", { name: /Text/ }));
    await user.type(screen.getByLabelText("Your answer"), "My words");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByTestId("brain-unavailable")).toHaveTextContent(
      "The Brain is unavailable: answer by tap or text, or try again later.",
    );
    expect(questionHeading()).toBe(q1.text.en);
    expect(screen.getByLabelText("Your answer")).toHaveValue("My words");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByTestId("readback");
    expect(screen.queryByTestId("brain-unavailable")).not.toBeInTheDocument();
  });

  it("the typed text survives 'later' and coming back", async () => {
    const user = await start();
    await user.click(screen.getByRole("button", { name: /Text/ }));
    await user.type(screen.getByLabelText("Your answer"), "Half an answer");
    await user.click(screen.getByRole("button", { name: "Later" }));
    for (let i = 1; i < operating.length; i += 1) await user.click(screen.getByRole("button", { name: "Skip" }));
    expect(questionHeading()).toBe(q1.text.en);
    await user.click(screen.getByRole("button", { name: /Text/ }));
    expect(screen.getByLabelText("Your answer")).toHaveValue("Half an answer");
  });

  it("a voice failure (504) falls back to text", async () => {
    installFakeMic();
    serve({ audio: () => brainError("timeout") });
    const user = await start();
    await user.click(screen.getByRole("button", { name: /Voice/ }));
    await user.click(screen.getByRole("button", { name: /Press to record/ }));
    await user.click(await screen.findByRole("button", { name: /Press to stop/ }));
    expect(await screen.findByTestId("brain-unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Text/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Voice didn't work this time: type your answer instead.")).toBeInTheDocument();
    expect(screen.getByLabelText("Your answer")).toBeInTheDocument();
  });

  it("a voice draft that fails keeps the transcript as text", async () => {
    installFakeMic();
    serve({
      audio: () => ({ status: 200, body: { answer_id: ANSWER_ID, audio_uri: "answers/a.webm", text: "Heard words", lang: "en" } }),
      draft: () => brainError("unavailable"),
    });
    const user = await start();
    await user.click(screen.getByRole("button", { name: /Voice/ }));
    await user.click(screen.getByRole("button", { name: /Press to record/ }));
    await user.click(await screen.findByRole("button", { name: /Press to stop/ }));
    await screen.findByTestId("brain-unavailable");
    expect(screen.getByLabelText("Your answer")).toHaveValue("Heard words");
  });

  it("Confirm failing with 503 keeps the filled fields", async () => {
    const draft = draftFor(q1.id, { only: ["action.text"] });
    serve({ draft: () => ({ status: 200, body: draftResponse(extractFor(draft)) }), confirm: () => brainError("unavailable") });
    const user = await start();
    await user.click(screen.getByRole("button", { name: /Text/ }));
    await user.type(screen.getByLabelText("Your answer"), "x");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await user.type(await screen.findByLabelText("Situation cue (not stated)"), "Cue words");
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByTestId("brain-unavailable")).toBeInTheDocument();
    expect(screen.getByLabelText("Situation cue (not stated)")).toHaveValue("Cue words");
    expect(screen.getByRole("button", { name: "Confirm" })).toBeEnabled();
  });

  it("says so up front when the Brain's health check is 503, in Japanese too", async () => {
    serve({ brainHealth: brainError("unavailable") });
    await act(() => i18n.changeLanguage("ja"));
    renderApp(`/cases/${CASE}/answer`);
    expect(await screen.findByTestId("brain-unavailable")).toHaveTextContent(
      "Brain を利用できません。タップかテキストで回答するか、しばらくしてからもう一度お試しください。",
    );
  });
});

describe("Answer app: Japanese", () => {
  it("shows the modes, the read-back labels and 'not stated' in Japanese", async () => {
    const q1 = operating[0];
    if (!q1) throw new Error("no question");
    serve({ draft: () => ({ status: 200, body: draftResponse(extractFor(draftFor(q1.id, { only: ["action.text"] }))) }) });
    await act(() => i18n.changeLanguage("ja"));
    const user = userEvent.setup();
    renderApp(`/cases/${CASE}/answer`);
    await user.type(await screen.findByLabelText("確認者（お名前）"), "田中");
    await user.click(screen.getByRole("button", { name: "回答を始める" }));
    await screen.findByTestId("progress");
    expect(questionHeading()).toBe(q1.text.ja);
    const modes = within(screen.getByRole("group", { name: "回答方法" })).getAllByRole("button");
    expect(modes.map((b) => b.textContent)).toEqual(["👆タップ", "🎙音声", "⌨テキスト"]);
    expect(screen.getByRole("button", { name: "スキップ" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "後で" })).toBeInTheDocument();
    await user.click(modes[2] as HTMLElement);
    await user.type(screen.getByLabelText("回答"), "対応");
    await user.click(screen.getByRole("button", { name: "送信" }));
    await screen.findByTestId("readback");
    expect(screen.getByLabelText("状況の手がかり（未回答）")).toHaveAttribute("placeholder", "未回答");
    expect(screen.getByTestId("confirm-hint")).toHaveTextContent("確定するには次を入力してください：状況の手がかり");
    expect(screen.getByRole("button", { name: "確定" })).toBeDisabled();
    expect(within(screen.getByTestId("chips")).getByText("対応")).toBeInTheDocument();
  });
});
