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
  getButlerSkills,
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
  triggerButler,
} from "./client.ts";

export type {
  ApiMeta,
  ApiResponse,
  ButlerConfigResponse,
  ButlerSkill,
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
  TriggerResponse,
} from "./types.ts";
