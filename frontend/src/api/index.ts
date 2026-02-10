/**
 * Public API surface — re-exports from client and types.
 */

export {
  ApiError,
  apiFetch,
  getButler,
  getButlerConfig,
  getButlerSession,
  getButlerSessions,
  getButlerSkills,
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
  SessionSummary,
  TopSession,
  TriggerResponse,
} from "./types.ts";
