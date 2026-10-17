/**
 * Server-Sent Events from the app server (`GET /api/events`, I5; app/server README "SSE events").
 * The browser's `EventSource` reconnects by itself (the server sends `retry: 3000`).
 */
import { useEffect, useRef, useState } from "react";

import type { CaseEndedEvent } from "./types";

export const EVENTS_URL = "/api/events";

/** `EventSource.OPEN` (a literal, so a stubbed `EventSource` in tests needs no statics). */
const OPEN = 1;

/** The events the web app listens to, with their payloads. */
export interface ServerEventMap {
  "case.ended": CaseEndedEvent;
}

export type ServerEventName = keyof ServerEventMap;

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

/** Checks a payload's shape before the UI trusts it (never show a made-up number). */
const guards: { [K in ServerEventName]: (data: unknown) => data is ServerEventMap[K] } = {
  "case.ended": (data): data is CaseEndedEvent => {
    if (typeof data !== "object" || data === null) return false;
    const d = data as Record<string, unknown>;
    const q = d.questions as Record<string, unknown> | null | undefined;
    return (
      typeof d.case_id === "string" &&
      typeof q === "object" &&
      q !== null &&
      isCount(q.operating) &&
      isCount(q.reviewer) &&
      typeof d.est_seconds === "number" &&
      Number.isFinite(d.est_seconds) &&
      d.est_seconds >= 0
    );
  },
};

/** Parses and checks one SSE `data` field; `null` when it isn't a valid `name` payload. */
export function parseServerEvent<K extends ServerEventName>(name: K, raw: string): ServerEventMap[K] | null {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  return guards[name](data) ? data : null;
}

/**
 * Subscribes to one server event for as long as the component is mounted (the `EventSource` is
 * closed on unmount). Returns whether the stream is currently connected. Without `EventSource`
 * (old browsers, jsdom) it does nothing and reports `false`.
 */
export function useServerEvent<K extends ServerEventName>(
  name: K,
  handler: (data: ServerEventMap[K]) => void,
): boolean {
  const latest = useRef(handler);
  useEffect(() => {
    latest.current = handler;
  });
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource(EVENTS_URL);
    const onMessage = (event: MessageEvent<string>) => {
      const data = parseServerEvent(name, event.data);
      if (data) latest.current(data);
    };
    source.addEventListener(name, onMessage);
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(source.readyState === OPEN);
    return () => {
      source.removeEventListener(name, onMessage);
      source.close();
      setConnected(false);
    };
  }, [name]);

  return connected;
}
