/**
 * TanStack Query hooks for the butlers API.
 */

import { useQuery } from "@tanstack/react-query";

import { getButler, getButlerConfig, getButlerSkills, getButlers } from "@/api/index.ts";

/** Fetch all butlers with live status. */
export function useButlers() {
  return useQuery({
    queryKey: ["butlers"],
    queryFn: () => getButlers(),
    refetchInterval: 30_000,
  });
}

/** Fetch a single butler by name. */
export function useButler(name: string) {
  return useQuery({
    queryKey: ["butlers", name],
    queryFn: () => getButler(name),
    enabled: !!name,
  });
}

/** Fetch configuration files for a specific butler. */
export function useButlerConfig(name: string) {
  return useQuery({
    queryKey: ["butlers", name, "config"],
    queryFn: () => getButlerConfig(name),
    enabled: !!name,
  });
}

/** Fetch skills available to a specific butler. */
export function useButlerSkills(name: string) {
  return useQuery({
    queryKey: ["butlers", name, "skills"],
    queryFn: () => getButlerSkills(name),
    enabled: !!name,
  });
}
