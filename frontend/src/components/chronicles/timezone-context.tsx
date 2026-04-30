// ---------------------------------------------------------------------------
// ChroniclesTimezoneContext — owner timezone propagation (bu-k18cm)
//
// Resolves the owner's configured timezone once per Chronicles page render.
// Default: "Asia/Singapore" (matches the briefing.py SGT constant).
//
// Source: GET /api/settings/general → data.timezone (IANA name).
//
// Two provider variants:
//   - ChroniclesTimezoneProvider (with `timezone` prop): injects a static tz.
//     Used in production (ChroniclesPage pre-fetches via useGeneralSettings
//     and passes ownerTz down) and in tests (explicit tz string, no API call).
//   - No-prop variant not exposed — callers always supply the resolved value.
//
// Usage (production):
//   const { data } = useGeneralSettings()
//   const ownerTz = data?.data?.timezone ?? DEFAULT_TZ
//   <ChroniclesTimezoneProvider timezone={ownerTz}>...</ChroniclesTimezoneProvider>
//
// Usage (tests):
//   <ChroniclesTimezoneProvider timezone="Asia/Singapore">...</ChroniclesTimezoneProvider>
// ---------------------------------------------------------------------------

import { createContext, useContext } from "react"

// ---------------------------------------------------------------------------
// Default and context
// ---------------------------------------------------------------------------

export const DEFAULT_TZ = "Asia/Singapore"

const ChroniclesTimezoneContext = createContext<string>(DEFAULT_TZ)

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

interface ChroniclesTimezoneProviderProps {
  children: React.ReactNode
  /**
   * Resolved IANA timezone name.
   * Callers (ChroniclesPage and tests) are responsible for fetching / deriving
   * this value. The provider is a thin context injector — no API calls here.
   */
  timezone: string
}

/**
 * Injects the owner's resolved timezone into context.
 *
 * This is intentionally a thin wrapper — no data fetching. The caller
 * (ChroniclesPage) fetches the value via useGeneralSettings and passes it in.
 * Tests pass an explicit string to avoid requiring a QueryClientProvider.
 */
export function ChroniclesTimezoneProvider({
  children,
  timezone,
}: ChroniclesTimezoneProviderProps) {
  return (
    <ChroniclesTimezoneContext.Provider value={timezone}>
      {children}
    </ChroniclesTimezoneContext.Provider>
  )
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Returns the owner's configured timezone (IANA name).
 * Must be called inside a ChroniclesTimezoneProvider.
 * Defaults to "Asia/Singapore" if the provider is absent.
 */
export function useChroniclesTimezone(): string {
  return useContext(ChroniclesTimezoneContext)
}
