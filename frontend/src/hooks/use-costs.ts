/**
 * TanStack Query hooks for the costs API.
 */

import { useQuery } from "@tanstack/react-query";

import { getCostSummary, getDailyCosts, getTopSessions } from "@/api/index.ts";

/** Fetch aggregate cost summary with auto-refresh. */
export function useCostSummary(period?: string) {
  return useQuery({
    queryKey: ["cost-summary", period],
    queryFn: () => getCostSummary(period),
    refetchInterval: 60_000,
  });
}

/** Fetch daily cost breakdown with auto-refresh. */
export function useDailyCosts() {
  return useQuery({
    queryKey: ["daily-costs"],
    queryFn: () => getDailyCosts(),
    refetchInterval: 60_000,
  });
}

/** Fetch most expensive sessions with auto-refresh. */
export function useTopSessions(limit?: number) {
  return useQuery({
    queryKey: ["top-sessions", limit],
    queryFn: () => getTopSessions(limit),
    refetchInterval: 60_000,
  });
}
