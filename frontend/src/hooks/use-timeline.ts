/**
 * TanStack Query hook for the unified timeline API.
 */

import { useQuery } from "@tanstack/react-query";

import { getTimeline } from "@/api/index.ts";
import type { TimelineParams } from "@/api/types.ts";

/** Fetch the unified timeline with cursor pagination and auto-refresh. */
export function useTimeline(params?: TimelineParams) {
  return useQuery({
    queryKey: ["timeline", params],
    queryFn: () => getTimeline(params),
    refetchInterval: 30_000,
  });
}
