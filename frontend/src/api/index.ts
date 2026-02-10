/**
 * Public API surface — re-exports from client and types.
 */

export {
  ApiError,
  apiFetch,
  getButler,
  getButlerConfig,
  getCostSummary,
  getDailyCosts,
  getButlerNotifications,
  getButlers,
  getHealth,
  getIssues,
  getNotifications,
  getNotificationStats,
  getSession,
  getTopSessions,
  getSessions,
} from "./client.ts";

export type {
  ApiMeta,
  ApiResponse,
  ButlerConfigResponse,
  ButlerSummary,
  CostSummary,
  DailyCost,
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
  TopSession,
} from "./types.ts";
