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
import type { SessionSummary } from "@/api/types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface SessionTableProps {
  sessions: SessionSummary[];
  isLoading: boolean;
  onSessionClick?: (session: SessionSummary) => void;
  showButlerColumn?: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format a duration in milliseconds to a human-readable string. */
function formatDuration(ms: number | null): string {
  if (ms == null) return "--";
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}

/** Format an ISO datetime string to a short local format. */
function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Render a status badge from the session success field. */
function statusBadge(success: boolean | null) {
  if (success === true) {
    return (
      <Badge className="bg-emerald-600 text-white hover:bg-emerald-600/90">
        Success
      </Badge>
    );
  }
  if (success === false) {
    return <Badge variant="destructive">Failed</Badge>;
  }
  return (
    <Badge variant="outline" className="border-amber-500 text-amber-600">
      Running
    </Badge>
  );
}

/** Truncate a string to a maximum length. */
function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + "...";
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function SessionTableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Status</TableHead>
          <TableHead>Prompt</TableHead>
          <TableHead>Trigger</TableHead>
          <TableHead>Started</TableHead>
          <TableHead>Duration</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {Array.from({ length: rows }).map((_, i) => (
          <TableRow key={i}>
            <TableCell><Skeleton className="h-5 w-16 rounded-full" /></TableCell>
            <TableCell><Skeleton className="h-4 w-48" /></TableCell>
            <TableCell><Skeleton className="h-4 w-20" /></TableCell>
            <TableCell><Skeleton className="h-4 w-28" /></TableCell>
            <TableCell><Skeleton className="h-4 w-16" /></TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

// ---------------------------------------------------------------------------
// SessionTable
// ---------------------------------------------------------------------------

export default function SessionTable({
  sessions,
  isLoading,
  onSessionClick,
  showButlerColumn = true,
}: SessionTableProps) {
  if (isLoading) {
    return <SessionTableSkeleton />;
  }

  if (sessions.length === 0) {
    return (
      <div className="text-muted-foreground flex items-center justify-center py-12 text-sm">
        No sessions found
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Status</TableHead>
          <TableHead>Prompt</TableHead>
          <TableHead>Trigger</TableHead>
          {showButlerColumn && <TableHead>Butler</TableHead>}
          <TableHead>Started</TableHead>
          <TableHead>Duration</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sessions.map((session) => (
          <TableRow
            key={session.id}
            className={onSessionClick ? "cursor-pointer" : ""}
            onClick={() => onSessionClick?.(session)}
          >
            <TableCell>{statusBadge(session.success)}</TableCell>
            <TableCell className="max-w-xs">
              <span title={session.prompt}>{truncate(session.prompt, 80)}</span>
            </TableCell>
            <TableCell>
              <Badge variant="secondary">{session.trigger_source}</Badge>
            </TableCell>
            {showButlerColumn && (
              <TableCell className="text-muted-foreground">
                {/* Butler name not in SessionSummary — shown via context */}
                --
              </TableCell>
            )}
            <TableCell className="text-muted-foreground">
              {formatTimestamp(session.started_at)}
            </TableCell>
            <TableCell className="text-muted-foreground">
              {formatDuration(session.duration_ms)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
