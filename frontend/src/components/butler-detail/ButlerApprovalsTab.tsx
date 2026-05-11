// ---------------------------------------------------------------------------
// ButlerApprovalsTab — bu-cbv4m
//
// Per-butler approvals panel shown in the Approvals tab on the butler detail
// page. Fetches pending approval actions for this butler and renders a compact
// action list. When the backend truncates at limit=50 and meta.has_more is
// true, a footer line is shown:
//   "Showing first N of M · View all approvals →"
// linked to /approvals (the full approvals page).
//
// Doctrine checklist:
//   - No raw oklch/hex — design tokens only
//   - No em-dashes in prose (used only as null placeholder "—")
//   - Sentence case copy
//   - tabular-nums (tnum) on numeric counts
// ---------------------------------------------------------------------------

import { useState } from "react";
import { Link } from "react-router";

import type { ApprovalAction } from "@/api/types";
import { ActionTable } from "@/components/approvals/action-table";
import { ActionDetailDialog } from "@/components/approvals/action-detail-dialog";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useApprovalActions } from "@/hooks/use-approvals";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** How many actions to request per page. Matches backend default. */
const LIMIT = 50;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ButlerApprovalsTabProps {
  butlerName: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ButlerApprovalsTab({ butlerName }: ButlerApprovalsTabProps) {
  const [selectedAction, setSelectedAction] = useState<ApprovalAction | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const { data: actionsResp, isLoading } = useApprovalActions({
    butler: butlerName,
    limit: LIMIT,
    offset: 0,
  });

  const actions = actionsResp?.data ?? [];
  const meta = actionsResp?.meta;
  const total = meta?.total ?? 0;
  const hasMore = meta?.has_more ?? false;
  const shown = actions.length;

  function handleActionClick(action: ApprovalAction) {
    setSelectedAction(action);
    setDialogOpen(true);
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Approvals</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2" data-testid="approvals-loading">
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : actions.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6" data-testid="approvals-empty">
              No approval actions found for this butler.
            </p>
          ) : (
            <>
              <ActionTable actions={actions} onActionClick={handleActionClick} />

              {hasMore && (
                <p
                  className="mt-3 text-xs text-muted-foreground"
                  data-testid="approvals-has-more"
                >
                  Showing first{" "}
                  <span className="tnum">{shown}</span> of{" "}
                  <span className="tnum">{total}</span>.{" "}
                  <Link
                    to="/approvals"
                    className="text-primary underline-offset-4 hover:underline"
                    data-testid="approvals-view-all-link"
                  >
                    View all approvals
                  </Link>
                </p>
              )}
            </>
          )}
        </CardContent>
      </Card>

      <ActionDetailDialog
        action={selectedAction}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </>
  );
}
