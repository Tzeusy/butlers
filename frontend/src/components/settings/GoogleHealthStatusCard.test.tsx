/**
 * Tests for GoogleHealthStatusCard and related helpers.
 *
 * Covers:
 * - computeTokenExpiry: test-mode countdown, production label, unknown fallback
 * - isTestModeTokenNearExpiry: threshold detection
 * - GoogleHealthStatusCard: refresh indicator visibility, test-mode banner variants
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import {
  GoogleHealthStatusCard,
  computeTokenExpiry,
  isTestModeTokenNearExpiry,
} from "@/components/settings/GoogleHealthStatusCard";
import { useGoogleHealthStatus } from "@/hooks/use-google-health";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/hooks/use-google-health", () => ({
  useGoogleHealthStatus: vi.fn(),
}));

type UseQueryResult = ReturnType<typeof useGoogleHealthStatus>;

function mockStatus(state: Partial<UseQueryResult>) {
  vi.mocked(useGoogleHealthStatus).mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    ...state,
  } as UseQueryResult);
}

// ---------------------------------------------------------------------------
// computeTokenExpiry
// ---------------------------------------------------------------------------

describe("computeTokenExpiry", () => {
  it("returns 'Long-lived (production mode)' for production accounts", () => {
    expect(computeTokenExpiry("2026-04-20T00:00:00Z", false)).toBe(
      "Long-lived (production mode)",
    );
  });

  it("returns 'Long-lived (production mode)' when no refresh date and not test-mode", () => {
    expect(computeTokenExpiry(null, false)).toBe("Long-lived (production mode)");
  });

  it("returns 'Unknown' when test-mode but no last_token_refresh_at", () => {
    expect(computeTokenExpiry(null, true)).toBe("Unknown");
  });

  it("returns 'Unknown' for invalid date strings in test-mode", () => {
    expect(computeTokenExpiry("not-a-date", true)).toBe("Unknown");
  });

  it("renders countdown 'Expires in ~Xd Yh' for test-mode accounts with future expiry", () => {
    // Token refreshed ~3 days 14 hours ago → ~3d 10h remaining
    const refreshedAt = new Date(Date.now() - (3 * 24 + 14) * 60 * 60 * 1000).toISOString();
    const result = computeTokenExpiry(refreshedAt, true);
    expect(result).toMatch(/^Expires in ~/);
    expect(result).toMatch(/d/); // contains days component
  });

  it("renders 'Expired' when token is past the 7-day limit in test-mode", () => {
    // Token refreshed 8 days ago
    const refreshedAt = new Date(Date.now() - 8 * 24 * 60 * 60 * 1000).toISOString();
    expect(computeTokenExpiry(refreshedAt, true)).toBe("Expired");
  });

  it("renders hours-only countdown when less than 1 day remains", () => {
    // Token refreshed 6 days 20 hours ago → ~4h remaining
    const refreshedAt = new Date(Date.now() - (6 * 24 + 20) * 60 * 60 * 1000).toISOString();
    const result = computeTokenExpiry(refreshedAt, true);
    expect(result).toMatch(/^Expires in ~/);
    expect(result).not.toMatch(/d/); // no days component
    expect(result).toMatch(/h$/);
  });
});

// ---------------------------------------------------------------------------
// isTestModeTokenNearExpiry
// ---------------------------------------------------------------------------

describe("isTestModeTokenNearExpiry", () => {
  it("returns false when last_token_refresh_at is null", () => {
    expect(isTestModeTokenNearExpiry(null)).toBe(false);
  });

  it("returns false when token age is below 5d 6h threshold", () => {
    // Refreshed 4 days ago — safe
    const refreshedAt = new Date(Date.now() - 4 * 24 * 60 * 60 * 1000).toISOString();
    expect(isTestModeTokenNearExpiry(refreshedAt)).toBe(false);
  });

  it("returns true when token age exceeds 5d 6h threshold", () => {
    // Refreshed 6 days ago — near expiry
    const refreshedAt = new Date(Date.now() - 6 * 24 * 60 * 60 * 1000).toISOString();
    expect(isTestModeTokenNearExpiry(refreshedAt)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// GoogleHealthStatusCard — rendering
// ---------------------------------------------------------------------------

describe("GoogleHealthStatusCard", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders loading skeleton while fetching initial data", () => {
    mockStatus({ isLoading: true });
    const html = renderToStaticMarkup(<GoogleHealthStatusCard />);
    expect(html).toContain("Google Health");
  });

  it("renders error state when status endpoint fails", () => {
    mockStatus({ isError: true, error: new Error("network error") });
    const html = renderToStaticMarkup(<GoogleHealthStatusCard />);
    expect(html).toContain("Unavailable");
    expect(html).toContain("Failed to fetch Google Health connector status");
  });

  it("renders healthy state badge", () => {
    mockStatus({
      data: {
        connected: true,
        state: "healthy",
        scopes_granted: ["https://www.googleapis.com/auth/googlehealth.sleep"],
        last_ingest_at: "2026-04-24T10:00:00Z",
        last_token_refresh_at: "2026-04-24T08:00:00Z",
        rate_limit_remaining: null,
        test_mode: false,
      },
    });
    const html = renderToStaticMarkup(<GoogleHealthStatusCard />);
    expect(html).toContain("Healthy");
  });

  it("renders degraded state badge", () => {
    mockStatus({
      data: {
        connected: false,
        state: "degraded",
        scopes_granted: [],
        last_ingest_at: null,
        last_token_refresh_at: null,
        rate_limit_remaining: null,
        test_mode: false,
      },
    });
    const html = renderToStaticMarkup(<GoogleHealthStatusCard />);
    expect(html).toContain("Degraded");
  });

  it("renders 'Long-lived (production mode)' expiry for production accounts", () => {
    mockStatus({
      data: {
        connected: true,
        state: "healthy",
        scopes_granted: [],
        last_ingest_at: null,
        last_token_refresh_at: "2026-04-20T00:00:00Z",
        rate_limit_remaining: null,
        test_mode: false,
      },
    });
    const html = renderToStaticMarkup(<GoogleHealthStatusCard />);
    expect(html).toContain("Long-lived (production mode)");
  });

  it("renders 'Unknown' expiry when no last_token_refresh_at in test-mode", () => {
    mockStatus({
      data: {
        connected: true,
        state: "degraded",
        scopes_granted: [],
        last_ingest_at: null,
        last_token_refresh_at: null,
        rate_limit_remaining: null,
        test_mode: true,
      },
    });
    const html = renderToStaticMarkup(<GoogleHealthStatusCard />);
    expect(html).toContain("Unknown");
  });

  it("renders orange test-mode banner when test_mode=true and token not near expiry", () => {
    // Refreshed 1 day ago — not near expiry
    const refreshedAt = new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString();
    mockStatus({
      data: {
        connected: true,
        state: "healthy",
        scopes_granted: [],
        last_ingest_at: null,
        last_token_refresh_at: refreshedAt,
        rate_limit_remaining: null,
        test_mode: true,
      },
    });
    const html = renderToStaticMarkup(<GoogleHealthStatusCard />);
    expect(html).toContain("OAuth client in test mode");
    expect(html).toContain("Learn more");
  });

  it("renders red expiry-warning banner when test-mode token is near expiry", () => {
    // Refreshed 6 days ago — near expiry
    const refreshedAt = new Date(Date.now() - 6 * 24 * 60 * 60 * 1000).toISOString();
    mockStatus({
      data: {
        connected: true,
        state: "healthy",
        scopes_granted: [],
        last_ingest_at: null,
        last_token_refresh_at: refreshedAt,
        rate_limit_remaining: null,
        test_mode: true,
      },
    });
    const html = renderToStaticMarkup(<GoogleHealthStatusCard />);
    expect(html).toContain("Google Health consent is about to expire");
    expect(html).toContain("Re-grant Health scopes");
  });

  it("renders refresh indicator (Loader2 spinner) when isFetching=true", () => {
    mockStatus({
      isFetching: true,
      data: {
        connected: true,
        state: "healthy",
        scopes_granted: [],
        last_ingest_at: null,
        last_token_refresh_at: "2026-04-20T00:00:00Z",
        rate_limit_remaining: null,
        test_mode: false,
      },
    });
    const html = renderToStaticMarkup(<GoogleHealthStatusCard />);
    // Loader2 renders as an SVG with aria-label="Refreshing"
    expect(html).toContain('aria-label="Refreshing"');
  });

  it("does NOT render refresh indicator when isFetching=false", () => {
    mockStatus({
      isFetching: false,
      data: {
        connected: true,
        state: "healthy",
        scopes_granted: [],
        last_ingest_at: null,
        last_token_refresh_at: "2026-04-20T00:00:00Z",
        rate_limit_remaining: null,
        test_mode: false,
      },
    });
    const html = renderToStaticMarkup(<GoogleHealthStatusCard />);
    expect(html).not.toContain('aria-label="Refreshing"');
  });

  it("renders rate-limit headroom when rate_limit_remaining is provided", () => {
    mockStatus({
      data: {
        connected: true,
        state: "healthy",
        scopes_granted: [],
        last_ingest_at: null,
        last_token_refresh_at: "2026-04-20T00:00:00Z",
        rate_limit_remaining: 42,
        test_mode: false,
      },
    });
    const html = renderToStaticMarkup(<GoogleHealthStatusCard />);
    expect(html).toContain("Rate limit headroom");
    expect(html).toContain("42");
  });

  it("hides rate-limit row when rate_limit_remaining is null", () => {
    mockStatus({
      data: {
        connected: true,
        state: "healthy",
        scopes_granted: [],
        last_ingest_at: null,
        last_token_refresh_at: "2026-04-20T00:00:00Z",
        rate_limit_remaining: null,
        test_mode: false,
      },
    });
    const html = renderToStaticMarkup(<GoogleHealthStatusCard />);
    expect(html).not.toContain("Rate limit headroom");
  });
});
