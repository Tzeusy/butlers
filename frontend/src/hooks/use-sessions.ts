/**
 * TanStack Query hooks for the sessions API.
 */

import { useQuery } from "@tanstack/react-query";

import {
  getButlerSession,
  getButlerSessions,
  getSessions,
} from "@/api/index.ts";

/** Query parameters for paginated session lists. */
export interface SessionParams {
  offset?: number;
  limit?: number;
}

/** Fetch a paginated list of sessions across all butlers. */
export function useSessions(params?: SessionParams) {
  return useQuery({
    queryKey: ["sessions", params],
    queryFn: () => getSessions(params),
    refetchInterval: 30_000,
  });
}

/** Fetch a paginated list of sessions for a single butler. */
export function useButlerSessions(name: string, params?: SessionParams) {
  return useQuery({
    queryKey: ["butler-sessions", name, params],
    queryFn: () => getButlerSessions(name, params),
    enabled: !!name,
    refetchInterval: 30_000,
  });
}

/** Fetch full session detail for a specific butler session. */
export function useSessionDetail(butler: string, id: string | null) {
  return useQuery({
    queryKey: ["session-detail", butler, id],
    queryFn: () => getButlerSession(butler, id!),
    enabled: !!butler && !!id,
  });
}
