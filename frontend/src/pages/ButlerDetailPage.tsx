import { Link, useParams } from "react-router";

import { NotificationFeed } from "@/components/notifications/notification-feed";
import { NotificationTableSkeleton } from "@/components/skeletons";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useButlerNotifications } from "@/hooks/use-notifications";

export default function ButlerDetailPage() {
  const { name = "" } = useParams<{ name: string }>();

  const {
    data: notificationsResponse,
    isLoading: notificationsLoading,
  } = useButlerNotifications(name, { limit: 5 });

  const notifications = notificationsResponse?.data ?? [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Butler: {name}</h1>

      {/* Recent Notifications */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Notifications</CardTitle>
          <CardDescription>
            Last {notifications.length || 5} notifications from this butler
          </CardDescription>
          <CardAction>
            <Button variant="link" size="sm" asChild>
              <Link to={`/notifications?butler=${encodeURIComponent(name)}`}>
                View all
              </Link>
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent>
          {notificationsLoading ? (
            <NotificationTableSkeleton rows={5} />
          ) : (
            <NotificationFeed
              notifications={notifications}
              isLoading={false}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
