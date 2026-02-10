import { Link } from "react-router";

import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";

interface CostWidgetProps {
  totalCostUsd: number;
  topButler: string | null;
  topButlerCost: number;
  isLoading?: boolean;
}

function formatCurrency(amount: number): string {
  if (amount < 0.01) return "$0.00";
  return `$${amount.toFixed(2)}`;
}

export default function CostWidget({
  totalCostUsd,
  topButler,
  topButlerCost,
  isLoading,
}: CostWidgetProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Cost Today</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-16 animate-pulse rounded bg-muted" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">Cost Today</CardTitle>
        <Button variant="ghost" size="sm" asChild>
          <Link to="/costs">View all</Link>
        </Button>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{formatCurrency(totalCostUsd)}</div>
        {topButler && (
          <p className="mt-1 text-xs text-muted-foreground">
            Top: {topButler} ({formatCurrency(topButlerCost)})
          </p>
        )}
        {/* Sparkline placeholder — will be replaced with Recharts */}
        <div className="mt-3 flex h-8 items-end gap-0.5">
          {Array.from({ length: 7 }).map((_, i) => (
            <div
              key={i}
              className="flex-1 rounded-sm bg-muted"
              style={{ height: `${20 + Math.random() * 80}%` }}
            />
          ))}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">7-day trend</p>
      </CardContent>
    </Card>
  );
}
