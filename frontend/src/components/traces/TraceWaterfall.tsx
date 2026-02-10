import { useState } from "react";

import type { SpanNode } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface TraceWaterfallProps {
  spans: SpanNode[];
  /** Total trace duration in ms — used to scale span bar widths. */
  totalDurationMs: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

/** Format token count. */
function formatTokens(n: number | null): string {
  if (n == null) return "\u2014";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

/** Truncate text to a maximum length. */
function truncate(text: string, max = 80): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + "\u2026";
}

/** Get bar color class based on span status. */
function barColorClass(success: boolean | null): string {
  if (success === true) return "bg-emerald-500";
  if (success === false) return "bg-red-500";
  return "bg-blue-500";
}

/** Status label for span detail. */
function spanStatusBadge(success: boolean | null) {
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
    <Badge variant="outline" className="border-blue-500 text-blue-600">
      Running
    </Badge>
  );
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
    <Badge className={cn(color, "text-white hover:opacity-90 text-xs")}>
      {name}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// SpanRow — a single span bar with expandable details
// ---------------------------------------------------------------------------

interface SpanRowProps {
  span: SpanNode;
  depth: number;
  totalDurationMs: number;
  traceStartMs: number;
}

function SpanRow({ span, depth, totalDurationMs, traceStartMs }: SpanRowProps) {
  const [expanded, setExpanded] = useState(false);

  const spanStartMs = new Date(span.started_at).getTime();
  const offsetMs = spanStartMs - traceStartMs;
  const durationMs = span.duration_ms ?? 0;

  // Calculate bar position and width as percentages
  const leftPct =
    totalDurationMs > 0 ? Math.max(0, (offsetMs / totalDurationMs) * 100) : 0;
  const widthPct =
    totalDurationMs > 0
      ? Math.max(1, (durationMs / totalDurationMs) * 100) // min 1% for visibility
      : 100;

  const indentPx = depth * 24;

  return (
    <>
      {/* Main span row */}
      <div
        className={cn(
          "group flex items-center gap-2 border-b border-border py-1.5 px-2 cursor-pointer transition-colors hover:bg-accent/30",
          expanded && "bg-accent/20",
        )}
        onClick={() => setExpanded((v) => !v)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded((v) => !v);
          }
        }}
      >
        {/* Label section */}
        <div
          className="flex shrink-0 items-center gap-1.5 min-w-0"
          style={{ width: `clamp(120px, 30%, 280px)`, paddingLeft: `${indentPx}px` }}
        >
          <span className="text-muted-foreground text-xs select-none">
            {expanded ? "\u25BE" : "\u25B8"}
          </span>
          {butlerBadge(span.butler)}
          <span className="truncate text-xs text-muted-foreground" title={span.prompt}>
            {truncate(span.prompt, 30)}
          </span>
        </div>

        {/* Timeline bar section */}
        <div className="relative flex-1 h-5 min-w-0">
          <div className="absolute inset-0 rounded bg-muted/40" />
          <div
            className={cn("absolute top-0 h-full rounded", barColorClass(span.success))}
            style={{
              left: `${leftPct}%`,
              width: `${Math.min(widthPct, 100 - leftPct)}%`,
            }}
          />
        </div>

        {/* Duration label */}
        <span className="shrink-0 tabular-nums text-xs text-muted-foreground w-16 text-right">
          {formatDuration(span.duration_ms)}
        </span>
      </div>

      {/* Expanded detail panel */}
      {expanded && (
        <div
          className="border-b border-border bg-muted/20 px-4 py-3"
          style={{ paddingLeft: `${indentPx + 32}px` }}
        >
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs">
            <dt className="text-muted-foreground font-medium">Session ID</dt>
            <dd className="font-mono">{span.id}</dd>

            <dt className="text-muted-foreground font-medium">Butler</dt>
            <dd>{span.butler}</dd>

            <dt className="text-muted-foreground font-medium">Status</dt>
            <dd>{spanStatusBadge(span.success)}</dd>

            <dt className="text-muted-foreground font-medium">Trigger</dt>
            <dd>{span.trigger_source}</dd>

            <dt className="text-muted-foreground font-medium">Duration</dt>
            <dd className="tabular-nums">{formatDuration(span.duration_ms)}</dd>

            {span.model && (
              <>
                <dt className="text-muted-foreground font-medium">Model</dt>
                <dd>{span.model}</dd>
              </>
            )}

            {(span.input_tokens != null || span.output_tokens != null) && (
              <>
                <dt className="text-muted-foreground font-medium">Tokens (in/out)</dt>
                <dd className="tabular-nums">
                  {formatTokens(span.input_tokens)} / {formatTokens(span.output_tokens)}
                </dd>
              </>
            )}

            <dt className="text-muted-foreground font-medium">Prompt</dt>
            <dd className="whitespace-pre-wrap break-words">{span.prompt}</dd>
          </dl>
        </div>
      )}

      {/* Render children recursively */}
      {span.children.map((child) => (
        <SpanRow
          key={child.id}
          span={child}
          depth={depth + 1}
          totalDurationMs={totalDurationMs}
          traceStartMs={traceStartMs}
        />
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// TraceWaterfall
// ---------------------------------------------------------------------------

export default function TraceWaterfall({
  spans,
  totalDurationMs,
}: TraceWaterfallProps) {
  if (spans.length === 0) {
    return (
      <div className="text-muted-foreground flex flex-col items-center justify-center py-12 text-sm">
        <p>No spans in this trace.</p>
      </div>
    );
  }

  // Find the earliest span start time to use as the trace origin
  const traceStartMs = Math.min(
    ...spans.map((s) => new Date(s.started_at).getTime()),
  );

  return (
    <div className="rounded-md border border-border overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border bg-muted/50 px-2 py-1.5">
        <div
          className="shrink-0 text-xs font-medium text-muted-foreground"
          style={{ width: `clamp(120px, 30%, 280px)` }}
        >
          Span
        </div>
        <div className="flex-1 text-xs font-medium text-muted-foreground">
          Timeline
        </div>
        <div className="shrink-0 w-16 text-right text-xs font-medium text-muted-foreground">
          Duration
        </div>
      </div>

      {/* Span rows */}
      {spans.map((span) => (
        <SpanRow
          key={span.id}
          span={span}
          depth={0}
          totalDurationMs={totalDurationMs}
          traceStartMs={traceStartMs}
        />
      ))}
    </div>
  );
}
