import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface CardSkeletonProps {
  /** Whether to show a header with title and description placeholders. @default true */
  showHeader?: boolean;
  /** Number of content lines to render. @default 3 */
  lines?: number;
}

/**
 * Skeleton loader for generic card content.
 *
 * Renders a card with optional header placeholders and a configurable number
 * of content line placeholders.
 */
export function CardSkeleton({ showHeader = true, lines = 3 }: CardSkeletonProps) {
  return (
    <Card>
      {showHeader && (
        <CardHeader>
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-64" />
        </CardHeader>
      )}
      <CardContent className="space-y-3">
        {Array.from({ length: lines }, (_, i) => (
          <Skeleton
            key={i}
            className={`h-4 ${i === lines - 1 ? "w-3/4" : "w-full"}`}
          />
        ))}
      </CardContent>
    </Card>
  );
}
