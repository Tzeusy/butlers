/**
 * IngestionTimelinePage — route component for /ingestion (Timeline root).
 *
 * Mounts under the INGESTION_DISPATCH_CONSOLE sub-route hierarchy when the
 * feature flag is on. The Timeline is the default landing view for the
 * ingestion surface.
 *
 * Uses Dispatch primitives (DispatchLayout, DispatchHeader) and the shared
 * IngestionSubNav for consistent navigation across all ingestion routes.
 * No legacy TabsTrigger shell — sub-nav replaces the old ?tab= switcher.
 *
 * Header aside: live status badge. Status is derived from the most-recent
 * event's received_at: "Live" when an event arrived within the last 60 s,
 * "Idle" otherwise.  TimelineTab reports freshness via onFreshnessChange
 * so the badge reflects real pipeline activity, not a wall-clock timer.
 *
 * Spec: openspec/changes/complete-ingestion-redesign-parity/specs/
 *       dashboard-ingestion-dispatch-console/spec.md §"Timeline route replaces legacy tab landing"
 *       §"Timeline Ledger" — header band with live freshness/status pill
 */

import { useCallback, useState } from 'react'
import { IngestionSubNav } from '@/components/ingestion/IngestionSubNav'
import { DispatchLayout, DispatchHeader, DispatchSurface } from '@/components/ingestion/dispatch'
import { TimelineTab } from '@/components/ingestion/TimelineTab'

// ---------------------------------------------------------------------------
// LiveStatusBadge — driven by real event freshness
// ---------------------------------------------------------------------------

/** Freshness window: an event received within this many ms is "live". */
const LIVE_FRESHNESS_MS = 60_000

type LiveStatus = 'checking' | 'live' | 'idle'

interface LiveStatusBadgeProps {
  /**
   * ISO-8601 received_at of the most-recent ingestion event, or null when the
   * events query has not yet returned (still loading / no events).
   * null → "checking"; within LIVE_FRESHNESS_MS → "live"; older → "idle".
   */
  latestReceivedAt: string | null
}

function deriveStatus(latestReceivedAt: string | null): LiveStatus {
  if (latestReceivedAt === null) return 'checking'
  const age = Date.now() - new Date(latestReceivedAt).getTime()
  return age <= LIVE_FRESHNESS_MS ? 'live' : 'idle'
}

function LiveStatusBadge({ latestReceivedAt }: LiveStatusBadgeProps) {
  const status = deriveStatus(latestReceivedAt)

  if (status === 'checking') {
    return (
      <span className="inline-flex items-center gap-1.5 font-mono text-[11px] tracking-[0.01em] text-muted-foreground">
        <span className="size-1.5 rounded-full bg-muted-foreground animate-pulse" />
        checking…
      </span>
    )
  }

  if (status === 'live') {
    return (
      <span
        className="inline-flex items-center gap-1.5 font-mono text-[11px] tracking-[0.01em]"
        style={{ color: 'var(--green, theme(colors.emerald.600))' }}
        data-testid="live-status-badge-live"
      >
        <span
          className="size-1.5 rounded-full animate-pulse"
          style={{ backgroundColor: 'var(--green, theme(colors.emerald.600))' }}
        />
        Live
      </span>
    )
  }

  return (
    <span
      className="inline-flex items-center gap-1.5 font-mono text-[11px] tracking-[0.01em] text-muted-foreground"
      data-testid="live-status-badge-idle"
    >
      <span className="size-1.5 rounded-full bg-muted-foreground/50" />
      Idle
    </span>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function IngestionTimelinePage() {
  // Freshness state: null until TimelineTab reports its first data fetch.
  const [latestReceivedAt, setLatestReceivedAt] = useState<string | null>(null)

  const handleFreshnessChange = useCallback((ra: string | null) => {
    setLatestReceivedAt(ra)
  }, [])

  return (
    <DispatchLayout>
      <DispatchHeader
        eyebrow="Ingestion · timeline"
        headline="Today, in order of arrival."
        description="Every external signal the house received, with end-to-end pipeline detail behind each row."
        aside={<LiveStatusBadge latestReceivedAt={latestReceivedAt} />}
      />
      <IngestionSubNav />
      <DispatchSurface>
        <TimelineTab isActive={true} onFreshnessChange={handleFreshnessChange} />
      </DispatchSurface>
    </DispatchLayout>
  )
}
