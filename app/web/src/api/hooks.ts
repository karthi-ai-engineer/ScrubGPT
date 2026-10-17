import { QueryClient, useQuery } from "@tanstack/react-query";

import { api, ApiRequestError } from "./client";

export const queryKeys = {
  cases: ["cases"] as const,
  case: (caseId: string) => ["cases", caseId] as const,
  reference: (procedureId: string) => ["references", procedureId] as const,
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
