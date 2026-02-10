import { useState } from "react";
import { useNavigate } from "react-router";

import type { TraceSummary } from "@/api/types";
import TraceList from "@/components/traces/TraceList";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useTraces } from "@/hooks/use-traces";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 20;

// ---------------------------------------------------------------------------
// TracesPage
// ---------------------------------------------------------------------------

export default function TracesPage() {
  const [page, setPage] = useState(0);
  const navigate = useNavigate();

  const { data: response, isLoading } = useTraces({
    offset: page * PAGE_SIZE,
    limit: PAGE_SIZE,
  });

  const traces = response?.data ?? [];
  const meta = response?.meta;
  const total = meta?.total ?? 0;
  const hasMore = meta?.has_more ?? false;

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = page + 1;

  function handleTraceClick(trace: TraceSummary) {
    navigate(`/traces/${encodeURIComponent(trace.trace_id)}`);
  }

  return (
    <div className="space-y-6">
      {/* Page heading */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Traces</h1>
        <p className="text-muted-foreground mt-1">
          Distributed traces across butler sessions.
        </p>
      </div>

      {/* Trace table */}
      <Card>
        <CardContent>
          <TraceList
            traces={traces}
            isLoading={isLoading}
            onTraceClick={handleTraceClick}
          />
        </CardContent>
      </Card>

      {/* Pagination controls */}
      {total > 0 && (
        <div className="flex items-center justify-between">
          <p className="text-muted-foreground text-sm">
            Page {currentPage} of {totalPages}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!hasMore}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
