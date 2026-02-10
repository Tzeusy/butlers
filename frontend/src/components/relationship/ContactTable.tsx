import { EmptyState as EmptyStateUI } from "@/components/ui/empty-state";
import { formatDistanceToNow } from "date-fns";
import { useNavigate } from "react-router";

import type { ContactSummary, Label } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ContactTableProps {
  contacts: ContactSummary[];
  isLoading: boolean;
  /** Search query, controlled externally. */
  search: string;
  onSearchChange: (value: string) => void;
  /** All available labels for the filter. */
  allLabels: Label[];
  /** Currently selected label filter (name), or empty for no filter. */
  activeLabel: string;
  onLabelFilter: (label: string) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Deterministic badge color from label color or name hash. */
function labelStyle(label: Label): string {
  if (label.color) {
    return label.color;
  }
  const colors = [
    "#3b82f6", "#8b5cf6", "#f59e0b", "#14b8a6",
    "#f43f5e", "#6366f1", "#06b6d4", "#f97316",
  ];
  let hash = 0;
  for (let i = 0; i < label.name.length; i++) {
    hash = (hash * 31 + label.name.charCodeAt(i)) | 0;
  }
  return colors[Math.abs(hash) % colors.length];
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SkeletonRows({ count = 5 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <TableRow key={i}>
          <TableCell><Skeleton className="h-4 w-36" /></TableCell>
          <TableCell><Skeleton className="h-4 w-40" /></TableCell>
          <TableCell><Skeleton className="h-4 w-28" /></TableCell>
          <TableCell><Skeleton className="h-4 w-24" /></TableCell>
          <TableCell><Skeleton className="h-4 w-20" /></TableCell>
        </TableRow>
      ))}
    </>
  );
}

function EmptyState() {
  return (
    <EmptyStateUI
      title="No contacts found"
      description="Contacts will appear here as they are added through the Relationship butler."
    />
  );
}

// ---------------------------------------------------------------------------
// ContactTable
// ---------------------------------------------------------------------------

export default function ContactTable({
  contacts,
  isLoading,
  search,
  onSearchChange,
  allLabels,
  activeLabel,
  onLabelFilter,
}: ContactTableProps) {
  const navigate = useNavigate();

  return (
    <div className="space-y-4">
      {/* Search + label filter */}
      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search contacts..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="w-64"
        />
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge
            variant={activeLabel === "" ? "default" : "outline"}
            className="cursor-pointer"
            onClick={() => onLabelFilter("")}
          >
            All
          </Badge>
          {allLabels.map((label) => (
            <Badge
              key={label.id}
              variant={activeLabel === label.name ? "default" : "outline"}
              className="cursor-pointer"
              style={
                activeLabel === label.name
                  ? { backgroundColor: labelStyle(label), color: "#fff" }
                  : {}
              }
              onClick={() =>
                onLabelFilter(activeLabel === label.name ? "" : label.name)
              }
            >
              {label.name}
            </Badge>
          ))}
        </div>
      </div>

      {/* Table */}
      {!isLoading && contacts.length === 0 ? (
        <EmptyState />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>Labels</TableHead>
              <TableHead>Last Interaction</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <SkeletonRows />
            ) : (
              contacts.map((contact) => (
                <TableRow
                  key={contact.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/contacts/${contact.id}`)}
                >
                  <TableCell className="font-medium">
                    {contact.full_name}
                    {contact.nickname && (
                      <span className="text-muted-foreground ml-1 text-xs">
                        ({contact.nickname})
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {contact.email ?? "\u2014"}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {contact.phone ?? "\u2014"}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {contact.labels.map((label) => (
                        <Badge
                          key={label.id}
                          variant="outline"
                          style={{
                            borderColor: labelStyle(label),
                            color: labelStyle(label),
                          }}
                          className="text-xs"
                        >
                          {label.name}
                        </Badge>
                      ))}
                      {contact.labels.length === 0 && (
                        <span className="text-muted-foreground text-xs">{"\u2014"}</span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {contact.last_interaction_at
                      ? formatDistanceToNow(new Date(contact.last_interaction_at), {
                          addSuffix: true,
                        })
                      : "\u2014"}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
