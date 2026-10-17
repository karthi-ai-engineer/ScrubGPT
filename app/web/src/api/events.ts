/**
 * Server-Sent Events from the app server (`GET /api/events`, I5; app/server README "SSE events").
 * The browser's `EventSource` reconnects by itself (the server sends `retry: 3000`).
 *
 * A page opens **one** `EventSource`, however many events it listens to: every `useServerEvent`
 * shares it (reference-counted; closed when the last subscriber unmounts).
 */
import { useEffect, useRef, useSyncExternalStore } from "react";

import type { AnswerConfirmedEvent, CaseEndedEvent, GraphUpdatedEvent, RecordCreatedEvent } from "./types";

export const EVENTS_URL = "/api/events";

/** `EventSource.OPEN` (a literal, so a stubbed `EventSource` in tests needs no statics). */
const OPEN = 1;

/** The events the web app listens to, with their payloads. */
export interface ServerEventMap {
  "case.ended": CaseEndedEvent;
  "answer.confirmed": AnswerConfirmedEvent;
  "record.created": RecordCreatedEvent;
  "graph.updated": GraphUpdatedEvent;
}

export type ServerEventName = keyof ServerEventMap;

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isBilingual(value: unknown): boolean {
  return isObject(value) && typeof value.ja === "string" && typeof value.en === "string";
}

/**
 * Enough of a stored Decision Record for the graph to place it (one node per record): its id,
 * case, moment or step, viewpoint, action text and trust label. The server validated the rest.
 */
function isRecordLike(value: unknown): boolean {
  if (!isObject(value)) return false;
  const action = value.action;
  const provenance = value.provenance;
  return (
    typeof value.id === "string" &&
    typeof value.case_id === "string" &&
    typeof value.step_id === "string" &&
    (value.moment_id === null || typeof value.moment_id === "string") &&
    (value.question_id === null || typeof value.question_id === "string") &&
    isObject(action) &&
    isBilingual(action.text) &&
    isObject(provenance) &&
    typeof provenance.trust_label === "string"
  );
}

/** Checks a payload's shape before the UI trusts it (never show a made-up number). */
const guards: { [K in ServerEventName]: (data: unknown) => data is ServerEventMap[K] } = {
  "case.ended": (data): data is CaseEndedEvent => {
    if (!isObject(data)) return false;
    const q = data.questions;
    return (
      typeof data.case_id === "string" &&
      isObject(q) &&
      isCount(q.operating) &&
      isCount(q.reviewer) &&
      typeof data.est_seconds === "number" &&
      Number.isFinite(data.est_seconds) &&
      data.est_seconds >= 0
    );
  },
  "answer.confirmed": (data): data is AnswerConfirmedEvent =>
    isObject(data) &&
    typeof data.case_id === "string" &&
    (data.question_id === null || typeof data.question_id === "string") &&
    typeof data.record_id === "string" &&
    typeof data.answer_id === "string",
  "record.created": (data): data is RecordCreatedEvent => isObject(data) && isRecordLike(data.record),
  "graph.updated": (data): data is GraphUpdatedEvent =>
    isObject(data) && typeof data.case_id === "string" && Array.isArray(data.nodes) && Array.isArray(data.edges),
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

// ── The shared connection ───────────────────────────────────────────────────────

interface Hub {
  source: EventSource;
  refs: number;
  connected: boolean;
}

let hub: Hub | null = null;
const statusListeners = new Set<() => void>();

function setConnected(target: Hub, connected: boolean) {
  if (target.connected === connected) return;
  target.connected = connected;
  for (const notify of statusListeners) notify();
}

function acquire(): Hub | null {
  if (typeof EventSource === "undefined") return null;
  if (!hub) {
    const created: Hub = { source: new EventSource(EVENTS_URL), refs: 0, connected: false };
    created.source.onopen = () => setConnected(created, true);
    created.source.onerror = () => setConnected(created, created.source.readyState === OPEN);
    hub = created;
  }
  hub.refs += 1;
  return hub;
}

function release(target: Hub) {
  target.refs -= 1;
  if (target.refs > 0) return;
  target.source.close();
  if (hub === target) hub = null;
  setConnected(target, false);
}

function subscribeStatus(notify: () => void) {
  statusListeners.add(notify);
  return () => {
    statusListeners.delete(notify);
  };
}

const connectedNow = () => hub?.connected ?? false;
const connectedOnServer = () => false;

/**
 * Subscribes to one server event for as long as the component is mounted. Returns whether the
 * stream is currently connected. Without `EventSource` (old browsers, jsdom) it does nothing and
 * reports `false`.
 */
export function useServerEvent<K extends ServerEventName>(
  name: K,
  handler: (data: ServerEventMap[K]) => void,
): boolean {
  const latest = useRef(handler);
  useEffect(() => {
    latest.current = handler;
  });
  const connected = useSyncExternalStore(subscribeStatus, connectedNow, connectedOnServer);

  useEffect(() => {
    const shared = acquire();
    if (!shared) return;
    const onMessage = (event: Event) => {
      const data = parseServerEvent(name, String((event as MessageEvent<unknown>).data));
      if (data) latest.current(data);
    };
    shared.source.addEventListener(name, onMessage);
    return () => {
      shared.source.removeEventListener(name, onMessage);
      release(shared);
    };
  }, [name]);

  return connected;
}
