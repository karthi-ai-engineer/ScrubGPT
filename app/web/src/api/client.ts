import type {
  ApiError,
  ErrorCode,
  HealthResponse,
  LangHint,
  ProcedureReference,
  TranslateRequest,
  TranslateResponse,
} from "@contracts/contracts";

import type {
  AnswerQueue,
  AppHealth,
  AudioAnswer,
  CaseDetail,
  CaseEndedEvent,
  CasesResponse,
  ConfirmRequest,
  ConfirmResponse,
  DraftRequest,
  DraftResponse,
  QueueRole,
  RecordsResponse,
} from "./types";

/**
 * `ErrorCode` from the server's `ApiError` body, plus two client-side codes:
 * `network` (the server could not be reached) and `http` (a non-JSON or unexpected error).
 */
export type ClientErrorCode = ErrorCode | "network" | "http";

/** Thrown by every API call; the UI shows a localised text for `code`. */
export class ApiRequestError extends Error {
  readonly code: ClientErrorCode;
  readonly status: number | null;
  readonly retryable: boolean;

  constructor(code: ClientErrorCode, message: string, status: number | null, retryable: boolean) {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
    this.status = status;
    this.retryable = retryable;
  }
}

function isApiError(body: unknown): body is ApiError {
  if (typeof body !== "object" || body === null || !("error" in body)) return false;
  const error = (body as { error: unknown }).error;
  return typeof error === "object" && error !== null && "code" in error && "message" in error;
}

/** What a POST sends: JSON (an object) or a multipart form. */
type Body = object | FormData;

async function requestJson<T>(
  path: string,
  signal?: AbortSignal,
  method: "GET" | "POST" = "GET",
  payload?: Body,
): Promise<T> {
  let response: Response;
  try {
    const init: RequestInit = { headers: { Accept: "application/json" }, signal };
    if (method === "GET") {
      response = await fetch(path, init);
    } else if (payload === undefined) {
      response = await fetch(path, { ...init, method });
    } else if (payload instanceof FormData) {
      // The browser sets the multipart boundary itself.
      response = await fetch(path, { ...init, method, body: payload });
    } else {
      response = await fetch(path, {
        ...init,
        method,
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }
  } catch (cause) {
    if (signal?.aborted) throw cause;
    throw new ApiRequestError("network", `Could not reach the app server (${path})`, null, true);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    if (isApiError(body)) {
      const { code, message, retryable } = body.error;
      throw new ApiRequestError(code, message, response.status, retryable);
    }
    // A 502/504 without an ApiError body comes from a proxy (the Vite dev server) whose
    // upstream app server is down: show it as "can't reach the app server".
    const unreachable = response.status === 502 || response.status === 504;
    throw new ApiRequestError(
      unreachable ? "network" : "http",
      `HTTP ${response.status} from ${path}`,
      response.status,
      response.status >= 500,
    );
  }
  if (body === null) {
    throw new ApiRequestError("http", `Response from ${path} is not JSON`, response.status, false);
  }
  return body as T;
}

/** 503 `unavailable` / 504 `timeout` from the Brain: the UI says "Brain unavailable" (D-071). */
export function isBrainUnavailable(error: unknown): boolean {
  return error instanceof ApiRequestError && (error.code === "unavailable" || error.code === "timeout");
}

export const api = {
  health: (signal?: AbortSignal) => requestJson<AppHealth>("/api/health", signal),
  cases: (signal?: AbortSignal) => requestJson<CasesResponse>("/api/cases", signal),
  case: (caseId: string, signal?: AbortSignal) =>
    requestJson<CaseDetail>(`/api/cases/${encodeURIComponent(caseId)}`, signal),
  reference: (procedureId: string, signal?: AbortSignal) =>
    requestJson<ProcedureReference>(`/api/references/${encodeURIComponent(procedureId)}`, signal),
  /** The Control Room's replay reached the end: the server publishes `case.ended` (SSE). */
  replayEnded: (caseId: string, signal?: AbortSignal) =>
    requestJson<CaseEndedEvent>(`/api/cases/${encodeURIComponent(caseId)}/replay-ended`, signal, "POST"),

  // ── Answer app (J3) ──
  answerQueue: (caseId: string, role: QueueRole, signal?: AbortSignal) =>
    requestJson<AnswerQueue>(
      `/api/cases/${encodeURIComponent(caseId)}/answer-queue?role=${encodeURIComponent(role)}`,
      signal,
    ),
  /** The case's stored Decision Records (seed + confirmed answers). */
  records: (caseId: string, signal?: AbortSignal) =>
    requestJson<RecordsResponse>(`/api/cases/${encodeURIComponent(caseId)}/records`, signal),
  /** Uploads a voice answer; the server assigns the UUIDv7 `answer_id`, keeps the file and transcribes it. */
  uploadAudio: (audio: Blob, filename: string, langHint: LangHint, signal?: AbortSignal) => {
    const form = new FormData();
    form.append("audio", audio, filename);
    form.append("lang_hint", langHint);
    return requestJson<AudioAnswer>("/api/answers/audio", signal, "POST", form);
  },
  draftAnswer: (body: DraftRequest, signal?: AbortSignal) =>
    requestJson<DraftResponse>("/api/answers/draft", signal, "POST", body),
  translate: (body: TranslateRequest, signal?: AbortSignal) =>
    requestJson<TranslateResponse>("/api/translate", signal, "POST", body),
  confirmAnswer: (body: ConfirmRequest, signal?: AbortSignal) =>
    requestJson<ConfirmResponse>("/api/answers/confirm", signal, "POST", body),
  brainHealth: (signal?: AbortSignal) => requestJson<HealthResponse>("/api/brain/health", signal),
};
