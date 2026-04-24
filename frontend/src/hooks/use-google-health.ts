/**
 * React Query hooks for the Google Health connector status card.
 *
 * Polls GET /api/connectors/google-health/status every 30 seconds to
 * surface connection state, token age, and ingest counts.
 */

import { useQuery } from "@tanstack/react-query";

import { getGoogleHealthStatus } from "@/api/index.ts";

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const googleHealthKeys = {
  all: ["googleHealth"] as const,
  status: () => ["googleHealth", "status"] as const,
};

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

/**
 * Fetch the current Google Health connector state.
 *
 * Auto-polls every 30 seconds while the page is visible (per spec E4).
 * Use `isFetching` to show the refresh indicator between polls.
 */
export function useGoogleHealthStatus() {
  return useQuery({
    queryKey: googleHealthKeys.status(),
    queryFn: () => getGoogleHealthStatus(),
    refetchInterval: 30_000,
    retry: false,
  });
}
