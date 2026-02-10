/**
 * Typed fetch wrapper for the Butlers dashboard API.
 *
 * Uses native `fetch` — no external HTTP libraries required.
 */

import type {
  ApiResponse,
  ButlerConfigResponse,
  ButlerSkill,
  ButlerSummary,
  CostSummary,
  DailyCost,
  ErrorResponse,
  HealthResponse,
  Issue,
  NotificationParams,
  NotificationStats,
  NotificationSummary,
  PaginatedResponse,
  SessionDetail,
  SessionParams,
  SessionSummary,
  TopSession,
  TriggerResponse,
} from "./types.ts";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const API_BASE_URL: string =
  import.meta.env.VITE_API_URL ?? "/api";

// ---------------------------------------------------------------------------
// Error class
// ---------------------------------------------------------------------------

/** Error thrown when an API request fails. */
export class ApiError extends Error {
  /** Machine-readable error code from the backend (or a fallback). */
  readonly code: string;
  /** HTTP status code of the response. */
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

// ---------------------------------------------------------------------------
// Base fetch wrapper
// ---------------------------------------------------------------------------

/**
 * Typed fetch wrapper that prepends `API_BASE_URL`, sets JSON headers,
 * and throws {@link ApiError} on non-ok responses.
 */
export async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let code = "UNKNOWN_ERROR";
    let message = response.statusText || "Request failed";

    try {
      const body = (await response.json()) as ErrorResponse;
      if (body.error) {
        code = body.error.code;
        message = body.error.message;
      }
    } catch {
      // Response body is not valid JSON — fall through to defaults.
    }

    throw new ApiError(code, message, response.status);
  }

  return (await response.json()) as T;
}

// ---------------------------------------------------------------------------
// Endpoint functions
// ---------------------------------------------------------------------------

/** Fetch the health-check endpoint. */
export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

/** Fetch all butlers. */
export function getButlers(): Promise<ApiResponse<ButlerSummary[]>> {
  return apiFetch<ApiResponse<ButlerSummary[]>>("/butlers");
}

/** Fetch a single butler by name. */
export function getButler(name: string): Promise<ApiResponse<ButlerSummary>> {
  return apiFetch<ApiResponse<ButlerSummary>>(`/butlers/${encodeURIComponent(name)}`);
}

/** Fetch configuration files for a specific butler. */
export function getButlerConfig(name: string): Promise<ApiResponse<ButlerConfigResponse>> {
  return apiFetch<ApiResponse<ButlerConfigResponse>>(
    `/butlers/${encodeURIComponent(name)}/config`,
  );
}

/** Build a URLSearchParams from session query parameters. */
function sessionSearchParams(params?: SessionParams): URLSearchParams {
  const sp = new URLSearchParams();
  if (params?.offset != null) sp.set("offset", String(params.offset));
  if (params?.limit != null) sp.set("limit", String(params.limit));
  if (params?.butler != null && params.butler !== "") sp.set("butler", params.butler);
  if (params?.trigger_source != null && params.trigger_source !== "")
    sp.set("trigger_source", params.trigger_source);
  if (params?.status != null && params.status !== "all") sp.set("status", params.status);
  if (params?.since != null && params.since !== "") sp.set("since", params.since);
  if (params?.until != null && params.until !== "") sp.set("until", params.until);
  return sp;
}

/** Fetch a paginated list of sessions across all butlers. */
export function getSessions(
  params?: SessionParams,
): Promise<PaginatedResponse<SessionSummary>> {
  const qs = sessionSearchParams(params).toString();
  const path = qs ? `/sessions?${qs}` : "/sessions";
  return apiFetch<PaginatedResponse<SessionSummary>>(path);
}

/** Fetch a single session by ID (cross-butler). */
export function getSession(id: string): Promise<ApiResponse<SessionDetail>> {
  return apiFetch<ApiResponse<SessionDetail>>(`/sessions/${encodeURIComponent(id)}`);
}

/** Fetch sessions for a specific butler. */
export function getButlerSessions(
  name: string,
  params?: SessionParams,
): Promise<PaginatedResponse<SessionSummary>> {
  const qs = sessionSearchParams(params).toString();
  const base = `/butlers/${encodeURIComponent(name)}/sessions`;
  const path = qs ? `${base}?${qs}` : base;
  return apiFetch<PaginatedResponse<SessionSummary>>(path);
}

