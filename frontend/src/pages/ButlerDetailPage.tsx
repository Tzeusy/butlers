import { lazy, Suspense } from "react";
import { Link, useParams, useSearchParams } from "react-router";

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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useButlerNotifications } from "@/hooks/use-notifications";

const ButlerSkillsTab = lazy(
  () => import("@/components/butler-detail/ButlerSkillsTab.tsx"),
);
const ButlerTriggerTab = lazy(
  () => import("@/components/butler-detail/ButlerTriggerTab.tsx"),
);

const TABS = ["overview", "sessions", "config", "skills", "trigger"] as const;
type TabValue = (typeof TABS)[number];

function isValidTab(value: string | null): value is TabValue {
  return TABS.includes(value as TabValue);
}

export default function ButlerDetailPage() {
  const { name = "" } = useParams<{ name: string }>();
  const [searchParams, setSearchParams] = useSearchParams();

  const tabParam = searchParams.get("tab");
  const activeTab: TabValue = isValidTab(tabParam) ? tabParam : "overview";

  const {
    data: notificationsResponse,
    isLoading: notificationsLoading,
  } = useButlerNotifications(name, { limit: 5 });

  const notifications = notificationsResponse?.data ?? [];

  function handleTabChange(value: string) {
    if (value === "overview") {
      // Remove tab param for the default tab to keep URLs clean
      setSearchParams({}, { replace: true });
    } else {
      setSearchParams({ tab: value }, { replace: true });
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">{name}</h1>

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="sessions">Sessions</TabsTrigger>
          <TabsTrigger value="config">Config</TabsTrigger>
          <TabsTrigger value="skills">Skills</TabsTrigger>
          <TabsTrigger value="trigger">Trigger</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <div className="space-y-6">
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
        </TabsContent>

        <TabsContent value="sessions">
          <Card>
            <CardHeader>
              <CardTitle>Sessions</CardTitle>
              <CardDescription>Session history for this butler</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-muted-foreground flex items-center justify-center py-12 text-sm">
                Coming soon
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="config">
          <Card>
            <CardHeader>
              <CardTitle>Configuration</CardTitle>
              <CardDescription>Butler configuration and settings</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-muted-foreground flex items-center justify-center py-12 text-sm">
                Coming soon
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="skills">
          <Suspense
            fallback={
              <div className="text-muted-foreground flex items-center justify-center py-12 text-sm">
                Loading skills...
              </div>
            }
          >
            <ButlerSkillsTab butlerName={name} />
          </Suspense>
        </TabsContent>

        <TabsContent value="trigger">
          <Suspense
            fallback={
              <div className="text-muted-foreground flex items-center justify-center py-12 text-sm">
                Loading trigger...
              </div>
            }
          >
            <ButlerTriggerTab butlerName={name} />
          </Suspense>
        </TabsContent>
      </Tabs>
    </div>
  );
}
