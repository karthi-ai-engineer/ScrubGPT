import { QueryClient, useQuery } from "@tanstack/react-query";

import { api, ApiRequestError } from "./client";
import type { QueueRole, RecordsResponse } from "./types";

export const queryKeys = {
  cases: ["cases"] as const,
  case: (caseId: string) => ["cases", caseId] as const,
  reference: (procedureId: string) => ["references", procedureId] as const,
  answerQueue: (caseId: string, role: QueueRole) => ["cases", caseId, "answer-queue", role] as const,
  records: (caseId: string) => ["cases", caseId, "records"] as const,
};

/** Retry once, and only errors that may go away (never a 404). */
function shouldRetry(failureCount: number, error: Error): boolean {
  return failureCount < 1 && error instanceof ApiRequestError && error.retryable;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: shouldRetry,
        // Case packages only change when the app server restarts.
        staleTime: 5 * 60 * 1000,
        refetchOnWindowFocus: false,
      },
    },
  });
}

export function useCases() {
  return useQuery({
    queryKey: queryKeys.cases,
    queryFn: ({ signal }) => api.cases(signal),
    select: (data) => data.cases,
  });
}

export function useCase(caseId: string) {
  return useQuery({
    queryKey: queryKeys.case(caseId),
    queryFn: ({ signal }) => api.case(caseId, signal),
  });
}

/** The Procedure Reference; `null` id disables the query. */
export function useReference(procedureId: string | null) {
  return useQuery({
    queryKey: queryKeys.reference(procedureId ?? ""),
    queryFn: ({ signal }) => api.reference(procedureId ?? "", signal),
    enabled: procedureId !== null,
    staleTime: Infinity,
  });
}

/** J3: the questions to answer (operating or reviewer list), with clips; always fresh. */
export function useAnswerQueue(caseId: string, role: QueueRole) {
  return useQuery({
    queryKey: queryKeys.answerQueue(caseId, role),
    queryFn: ({ signal }) => api.answerQueue(caseId, role, signal),
    staleTime: 0,
  });
}

/** Stable (module-level), so the selected list keeps its identity between renders. */
const recordsOnly = (data: RecordsResponse) => data.records.map((stored) => stored.record);

/** I2: the case's stored Decision Records (seed + confirmed answers); always fresh. */
export function useCaseRecords(caseId: string) {
  return useQuery({
    queryKey: queryKeys.records(caseId),
    queryFn: ({ signal }) => api.records(caseId, signal),
    select: recordsOnly,
    staleTime: 0,
    retry: false,
  });
}
