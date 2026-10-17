import type { ApiError, ErrorCode, ProcedureReference } from "@contracts/contracts";

import type { AppHealth, CaseDetail, CaseEndedEvent, CasesResponse } from "./types";

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

async function requestJson<T>(path: string, signal?: AbortSignal, method: "GET" | "POST" = "GET"): Promise<T> {
  let response: Response;
  try {
    const init: RequestInit = { headers: { Accept: "application/json" }, signal };
    response = await fetch(path, method === "GET" ? init : { ...init, method });
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
};
