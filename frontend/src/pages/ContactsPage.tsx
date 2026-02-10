import { useState } from "react";

import type { ContactParams } from "@/api/types";
import ContactTable from "@/components/relationship/ContactTable";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useContacts, useLabels } from "@/hooks/use-contacts";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 50;

// ---------------------------------------------------------------------------
// ContactsPage
// ---------------------------------------------------------------------------

export default function ContactsPage() {
  const [search, setSearch] = useState("");
  const [activeLabel, setActiveLabel] = useState("");
  const [page, setPage] = useState(0);

  const params: ContactParams = {
    q: search || undefined,
    label: activeLabel || undefined,
    offset: page * PAGE_SIZE,
    limit: PAGE_SIZE,
  };

  const { data, isLoading } = useContacts(params);
  const { data: labels } = useLabels();

  const contacts = data?.contacts ?? [];
  const total = data?.total ?? 0;
  const hasMore = contacts.length === PAGE_SIZE && (page + 1) * PAGE_SIZE < total;

  const rangeStart = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const rangeEnd = Math.min((page + 1) * PAGE_SIZE, total);

  function handleSearchChange(value: string) {
    setSearch(value);
    setPage(0);
  }

  function handleLabelFilter(label: string) {
    setActiveLabel(label);
    setPage(0);
  }

  return (
    <div className="space-y-6">
      {/* Page heading */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Contacts</h1>
        <p className="text-muted-foreground mt-1">
          Manage your personal and professional contacts.
        </p>
      </div>

      {/* Contact table */}
      <Card>
        <CardHeader>
          <CardTitle>All Contacts</CardTitle>
          <CardDescription>
            {total > 0 ? `${total.toLocaleString()} contact${total !== 1 ? "s" : ""}` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ContactTable
            contacts={contacts}
            isLoading={isLoading}
            search={search}
            onSearchChange={handleSearchChange}
            allLabels={labels ?? []}
            activeLabel={activeLabel}
            onLabelFilter={handleLabelFilter}
          />
        </CardContent>
      </Card>

      {/* Pagination */}
      {total > 0 && (
        <div className="flex items-center justify-between">
          <p className="text-muted-foreground text-sm">
            Showing {rangeStart}–{rangeEnd} of {total.toLocaleString()}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!hasMore}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
