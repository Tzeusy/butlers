import type { QaPatrolReadStatus, QaPatrolStatus } from "@/api/types";

export interface QaPatrolStatusPresentation {
  label: string;
  dotClassName: string;
}

const PATROL_STATUS_PRESENTATIONS: Record<QaPatrolStatus, QaPatrolStatusPresentation> = {
  clean: { label: "clean", dotClassName: "bg-[var(--green)]" },
  findings_dispatched: {
    label: "findings dispatched",
    dotClassName: "bg-[var(--amber)]",
  },
  suppressed: {
    label: "findings suppressed",
    dotClassName: "bg-[var(--amber)]",
  },
  error: { label: "patrol error", dotClassName: "bg-destructive" },
  running: { label: "patrol running", dotClassName: "bg-muted-foreground" },
  skipped_overlap: {
    label: "patrol skipped due to overlap",
    dotClassName: "bg-muted-foreground",
  },
};

const UNKNOWN_PATROL_STATUS_PRESENTATION: QaPatrolStatusPresentation = {
  label: "unknown patrol status",
  dotClassName: "bg-destructive",
};

/**
 * Return a total, fail-closed presentation for a status read from QA patrols.
 *
 * The response can contain a corrupt or newer persisted value; never let that
 * value inherit the healthy presentation used only by ``clean``.
 */
export function getQaPatrolStatusPresentation(
  status: QaPatrolReadStatus,
): QaPatrolStatusPresentation {
  if (Object.prototype.hasOwnProperty.call(PATROL_STATUS_PRESENTATIONS, status)) {
    return PATROL_STATUS_PRESENTATIONS[status as QaPatrolStatus];
  }
  return UNKNOWN_PATROL_STATUS_PRESENTATION;
}
