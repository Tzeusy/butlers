import { Link, useParams } from "react-router";

import ContactDetailView from "@/components/relationship/ContactDetailView";
import { Skeleton } from "@/components/ui/skeleton";
import { useContact } from "@/hooks/use-contacts";

// ---------------------------------------------------------------------------
// ContactDetailPage
// ---------------------------------------------------------------------------

export default function ContactDetailPage() {
  const { contactId } = useParams<{ contactId: string }>();
  const { data: contact, isLoading, error } = useContact(contactId);

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        to="/contacts"
        className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm transition-colors"
      >
        &larr; Back to Contacts
      </Link>

      {/* Content */}
      {isLoading && (
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      )}

      {error && (
        <div className="text-destructive py-12 text-center text-sm">
          Failed to load contact. {(error as Error).message}
        </div>
      )}

      {contact && <ContactDetailView contact={contact} />}
    </div>
  );
}
