/**
 * CollectionsPage — grid of collection cards.
 *
 * Each card shows: name, description, entity count, created date.
 * Click navigates to the entities page filtered by that collection.
 */

import { useState } from "react";
import { format } from "date-fns";
import { useNavigate } from "react-router";

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
import { useCollections } from "@/hooks/use-general";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 24;

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SkeletonGrid({ count = 6 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }, (_, i) => (
        <Card key={i}>
          <CardHeader>
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-4 w-56 mt-1" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-4 w-24" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center rounded-md border border-dashed py-16">
      <p className="text-sm text-muted-foreground">No collections found.</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CollectionsPage
// ---------------------------------------------------------------------------

export default function CollectionsPage() {
  const [page, setPage] = useState(0);
  const params = { offset: page * PAGE_SIZE, limit: PAGE_SIZE };
  const { data, isLoading } = useCollections(params);
  const navigate = useNavigate();

  const collections = data?.data ?? [];
  const total = data?.meta?.total ?? 0;
  const hasMore = data?.meta?.has_more ?? false;

  const rangeStart = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const rangeEnd = Math.min((page + 1) * PAGE_SIZE, total);

  return (
    <div className="space-y-6">
      {/* Page heading */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Collections</h1>
        <p className="text-muted-foreground mt-1">
          Browse entity collections managed by the General butler.
        </p>
      </div>

      {/* Content */}
      {isLoading ? (
        <SkeletonGrid />
      ) : collections.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {collections.map((col) => (
            <Card
              key={col.id}
              className="cursor-pointer transition-colors hover:bg-accent/30"
              onClick={() => navigate(`/entities?collection=${col.id}`)}
            >
              <CardHeader>
                <CardTitle className="text-base">{col.name}</CardTitle>
                {col.description && (
                  <CardDescription className="line-clamp-2">
                    {col.description}
                  </CardDescription>
                )}
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <Badge variant="secondary">
                    {col.entity_count} {col.entity_count === 1 ? "entity" : "entities"}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {format(new Date(col.created_at), "MMM d, yyyy")}
                  </span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Pagination */}
      {total > 0 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Showing {rangeStart}–{rangeEnd} of {total.toLocaleString()}
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
