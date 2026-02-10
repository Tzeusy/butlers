/**
 * TanStack Query hooks for the sessions API.
 */

import { useQuery } from "@tanstack/react-query";

import {
  getButlerSession,
  getButlerSessions,
  getSession,
  getSessions,
} from "@/api/index.ts";
import type { SessionParams } from "@/api/index.ts";

/** Fetch a paginated list of sessions across all butlers. */
export function useSessions(params?: SessionParams) {
  return useQuery({
    queryKey: ["sessions", params],
    queryFn: () => getSessions(params),
  });
}

/** Fetch sessions scoped to a specific butler. */
export function useButlerSessions(name: string, params?: SessionParams) {
  return useQuery({
    queryKey: ["butler-sessions", name, params],
    queryFn: () => getButlerSessions(name, params),
    enabled: !!name,
  });
}

/** Fetch a single session detail (cross-butler). */
export function useSessionDetail(id: string) {
  return useQuery({
    queryKey: ["session", id],
    queryFn: () => getSession(id),
    enabled: !!id,
  });
}

/** Fetch a single session detail for a specific butler. */
export function useButlerSessionDetail(butler: string, id: string) {
  return useQuery({
    queryKey: ["butler-session", butler, id],
    queryFn: () => getButlerSession(butler, id),
    enabled: !!butler && !!id,
  });
}
