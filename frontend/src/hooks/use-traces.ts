/**
 * TanStack Query hooks for the traces API.
 */

import { useQuery } from "@tanstack/react-query";

import { getTrace, getTraces } from "@/api/index.ts";
import type { TraceParams } from "@/api/types.ts";

/** Fetch a paginated list of traces across all butlers. */
export function useTraces(params?: TraceParams) {
  return useQuery({
    queryKey: ["traces", params],
    queryFn: () => getTraces(params),
    refetchInterval: 30_000,
  });
}

/** Fetch full trace detail including the span tree. */
export function useTraceDetail(traceId: string | null) {
  return useQuery({
    queryKey: ["trace-detail", traceId],
    queryFn: () => getTrace(traceId!),
    enabled: !!traceId,
  });
}
