/**
 * Voice answers (J3, app/web CLAUDE.md rule 7): MediaRecorder with webm/opus in Chromium and
 * mp4/aac in Safari. Browsers allow the microphone only on `localhost` or over HTTPS.
 */
import { useCallback, useEffect, useRef, useState } from "react";

const PREFERRED_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"] as const;

/** The first recording format the browser supports; `""` lets the browser choose. */
export function pickMimeType(): string {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") return "";
  return PREFERRED_TYPES.find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
}

/** The upload file name for a recording type (the server keeps `answers/<answer_id>.<ext>`). */
export function audioFileName(mimeType: string): string {
  const base = mimeType.split(";")[0]?.trim().toLowerCase() ?? "";
  if (base === "audio/mp4" || base === "video/mp4") return "answer.m4a";
  if (base === "audio/ogg") return "answer.ogg";
  return "answer.webm";
}

/** Whether this page can record at all (a secure context, `getUserMedia` and `MediaRecorder`). */
export function micSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    window.isSecureContext !== false &&
    typeof navigator !== "undefined" &&
    typeof navigator.mediaDevices?.getUserMedia === "function" &&
    typeof MediaRecorder !== "undefined"
  );
}

export type RecorderStatus = "idle" | "starting" | "recording" | "unsupported" | "denied" | "failed";

export interface Recording {
  blob: Blob;
  mimeType: string;
}

export interface Recorder {
  status: RecorderStatus;
  start: () => void;
  stop: () => void;
}

/** Press to record, press to stop; `onRecorded` gets the audio once the recorder has flushed. */
export function useRecorder(onRecorded: (recording: Recording) => void): Recorder {
  const [status, setStatus] = useState<RecorderStatus>(() => (micSupported() ? "idle" : "unsupported"));
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const latest = useRef(onRecorded);
  useEffect(() => {
    latest.current = onRecorded;
  });

  const release = useCallback(() => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    recorder.current = null;
  }, []);

  useEffect(
    () => () => {
      if (recorder.current && recorder.current.state !== "inactive") {
        recorder.current.onstop = null;
        recorder.current.stop();
      }
      release();
    },
    [release],
  );

  const start = useCallback(() => {
    if (!micSupported()) {
      setStatus("unsupported");
      return;
    }
    setStatus("starting");
    navigator.mediaDevices.getUserMedia({ audio: true }).then(
      (media) => {
        stream.current = media;
        const mimeType = pickMimeType();
        let created: MediaRecorder;
        try {
          created = mimeType ? new MediaRecorder(media, { mimeType }) : new MediaRecorder(media);
        } catch {
          release();
          setStatus("failed");
          return;
        }
        const chunks: Blob[] = [];
        created.ondataavailable = (event: BlobEvent) => {
          if (event.data.size > 0) chunks.push(event.data);
        };
        created.onstop = () => {
          const type = created.mimeType || mimeType || "audio/webm";
          release();
          setStatus("idle");
          latest.current({ blob: new Blob(chunks, { type }), mimeType: type });
        };
        recorder.current = created;
        created.start();
        setStatus("recording");
      },
      (error: unknown) => {
        const name = error instanceof DOMException || error instanceof Error ? error.name : "";
        setStatus(name === "NotAllowedError" || name === "SecurityError" ? "denied" : "failed");
      },
    );
  }, [release]);

  const stop = useCallback(() => {
    const current = recorder.current;
    if (current && current.state !== "inactive") current.stop();
  }, []);

  return { status, start, stop };
}
