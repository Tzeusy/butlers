/**
 * ButlerCollectionsTab — Collections tab for the General butler detail page.
 *
 * Shows a grid of collection cards with entity counts.
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

const PAGE_SIZE = 12;

// ---------------------------------------------------------------------------
// ButlerCollectionsTab
// ---------------------------------------------------------------------------

export default function ButlerCollectionsTab() {
  const [page, setPage] = useState(0);
  const params = { offset: page * PAGE_SIZE, limit: PAGE_SIZE };
  const { data, isLoading } = useCollections(params);
  const navigate = useNavigate();

  const collections = data?.data ?? [];
  const total = data?.meta?.total ?? 0;
  const hasMore = data?.meta?.has_more ?? false;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Collections</CardTitle>
          <CardDescription>
            Entity collections managed by this butler
            {total > 0 && ` (${total})`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }, (_, i) => (
                <Card key={i}>
                  <CardHeader>
                    <Skeleton className="h-5 w-40" />
                    <Skeleton className="mt-1 h-4 w-56" />
                  </CardHeader>
                  <CardContent>
                    <Skeleton className="h-4 w-24" />
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : collections.length === 0 ? (
            <div className="flex items-center justify-center rounded-md border border-dashed py-12">
              <p className="text-sm text-muted-foreground">No collections found.</p>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {collections.map((col) => (
                <Card
                  key={col.id}
                  className="cursor-pointer transition-colors hover:bg-accent/30"
                  onClick={() => navigate(`/entities?collection=${col.id}`)}
                >
                  <CardHeader className="pb-2">
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
                        {col.entity_count}{" "}
                        {col.entity_count === 1 ? "entity" : "entities"}
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
        </CardContent>
      </Card>

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Page {page + 1} of {Math.ceil(total / PAGE_SIZE)}
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
