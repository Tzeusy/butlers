import { Link, useParams } from "react-router";

import TraceWaterfall from "@/components/traces/TraceWaterfall";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useTraceDetail } from "@/hooks/use-traces";
import { Breadcrumbs } from "@/components/ui/breadcrumbs";

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

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function DetailSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-64" />
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-32" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-24" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TraceDetailPage
// ---------------------------------------------------------------------------

export default function TraceDetailPage() {
  const { traceId = "" } = useParams<{ traceId: string }>();

  const { data: response, isLoading, isError } = useTraceDetail(traceId || null);
  const trace = response?.data;

  if (!traceId) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold tracking-tight">Trace Detail</h1>
        <Card>
          <CardContent>
            <p className="text-muted-foreground py-12 text-center text-sm">
              No trace ID provided.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (isLoading) {
    return <DetailSkeleton />;
  }

  if (isError || !trace) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="outline" size="sm" asChild>
            <Link to="/traces">Back to traces</Link>
          </Button>
          <h1 className="text-2xl font-bold tracking-tight">Trace Detail</h1>
        </div>
        <Card>
          <CardContent>
            <p className="text-destructive py-12 text-center text-sm">
              Failed to load trace details. The trace may not exist.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <Breadcrumbs items={[{ label: "Traces", href: "/traces" }, { label: traceId.slice(0, 8) }]} />
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold tracking-tight">Trace Detail</h1>
        {statusBadge(trace.status)}
      </div>

      {/* Trace metadata */}
      <Card>
        <CardHeader>
          <CardTitle>Metadata</CardTitle>
          <CardDescription>
            <code className="text-xs">{trace.trace_id}</code>
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 text-sm">
            <dt className="text-muted-foreground font-medium">Trace ID</dt>
            <dd className="font-mono text-xs">{trace.trace_id}</dd>

            <dt className="text-muted-foreground font-medium">Root Butler</dt>
            <dd>
              <Link
                to={`/butlers/${encodeURIComponent(trace.root_butler)}`}
                className="text-primary underline-offset-4 hover:underline"
              >
                {trace.root_butler}
              </Link>
            </dd>

            <dt className="text-muted-foreground font-medium">Span Count</dt>
            <dd>{trace.span_count}</dd>

            <dt className="text-muted-foreground font-medium">Status</dt>
            <dd>{statusBadge(trace.status)}</dd>

            <dt className="text-muted-foreground font-medium">Total Duration</dt>
            <dd className="tabular-nums">{formatDuration(trace.total_duration_ms)}</dd>

            <dt className="text-muted-foreground font-medium">Started</dt>
            <dd>{formatTimestamp(trace.started_at)}</dd>
          </dl>
        </CardContent>
      </Card>

      {/* Waterfall timeline */}
      <Card>
        <CardHeader>
          <CardTitle>Span Timeline</CardTitle>
          <CardDescription>
            Waterfall view of {trace.span_count} span{trace.span_count !== 1 ? "s" : ""}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <TraceWaterfall
            spans={trace.spans}
            totalDurationMs={trace.total_duration_ms ?? 0}
          />
        </CardContent>
      </Card>
    </div>
  );
}
