/**
 * Tests for <Page> primitive.
 *
 * Uses renderToStaticMarkup (SSR-safe, no DOM setup required) consistent with
 * the project's other component/page tests.
 */
import { describe, expect, it, vi, afterEach } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";

import { Page, type PageProps } from "@/components/ui/page";

// useEffect is a no-op in renderToStaticMarkup; we just need to avoid
// "document is not defined" errors when the effect fires in test.  Since
// renderToStaticMarkup never calls useEffect we don't need to stub anything.

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type PartialPageProps = Omit<PageProps, "archetype" | "title" | "children"> &
  Pick<PageProps, "title"> &
  Partial<Pick<PageProps, "archetype">> & {
    children?: React.ReactNode;
  };

function render(props: PartialPageProps): string {
  const fullProps: PageProps = {
    archetype: "overview",
    children: <div>Page content</div>,
    ...props,
  };
  return renderToStaticMarkup(
    <MemoryRouter>
      <Page {...fullProps} />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Title and description
// ---------------------------------------------------------------------------

describe("Page -- title and description", () => {
  it("renders the title as h1", () => {
    const html = render({ title: "My Page" });
    expect(html).toContain("<h1");
    expect(html).toContain("My Page");
  });

  it("renders description below the title", () => {
    const html = render({ title: "My Page", description: "A helpful subtitle" });
    expect(html).toContain("A helpful subtitle");
  });

  it("renders without description when omitted", () => {
    const html = render({ title: "My Page" });
    // Should not have an empty paragraph from missing description
    expect(html).not.toContain('<p class="text-muted-foreground mt-1"></p>');
  });
});

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

describe("Page -- actions", () => {
  it("renders action nodes in the heading row", () => {
    const html = render({
      title: "Actions Page",
      actions: <button>Save</button>,
    });
    expect(html).toContain("Save");
  });

  it("renders without action container when actions is omitted", () => {
    const html = render({ title: "No Actions" });
    // The shrink-0 wrapper should not appear when actions is undefined
    expect(html).not.toContain('class="shrink-0"');
  });
});

// ---------------------------------------------------------------------------
// Breadcrumbs
// ---------------------------------------------------------------------------

describe("Page -- breadcrumbs", () => {
  it("renders breadcrumbs above the h1 when provided", () => {
    const html = render({
      title: "Detail Page",
      archetype: "detail",
      breadcrumbs: [
        { label: "Entities", href: "/entities" },
        { label: "Alice" },
      ],
    });
    expect(html).toContain("Entities");
    expect(html).toContain("Alice");
    // breadcrumbs nav must precede the h1
    const breadcrumbPos = html.indexOf('aria-label="Breadcrumb"');
    const h1Pos = html.indexOf("<h1");
    expect(breadcrumbPos).toBeLessThan(h1Pos);
  });

  it("does not render breadcrumb nav when breadcrumbs prop is omitted", () => {
    const html = render({ title: "No Breadcrumbs" });
    expect(html).not.toContain('aria-label="Breadcrumb"');
  });

  it("does not render breadcrumb nav when breadcrumbs is an empty array", () => {
    const html = render({ title: "Empty Breadcrumbs", breadcrumbs: [] });
    expect(html).not.toContain('aria-label="Breadcrumb"');
  });
});

// ---------------------------------------------------------------------------
// Loading skeleton -- all archetypes
// ---------------------------------------------------------------------------

describe("Page -- loading state", () => {
  it("overview: renders heading skeleton and stats/card placeholders", () => {
    const html = render({
      title: "Overview",
      archetype: "overview",
      loading: true,
      children: <div>SHOULD NOT APPEAR</div>,
    });
    // No children
    expect(html).not.toContain("SHOULD NOT APPEAR");
    // Heading skeleton: h-8 w-48
    expect(html).toContain("h-8 w-48");
    // StatsSkeleton produces a 4-col grid
    expect(html).toContain("grid-cols-2");
  });

  it("list: renders heading skeleton and a table skeleton inside a card", () => {
    const html = render({
      title: "List",
      archetype: "list",
      loading: true,
      children: <div>SHOULD NOT APPEAR</div>,
    });
    expect(html).not.toContain("SHOULD NOT APPEAR");
    // TableSkeleton renders a <table>
    expect(html).toContain("<table");
  });

  it("detail: renders heading skeleton and tab-strip placeholder", () => {
    const html = render({
      title: "Detail",
      archetype: "detail",
      loading: true,
      children: <div>SHOULD NOT APPEAR</div>,
    });
    expect(html).not.toContain("SHOULD NOT APPEAR");
    // Tab-strip skeleton: h-10 w-full
    expect(html).toContain("h-10 w-full");
  });

  it("workspace: renders a single full-width coarse placeholder", () => {
    const html = render({
      title: "Workspace",
      archetype: "workspace",
      loading: true,
      children: <div>SHOULD NOT APPEAR</div>,
    });
    expect(html).not.toContain("SHOULD NOT APPEAR");
    expect(html).toContain("h-96");
  });

  it("editor: renders default 2 CardSkeleton placeholders", () => {
    const html = render({
      title: "Editor",
      archetype: "editor",
      loading: true,
      children: <div>SHOULD NOT APPEAR</div>,
    });
    expect(html).not.toContain("SHOULD NOT APPEAR");
    // CardSkeleton renders a card; there should be at least 2 card elements
    const cardCount = (html.match(/data-slot="card"/g) ?? []).length;
    expect(cardCount).toBeGreaterThanOrEqual(2);
  });

  it("editor: honours skeletonSectionCount prop", () => {
    const html = render({
      title: "Editor",
      archetype: "editor",
      loading: true,
      skeletonSectionCount: 4,
      children: <div>SHOULD NOT APPEAR</div>,
    });
    const cardCount = (html.match(/data-slot="card"/g) ?? []).length;
    expect(cardCount).toBeGreaterThanOrEqual(4);
  });

  it("loading wins over error when both are set", () => {
    const html = render({
      title: "Priority Test",
      archetype: "overview",
      loading: true,
      error: new Error("Should not render"),
      children: <div>SHOULD NOT APPEAR</div>,
    });
    expect(html).not.toContain("Should not render");
    expect(html).not.toContain("SHOULD NOT APPEAR");
    // Skeleton rendered
    expect(html).toContain("h-8 w-48");
  });
});

// ---------------------------------------------------------------------------
// Error state
// ---------------------------------------------------------------------------

describe("Page -- error state", () => {
  it("renders error message from an Error instance", () => {
    const html = render({
      title: "Failing Page",
      error: new Error("Network timeout"),
      children: <div>SHOULD NOT APPEAR</div>,
    });
    expect(html).toContain("Network timeout");
    expect(html).not.toContain("SHOULD NOT APPEAR");
  });

  it("renders error message from a plain string", () => {
    const html = render({
      title: "Failing Page",
      error: "Unexpected error",
      children: <div>SHOULD NOT APPEAR</div>,
    });
    expect(html).toContain("Unexpected error");
  });

  it("still renders the heading block in error state", () => {
    const html = render({
      title: "Still Visible Title",
      error: new Error("boom"),
      children: <div>hidden</div>,
    });
    expect(html).toContain("Still Visible Title");
  });

  it("renders a Retry button when onRetry is provided", () => {
    const html = render({
      title: "Retryable",
      error: new Error("failed"),
      onRetry: vi.fn(),
      children: <div>hidden</div>,
    });
    expect(html).toContain("Retry");
  });

  it("does not render a Retry button when onRetry is omitted", () => {
    const html = render({
      title: "Failing Page",
      error: new Error("failed"),
      children: <div>hidden</div>,
    });
    // No onRetry supplied, so no retry button should appear
    expect(html).not.toContain(">Retry<");
  });

  it("error wins over empty when both are set", () => {
    const html = render({
      title: "Priority",
      error: new Error("error takes priority"),
      empty: { title: "Nothing here", description: "Empty state" },
      children: <div>hidden</div>,
    });
    expect(html).toContain("error takes priority");
    expect(html).not.toContain("Nothing here");
  });
});

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

describe("Page -- empty state", () => {
  it("renders EmptyState when empty is set and not loading", () => {
    const html = render({
      title: "Empty List",
      empty: { title: "No items found", description: "Create one to get started" },
      children: <div>SHOULD NOT APPEAR</div>,
    });
    expect(html).toContain("No items found");
    expect(html).toContain("Create one to get started");
    expect(html).not.toContain("SHOULD NOT APPEAR");
  });

  it("renders children when empty is null", () => {
    const html = render({
      title: "Has Content",
      empty: null,
      children: <div>Actual content</div>,
    });
    expect(html).toContain("Actual content");
  });

  it("renders children when empty is undefined", () => {
    const html = render({
      title: "Has Content",
      children: <div>Also content</div>,
    });
    expect(html).toContain("Also content");
  });
});

// ---------------------------------------------------------------------------
// Archetype layout constraints
// ---------------------------------------------------------------------------

describe("Page -- archetype layout", () => {
  it("overview: no max-width constraint", () => {
    const html = render({
      title: "Overview",
      archetype: "overview",
      children: <div>content</div>,
    });
    expect(html).not.toContain("max-w-5xl");
    expect(html).not.toContain("max-w-2xl");
  });

  it("list: no max-width constraint", () => {
    const html = render({
      title: "List",
      archetype: "list",
      children: <div>content</div>,
    });
    expect(html).not.toContain("max-w-5xl");
    expect(html).not.toContain("max-w-2xl");
  });

  it("detail: applies max-w-5xl constraint", () => {
    const html = render({
      title: "Detail",
      archetype: "detail",
      children: <div>content</div>,
    });
    expect(html).toContain("max-w-5xl");
  });

  it("workspace: no max-width constraint", () => {
    const html = render({
      title: "Workspace",
      archetype: "workspace",
      children: <div>content</div>,
    });
    expect(html).not.toContain("max-w-5xl");
    expect(html).not.toContain("max-w-2xl");
  });

  it("editor: applies max-w-2xl constraint", () => {
    const html = render({
      title: "Editor",
      archetype: "editor",
      children: <div>content</div>,
    });
    expect(html).toContain("max-w-2xl");
  });
});

// ---------------------------------------------------------------------------
// Children render (happy path)
// ---------------------------------------------------------------------------

describe("Page -- children", () => {
  it("renders children when no async state flags are set", () => {
    const html = render({
      title: "Normal Page",
      archetype: "overview",
      children: <div id="content">Hello world</div>,
    });
    expect(html).toContain("Hello world");
  });

  it("renders children when loading=false and error=null and empty=null", () => {
    const html = render({
      title: "Normal Page",
      archetype: "list",
      loading: false,
      error: null,
      empty: null,
      children: <div>Table here</div>,
    });
    expect(html).toContain("Table here");
  });
});

// ---------------------------------------------------------------------------
// document.title (smoke-check that the effect does not blow up during SSR)
// ---------------------------------------------------------------------------

describe("Page -- document.title", () => {
  afterEach(() => {
    // Reset title after each test
    if (typeof document !== "undefined") {
      document.title = "";
    }
  });

  it("renders without throwing when title is provided", () => {
    expect(() => render({ title: "My Settings" })).not.toThrow();
  });
});
