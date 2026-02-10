import { format, formatDistanceToNow } from "date-fns";

import type {
  ActivityFeedItem,
  ContactDetail,
  Gift,
  Interaction,
  Loan,
  Note,
} from "@/api/types";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useContactFeed,
  useContactGifts,
  useContactInteractions,
  useContactLoans,
  useContactNotes,
} from "@/hooks/use-contacts";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ContactDetailViewProps {
  contact: ContactDetail;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function labelStyle(label: { color: string | null; name: string }): string {
  if (label.color) return label.color;
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

function formatDate(iso: string): string {
  return format(new Date(iso), "MMM d, yyyy");
}

function formatRelative(iso: string): string {
  return formatDistanceToNow(new Date(iso), { addSuffix: true });
}

// ---------------------------------------------------------------------------
// Loading skeleton for tab content
// ---------------------------------------------------------------------------

function TabSkeleton() {
  return (
    <div className="space-y-3 py-4">
      {Array.from({ length: 3 }, (_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}

function EmptyTab({ message }: { message: string }) {
  return (
    <div className="text-muted-foreground flex items-center justify-center py-12 text-sm">
      {message}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Notes tab
// ---------------------------------------------------------------------------

function NotesTab({ contactId }: { contactId: string }) {
  const { data: notes, isLoading } = useContactNotes(contactId);

  if (isLoading) return <TabSkeleton />;
  if (!notes || notes.length === 0) return <EmptyTab message="No notes yet." />;

  return (
    <div className="space-y-3 py-4">
      {notes.map((note: Note) => (
        <Card key={note.id}>
          <CardContent className="py-3">
            <p className="text-sm whitespace-pre-wrap">{note.content}</p>
            <p className="text-muted-foreground mt-2 text-xs">
              {formatRelative(note.created_at)}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Interactions tab
// ---------------------------------------------------------------------------

function InteractionsTab({ contactId }: { contactId: string }) {
  const { data: interactions, isLoading } = useContactInteractions(contactId);

  if (isLoading) return <TabSkeleton />;
  if (!interactions || interactions.length === 0)
    return <EmptyTab message="No interactions recorded." />;

  return (
    <div className="space-y-3 py-4">
      {interactions.map((item: Interaction) => (
        <div
          key={item.id}
          className="flex items-start gap-3 border-l-2 border-border pl-4 py-2"
        >
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-xs">
                {item.type}
              </Badge>
              <span className="text-muted-foreground text-xs">
                {formatDate(item.occurred_at)}
              </span>
            </div>
            <p className="mt-1 text-sm font-medium">{item.summary}</p>
            {item.details && (
              <p className="text-muted-foreground mt-1 text-xs">{item.details}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Gifts tab
// ---------------------------------------------------------------------------

function GiftsTab({ contactId }: { contactId: string }) {
  const { data: gifts, isLoading } = useContactGifts(contactId);

  if (isLoading) return <TabSkeleton />;
  if (!gifts || gifts.length === 0) return <EmptyTab message="No gifts recorded." />;

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Description</TableHead>
          <TableHead>Direction</TableHead>
          <TableHead>Occasion</TableHead>
          <TableHead>Date</TableHead>
          <TableHead className="text-right">Value</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {gifts.map((gift: Gift) => (
          <TableRow key={gift.id}>
            <TableCell className="font-medium">{gift.description}</TableCell>
            <TableCell>
              <Badge
                variant={gift.direction === "given" ? "default" : "outline"}
                className="text-xs"
              >
                {gift.direction}
              </Badge>
            </TableCell>
            <TableCell className="text-muted-foreground text-sm">
              {gift.occasion ?? "\u2014"}
            </TableCell>
            <TableCell className="text-muted-foreground text-sm">
              {formatDate(gift.date)}
            </TableCell>
            <TableCell className="text-right tabular-nums text-sm">
              {gift.value != null ? `$${gift.value.toFixed(2)}` : "\u2014"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

// ---------------------------------------------------------------------------
// Loans tab
// ---------------------------------------------------------------------------

function statusVariant(
  status: string,
): "default" | "destructive" | "outline" | "secondary" {
  switch (status.toLowerCase()) {
    case "active":
      return "default";
    case "repaid":
      return "secondary";
    case "forgiven":
      return "outline";
    default:
      return "outline";
  }
}

function LoansTab({ contactId }: { contactId: string }) {
  const { data: loans, isLoading } = useContactLoans(contactId);

  if (isLoading) return <TabSkeleton />;
  if (!loans || loans.length === 0) return <EmptyTab message="No loans recorded." />;

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Description</TableHead>
          <TableHead>Direction</TableHead>
          <TableHead>Amount</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Date</TableHead>
          <TableHead>Due Date</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {loans.map((loan: Loan) => (
          <TableRow key={loan.id}>
            <TableCell className="font-medium">{loan.description}</TableCell>
            <TableCell>
              <Badge
                variant={loan.direction === "lent" ? "default" : "outline"}
                className="text-xs"
              >
                {loan.direction}
              </Badge>
            </TableCell>
            <TableCell className="tabular-nums text-sm">
              {loan.amount.toFixed(2)} {loan.currency}
            </TableCell>
            <TableCell>
              <Badge variant={statusVariant(loan.status)} className="text-xs">
                {loan.status}
              </Badge>
            </TableCell>
            <TableCell className="text-muted-foreground text-sm">
              {formatDate(loan.date)}
            </TableCell>
            <TableCell className="text-muted-foreground text-sm">
              {loan.due_date ? formatDate(loan.due_date) : "\u2014"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

// ---------------------------------------------------------------------------
// Activity tab
// ---------------------------------------------------------------------------

function ActivityTab({ contactId }: { contactId: string }) {
  const { data: feed, isLoading } = useContactFeed(contactId);

  if (isLoading) return <TabSkeleton />;
  if (!feed || feed.length === 0)
    return <EmptyTab message="No activity yet." />;

  return (
    <div className="space-y-2 py-4">
      {feed.map((item: ActivityFeedItem) => (
        <div
          key={item.id}
          className="flex items-center gap-3 rounded-md border px-3 py-2"
        >
          <Badge variant="outline" className="text-xs shrink-0">
            {item.action}
          </Badge>
          <span className="text-sm flex-1">
            {Object.keys(item.details).length > 0
              ? JSON.stringify(item.details)
              : "No additional details"}
          </span>
          <span className="text-muted-foreground text-xs shrink-0">
            {formatRelative(item.created_at)}
          </span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Contact detail header + info
// ---------------------------------------------------------------------------

function InfoRow({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div className="flex gap-2">
      <span className="text-muted-foreground text-sm w-24 shrink-0">{label}</span>
      <span className="text-sm">{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ContactDetailView
// ---------------------------------------------------------------------------

export default function ContactDetailView({ contact }: ContactDetailViewProps) {
  return (
    <div className="space-y-6">
      {/* Header */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between">
            <div>
              <CardTitle className="text-xl">
                {contact.full_name}
                {contact.nickname && (
                  <span className="text-muted-foreground ml-2 text-base font-normal">
                    ({contact.nickname})
                  </span>
                )}
              </CardTitle>
              {(contact.company || contact.job_title) && (
                <CardDescription className="mt-1">
                  {[contact.job_title, contact.company].filter(Boolean).join(" at ")}
                </CardDescription>
              )}
            </div>
            <div className="flex gap-1.5">
              {contact.labels.map((label) => (
                <Badge
                  key={label.id}
                  style={{
                    backgroundColor: labelStyle(label),
                    color: "#fff",
                  }}
                >
                  {label.name}
                </Badge>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-1.5">
            <InfoRow label="Email" value={contact.email} />
            <InfoRow label="Phone" value={contact.phone} />
            <InfoRow label="Address" value={contact.address} />
            <InfoRow
              label="Birthday"
              value={contact.birthday ? formatDate(contact.birthday) : null}
            />
          </div>
        </CardContent>
      </Card>

      {/* Tabs for sub-resources */}
      <Tabs defaultValue="notes">
        <TabsList>
          <TabsTrigger value="notes">Notes</TabsTrigger>
          <TabsTrigger value="interactions">Interactions</TabsTrigger>
          <TabsTrigger value="gifts">Gifts</TabsTrigger>
          <TabsTrigger value="loans">Loans</TabsTrigger>
          <TabsTrigger value="activity">Activity</TabsTrigger>
        </TabsList>

        <TabsContent value="notes">
          <NotesTab contactId={contact.id} />
        </TabsContent>
        <TabsContent value="interactions">
          <InteractionsTab contactId={contact.id} />
        </TabsContent>
        <TabsContent value="gifts">
          <GiftsTab contactId={contact.id} />
        </TabsContent>
        <TabsContent value="loans">
          <LoansTab contactId={contact.id} />
        </TabsContent>
        <TabsContent value="activity">
          <ActivityTab contactId={contact.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
