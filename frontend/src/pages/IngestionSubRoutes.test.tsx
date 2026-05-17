// @vitest-environment jsdom
/**
 * Tests for the INGESTION_DISPATCH_CONSOLE sub-route scaffolding (§2.1).
 *
 * Covers:
 *   - IngestionTabRedirect: ?tab=connectors|filters|history → sub-route redirect
 *   - IngestionTabRedirect: no ?tab= or unknown ?tab= → renders Timeline
 *   - IngestionTabRedirect: filter params (period, channel, status) preserved
 *   - Sub-route pages render their page headings
 *
 * Tests exercise the components in isolation via MemoryRouter to avoid
 * importing the full router (which evaluates the feature flag at module load
 * time in the actual createBrowserRouter call).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, Route, Routes, Navigate, useSearchParams } from 'react-router'

// ---------------------------------------------------------------------------
// Inline IngestionTabRedirect — same logic as router.tsx, tested in isolation
// so these tests do not depend on the full router or feature-flag evaluation.
// ---------------------------------------------------------------------------

// Stub page components used by the redirect
function TimelineStub() {
  return <div data-testid="timeline-page">Timeline</div>
}

function ConnectorsStub() {
  return <div data-testid="connectors-page">Connectors</div>
}

function FiltersStub() {
  return <div data-testid="filters-page">Filters</div>
}

function HistoryStub() {
  return <div data-testid="history-page">History</div>
}

// Inline redirect component (mirrors router.tsx IngestionTabRedirect)
function IngestionTabRedirect() {
  const [searchParams] = useSearchParams()
  const tab = searchParams.get('tab')

  const filtered = new URLSearchParams(searchParams)
  filtered.delete('tab')
  const qs = filtered.toString()

  if (tab === 'connectors') {
    return <Navigate to={`/ingestion/connectors${qs ? `?${qs}` : ''}`} replace />
  }
  if (tab === 'filters') {
    return <Navigate to={`/ingestion/filters${qs ? `?${qs}` : ''}`} replace />
  }
  if (tab === 'history') {
    return <Navigate to={`/ingestion/history${qs ? `?${qs}` : ''}`} replace />
  }

  return <TimelineStub />
}

;(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true

// ---------------------------------------------------------------------------
// Mock the page components used by the sub-route pages so tests don't
// need QueryClientProvider.
// ---------------------------------------------------------------------------

vi.mock('@/components/ingestion/TimelineTab', () => ({
  TimelineTab: () => <div data-testid="timeline-tab-stub">Timeline tab</div>,
}))
vi.mock('@/components/ingestion/ConnectorsTab', () => ({
  ConnectorsTab: () => <div data-testid="connectors-tab-stub">Connectors tab</div>,
}))
vi.mock('@/components/switchboard/FiltersTab', () => ({
  FiltersTab: () => <div data-testid="filters-tab-stub">Filters tab</div>,
}))
vi.mock('@/components/switchboard/BackfillHistoryTab', () => ({
  BackfillHistoryTab: () => <div data-testid="history-tab-stub">History tab</div>,
}))

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

describe('IngestionTabRedirect', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
    document.body.innerHTML = ''
  })

  function render(initialPath: string) {
    act(() => {
      root.render(
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route path="/ingestion" element={<IngestionTabRedirect />} />
            <Route path="/ingestion/connectors" element={<ConnectorsStub />} />
            <Route path="/ingestion/filters" element={<FiltersStub />} />
            <Route path="/ingestion/history" element={<HistoryStub />} />
          </Routes>
        </MemoryRouter>,
      )
    })
  }

  // --- 301-equivalent redirects ---

  it('redirects ?tab=connectors to /ingestion/connectors', () => {
    render('/ingestion?tab=connectors')
    expect(container.querySelector('[data-testid="connectors-page"]')).not.toBeNull()
  })

  it('redirects ?tab=filters to /ingestion/filters', () => {
    render('/ingestion?tab=filters')
    expect(container.querySelector('[data-testid="filters-page"]')).not.toBeNull()
  })

  it('redirects ?tab=history to /ingestion/history', () => {
    render('/ingestion?tab=history')
    expect(container.querySelector('[data-testid="history-page"]')).not.toBeNull()
  })

  // --- Filter param preservation ---

  it('preserves period param when redirecting ?tab=connectors&period=7d', () => {
    // We test that the redirect destination contains the preserved params by
    // rendering a stub that reads search params and exposes them.
    function ConnectorsWithParams() {
      const [sp] = useSearchParams()
      return (
        <div data-testid="connectors-page" data-period={sp.get('period') ?? ''}>
          Connectors
        </div>
      )
    }

    act(() => {
      root.render(
        <MemoryRouter initialEntries={['/ingestion?tab=connectors&period=7d']}>
          <Routes>
            <Route path="/ingestion" element={<IngestionTabRedirect />} />
            <Route path="/ingestion/connectors" element={<ConnectorsWithParams />} />
          </Routes>
        </MemoryRouter>,
      )
    })

    const el = container.querySelector('[data-testid="connectors-page"]')
    expect(el).not.toBeNull()
    expect(el?.getAttribute('data-period')).toBe('7d')
  })

  it('strips ?tab= from the redirected URL', () => {
    // Verifies the 'tab' key does not leak into the sub-route query string.
    function ConnectorsWithParams() {
      const [sp] = useSearchParams()
      return (
        <div data-testid="connectors-page" data-has-tab={sp.has('tab') ? 'yes' : 'no'}>
          Connectors
        </div>
      )
    }

    act(() => {
      root.render(
        <MemoryRouter initialEntries={['/ingestion?tab=connectors&period=7d']}>
          <Routes>
            <Route path="/ingestion" element={<IngestionTabRedirect />} />
            <Route path="/ingestion/connectors" element={<ConnectorsWithParams />} />
          </Routes>
        </MemoryRouter>,
      )
    })

    const el = container.querySelector('[data-testid="connectors-page"]')
    expect(el?.getAttribute('data-has-tab')).toBe('no')
  })

  // --- Fall-through to Timeline ---

  it('renders Timeline for /ingestion with no ?tab= param', () => {
    render('/ingestion')
    expect(container.querySelector('[data-testid="timeline-page"]')).not.toBeNull()
  })

  it('renders Timeline for unrecognized ?tab=unknown', () => {
    render('/ingestion?tab=unknown')
    expect(container.querySelector('[data-testid="timeline-page"]')).not.toBeNull()
  })

  it('does not redirect when ?tab= is absent', () => {
    render('/ingestion')
    expect(container.querySelector('[data-testid="connectors-page"]')).toBeNull()
    expect(container.querySelector('[data-testid="filters-page"]')).toBeNull()
    expect(container.querySelector('[data-testid="history-page"]')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Sub-route page components (smoke: heading and tab content rendered)
// ---------------------------------------------------------------------------

describe('IngestionTimelinePage', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
    document.body.innerHTML = ''
  })

  it('renders the Ingestion heading and timeline tab', async () => {
    const { default: IngestionTimelinePage } = await import('@/pages/IngestionTimelinePage')
    act(() => {
      root.render(
        <MemoryRouter>
          <IngestionTimelinePage />
        </MemoryRouter>,
      )
    })
    expect(container.querySelector('h1')?.textContent).toBe('Ingestion')
    expect(container.querySelector('[data-testid="timeline-tab-stub"]')).not.toBeNull()
  })
})

describe('IngestionConnectorsPage', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
    document.body.innerHTML = ''
  })

  it('renders the Connectors heading and connectors tab', async () => {
    const { default: IngestionConnectorsPage } = await import('@/pages/IngestionConnectorsPage')
    act(() => {
      root.render(
        <MemoryRouter>
          <IngestionConnectorsPage />
        </MemoryRouter>,
      )
    })
    expect(container.querySelector('h1')?.textContent).toBe('Connectors')
    expect(container.querySelector('[data-testid="connectors-tab-stub"]')).not.toBeNull()
  })
})

describe('IngestionFiltersPage', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
    document.body.innerHTML = ''
  })

  it('renders the Filters heading and filters tab stub', async () => {
    const { default: IngestionFiltersPage } = await import('@/pages/IngestionFiltersPage')
    act(() => {
      root.render(
        <MemoryRouter>
          <IngestionFiltersPage />
        </MemoryRouter>,
      )
    })
    expect(container.querySelector('h1')?.textContent).toBe('Filters')
    expect(container.querySelector('[data-testid="filters-tab-stub"]')).not.toBeNull()
  })
})

describe('IngestionHistoryPage', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
    document.body.innerHTML = ''
  })

  it('renders the History heading and history tab stub', async () => {
    const { default: IngestionHistoryPage } = await import('@/pages/IngestionHistoryPage')
    act(() => {
      root.render(
        <MemoryRouter>
          <IngestionHistoryPage />
        </MemoryRouter>,
      )
    })
    expect(container.querySelector('h1')?.textContent).toBe('History')
    expect(container.querySelector('[data-testid="history-tab-stub"]')).not.toBeNull()
  })
})
