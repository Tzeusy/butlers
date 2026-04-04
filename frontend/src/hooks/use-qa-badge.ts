/**
 * Provides live badge counts for QA nav items.
 *
 * Returns a map from badgeKey → count so the Sidebar can render
 * badge indicators without needing to know about QA specifics.
 */

import { useQaKnownIssues } from './use-qa'

/** Returns the count of active (non-dismissed) QA known issues for the sidebar badge. */
export function useQaActiveBadge(): number {
  const { data } = useQaKnownIssues({ dismissed: false, limit: 1 })
  return data?.meta.total ?? 0
}

/** Badge registry — maps badgeKey to a hook that returns a count (or 0). */
export function useBadgeCounts(): Record<string, number> {
  const qaActive = useQaActiveBadge()
  return {
    'qa-active-investigations': qaActive,
  }
}
