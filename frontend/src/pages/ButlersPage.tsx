// ---------------------------------------------------------------------------
// ButlersPage — status-board rewrite (bu-hb7dh.8)
//
// Replaces the alphabetical row-list layout with the 4-column status-board
// grid introduced by the bu-hb7dh epic. All upstream primitives are on main:
//   - Page archetype='status-board' with header/footer slots (PR #1526)
//   - useButlerStatusBoard hook (PR #1528)
//   - StatusBoardCell component (PR #1532)
//   - BoardHeader + BoardFooter chrome (PR #1531)
//
// Patterns preserved from the old page:
//   - Stale-data banner when the query is in error but cached rows exist.
//   - Empty state via the Page primitive's `empty` slot.
//   - Full-page error (no cached data) via Page primitive's `error` prop.
//   - Loading state delegated to the Page primitive skeleton.
//   - onRestore wired to useSetEligibility mutation.
//
// Restore-with-reason-and-undo (JARVIS audit move 6, bu-86c4c.15): the
// StatusBoardCell chip already surfaces the quarantine_reason as its title
// (bu-86c4c.3) and IS the "Restore" button — what was missing was the undo
// half. Restoring a quarantined butler is a real, consequential action (it
// starts running again), so a click doesn't fire the mutation instantly; it
// schedules it RESTORE_UNDO_WINDOW_MS out and offers an "Undo" toast action,
// mirroring the scheduled-decision pattern ApprovalsPage established for its
// a/d/x keyboard verbs (bu-86c4c.14). Nothing reaches the backend unless the
// window elapses without an undo.
// ---------------------------------------------------------------------------

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Card, CardContent } from "@/components/ui/card";
import { Page } from "@/components/ui/page";
import { BoardFooter } from "@/components/butlers/BoardFooter";
import { BoardHeader } from "@/components/butlers/BoardHeader";
import { NeedsYouStrip } from "@/components/butlers/NeedsYouStrip";
import { StatusBoardCell } from "@/components/butlers/StatusBoardCell";
import { useButlerStatusBoard } from "@/hooks/use-butler-status-board";
import { useSetEligibility } from "@/hooks/use-general";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Polling interval forwarded to BoardHeader's refresh caption. */
const REFRESH_INTERVAL_MS = 30_000;

/**
 * How long an owner has to undo a restore before it actually fires
 * (matches ApprovalsPage's UNDO_WINDOW_MS convention, bu-86c4c.14).
 */
const RESTORE_UNDO_WINDOW_MS = 5_000;

// ---------------------------------------------------------------------------
// ButlersPage
// ---------------------------------------------------------------------------

export default function ButlersPage() {
  const { rows, aggregates, needsYou } = useButlerStatusBoard();
  const setEligibility = useSetEligibility();

  const { isLoading, isError, error, refetch } = aggregates;
  const hasRows = rows.length > 0;

  // Full-page error only when there is no cached data to show.
  const pageError = isError && !hasRows ? error : null;

  // Stale-data banner: last refetch errored but cached rows are still visible.
  // We key off `error != null && hasRows` rather than `isError && hasRows`
  // because the hook sets isError only when there is no cached data; when rows
  // survive from cache the error object is still populated but isError is false.
  const showStaleBanner = error != null && hasRows;

  // Butler names with a restore scheduled but not yet fired, each mapped to
  // its pending setTimeout id so an Undo click can cancel it.
  const [scheduledRestores, setScheduledRestores] = useState<Map<string, number>>(new Map());

  // Guards the setTimeout callback's own setState: the restore itself must
  // still fire on schedule even if the owner has navigated away in the
  // meantime (an undo window is a chance to CANCEL, not a reason to silently
  // drop an already-committed restore), but React state on an unmounted
  // component would just warn -- skip that part once unmounted.
  const isMountedRef = useRef(true);
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const networkPendingName = setEligibility.isPending ? setEligibility.variables?.name : undefined;

  function fireRestore(name: string) {
    setEligibility.mutate(
      { name, state: "active" },
      {
        onSuccess: () => toast.success(`${name} restored`),
        onError: (err) =>
          toast.error(`Failed to restore ${name}`, {
            description: err instanceof Error ? err.message : undefined,
          }),
      },
    );
  }

  function cancelScheduledRestore(name: string) {
    setScheduledRestores((prev) => {
      const timeoutId = prev.get(name);
      if (timeoutId === undefined) return prev;
      window.clearTimeout(timeoutId);
      const next = new Map(prev);
      next.delete(name);
      return next;
    });
  }

  function handleRestore(name: string) {
    if (scheduledRestores.has(name)) return; // already scheduled -- ignore repeat clicks

    const timeoutId = window.setTimeout(() => {
      if (isMountedRef.current) {
        setScheduledRestores((prev) => {
          const next = new Map(prev);
          next.delete(name);
          return next;
        });
      }
      fireRestore(name);
    }, RESTORE_UNDO_WINDOW_MS);

    setScheduledRestores((prev) => new Map(prev).set(name, timeoutId));

    toast(`Restoring ${name}`, {
      action: { label: "Undo", onClick: () => cancelScheduledRestore(name) },
      duration: RESTORE_UNDO_WINDOW_MS,
    });
  }

  return (
    <Page
      archetype="status-board"
      title="Butlers"
      loading={isLoading}
      error={pageError}
      onRetry={pageError != null ? () => void refetch() : undefined}
      empty={
        !isError && !hasRows && !isLoading
          ? { title: "No butlers found", description: "Check daemon status and try again." }
          : null
      }
      header={<BoardHeader aggregates={aggregates} refreshIntervalMs={REFRESH_INTERVAL_MS} />}
      footer={<BoardFooter aggregates={aggregates} />}
    >
      {/* Needs-you triage strip — leads with every butler that needs the owner
          (offline, quarantined, or overdue against its own cron cadence),
          collapsing to a single calm line when the fleet is fully healthy. */}
      {hasRows && <NeedsYouStrip rows={needsYou} total={aggregates.total} />}

      {/* Stale-data banner — shown above the grid when cached rows exist but the
          last refresh failed. Mirrors the pattern from the old ButlersPage. */}
      {showStaleBanner && (
        <Card>
          <CardContent className="py-4">
            <p className="text-sm text-destructive">
              Showing last known butler status. Refresh failed:{" "}
              {error instanceof Error ? error.message : "Unknown error"}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Status-board grid — 4 columns, each cell links to the butler detail page. */}
      {hasRows && (
        <div
          role="group"
          aria-label="Butler status board"
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 border-t border-l border-border/60"
        >
          {rows.map((row) => (
            <StatusBoardCell
              key={row.name}
              row={row}
              onRestore={handleRestore}
              isRestorePending={scheduledRestores.has(row.name) || networkPendingName === row.name}
            />
          ))}
        </div>
      )}
    </Page>
  );
}
