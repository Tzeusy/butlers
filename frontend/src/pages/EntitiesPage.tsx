/**
 * EntitiesPage — full entity search page with EntityBrowser.
 *
 * Reads optional `collection` and `tag` query parameters from the URL
 * to support pre-filtered navigation from CollectionsPage.
 */

import { useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import type { EntityParams } from "@/api/types.ts";
import EntityBrowser from "@/components/general/EntityBrowser.tsx";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useCollections, useEntities } from "@/hooks/use-general";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 50;

// ---------------------------------------------------------------------------
// EntitiesPage
// ---------------------------------------------------------------------------

export default function EntitiesPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);

  // Read initial filters from URL query params
  const collectionFromUrl = searchParams.get("collection") ?? "";
  const tagFromUrl = searchParams.get("tag") ?? "";

  const [activeCollection, setActiveCollection] = useState(collectionFromUrl);
  const [activeTag, setActiveTag] = useState(tagFromUrl);

  const params: EntityParams = {
    q: search || undefined,
    collection: activeCollection || undefined,
    tag: activeTag || undefined,
    offset: page * PAGE_SIZE,
    limit: PAGE_SIZE,
  };

  const { data, isLoading } = useEntities(params);
  const { data: collectionsData } = useCollections({ limit: 100 });

  const entities = data?.data ?? [];
  const total = data?.meta?.total ?? 0;
  const hasMore = data?.meta?.has_more ?? false;

  const collections = collectionsData?.data ?? [];

  // Derive unique tags from the current entity set
  const availableTags = useMemo(() => {
    const tagSet = new Set<string>();
    entities.forEach((e) => e.tags.forEach((t) => tagSet.add(t)));
    return Array.from(tagSet).sort();
  }, [entities]);

  const rangeStart = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const rangeEnd = Math.min((page + 1) * PAGE_SIZE, total);

  function handleSearchChange(value: string) {
    setSearch(value);
    setPage(0);
  }

  function handleCollectionFilter(collectionId: string) {
    const actual = collectionId === "__all__" ? "" : collectionId;
    setActiveCollection(actual);
    setPage(0);
    // Update URL params
    const next = new URLSearchParams(searchParams);
    if (actual) {
      next.set("collection", actual);
    } else {
      next.delete("collection");
    }
    setSearchParams(next, { replace: true });
  }

  function handleTagFilter(tag: string) {
    const actual = tag === "__all__" ? "" : tag;
    setActiveTag(actual);
    setPage(0);
    const next = new URLSearchParams(searchParams);
    if (actual) {
      next.set("tag", actual);
    } else {
      next.delete("tag");
    }
    setSearchParams(next, { replace: true });
  }

  return (
    <div className="space-y-6">
      {/* Page heading */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Entities</h1>
        <p className="text-muted-foreground mt-1">
          Search and browse entities stored by the General butler.
        </p>
      </div>

      {/* Entity browser */}
      <Card>
        <CardHeader>
          <CardTitle>All Entities</CardTitle>
          <CardDescription>
            {total > 0
              ? `${total.toLocaleString()} entit${total !== 1 ? "ies" : "y"}`
              : ""}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <EntityBrowser
            entities={entities}
            isLoading={isLoading}
            search={search}
            onSearchChange={handleSearchChange}
            collections={collections}
            activeCollection={activeCollection}
            onCollectionFilter={handleCollectionFilter}
            activeTag={activeTag}
            onTagFilter={handleTagFilter}
            availableTags={availableTags}
          />
        </CardContent>
      </Card>

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
