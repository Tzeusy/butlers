import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import type { NotificationStats } from "@/api/types"
import { Bell, CheckCircle, XCircle, Percent } from "lucide-react"

interface NotificationStatsBarProps {
  stats: NotificationStats | undefined
  isLoading?: boolean
}

function StatCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <Skeleton className="h-4 w-24" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-8 w-16" />
      </CardContent>
    </Card>
  )
}

export function NotificationStatsBar({ stats, isLoading }: NotificationStatsBarProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
      </div>
    )
  }

  const total = stats?.total ?? 0
  const sent = stats?.sent ?? 0
  const failed = stats?.failed ?? 0
  const failureRate = total > 0 ? ((failed / total) * 100).toFixed(1) : "0.0"
  const channels = stats?.by_channel ?? {}

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {/* Total Notifications */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Notifications
            </CardTitle>
            <Bell className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{total.toLocaleString()}</div>
          </CardContent>
        </Card>

        {/* Sent */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Sent</CardTitle>
            <CheckCircle className="h-4 w-4 text-emerald-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
              {sent.toLocaleString()}
            </div>
          </CardContent>
        </Card>

        {/* Failed */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Failed</CardTitle>
            <XCircle className="h-4 w-4 text-red-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600 dark:text-red-400">
              {failed.toLocaleString()}
            </div>
          </CardContent>
        </Card>

        {/* Failure Rate */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Failure Rate
            </CardTitle>
            <Percent className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div
              className={`text-2xl font-bold ${
                Number(failureRate) > 10
                  ? "text-red-600 dark:text-red-400"
                  : Number(failureRate) > 0
                    ? "text-amber-600 dark:text-amber-400"
                    : "text-emerald-600 dark:text-emerald-400"
              }`}
            >
              {failureRate}%
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Per-channel breakdown */}
      {Object.keys(channels).length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-muted-foreground">By channel:</span>
          {Object.entries(channels).map(([channel, count]) => (
            <Badge key={channel} variant="secondary">
              {channel}: {count.toLocaleString()}
            </Badge>
          ))}
        </div>
      )}
    </div>
  )
}
