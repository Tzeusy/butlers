/**
 * EntityDetailPage — shows full entity detail with JsonViewer.
 *
 * Displays:
 * - Back link to entities
 * - Metadata card (collection, tags, dates)
 * - Full data via JsonViewer
 */

import { format } from "date-fns";
import { useParams } from "react-router";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import JsonViewer from "@/components/general/JsonViewer.tsx";
import { useEntity } from "@/hooks/use-general";
import { Breadcrumbs } from "@/components/ui/breadcrumbs";

// ---------------------------------------------------------------------------
// EntityDetailPage
// ---------------------------------------------------------------------------

export default function EntityDetailPage() {
  const { entityId } = useParams<{ entityId: string }>();
  const { data: response, isLoading, error } = useEntity(entityId ?? "");

  const entity = response?.data;

  return (
    <div className="space-y-6">
      {/* Breadcrumbs */}
      <Breadcrumbs
        items={[
          { label: "Entities", href: "/entities" },
          { label: entityId?.slice(0, 8) ?? "Entity" },
        ]}
      />

      {/* Loading */}
      {isLoading && (
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="text-destructive py-12 text-center text-sm">
          Failed to load entity. {(error as Error).message}
        </div>
      )}

      {/* Content */}
      {entity && (
        <div className="space-y-6">
          {/* Metadata card */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Entity Metadata</CardTitle>
              <CardDescription>ID: {entity.id}</CardDescription>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-4 sm:grid-cols-2">
                <div>
                  <dt className="text-sm font-medium text-muted-foreground">Collection</dt>
                  <dd className="mt-1">
                    <Badge variant="outline">
                      {entity.collection_name ?? entity.collection_id}
                    </Badge>
                  </dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-muted-foreground">Tags</dt>
                  <dd className="mt-1 flex flex-wrap gap-1">
                    {entity.tags.length > 0 ? (
                      entity.tags.map((tag) => (
                        <Badge key={tag} variant="secondary" className="text-xs">
                          {tag}
                        </Badge>
                      ))
                    ) : (
                      <span className="text-sm text-muted-foreground">{"\u2014"}</span>
                    )}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-muted-foreground">Created</dt>
                  <dd className="mt-1 text-sm">
                    {format(new Date(entity.created_at), "PPpp")}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-muted-foreground">Updated</dt>
                  <dd className="mt-1 text-sm">
                    {format(new Date(entity.updated_at), "PPpp")}
                  </dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          {/* Data card */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Data</CardTitle>
            </CardHeader>
            <CardContent>
              <JsonViewer data={entity.data} />
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
