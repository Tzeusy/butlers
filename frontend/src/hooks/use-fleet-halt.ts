/**
 * useFleetHaltStatus — derives the monthly spend-ceiling fleet-halt state
 * from GET /api/dispatch/attempts (bu-7o89u.3).
 *
 * The ceiling is enforced by check_monthly_ceiling / the spawner
 * (spawner.py:1179-1202): once month-to-date spend reaches the configured
 * ceiling, EVERY dispatch across EVERY butler is denied and a `quota_skip`
 * provenance row is written with a `failure_reason` starting "Monthly spend
 * ceiling reached". That's distinct from the routine same-tier token-quota
 * `quota_skip` rows written during normal failover (spawner.py:1082,1122) --
 * `reason_prefix` isolates the ceiling-specific denials from that noise.
 *
 * Three lightweight queries against the same endpoint, scoped by params:
 *   - onset:  since=start-of-month, order=asc,  limit=1  -> total this month
 *             (accurate regardless of limit -- meta.total is a server-side
 *             COUNT) + the earliest row's ts ("denied since <ts>").
 *   - today:  since=start-of-today, limit=1              -> today's count.
 *   - recent: since=start-of-month, order=desc, limit=N  -> drawer rows.
 *
 * `isError` MUST gate the caller's render -- a failed fetch is NOT "no
 * halt" (fleet degraded-source convention: never fabricate calm).
 */

import { useQuery } from "@tanstack/react-query";

import { getDispatchAttempts } from "@/api/client";
import type { DispatchAttemptEntry } from "@/api/types";
import { useBusAwarePollInterval } from "@/hooks/use-bus-aware-poll-interval";

/** The quota_skip failure_reason prefix written by the monthly spend-ceiling
 * hard block -- see module doc above for why this must be reason-scoped, not
 * just outcome-scoped. */
export const CEILING_DENIAL_REASON_PREFIX = "Monthly spend ceiling reached";

const DEFAULT_DRAWER_LIMIT = 20;

function startOfTodayIso(): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

function startOfMonthIso(): string {
  const d = new Date();
  d.setDate(1);
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

export interface FleetHaltStatus {
  /** True once loaded, not errored, and at least one ceiling denial exists this month. */
  active: boolean;
  /** Total ceiling denials since the start of the current calendar month. */
  deniedTotal: number;
  /** Ceiling denials since the start of the current owner-local day. */
  deniedToday: number;
  /** ISO timestamp of the earliest ceiling denial this month, or null if none/unknown. */
  since: string | null;
  /** Most recent denied attempts (desc by ts) for the attempts drawer. */
  recentAttempts: DispatchAttemptEntry[];
  isLoading: boolean;
  /** True when any of the underlying queries failed -- render a degraded note, not "no halt". */
  isError: boolean;
}

export function useFleetHaltStatus(drawerLimit: number = DEFAULT_DRAWER_LIMIT): FleetHaltStatus {
  const refetchInterval = useBusAwarePollInterval();
  const sinceMonth = startOfMonthIso();
  const sinceToday = startOfTodayIso();

  const onset = useQuery({
    queryKey: ["dispatch-attempts", "ceiling-onset", sinceMonth],
    queryFn: () =>
      getDispatchAttempts({
        outcome: "quota_skip",
        reason_prefix: CEILING_DENIAL_REASON_PREFIX,
        since: sinceMonth,
        order: "asc",
        limit: 1,
      }),
    refetchInterval,
  });

  const today = useQuery({
    queryKey: ["dispatch-attempts", "ceiling-today", sinceToday],
    queryFn: () =>
      getDispatchAttempts({
        outcome: "quota_skip",
        reason_prefix: CEILING_DENIAL_REASON_PREFIX,
        since: sinceToday,
        limit: 1,
      }),
    refetchInterval,
  });

  const recent = useQuery({
    queryKey: ["dispatch-attempts", "ceiling-recent", sinceMonth, drawerLimit],
    queryFn: () =>
      getDispatchAttempts({
        outcome: "quota_skip",
        reason_prefix: CEILING_DENIAL_REASON_PREFIX,
        since: sinceMonth,
        order: "desc",
        limit: drawerLimit,
      }),
    refetchInterval,
  });

  const isLoading = onset.isLoading || today.isLoading || recent.isLoading;
  const isError = onset.isError || today.isError || recent.isError;
  const deniedTotal = onset.data?.meta.total ?? 0;

  return {
    active: !isError && !isLoading && deniedTotal > 0,
    deniedTotal,
    deniedToday: today.data?.meta.total ?? 0,
    since: onset.data?.data[0]?.ts ?? null,
    recentAttempts: recent.data?.data ?? [],
    isLoading,
    isError,
  };
}
