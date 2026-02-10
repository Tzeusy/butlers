/**
 * Public API surface — re-exports from client and types.
 */

export {
  ApiError,
  apiFetch,
  getButler,
  getButlerConfig,
  getButlerNotifications,
  getButlerSession,
  getButlerSessions,
  getButlers,
  getCostSummary,
  getDailyCosts,
  getHealth,
  getIssues,
  getNotifications,
  getNotificationStats,
  getSession,
  getSessions,
  getTopSessions,
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
  SessionDetail,
  SessionParams,
  SessionSummary,
  TopSession,
} from "./types.ts";