/** Fetch a single session by ID for a specific butler. */
export function getButlerSession(
  name: string,
  id: string,
): Promise<ApiResponse<SessionDetail>> {
  return apiFetch<ApiResponse<SessionDetail>>(
    `/butlers/${encodeURIComponent(name)}/sessions/${encodeURIComponent(id)}`,
  );
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

/** Build a URLSearchParams from notification query parameters. */
function notificationSearchParams(params?: NotificationParams): URLSearchParams {
  const sp = new URLSearchParams();
  if (params?.offset != null) sp.set("offset", String(params.offset));
  if (params?.limit != null) sp.set("limit", String(params.limit));
  if (params?.butler != null) sp.set("butler", params.butler);
  if (params?.channel != null) sp.set("channel", params.channel);
  if (params?.status != null) sp.set("status", params.status);
  if (params?.since != null) sp.set("since", params.since);
  if (params?.until != null) sp.set("until", params.until);
  return sp;
}

/** Fetch a paginated list of notifications across all butlers. */
export function getNotifications(
  params?: NotificationParams,
): Promise<PaginatedResponse<NotificationSummary>> {
  const qs = notificationSearchParams(params).toString();
  const path = qs ? `/notifications?${qs}` : "/notifications";
  return apiFetch<PaginatedResponse<NotificationSummary>>(path);
}

/** Fetch aggregate notification statistics. */
export function getNotificationStats(): Promise<ApiResponse<NotificationStats>> {
  return apiFetch<ApiResponse<NotificationStats>>("/notifications/stats");
}

/** Fetch notifications for a specific butler. */
export function getButlerNotifications(
  name: string,
  params?: NotificationParams,
): Promise<PaginatedResponse<NotificationSummary>> {
  const qs = notificationSearchParams(params).toString();
  const base = `/butlers/${encodeURIComponent(name)}/notifications`;
  const path = qs ? `${base}?${qs}` : base;
  return apiFetch<PaginatedResponse<NotificationSummary>>(path);
}

// ---------------------------------------------------------------------------
// Issues
// ---------------------------------------------------------------------------

/** Fetch active issues across all butlers. */
export function getIssues(): Promise<ApiResponse<Issue[]>> {
  return apiFetch<ApiResponse<Issue[]>>("/issues");
}

// ---------------------------------------------------------------------------
// Costs
// ---------------------------------------------------------------------------

/** Fetch aggregate cost summary, optionally scoped to a time period. */
export function getCostSummary(period?: string): Promise<ApiResponse<CostSummary>> {
  const params = period ? `?period=${period}` : "";
  return apiFetch<ApiResponse<CostSummary>>(`/costs/summary${params}`);
}

/** Fetch daily cost breakdown. */
export function getDailyCosts(): Promise<ApiResponse<DailyCost[]>> {
  return apiFetch<ApiResponse<DailyCost[]>>("/costs/daily");
}

/** Fetch most expensive sessions. */
export function getTopSessions(limit?: number): Promise<ApiResponse<TopSession[]>> {
  const params = limit ? `?limit=${limit}` : "";
  return apiFetch<ApiResponse<TopSession[]>>(`/costs/top-sessions${params}`);
}

// ---------------------------------------------------------------------------
// Skills
// ---------------------------------------------------------------------------

/** Fetch skills available to a specific butler. */
export function getButlerSkills(name: string): Promise<ApiResponse<ButlerSkill[]>> {
  return apiFetch<ApiResponse<ButlerSkill[]>>(
    `/butlers/${encodeURIComponent(name)}/skills`,
  );
}

// ---------------------------------------------------------------------------
// Trigger
// ---------------------------------------------------------------------------

/** Trigger a CC session for a specific butler. */
export function triggerButler(
  name: string,
  prompt: string,
): Promise<TriggerResponse> {
  return apiFetch<TriggerResponse>(
    `/butlers/${encodeURIComponent(name)}/trigger`,
    {
      method: "POST",
      body: JSON.stringify({ prompt }),
    },
  );
}
