/**
 * GoogleHealthStatusCard — connector status card for the settings page.
 *
 * Displays the Google Health connector state with:
 *   - Connection state pill (Healthy / Degraded / Error)
 *   - Last ingest timestamp (relative)
 *   - Token expiry estimate:
 *       · Test-mode accounts: computed countdown from last_token_refresh_at + 7 days
 *         (heuristic — Google OAuth test-mode tokens invalidate ~7 days after issue)
 *       · Production accounts: "Long-lived (production mode)"
 *       · Unknown (no last_token_refresh_at): "Unknown"
 *   - Refresh indicator: small spinner while React Query is re-fetching (30 s poll)
 *   - Test-mode banner variants (orange / red) per spec E4
 *
 * Frontend-only. No backend changes — data flows from GET /api/connectors/google-health/status.
 */

import { formatDistanceToNow } from "date-fns";
import { Loader2 } from "lucide-react";

import type { GoogleHealthStatusResponse } from "@/api/index.ts";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useGoogleHealthStatus } from "@/hooks/use-google-health";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/**
 * Heuristic token lifetime for Google OAuth test-mode clients.
 * Google invalidates refresh tokens ~7 days after issue in test mode.
 */
const TEST_MODE_TOKEN_LIFETIME_MS = 7 * 24 * 60 * 60 * 1000;

/**
 * Warning threshold: elevate banner to red when token age exceeds 5 d 6 h.
 * (7 days – 42 h grace margin = 5 d 6 h = 126 h)
 */
const TEST_MODE_WARN_AT_AGE_MS = (5 * 24 + 6) * 60 * 60 * 1000;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function stateBadgeVariant(
  state: GoogleHealthStatusResponse["state"],
): "default" | "secondary" | "destructive" | "outline" {
  switch (state) {
    case "healthy":
      return "default";
    case "degraded":
      return "secondary";
    case "error":
      return "destructive";
    default:
      return "outline";
  }
}

function stateBadgeLabel(state: GoogleHealthStatusResponse["state"]): string {
  switch (state) {
    case "healthy":
      return "Healthy";
    case "degraded":
      return "Degraded";
    case "error":
      return "Error";
    default:
      return state;
  }
}

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true });
  } catch {
    return iso;
  }
}

/**
 * Derive a human-readable token expiry estimate.
 *
 * - Test-mode: heuristic countdown = last_token_refresh_at + 7 days - now.
 *   If the computed expiry is in the past, returns "Expired".
 * - Production (test_mode=false): long-lived tokens, no countdown needed.
 * - Unknown (no last_token_refresh_at): render "Unknown".
 */
export function computeTokenExpiry(
  lastRefreshAt: string | null,
  testMode: boolean,
): string {
  if (!testMode) {
    return "Long-lived (production mode)";
  }
  if (!lastRefreshAt) {
    return "Unknown";
  }
  const refreshMs = new Date(lastRefreshAt).getTime();
  if (Number.isNaN(refreshMs)) {
    return "Unknown";
  }
  const expiryMs = refreshMs + TEST_MODE_TOKEN_LIFETIME_MS;
  const nowMs = Date.now();
  const remainingMs = expiryMs - nowMs;
  if (remainingMs <= 0) {
    return "Expired";
  }
  // Format as "Xd Yh" for readability
  const totalHours = Math.floor(remainingMs / (60 * 60 * 1000));
  const days = Math.floor(totalHours / 24);
  const hours = totalHours % 24;
  if (days > 0) {
    return `Expires in ~${days}d ${hours}h`;
  }
  return `Expires in ~${hours}h`;
}

/**
 * Returns true when a test-mode token is approaching expiry (age > 5d 6h).
 * Used to elevate the banner from orange to red.
 */
export function isTestModeTokenNearExpiry(lastRefreshAt: string | null): boolean {
  if (!lastRefreshAt) return false;
  const refreshMs = new Date(lastRefreshAt).getTime();
  if (Number.isNaN(refreshMs)) return false;
  return Date.now() - refreshMs > TEST_MODE_WARN_AT_AGE_MS;
}

// ---------------------------------------------------------------------------
// Test-mode banner
// ---------------------------------------------------------------------------

function TestModeBanner({
  lastRefreshAt,
}: {
  lastRefreshAt: string | null;
}) {
  const nearExpiry = isTestModeTokenNearExpiry(lastRefreshAt);

  if (nearExpiry) {
    return (
      <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
        <p className="font-medium">Google Health consent is about to expire</p>
        <p className="mt-1">
          Your Google Health consent is about to expire. Re-grant scopes to avoid an ingestion gap.{" "}
          <a
            href="/api/oauth/google/start?scope_set=health&force_consent=true"
            className="underline underline-offset-2"
          >
            Re-grant Health scopes
          </a>
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-orange-500/50 bg-orange-500/10 p-3 text-sm text-orange-700 dark:text-orange-400">
      <p className="font-medium">OAuth client in test mode</p>
      <p className="mt-1">
        This OAuth client is in Google&apos;s test mode. Your consent expires every 7 days until
        the production-mode verification completes. You may need to re-grant Google Health scopes
        periodically.{" "}
        <a
          href="https://support.google.com/cloud/answer/10311615"
          target="_blank"
          rel="noopener noreferrer"
          className="underline underline-offset-2"
        >
          Learn more
        </a>
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status rows
// ---------------------------------------------------------------------------

function StatusRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground min-w-[10rem]">{label}</span>
      <span>{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// GoogleHealthStatusCard
// ---------------------------------------------------------------------------

export function GoogleHealthStatusCard() {
  const statusQuery = useGoogleHealthStatus();
  const { data: status, isLoading, isError, isFetching } = statusQuery;

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Google Health</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (isError || !status) {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Google Health</CardTitle>
            <Badge variant="destructive">Unavailable</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-destructive">
            Failed to fetch Google Health connector status. Ensure the dashboard API is running.
          </p>
        </CardContent>
      </Card>
    );
  }

  const tokenExpiry = computeTokenExpiry(status.last_token_refresh_at, status.test_mode);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              Google Health
              {/* Refresh indicator: shown while React Query is re-fetching */}
              {isFetching && (
                <Loader2
                  className="h-3.5 w-3.5 animate-spin text-muted-foreground"
                  aria-label="Refreshing"
                />
              )}
            </CardTitle>
            <CardDescription className="mt-1">
              Sleep, activity, and health metrics connector
            </CardDescription>
          </div>
          <Badge variant={stateBadgeVariant(status.state)}>
            {stateBadgeLabel(status.state)}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {status.test_mode && (
          <TestModeBanner lastRefreshAt={status.last_token_refresh_at} />
        )}

        <div className="space-y-1.5">
          <StatusRow
            label="Last ingest"
            value={formatRelative(status.last_ingest_at)}
          />
          <StatusRow
            label="Last token refresh"
            value={formatRelative(status.last_token_refresh_at)}
          />
          <StatusRow
            label="Token expiry estimate"
            value={tokenExpiry}
          />
          {status.rate_limit_remaining !== null && (
            <StatusRow
              label="Rate limit headroom"
              value={status.rate_limit_remaining}
            />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
