/**
 * TanStack Query hooks for the notifications API.
 */

import { useQuery } from "@tanstack/react-query";

import {
  getButlerNotifications,
  getNotifications,
  getNotificationStats,
} from "@/api/index.ts";
import type { NotificationParams } from "@/api/index.ts";

/** Fetch a paginated list of notifications across all butlers. */
export function useNotifications(params?: NotificationParams) {
  return useQuery({
    queryKey: ["notifications", params],
    queryFn: () => getNotifications(params),
  });
}

/** Fetch aggregate notification statistics. */
export function useNotificationStats() {
  return useQuery({
    queryKey: ["notification-stats"],
    queryFn: () => getNotificationStats(),
  });
}

/** Fetch notifications scoped to a specific butler. */
export function useButlerNotifications(
  name: string,
  params?: NotificationParams,
) {
  return useQuery({
    queryKey: ["butler-notifications", name, params],
    queryFn: () => getButlerNotifications(name, params),
    enabled: !!name,
  });
}
