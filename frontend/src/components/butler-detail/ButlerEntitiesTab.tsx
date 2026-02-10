/**
 * ButlerEntitiesTab — Entities tab for the General butler detail page.
 *
 * Wraps the EntityBrowser component with local state management.
 */

import { useMemo, useState } from "react";

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

const PAGE_SIZE = 25;

// ---------------------------------------------------------------------------
// ButlerEntitiesTab
// ---------------------------------------------------------------------------

export default function ButlerEntitiesTab() {
  const [search, setSearch] = useState("");
  const [activeCollection, setActiveCollection] = useState("");
  const [activeTag, setActiveTag] = useState("");
  const [page, setPage] = useState(0);

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

  const availableTags = useMemo(() => {
    const tagSet = new Set<string>();
    entities.forEach((e) => e.tags.forEach((t) => tagSet.add(t)));
    return Array.from(tagSet).sort();
  }, [entities]);

  function handleSearchChange(value: string) {
    setSearch(value);
    setPage(0);
  }

  function handleCollectionFilter(id: string) {
    setActiveCollection(id === "__all__" ? "" : id);
    setPage(0);
  }

  function handleTagFilter(tag: string) {
    setActiveTag(tag === "__all__" ? "" : tag);
    setPage(0);
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Entities</CardTitle>
          <CardDescription>
            {total > 0
              ? `${total.toLocaleString()} entit${total !== 1 ? "ies" : "y"}`
              : "Browse entities stored by this butler"}
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
            Page {page + 1} of {Math.max(1, Math.ceil(total / PAGE_SIZE))}
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
