/**
 * TanStack Query hooks for the relationship / CRM API.
 */

import { useQuery } from "@tanstack/react-query";

import {
  getContact,
  getContactFeed,
  getContactGifts,
  getContactInteractions,
  getContactLoans,
  getContactNotes,
  getContacts,
  getGroups,
  getLabels,
  getUpcomingDates,
} from "@/api/index.ts";
import type { ContactParams, GroupParams } from "@/api/index.ts";

/** Fetch a paginated list of contacts. */
export function useContacts(params?: ContactParams) {
  return useQuery({
    queryKey: ["contacts", params],
    queryFn: () => getContacts(params),
  });
}

/** Fetch full detail for a single contact. */
export function useContact(contactId: string | undefined) {
  return useQuery({
    queryKey: ["contact", contactId],
    queryFn: () => getContact(contactId!),
    enabled: !!contactId,
  });
}

/** Fetch notes for a contact. */
export function useContactNotes(contactId: string | undefined) {
  return useQuery({
    queryKey: ["contact-notes", contactId],
    queryFn: () => getContactNotes(contactId!),
    enabled: !!contactId,
  });
}

/** Fetch interactions for a contact. */
export function useContactInteractions(contactId: string | undefined) {
  return useQuery({
    queryKey: ["contact-interactions", contactId],
    queryFn: () => getContactInteractions(contactId!),
    enabled: !!contactId,
  });
}

/** Fetch gifts for a contact. */
export function useContactGifts(contactId: string | undefined) {
  return useQuery({
    queryKey: ["contact-gifts", contactId],
    queryFn: () => getContactGifts(contactId!),
    enabled: !!contactId,
  });
}

/** Fetch loans for a contact. */
export function useContactLoans(contactId: string | undefined) {
  return useQuery({
    queryKey: ["contact-loans", contactId],
    queryFn: () => getContactLoans(contactId!),
    enabled: !!contactId,
  });
}

/** Fetch the activity feed for a contact. */
export function useContactFeed(contactId: string | undefined) {
  return useQuery({
    queryKey: ["contact-feed", contactId],
    queryFn: () => getContactFeed(contactId!),
    enabled: !!contactId,
  });
}

/** Fetch a paginated list of groups. */
export function useGroups(params?: GroupParams) {
  return useQuery({
    queryKey: ["groups", params],
    queryFn: () => getGroups(params),
  });
}

/** Fetch all labels. */
export function useLabels() {
  return useQuery({
    queryKey: ["labels"],
    queryFn: () => getLabels(),
  });
}

/** Fetch upcoming dates within a given number of days. */
export function useUpcomingDates(days?: number) {
  return useQuery({
    queryKey: ["upcoming-dates", days],
    queryFn: () => getUpcomingDates(days),
  });
}
