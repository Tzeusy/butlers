import { Link } from "react-router";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useSessionDetail, useButlerSessionDetail } from "@/hooks/use-sessions";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface SessionDetailDrawerProps {
  /** Butler name — if provided, uses butler-scoped endpoint. */
  butler?: string;
  /** The session ID to display. */
  sessionId: string | null;
  /** Callback to close the drawer. */
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(ms: number | null): string {
  if (ms == null) return "--";
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return "--";
  return new Date(iso).toLocaleString();
}

function formatTokens(n: number | null): string {
  if (n == null) return "--";
  return n.toLocaleString();
}

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

// ---------------------------------------------------------------------------
// Drawer content (uses butler-scoped or cross-butler hook)
// ---------------------------------------------------------------------------

function DrawerBody({ butler, sessionId }: { butler?: string; sessionId: string }) {
  // Use butler-scoped endpoint when a butler name is provided
  const butlerQuery = useButlerSessionDetail(butler ?? "", sessionId);
  const globalQuery = useSessionDetail(butler ? "" : sessionId);
  const { data: response, isLoading, isError } = butler ? butlerQuery : globalQuery;
  const session = response?.data;

  if (isLoading) {
    return (
      <div className="space-y-4 p-4">
        <Skeleton className="h-5 w-24" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  if (isError || !session) {
    return (
      <div className="p-4 text-sm text-destructive">
        Failed to load session details.
      </div>
    );
  }

  return (
    <div className="space-y-6 p-4">
      {/* Status & ID */}
      <div className="flex items-center gap-3">
        {statusBadge(session.success)}
        <code className="text-muted-foreground text-xs">{session.id}</code>
      </div>

      {/* Metadata grid */}
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        <dt className="text-muted-foreground font-medium">Trigger</dt>
        <dd><Badge variant="secondary">{session.trigger_source}</Badge></dd>

        <dt className="text-muted-foreground font-medium">Started</dt>
        <dd>{formatTimestamp(session.started_at)}</dd>

        <dt className="text-muted-foreground font-medium">Completed</dt>
        <dd>{formatTimestamp(session.completed_at)}</dd>

        <dt className="text-muted-foreground font-medium">Duration</dt>
        <dd>{formatDuration(session.duration_ms)}</dd>

        {session.model && (
          <>
            <dt className="text-muted-foreground font-medium">Model</dt>
            <dd>{session.model}</dd>
          </>
        )}

        {session.tool_calls != null && (
          <>
            <dt className="text-muted-foreground font-medium">Tool Calls</dt>
            <dd>{session.tool_calls}</dd>
          </>
        )}

        {(session.input_tokens != null || session.output_tokens != null) && (
          <>
            <dt className="text-muted-foreground font-medium">Tokens (in/out)</dt>
            <dd>
              {formatTokens(session.input_tokens)} / {formatTokens(session.output_tokens)}
            </dd>
          </>
        )}
      </dl>

      {/* Prompt */}
      <div>
        <h4 className="mb-2 text-sm font-medium">Prompt</h4>
        <pre className="overflow-auto rounded-md bg-muted p-3 text-xs font-mono whitespace-pre-wrap">
          {session.prompt}
        </pre>
      </div>

      {/* Result */}
      {session.result && (
        <div>
          <h4 className="mb-2 text-sm font-medium">Result</h4>
          <pre className="overflow-auto rounded-md bg-muted p-3 text-xs font-mono whitespace-pre-wrap">
            {session.result}
          </pre>
        </div>
      )}

      {/* Error */}
      {session.error && (
        <div>
          <h4 className="mb-2 text-sm font-medium text-destructive">Error</h4>
          <pre className="overflow-auto rounded-md bg-destructive/10 p-3 text-xs font-mono whitespace-pre-wrap text-destructive">
            {session.error}
          </pre>
        </div>
      )}

      {/* Link to full page */}
      <Button variant="outline" size="sm" asChild>
        <Link to={`/sessions/${encodeURIComponent(session.id)}${butler ? `?butler=${encodeURIComponent(butler)}` : ""}`}>
          Open full page
        </Link>
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SessionDetailDrawer
// ---------------------------------------------------------------------------

export default function SessionDetailDrawer({
  butler,
  sessionId,
  onClose,
}: SessionDetailDrawerProps) {
  return (
    <Sheet open={sessionId != null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-lg overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Session Detail</SheetTitle>
          <SheetDescription>
            {sessionId ? `Session ${sessionId.slice(0, 8)}...` : ""}
          </SheetDescription>
        </SheetHeader>
        {sessionId && <DrawerBody butler={butler} sessionId={sessionId} />}
      </SheetContent>
    </Sheet>
  );
}
