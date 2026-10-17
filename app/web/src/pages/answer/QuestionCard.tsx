import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { AnswerMode, DecisionRecord, Verdict } from "@contracts/contracts";

import { api, ApiRequestError, isBrainUnavailable, type ClientErrorCode } from "@/api/client";
import type { AnswerQueueItem, DraftAnswer, DraftResponse } from "@/api/types";
import { TrustBadge } from "@/components/TrustBadge";
import { Button } from "@/components/ui/button";
import { useBilingual, useLang } from "@/i18n/useBilingual";
import { cn } from "@/lib/utils";

import type { Answerer, CardNotes } from "./answerer";
import { BrainUnavailableBanner } from "./BrainUnavailableBanner";
import { canAnswer } from "./fields";
import { ReadbackPanel } from "./ReadbackPanel";
import { audioFileName, useRecorder, type Recording } from "./recorder";

const MODE_ICON: Readonly<Record<AnswerMode, string>> = { tap: "👆", voice: "🎙", text: "⌨" };
const MODES: readonly AnswerMode[] = ["tap", "voice", "text"];
const VERDICT_ICON: Readonly<Record<Verdict, string>> = { confirm: "✓", edit: "✎", reject: "✗" };
const VERDICTS: readonly Verdict[] = ["confirm", "edit", "reject"];

interface QuestionCardProps {
  caseId: string;
  item: AnswerQueueItem;
  answerer: Answerer;
  notes: CardNotes;
  onNotes: (notes: CardNotes) => void;
  onSaved: (record: DecisionRecord) => void;
}

/**
 * One question (J3): the moment's clip looping, the question, the AI draft or quote being checked
 * (with its trust label), and tap, voice and text side by side with equal weight. A sent answer
 * becomes a read-back with chips; Confirm stores the record.
 */
