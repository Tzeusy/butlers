// ---------------------------------------------------------------------------
// RecentMoments — compact above-the-fold feed of recent butler actions
// (bu-2okpr.3)
//
// Renders a vertical list of recent sessions, one row per session:
//   relative time  |  butler glyph  |  one-line prompt summary  |  detail link
//
// Data source: /api/sessions (useSessions hook).
// Skeleton via shadcn Skeleton. Time via <Time mode="relative" />.
//
// This component is intentionally standalone — no DashboardPage wiring yet.
// ---------------------------------------------------------------------------

import { Link } from "react-router"
import { ExternalLinkIcon } from "lucide-react"

import type { SessionSummary } from "@/api/types"
import { Skeleton } from "@/components/ui/skeleton"
import { Time } from "@/components/ui/time"
import { useSessions } from "@/hooks/use-sessions"
import { cn } from "@/lib/utils"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface RecentMomentsProps {
  /** Maximum number of moments to show. @default 7 */
  limit?: number
}

// ---------------------------------------------------------------------------
// Butler glyph helpers
// ---------------------------------------------------------------------------

/**
 * Categorical color slots (8) mapped to CSS token classes.
 * Same slot count as ActivityFeed and SessionTable to keep color assignments
 * visually consistent across the dashboard.
 */
const GLYPH_COLORS = [
  "bg-[oklch(0.623_0.214_259.0)] text-white",  // category-1: blue
  "bg-[oklch(0.581_0.234_292.5)] text-white",  // category-2: violet
  "bg-[oklch(0.769_0.189_84.0)]  text-white",  // category-3: amber
  "bg-[oklch(0.706_0.145_183.5)] text-white",  // category-4: teal
  "bg-[oklch(0.641_0.271_11.2)]  text-white",  // category-5: rose
  "bg-[oklch(0.585_0.233_278.0)] text-white",  // category-6: indigo
  "bg-[oklch(0.717_0.184_208.5)] text-white",  // category-7: cyan
  "bg-[oklch(0.737_0.213_58.0)]  text-white",  // category-8: orange
] as const

/** Deterministic slot for a butler name based on a simple djb2-style hash. */
function butlerColorSlot(name: string): number {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) | 0
  }
  return Math.abs(hash) % GLYPH_COLORS.length
}

/** Single uppercase letter used as the visual glyph for a butler. */
function butlerInitial(name: string): string {
  return (name[0] ?? "?").toUpperCase()
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Truncate a prompt to a single readable line. */
function truncatePrompt(text: string, max = 72): string {
  const firstLine = text.split("\n")[0] ?? text
  if (firstLine.length <= max) return firstLine
  return firstLine.slice(0, max) + "…"
}

// ---------------------------------------------------------------------------
// Skeleton row
// ---------------------------------------------------------------------------

function SkeletonRow() {
  return (
    <div className="flex items-center gap-3 py-2" aria-hidden="true">
      <Skeleton className="h-4 w-16 shrink-0" />
      <Skeleton className="h-6 w-6 shrink-0 rounded-full" />
      <Skeleton className="h-4 flex-1" />
      <Skeleton className="h-4 w-4 shrink-0" />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <p className="py-4 text-sm text-muted-foreground">
      No recent activity yet.
    </p>
  )
}

// ---------------------------------------------------------------------------
// Single moment row
// ---------------------------------------------------------------------------

interface MomentRowProps {
  session: SessionSummary
}

function MomentRow({ session }: MomentRowProps) {
  const butlerName = session.butler ?? "unknown"
  const slot = butlerColorSlot(butlerName)
  const colorClass = GLYPH_COLORS[slot]

  return (
    <div
      className={cn(
        "group flex items-center gap-3 py-2",
        "border-b border-border/50 last:border-0",
      )}
    >
      {/* Relative time */}
      <Time
        value={session.started_at}
        mode="relative"
        showTitle={true}
        className="w-16 shrink-0 text-xs text-muted-foreground tabular-nums"
      />

      {/* Butler glyph */}
      <span
        className={cn(
          "flex h-6 w-6 shrink-0 items-center justify-center rounded-full",
          "text-xs font-semibold leading-none",
          colorClass,
        )}
        title={butlerName}
        aria-label={butlerName}
      >
        {butlerInitial(butlerName)}
      </span>

      {/* Prompt summary */}
      <span
        className="min-w-0 flex-1 truncate text-sm"
        title={session.prompt}
      >
        {truncatePrompt(session.prompt)}
      </span>

      {/* Detail link */}
      <Link
        to={`/sessions/${session.id}`}
        className={cn(
          "shrink-0 text-muted-foreground",
          "opacity-0 group-hover:opacity-100 focus-visible:opacity-100",
          "transition-opacity",
        )}
        aria-label={`View session details`}
      >
        <ExternalLinkIcon className="h-3.5 w-3.5" />
      </Link>
    </div>
  )
}

// ---------------------------------------------------------------------------
// RecentMoments
// ---------------------------------------------------------------------------

/**
 * Compact feed of the most recent butler actions (sessions).
 *
 * Renders up to `limit` sessions sorted by recency. The component is
 * intentionally unstyled at the container level so callers can embed it
 * inside any card or panel layout.
 *
 * @example
 * <RecentMoments limit={5} />
 */
export function RecentMoments({ limit = 7 }: RecentMomentsProps) {
  const { data, isPending } = useSessions(
    { limit, status: "all" },
    { refetchInterval: 30_000 },
  )

  const sessions = data?.data ?? []

  if (isPending) {
    return (
      <div data-testid="recent-moments-skeleton">
        {Array.from({ length: limit }, (_, i) => (
          <SkeletonRow key={i} />
        ))}
      </div>
    )
  }

  if (sessions.length === 0) {
    return <EmptyState />
  }

  return (
    <div data-testid="recent-moments-list">
      {sessions.map((session) => (
        <MomentRow key={session.id} session={session} />
      ))}
    </div>
  )
}
