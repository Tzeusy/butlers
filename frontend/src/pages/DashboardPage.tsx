import { Link } from "react-router";

import { NotificationFeed } from "@/components/notifications/notification-feed";
import { NotificationTableSkeleton } from "@/components/skeletons";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useNotifications } from "@/hooks/use-notifications";

export default function DashboardPage() {
  const {
    data: failedResponse,
    isLoading: failedLoading,
  } = useNotifications({ status: "failed", limit: 5 });

  const failedNotifications = failedResponse?.data ?? [];
  const failedTotal = failedResponse?.meta.total ?? 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>

      {/* Failed Notifications / Issues Panel */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Failed Notifications
            {!failedLoading && failedTotal > 0 && (
              <Badge variant="destructive">{failedTotal}</Badge>
            )}
          </CardTitle>
          <CardDescription>
            Recent notification delivery failures across all butlers
          </CardDescription>
          <CardAction>
            <Button variant="link" size="sm" asChild>
              <Link to="/notifications">View all notifications</Link>
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent>
          {failedLoading ? (
            <NotificationTableSkeleton rows={5} />
          ) : failedNotifications.length === 0 ? (
            <div className="text-muted-foreground flex flex-col items-center justify-center py-8 text-sm">
              <p>No failed notifications. All systems healthy.</p>
            </div>
          ) : (
            <NotificationFeed
              notifications={failedNotifications}
              isLoading={false}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