export function QuestionCard({ caseId, item, answerer, notes, onNotes, onSaved }: QuestionCardProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const pick = useBilingual();
  const ids = useId();
  const { question, moment } = item;

  const [mode, setMode] = useState<AnswerMode | null>(null);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [choices, setChoices] = useState<string[]>([]);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<DraftResponse | null>(null);
  const [brainDown, setBrainDown] = useState(false);
  const [error, setError] = useState<ClientErrorCode | null>(null);
  const [voiceNote, setVoiceNote] = useState<"noSpeech" | "fallback" | null>(null);
  const [uploading, setUploading] = useState(false);
  const [transcript, setTranscript] = useState<string | null>(null);
  const textArea = useRef<HTMLTextAreaElement>(null);
  const allowed = canAnswer(answerer.role, question.id);

  const fail = (cause: unknown) => {
    if (isBrainUnavailable(cause)) setBrainDown(true);
    else setError(cause instanceof ApiRequestError ? cause.code : "network");
  };

  /** A voice failure falls back to text, keeping any transcript as the starting text. */
  const fallBackToText = (heard: string | null) => {
    setVoiceNote("fallback");
    setMode("text");
    if (heard && !notes.text.trim()) onNotes({ ...notes, text: heard });
    window.setTimeout(() => textArea.current?.focus(), 0);
  };

  const send = (answer: DraftAnswer) => {
    if (!allowed || sending) return;
    setSending(true);
    setBrainDown(false);
    setError(null);
    api
      .draftAnswer({ case_id: caseId, question_id: question.id, answerer_role: answerer.role, answer })
      .then(
        (response) => {
          setSending(false);
          setResult(response);
        },
        (cause: unknown) => {
          setSending(false);
          fail(cause);
          if (answer.mode === "voice") fallBackToText(answer.text);
        },
      );
  };

  const onRecorded = ({ blob, mimeType }: Recording) => {
    setUploading(true);
    setBrainDown(false);
    setError(null);
    setVoiceNote(null);
    api.uploadAudio(blob, audioFileName(mimeType), lang).then(
      (heard) => {
        setUploading(false);
        if (!heard.text.trim()) {
          setVoiceNote("noSpeech");
          return;
        }
        setTranscript(heard.text);
        send({
          answer_id: heard.answer_id,
          mode: "voice",
          tap: null,
          text: heard.text,
          lang: heard.lang,
          audio_uri: heard.audio_uri,
        });
      },
      (cause: unknown) => {
        setUploading(false);
        fail(cause);
        fallBackToText(null);
      },
    );
  };
  const recorder = useRecorder(onRecorded);

  const tapText = notes.tapEdit.trim();
  const tapReady = verdict !== null && (verdict !== "edit" || tapText !== "");
  const sendTap = () => {
    if (!verdict || !tapReady) return;
    send({
      mode: "tap",
      tap: { verdict, choice_ids: choices },
      text: verdict === "edit" ? tapText : null,
      lang,
      audio_uri: null,
    });
  };
  const sendText = () => {
    const text = notes.text.trim();
    if (!text) return;
    send({ mode: "text", tap: null, text, lang, audio_uri: null });
  };
  const toggleChoice = (id: string) =>
    setChoices((current) => (current.includes(id) ? current.filter((c) => c !== id) : [...current, id]));

  const recording = recorder.status === "recording";
  const micProblem =
    recorder.status === "unsupported" || recorder.status === "denied" || recorder.status === "failed" ? recorder.status : null;
  const busy = sending || uploading;

  return (
    <article className="flex flex-col gap-3" aria-labelledby={`${ids}-question`} data-question-id={question.id}>
      <video
        key={item.clip}
        src={item.clip}
        poster={item.poster}
        autoPlay
        loop
        muted
        playsInline
        preload="auto"
        aria-label={t("answer.clipLabel", { title: pick(moment.title) })}
        className="aspect-video w-full rounded-lg bg-black object-contain"
      />
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>{pick(moment.title)}</span>
        <TrustBadge label={moment.provenance.trust_label} />
      </div>

      <h2 id={`${ids}-question`} className="m-0 text-lg leading-snug font-semibold">
        {pick(question.text)}
      </h2>

      {question.ai_draft && (
        <figure className="m-0 flex flex-col gap-1 rounded-lg border border-border bg-card p-2.5" data-testid="ai-draft">
          <figcaption className="flex items-center gap-2 text-xs text-muted-foreground">
            {t("answer.aiDraft")}
            <TrustBadge label="ai_detected" />
          </figcaption>
          <p className="m-0 text-sm">{pick(question.ai_draft)}</p>
        </figure>
      )}
      {question.quote && (
        <figure className="m-0 flex flex-col gap-1 rounded-lg border border-border bg-card p-2.5" data-testid="quote">
          <figcaption className="flex items-center gap-2 text-xs text-muted-foreground">
            {t("answer.quote")}
            <TrustBadge label="narration_extracted" />
          </figcaption>
          <blockquote className="m-0 text-sm italic">“{pick(question.quote.text)}”</blockquote>
        </figure>
      )}

      {!allowed && (
        <p role="alert" className="m-0 text-sm text-destructive">
          {t("answer.roleMismatch")}
        </p>
      )}
      {brainDown && <BrainUnavailableBanner />}
      {error && (
        <p role="alert" className="m-0 text-sm text-destructive">
          {t("answer.error", { reason: t(`errors.code.${error}`) })}
        </p>
      )}

      {result ? (
        <ReadbackPanel
          caseId={caseId}
          result={result}
          confirmedBy={answerer.name}
          onConfirmed={onSaved}
          onStartOver={() => {
            setResult(null);
            setTranscript(null);
          }}
        />
      ) : (
        <div className="flex flex-col gap-3">
          <div role="group" aria-label={t("answer.modes")} className="grid grid-cols-3 gap-2">
            {MODES.map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={mode === option}
                disabled={!allowed || busy}
                onClick={() => setMode(option)}
                className={cn(
                  "flex h-16 cursor-pointer flex-col items-center justify-center gap-0.5 rounded-xl border-2 border-border bg-card text-sm font-semibold transition-colors hover:border-primary disabled:cursor-not-allowed disabled:opacity-50",
                  mode === option && "border-primary bg-accent text-accent-foreground",
                )}
              >
                <span aria-hidden="true" className="text-xl leading-none">
                  {MODE_ICON[option]}
                </span>
                {t(`answer.mode.${option}`)}
              </button>
            ))}
          </div>

          {mode === "tap" && (
            <div className="flex flex-col gap-2.5" data-testid="tap-panel">
              <div role="group" aria-label={t("answer.tap.verdicts")} className="grid grid-cols-3 gap-2">
                {VERDICTS.map((option) => (
                  <Button
                    key={option}
                    variant={verdict === option ? "default" : "outline"}
                    aria-pressed={verdict === option}
                    onClick={() => setVerdict(option)}
                    disabled={busy}
                  >
                    <span aria-hidden="true">{VERDICT_ICON[option]}</span>
                    {t(`answer.tap.${option}`)}
                  </Button>
                ))}
              </div>
              {question.tap_options.length > 0 && (
                <div className="flex flex-col gap-1.5">
                  <span className="text-xs text-muted-foreground">{t("answer.tap.options")}</span>
                  <div className="flex flex-wrap gap-1.5">
                    {question.tap_options.map((option) => (
                      <button
                        key={option.id}
                        type="button"
                        aria-pressed={choices.includes(option.id)}
                        onClick={() => toggleChoice(option.id)}
                        disabled={busy}
                        className={cn(
                          "cursor-pointer rounded-full border border-border bg-card px-3 py-1.5 text-sm",
                          choices.includes(option.id) && "border-primary bg-accent text-accent-foreground",
                        )}
                      >
                        {pick(option.label)}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {verdict === "edit" && (
                <div className="flex flex-col gap-1">
                  <label htmlFor={`${ids}-tap-edit`} className="text-xs font-medium">
                    {t("answer.tap.editLabel")}
                  </label>
                  <input
                    id={`${ids}-tap-edit`}
                    value={notes.tapEdit}
                    onChange={(event) => onNotes({ ...notes, tapEdit: event.target.value })}
                    className="h-9 rounded-md border border-input bg-card px-2.5 text-sm"
                  />
                  {!tapText && <span className="text-xs text-muted-foreground">{t("answer.tap.editRequired")}</span>}
                </div>
              )}
              {verdict === null && <span className="text-xs text-muted-foreground">{t("answer.tap.chooseVerdict")}</span>}
              <Button size="lg" onClick={sendTap} disabled={!tapReady || busy}>
                {t("answer.tap.send")}
              </Button>
            </div>
          )}

          {mode === "voice" && (
            <div className="flex flex-col items-center gap-2" data-testid="voice-panel">
              {micProblem ? (
                <p role="alert" className="m-0 text-sm">
                  {t(`answer.voice.${micProblem}`)}
                </p>
              ) : null}
              {recorder.status !== "unsupported" && (
                <Button
                  size="lg"
                  variant={recording ? "default" : "outline"}
                  className={cn("h-20 w-full text-base", recording && "animate-pulse")}
                  aria-pressed={recording}
                  disabled={busy || recorder.status === "starting"}
                  onClick={recording ? recorder.stop : recorder.start}
                >
                  <span aria-hidden="true">{recording ? "⏹" : "🎙"}</span>
                  {recording ? t("answer.voice.stop") : t("answer.voice.start")}
                </Button>
              )}
              <p className="m-0 min-h-5 text-sm text-muted-foreground" aria-live="polite">
                {recorder.status === "starting" && t("answer.voice.starting")}
                {recording && t("answer.voice.recording")}
                {uploading && t("answer.voice.uploading")}
              </p>
              {voiceNote === "noSpeech" && <p className="m-0 text-sm">{t("answer.voice.noSpeech")}</p>}
              {transcript && (
                <figure className="m-0 w-full rounded-lg border border-border bg-card p-2.5" data-testid="transcript">
                  <figcaption className="text-xs text-muted-foreground">{t("answer.voice.transcript")}</figcaption>
                  <p className="m-0 text-sm">{transcript}</p>
                </figure>
              )}
            </div>
          )}

          {mode === "text" && (
            <div className="flex flex-col gap-1.5" data-testid="text-panel">
              {voiceNote === "fallback" && <p className="m-0 text-sm">{t("answer.voice.fallback")}</p>}
              <label htmlFor={`${ids}-text`} className="text-xs font-medium">
                {t("answer.text.label")}
              </label>
              <textarea
                id={`${ids}-text`}
                ref={textArea}
                value={notes.text}
                onChange={(event) => onNotes({ ...notes, text: event.target.value })}
                placeholder={t("answer.text.placeholder")}
                lang={lang}
                rows={4}
                className="rounded-md border border-input bg-card p-2.5 text-base"
              />
              <Button size="lg" onClick={sendText} disabled={!notes.text.trim() || busy}>
                {t("answer.text.send")}
              </Button>
            </div>
          )}

          {sending && (
            <p role="status" className="m-0 text-sm text-muted-foreground">
              {t("answer.sending")}
            </p>
          )}
        </div>
      )}
    </article>
  );
}
