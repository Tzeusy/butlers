/**
 * Public API surface — re-exports from client and types.
 */

export {
  ApiError,
  apiFetch,
  getButler,
  getButlerNotifications,
  getButlers,
  getHealth,
  getNotifications,
  getNotificationStats,
  getSession,
  getSessions,
} from "./client.ts";

export type {
  ApiMeta,
  ApiResponse,
  ButlerSummary,
  ErrorDetail,
  ErrorResponse,
  HealthResponse,
  NotificationParams,
  NotificationStats,
  NotificationSummary,
  PaginatedResponse,
  PaginationMeta,
  SessionSummary,
} from "./types.ts";
