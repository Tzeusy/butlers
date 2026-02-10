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
  getIssues,
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
  Issue,
  NotificationParams,
  NotificationStats,
  NotificationSummary,
  PaginatedResponse,
  PaginationMeta,
  SessionSummary,
} from "./types.ts";
