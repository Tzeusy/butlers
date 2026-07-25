// ---------------------------------------------------------------------------
// StandingConditionsTile -- standing infrastructure condition ledger
// (bu-27dxl.6.2 / bu-ep4ks.3)
//
// Data source: useSystemConditions -> GET /api/system/conditions
// Opens the door on public.infra_conditions: until now an L0-L3 escalating
// outage was durable in Postgres but visible only via psql, and QA-dispatch
// Gate 5.5 suppressed repeat findings against it invisibly. Also surfaces,
// per condition, how many QA dispatches it suppressed (useInfraConditionSuppressionCounts
// -> GET /api/healing/dispatch-events?decision=infra_condition_open), joined
// on the shared fingerprint identity -- the concrete "link to the condition
// that suppressed them" slice 3 asks for.
// ---------------------------------------------------------------------------

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { StateDot, type DispatchState } from "@/components/ui/StateDot"
import { Time } from "@/components/ui/time"
import { useSystemConditions } from "@/hooks/use-system"
import { useInfraConditionSuppressionCounts } from "@/hooks/use-healing"
import { formatDurationCompact } from "@/lib/format-duration"
import type { ConditionEntry } from "@/api/types"

function TileSkeleton() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Standing Conditions</CardTitle>
        <CardDescription>Infrastructure outages tracked by the reliability ledger</CardDescription>
      </CardHeader>
      <CardContent>
        <div data-testid="standing-conditions-skeleton" className="space-y-2">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-5 w-44" />
        </div>
      </CardContent>
    </Card>
  )
}

function TileFrame({ children, testId }: { children: React.ReactNode; testId?: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Standing Conditions</CardTitle>
        <CardDescription>Infrastructure outages tracked by the reliability ledger</CardDescription>
      </CardHeader>
      <CardContent data-testid={testId}>{children}</CardContent>
    </Card>
  )
}

function conditionDotState(state: string): DispatchState {
  if (state === "open") return "error"
  if (state === "aging") return "degraded"
  return "ok"
}

function ConditionRow({ condition, suppressedCount }: { condition: ConditionEntry; suppressedCount: number }) {
  const isResolved = condition.state === "resolved"
  return (
    <li className="text-sm" data-testid="standing-condition-row">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 min-w-0">
          <StateDot state={conditionDotState(condition.state)} />
          <span className="font-medium truncate">{condition.source}</span>
          <span className="text-muted-foreground font-mono text-xs shrink-0">
            {condition.escalation_level}
          </span>
        </span>
        <span className="text-muted-foreground tabular-nums shrink-0 text-xs uppercase">
          {condition.state}
        </span>
      </div>
      {condition.summary ? (
        <div className="text-muted-foreground text-xs truncate" title={condition.summary}>
          {condition.summary}
        </div>
      ) : null}
      <div className="text-muted-foreground text-xs">
        {isResolved ? (
          <>
            Resolved <Time value={condition.resolved_at ?? condition.last_confirmed_at} mode="relative" />
            {condition.recovered_after_s != null
              ? ` (recovered after ${formatDurationCompact(condition.recovered_after_s * 1000)})`
              : null}
          </>
        ) : (
          <>
            Detected <Time value={condition.first_detected_at} mode="relative" />
          </>
        )}
        {suppressedCount > 0 ? (
          <span data-testid="condition-suppressed-count">
            {" "}
            · {suppressedCount} QA dispatch{suppressedCount === 1 ? "" : "es"} suppressed
          </span>
        ) : null}
      </div>
    </li>
  )
}

export function StandingConditionsTile() {
  const { data: response, isPending, isError } = useSystemConditions({ limit: 20 })
  const { counts: suppressedCounts } = useInfraConditionSuppressionCounts()

  if (isPending) return <TileSkeleton />

  if (isError) {
    return (
      <TileFrame testId="standing-conditions-error">
        <p className="text-destructive text-sm">Could not load standing conditions.</p>
      </TileFrame>
    )
  }

  const facts = response?.data

  if (!facts || !facts.conditions_available) {
    return (
      <TileFrame testId="standing-conditions-degraded">
        <p className="text-destructive text-sm">
          Standing conditions unavailable. The reliability ledger could not be reached.
        </p>
      </TileFrame>
    )
  }

  if (facts.conditions.length === 0) {
    return (
      <TileFrame testId="standing-conditions-empty">
        <p className="text-muted-foreground text-sm">No standing conditions recorded.</p>
      </TileFrame>
    )
  }

  return (
    <TileFrame testId="standing-conditions-content">
      <ul className="space-y-3 max-h-[320px] overflow-y-auto">
        {facts.conditions.map((condition) => (
          <ConditionRow
            key={condition.id}
            condition={condition}
            suppressedCount={suppressedCounts.get(condition.fingerprint) ?? 0}
          />
        ))}
      </ul>
    </TileFrame>
  )
}
