import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useMemoryStats } from "@/hooks/use-memory";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statRow(label: string, value: number, total?: number) {
  const pct = total && total > 0 ? Math.round((value / total) * 100) : null;
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">
        {value.toLocaleString()}
        {pct != null && (
          <span className="text-muted-foreground ml-1 text-xs">({pct}%)</span>
        )}
      </span>
    </div>
  );
}

function healthBadge(ratio: number) {
  if (ratio >= 0.8) {
    return (
      <Badge className="bg-emerald-600 text-white hover:bg-emerald-600/90">
        Healthy
      </Badge>
    );
  }
  if (ratio >= 0.5) {
    return (
      <Badge
        variant="outline"
        className="border-amber-500 text-amber-600"
      >
        Warning
      </Badge>
    );
  }
  return <Badge variant="destructive">Needs attention</Badge>;
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function TierCardSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-24" />
        <Skeleton className="h-4 w-40" />
      </CardHeader>
      <CardContent className="space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-full" />
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// MemoryTierCards
// ---------------------------------------------------------------------------

export default function MemoryTierCards() {
  const { data: statsResponse, isLoading } = useMemoryStats();

  if (isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-3">
        <TierCardSkeleton />
        <TierCardSkeleton />
        <TierCardSkeleton />
      </div>
    );
  }

  const stats = statsResponse?.data;
  if (!stats) {
    return (
      <div className="text-muted-foreground py-6 text-center text-sm">
        Memory stats unavailable.
      </div>
    );
  }

  const consolidatedEpisodes = stats.total_episodes - stats.unconsolidated_episodes;
  const episodeHealth =
    stats.total_episodes > 0
      ? consolidatedEpisodes / stats.total_episodes
      : 1;

  const factHealth =
    stats.total_facts > 0
      ? stats.active_facts / stats.total_facts
      : 1;

  const effectiveRules =
    stats.established_rules + stats.proven_rules;
  const ruleHealth =
    stats.total_rules > 0
      ? effectiveRules / stats.total_rules
      : 1;

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {/* Episodes (Eden) */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            Episodes
            {healthBadge(episodeHealth)}
          </CardTitle>
          <CardDescription>Eden tier — raw session memories</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {statRow("Total", stats.total_episodes)}
          {statRow(
            "Unconsolidated",
            stats.unconsolidated_episodes,
            stats.total_episodes,
          )}
          {statRow(
            "Consolidated",
            consolidatedEpisodes,
            stats.total_episodes,
          )}
        </CardContent>
      </Card>

      {/* Facts (Mid-term) */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            Facts
            {healthBadge(factHealth)}
          </CardTitle>
          <CardDescription>Mid-term tier — consolidated knowledge</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {statRow("Total", stats.total_facts)}
          {statRow("Active", stats.active_facts, stats.total_facts)}
          {statRow("Fading", stats.fading_facts, stats.total_facts)}
        </CardContent>
      </Card>

      {/* Rules (Long-term) */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            Rules
            {healthBadge(ruleHealth)}
          </CardTitle>
          <CardDescription>Long-term tier — behavioral patterns</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {statRow("Total", stats.total_rules)}
          {statRow("Candidate", stats.candidate_rules, stats.total_rules)}
          {statRow("Established", stats.established_rules, stats.total_rules)}
          {statRow("Proven", stats.proven_rules, stats.total_rules)}
          {statRow(
            "Anti-pattern",
            stats.anti_pattern_rules,
            stats.total_rules,
          )}
        </CardContent>
      </Card>
    </div>
  );
}
