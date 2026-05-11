// @vitest-environment jsdom
/**
 * ButlerApprovalsTab — RTL tests for the per-butler approvals panel.
 *
 * Tests:
 *  - Loading state renders skeleton placeholder
 *  - Empty state shown when no approval actions found
 *  - Actions rendered when data is present (has_more=false, no footer)
 *  - has_more=true shows truncation footer with correct counts
 *  - Footer link points to /approvals
 *  - has_more=false with actions suppresses footer entirely
 *
 * bead: bu-cbv4m
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import ButlerApprovalsTab from "./ButlerApprovalsTab";

// ---------------------------------------------------------------------------
// Mock hooks
// ---------------------------------------------------------------------------

vi.mock("@/hooks/use-approvals", () => ({
  useApprovalActions: vi.fn(),
}));

// ActionDetailDialog uses its own hook calls; mock them to avoid cascade.
vi.mock("@/components/approvals/action-detail-dialog", () => ({
  ActionDetailDialog: () => null,
}));

// ActionTable renders a complex table; mock it so tests are lightweight.
vi.mock("@/components/approvals/action-table", () => ({
  ActionTable: ({ actions }: { actions: { id: string }[] }) => (
    <ul data-testid="action-table">
      {actions.map((a) => (
        <li key={a.id} data-testid="action-row">
          {a.id}
        </li>
      ))}
    </ul>
  ),
}));

import { useApprovalActions } from "@/hooks/use-approvals";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeAction(id: string) {
  return {
    id,
    tool_name: "send_email",
    tool_args: {},
    status: "pending",
    requested_at: "2026-05-11T10:00:00Z",
    agent_summary: null,
    session_id: null,
    expires_at: null,
    decided_by: null,
    decided_at: null,
    execution_result: null,
    approval_rule_id: null,
    target_contact: null,
  };
}

/** Response with has_more=false (no truncation). */
function makeResp(count: number, total?: number, hasMore = false) {
  const actions = Array.from({ length: count }, (_, i) => makeAction(`action-${i + 1}`));
  return {
    data: actions,
    meta: {
      total: total ?? count,
      offset: 0,
      limit: 50,
      has_more: hasMore,
    },
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderTab(butlerName = "general") {
  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter>
        <ButlerApprovalsTab butlerName={butlerName} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ButlerApprovalsTab", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("shows loading skeleton when data is loading", () => {
    vi.mocked(useApprovalActions).mockReturnValue({
      data: undefined,
      isLoading: true,
    } as ReturnType<typeof useApprovalActions>);

    renderTab();

    expect(screen.getByTestId("approvals-loading")).toBeTruthy();
    expect(screen.queryByTestId("approvals-empty")).toBeNull();
    expect(screen.queryByTestId("approvals-has-more")).toBeNull();
  });

  it("shows empty state when no actions are returned", () => {
    vi.mocked(useApprovalActions).mockReturnValue({
      data: makeResp(0),
      isLoading: false,
    } as ReturnType<typeof useApprovalActions>);

    renderTab();

    expect(screen.getByTestId("approvals-empty")).toBeTruthy();
    expect(screen.queryByTestId("action-table")).toBeNull();
    expect(screen.queryByTestId("approvals-has-more")).toBeNull();
  });

  it("renders action table without footer when has_more=false", () => {
    vi.mocked(useApprovalActions).mockReturnValue({
      data: makeResp(12, 12, false),
      isLoading: false,
    } as ReturnType<typeof useApprovalActions>);

    renderTab();

    expect(screen.getByTestId("action-table")).toBeTruthy();
    expect(screen.getAllByTestId("action-row")).toHaveLength(12);
    // No "has_more" footer — would add noise when all items are shown
    expect(screen.queryByTestId("approvals-has-more")).toBeNull();
  });

  it("shows truncation footer with counts when has_more=true", () => {
    vi.mocked(useApprovalActions).mockReturnValue({
      data: makeResp(50, 127, true),
      isLoading: false,
    } as ReturnType<typeof useApprovalActions>);

    renderTab();

    const footer = screen.getByTestId("approvals-has-more");
    expect(footer).toBeTruthy();
    expect(footer.textContent).toContain("50");
    expect(footer.textContent).toContain("127");
  });

  it("footer link points to /approvals when has_more=true", () => {
    vi.mocked(useApprovalActions).mockReturnValue({
      data: makeResp(50, 200, true),
      isLoading: false,
    } as ReturnType<typeof useApprovalActions>);

    renderTab();

    const link = screen.getByTestId("approvals-view-all-link") as HTMLAnchorElement;
    expect(link).toBeTruthy();
    expect(link.getAttribute("href")).toBe("/approvals");
  });

  it("passes butlerName as filter param to useApprovalActions", () => {
    vi.mocked(useApprovalActions).mockReturnValue({
      data: makeResp(0),
      isLoading: false,
    } as ReturnType<typeof useApprovalActions>);

    renderTab("memory");

    expect(useApprovalActions).toHaveBeenCalledWith(
      expect.objectContaining({ butler: "memory" }),
    );
  });
});
