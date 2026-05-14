import type { QaCaseSummary } from "@/api/types";
import { cn } from "@/lib/utils";

import { StateTrack, type QaStateTrackStage } from "./StateTrack";

interface CaseDossierHeaderProps {
  case: QaCaseSummary;
  stage: QaStateTrackStage;
  className?: string;
}

const severityClass: Record<QaCaseSummary["sev"], string> = {
  high: "bg-destructive",
  medium: "bg-amber-500",
  low: "bg-muted-foreground",
};

function formatDetectedTime(ts: string): string {
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return ts;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function CaseDossierHeader({ case: qaCase, stage, className }: CaseDossierHeaderProps) {
  return (
    <header className={cn("space-y-2", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn("h-2.5 w-2.5 shrink-0", severityClass[qaCase.sev])}
          aria-label={`${qaCase.sev} severity`}
        />
        <p className="min-w-0 flex-1 truncate font-mono text-[10px] uppercase tracking-[0.10em] text-muted-foreground tnum">
          #{qaCase.short_id} · {qaCase.butler} · detected {formatDetectedTime(qaCase.detected)}
        </p>
        <StateTrack stage={stage} className="ml-auto" />
      </div>
      <h2 className="font-sans text-[22px] font-medium leading-[1.2] tracking-normal text-foreground">
        {qaCase.headline ?? "Untitled QA case"}
      </h2>
    </header>
  );
}
