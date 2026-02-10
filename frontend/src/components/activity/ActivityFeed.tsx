import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { ActivityEvent } from "@/api/types"

interface CollapsedEvent {
  type: "collapsed"
  count: number
  failures: number
  timestamp: string
  events: ActivityEvent[]
}

type DisplayEvent = (ActivityEvent & { type: string }) | CollapsedEvent

function isHeartbeatTick(event: ActivityEvent): boolean {
  return (
    event.type === "schedule" &&
    (event.task_name?.toLowerCase().includes("heartbeat") ?? false)
  )
}

function collapseHeartbeats(events: ActivityEvent[]): DisplayEvent[] {
  const result: DisplayEvent[] = []
  let i = 0

  while (i < events.length) {
    if (isHeartbeatTick(events[i])) {
      const group: ActivityEvent[] = [events[i]]
      let j = i + 1
      while (j < events.length && isHeartbeatTick(events[j])) {
        group.push(events[j])
        j++
      }
      if (group.length > 1) {
        const failures = group.filter((e) =>
          e.summary.toLowerCase().includes("fail"),
        ).length
        result.push({
          type: "collapsed",
          count: group.length,
          failures,
          timestamp: group[0].timestamp,
          events: group,
        })
      } else {
        result.push(group[0])
      }
      i = j
    } else {
      result.push(events[i])
      i++
    }
  }

  return result
}

function formatRelativeTime(timestamp: string): string {
  const now = Date.now()
  const then = new Date(timestamp).getTime()
  const diffMs = now - then
  const diffMin = Math.floor(diffMs / 60_000)

  if (diffMin < 1) return "just now"
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHrs = Math.floor(diffMin / 60)
  if (diffHrs < 24) return `${diffHrs}h ago`
  const diffDays = Math.floor(diffHrs / 24)
  return `${diffDays}d ago`
}

function eventTypeIcon(type: string): string {
  switch (type) {
    case "session":
      return "S"
    case "schedule":
      return "C"
    case "notification":
      return "N"
    case "startup":
      return "P"
    default:
      return "E"
  }
}

interface ActivityFeedProps {
  events: ActivityEvent[]
  isLoading?: boolean
}

export default function ActivityFeed({ events, isLoading }: ActivityFeedProps) {
  const displayEvents = collapseHeartbeats(events)

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (displayEvents.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No recent activity</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent Activity</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {displayEvents.map((event, i) => {
            if ("count" in event && event.type === "collapsed") {
              return (
                <div
                  key={`collapsed-${i}`}
                  className="flex items-center gap-3 text-sm"
                >
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-xs font-medium">
                    H
                  </span>
                  <span className="flex-1 text-muted-foreground">
                    Heartbeat: {event.count} butlers ticked
                    {event.failures > 0 && `, ${event.failures} failures`}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {formatRelativeTime(event.timestamp)}
                  </span>
                </div>
              )
            }

            const ev = event as ActivityEvent
            return (
              <div key={ev.id} className="flex items-center gap-3 text-sm">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-xs font-medium">
                  {eventTypeIcon(ev.type)}
                </span>
                <Badge variant="outline" className="text-xs">
                  {ev.butler}
                </Badge>
                <span className="flex-1 truncate">{ev.summary}</span>
                <span className="text-xs text-muted-foreground whitespace-nowrap">
                  {formatRelativeTime(ev.timestamp)}
                </span>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
