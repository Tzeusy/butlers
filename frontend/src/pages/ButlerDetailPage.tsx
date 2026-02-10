import { lazy, Suspense, useState } from "react";
import { useParams, useSearchParams } from "react-router";

import type { SessionParams, SessionSummary } from "@/api/types";
import ButlerConfigTab from "@/components/butler-detail/ButlerConfigTab";
import ButlerOverviewTab from "@/components/butler-detail/ButlerOverviewTab";
import SessionDetailDrawer from "@/components/sessions/SessionDetailDrawer";
import SessionTable from "@/components/sessions/SessionTable";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useButlerSessions } from "@/hooks/use-sessions";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ButlerSkillsTab = lazy(
  () => import("@/components/butler-detail/ButlerSkillsTab.tsx"),
);
const ButlerTriggerTab = lazy(
  () => import("@/components/butler-detail/ButlerTriggerTab.tsx"),
);

const TABS = ["overview", "sessions", "config", "skills", "trigger"] as const;
type TabValue = (typeof TABS)[number];

const PAGE_SIZE = 20;

function isValidTab(value: string | null): value is TabValue {
  return TABS.includes(value as TabValue);
}

// ---------------------------------------------------------------------------
// Sessions Tab sub-component
// ---------------------------------------------------------------------------

function ButlerSessionsTab({ butlerName }: { butlerName: string }) {
  const [page, setPage] = useState(0);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

  const params: SessionParams = {
    offset: page * PAGE_SIZE,
    limit: PAGE_SIZE,
  };

  const { data: sessionsResponse, isLoading } = useButlerSessions(butlerName, params);
  const sessions = sessionsResponse?.data ?? [];
  const meta = sessionsResponse?.meta;
  const total = meta?.total ?? 0;
  const hasMore = meta?.has_more ?? false;

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = page + 1;

  function handleSessionClick(session: SessionSummary) {
    setSelectedSessionId(session.id);
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Sessions</CardTitle>
          <CardDescription>Session history for this butler</CardDescription>
        </CardHeader>
        <CardContent>
          <SessionTable
            sessions={sessions}
            isLoading={isLoading}
            onSessionClick={handleSessionClick}
            showButlerColumn={false}
          />
        </CardContent>
      </Card>

      {/* Pagination controls */}
      {total > 0 && (
        <div className="flex items-center justify-between">
          <p className="text-muted-foreground text-sm">
            Page {currentPage} of {totalPages}
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

      {/* Session detail drawer */}
      <SessionDetailDrawer
        butler={butlerName}
        sessionId={selectedSessionId}
        onClose={() => setSelectedSessionId(null)}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// ButlerDetailPage
// ---------------------------------------------------------------------------

export default function ButlerDetailPage() {
  const { name = "" } = useParams<{ name: string }>();
  const [searchParams, setSearchParams] = useSearchParams();

  const tabParam = searchParams.get("tab");
  const activeTab: TabValue = isValidTab(tabParam) ? tabParam : "overview";

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
          <ButlerOverviewTab butlerName={name} />
        </TabsContent>

        <TabsContent value="sessions">
          <ButlerSessionsTab butlerName={name} />
        </TabsContent>

        <TabsContent value="config">
          <ButlerConfigTab butlerName={name} />
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
