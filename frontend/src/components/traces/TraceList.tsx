import { EmptyState as EmptyStateUI } from "@/components/ui/empty-state";
import { formatDistanceToNow, format } from "date-fns";

import type { TraceSummary } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface TraceListProps {
  traces: TraceSummary[];
  isLoading: boolean;
  onTraceClick?: (trace: TraceSummary) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format an ISO timestamp as relative ("2h ago") or absolute ("Feb 10, 2:30 PM"). */
function formatTimestamp(iso: string): { relative: string; absolute: string } {
  const date = new Date(iso);
  const relative = formatDistanceToNow(date, { addSuffix: true });
  const absolute = format(date, "MMM d, h:mm a");
  return { relative, absolute };
}

/** Format duration_ms to a human-friendly string. */
function formatDuration(ms: number | null): string {
  if (ms == null) return "\u2014";
  if (ms < 1000) return `${ms}ms`;
  const totalSeconds = Math.floor(ms / 1000);
  const frac = ms / 1000;
  if (totalSeconds < 60) {
    return frac % 1 === 0 ? `${totalSeconds}s` : `${frac.toFixed(1)}s`;
  }
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;
}

/** Truncate a trace_id to a shorter display form. */
function truncateId(id: string, max = 12): string {
  if (id.length <= max) return id;
  return id.slice(0, max) + "\u2026";
}

/** Map trace status to a color-coded badge. */
function statusBadge(status: string) {
  switch (status) {
    case "success":
      return (
        <Badge className="bg-emerald-600 text-white hover:bg-emerald-600/90">
          Success
        </Badge>
      );
    case "failed":
      return <Badge variant="destructive">Failed</Badge>;
    case "running":
      return (
        <Badge variant="outline" className="border-blue-500 text-blue-600">
          Running
        </Badge>
      );
    case "partial":
      return (
        <Badge variant="outline" className="border-amber-500 text-amber-600">
          Partial
        </Badge>
      );
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

/** Deterministic color for butler badges. */
const BUTLER_COLORS = [
  "bg-blue-600",
  "bg-violet-600",
  "bg-amber-600",
  "bg-teal-600",
  "bg-rose-600",
  "bg-indigo-600",
  "bg-cyan-600",
  "bg-orange-600",
];

function butlerBadge(name: string) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) | 0;
  }
  const color = BUTLER_COLORS[Math.abs(hash) % BUTLER_COLORS.length];
  return (
    <Badge className={cn(color, "text-white hover:opacity-90")}>
      {name}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Skeleton rows
// ---------------------------------------------------------------------------

function SkeletonRows({ count = 5 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <TableRow key={i}>
          <TableCell><Skeleton className="h-4 w-24" /></TableCell>
          <TableCell><Skeleton className="h-4 w-16" /></TableCell>
          <TableCell><Skeleton className="h-4 w-10" /></TableCell>
          <TableCell><Skeleton className="h-4 w-14" /></TableCell>
          <TableCell><Skeleton className="h-4 w-16" /></TableCell>
          <TableCell><Skeleton className="h-4 w-20" /></TableCell>
        </TableRow>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <EmptyStateUI
      title="No traces found"
      description="Distributed traces will appear here when butlers span cross-service operations."
    />
  );
}

// ---------------------------------------------------------------------------
// TraceList
// ---------------------------------------------------------------------------

export default function TraceList({
  traces,
  isLoading,
  onTraceClick,
}: TraceListProps) {
  if (!isLoading && traces.length === 0) {
    return <EmptyState />;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Trace ID</TableHead>
          <TableHead>Root Butler</TableHead>
          <TableHead>Spans</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Duration</TableHead>
          <TableHead>Started</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {isLoading ? (
          <SkeletonRows />
        ) : (
          traces.map((trace) => {
            const ts = formatTimestamp(trace.started_at);
            return (
              <TableRow
                key={trace.trace_id}
                className={cn(
                  trace.status === "failed" && "bg-destructive/5",
                  onTraceClick && "cursor-pointer",
                )}
                onClick={() => onTraceClick?.(trace)}
              >
                <TableCell
                  className="font-mono text-xs"
                  title={trace.trace_id}
                >
                  {truncateId(trace.trace_id)}
                </TableCell>
                <TableCell>{butlerBadge(trace.root_butler)}</TableCell>
                <TableCell className="tabular-nums text-xs text-muted-foreground">
                  {trace.span_count}
                </TableCell>
                <TableCell>{statusBadge(trace.status)}</TableCell>
                <TableCell className="tabular-nums text-xs text-muted-foreground">
                  {formatDuration(trace.total_duration_ms)}
                </TableCell>
                <TableCell
                  className="text-muted-foreground text-xs"
                  title={ts.absolute}
                >
                  {ts.relative}
                </TableCell>
              </TableRow>
            );
          })
        )}
      </TableBody>
    </Table>
  );
}
