// ---------------------------------------------------------------------------
// SessionStripeChart — stacked bar chart of session counts over time (bu-2okpr.2)
//
// Renders a recharts BarChart with one stacked Bar per butler.
// X = time bucket (hourly for <= 48h windows, daily otherwise)
// Y = session count
// Color: deterministic mapping butler-name -> --category-1..8 CSS tokens
// ---------------------------------------------------------------------------

import {
  Bar,
  BarChart,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { Skeleton } from "@/components/ui/skeleton"
import type { ButlerSummary } from "@/api/types"
import {
  bucketUnit,
  formatBucketKey,
  pivotSessionsIntoRows,
  useSessionStripeData,
} from "./session-stripe-utils"

// ---------------------------------------------------------------------------
// Color tokens — maps butler index (0-based, mod 8) to CSS variable names
// ---------------------------------------------------------------------------

const CATEGORY_VARS = [
  "var(--category-1)",
  "var(--category-2)",
  "var(--category-3)",
  "var(--category-4)",
  "var(--category-5)",
  "var(--category-6)",
  "var(--category-7)",
  "var(--category-8)",
] as const

/** Deterministic butler-name to color token mapping. */
function butlerColor(name: string, allButlers: readonly ButlerSummary[]): string {
  const idx = allButlers.findIndex((b) => b.name === name)
  if (idx === -1) return CATEGORY_VARS[0]
  return CATEGORY_VARS[idx % CATEGORY_VARS.length]
}

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------

interface TooltipPayloadEntry {
  dataKey: string
  value: number
  color: string
}

interface CustomTooltipProps {
  active?: boolean
  label?: string
  payload?: TooltipPayloadEntry[]
  unit: "hour" | "day"
}

function StripeTooltip({ active, label, payload, unit }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0 || !label) return null

  const entries = payload.filter((p) => p.value > 0).sort((a, b) => b.value - a.value)

  if (entries.length === 0) return null

  const total = entries.reduce((sum, p) => sum + p.value, 0)

  return (
    <div className="rounded-md border bg-popover p-3 text-sm shadow-md">
      <p className="mb-2 font-medium">{formatBucketKey(label, unit)}</p>
      {entries.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
            style={{ backgroundColor: p.color }}
          />
          <span className="text-muted-foreground">{p.dataKey}:</span>
          <span className="ml-auto font-mono">{p.value}</span>
        </div>
      ))}
      {entries.length > 1 && (
        <div className="mt-2 border-t pt-2 flex justify-between text-muted-foreground">
          <span>Total</span>
          <span className="font-mono">{total}</span>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function SessionStripeChartSkeleton() {
  return (
    <div
      className="flex h-[200px] flex-col gap-2 py-4"
      data-testid="session-stripe-skeleton"
      role="status"
      aria-label="Loading session chart"
    >
      <div className="flex h-full gap-2">
        <Skeleton className="w-8 h-full rounded-md" />
        <div className="flex flex-1 items-end gap-0.5">
          {Array.from({ length: 24 }, (_, i) => (
            <Skeleton
              key={i}
              className="flex-1 rounded-sm"
              style={{ height: `${20 + (i % 4) * 15}%` }}
            />
          ))}
        </div>
      </div>
      <div className="flex gap-0.5 pl-10">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="flex-1 h-3 rounded" />
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface SessionStripeChartProps {
  window: { from: Date; to: Date }
  butlers: ButlerSummary[]
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function SessionStripeChart({ window, butlers }: SessionStripeChartProps) {
  const { data, isLoading, isError } = useSessionStripeData(window)

  if (isLoading) {
    return <SessionStripeChartSkeleton />
  }

  if (isError) {
    return (
      <div
        className="flex h-[200px] items-center justify-center text-sm text-muted-foreground"
        data-testid="session-stripe-error"
      >
        Failed to load session data.
      </div>
    )
  }

  const sessions = data?.data ?? []

  if (sessions.length === 0) {
    return (
      <div
        className="flex h-[200px] items-center justify-center text-sm text-muted-foreground"
        data-testid="session-stripe-empty"
      >
        No sessions in this window.
      </div>
    )
  }

  const unit = bucketUnit(window.from, window.to)
  const rows = pivotSessionsIntoRows(sessions, window.from, window.to, unit)

  // Discover which butler names are present in the data. Use the butlers prop
  // order for known names; fall back to alphabetical for any unlisted names.
  const presentNames = new Set(sessions.map((s) => s.butler).filter(Boolean) as string[])
  const orderedNames = [
    ...butlers.map((b) => b.name).filter((n) => presentNames.has(n)),
    ...[...presentNames].filter((n) => !butlers.some((b) => b.name === n)).sort(),
  ]

  return (
    <div data-testid="session-stripe-chart">
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={rows} margin={{ top: 5, right: 5, bottom: 5, left: 0 }}>
          <XAxis
            dataKey="bucket"
            tickFormatter={(v: string) => formatBucketKey(v, unit)}
            tick={{ fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            allowDecimals={false}
            tick={{ fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            width={32}
          />
          <Tooltip content={<StripeTooltip unit={unit} />} />
          <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
          {orderedNames.map((name) => (
            <Bar
              key={name}
              dataKey={name}
              stackId="bucket"
              fill={butlerColor(name, butlers)}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
