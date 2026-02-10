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
  Schedule,
  ScheduleCreate,
  ScheduleUpdate,
  SearchResults,
  SessionDetail,
  SessionParams,
  SessionSummary,
  StateEntry,
  StateSetRequest,
  TopSession,
  TraceDetail,
  TraceParams,
  TraceSummary,
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
// Schedules
// ---------------------------------------------------------------------------

/** Fetch all schedules for a specific butler. */
export function getButlerSchedules(name: string): Promise<ApiResponse<Schedule[]>> {
  return apiFetch<ApiResponse<Schedule[]>>(
    `/butlers/${encodeURIComponent(name)}/schedules`,
  );
}

/** Create a new schedule for a specific butler. */
export function createButlerSchedule(
  name: string,
  body: ScheduleCreate,
): Promise<ApiResponse<Record<string, unknown>>> {
  return apiFetch<ApiResponse<Record<string, unknown>>>(
    `/butlers/${encodeURIComponent(name)}/schedules`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

/** Update an existing schedule for a specific butler. */
export function updateButlerSchedule(
  name: string,
  scheduleId: string,
  body: ScheduleUpdate,
): Promise<ApiResponse<Record<string, unknown>>> {
  return apiFetch<ApiResponse<Record<string, unknown>>>(
    `/butlers/${encodeURIComponent(name)}/schedules/${encodeURIComponent(scheduleId)}`,
    {
      method: "PUT",
      body: JSON.stringify(body),
    },
  );
}

/** Delete a schedule for a specific butler. */
export function deleteButlerSchedule(
  name: string,
  scheduleId: string,
): Promise<ApiResponse<Record<string, unknown>>> {
  return apiFetch<ApiResponse<Record<string, unknown>>>(
    `/butlers/${encodeURIComponent(name)}/schedules/${encodeURIComponent(scheduleId)}`,
    {
      method: "DELETE",
    },
  );
}

/** Toggle the enabled/disabled state of a schedule. */
export function toggleButlerSchedule(
  name: string,
  scheduleId: string,
): Promise<ApiResponse<Record<string, unknown>>> {
  return apiFetch<ApiResponse<Record<string, unknown>>>(
    `/butlers/${encodeURIComponent(name)}/schedules/${encodeURIComponent(scheduleId)}/toggle`,
    {
      method: "PATCH",
    },
  );
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
// State
// ---------------------------------------------------------------------------

/** Fetch all state entries for a butler. */
export function getButlerState(name: string): Promise<ApiResponse<StateEntry[]>> {
  return apiFetch<ApiResponse<StateEntry[]>>(
    `/butlers/${encodeURIComponent(name)}/state`,
  );
}

/** Set a state value for a butler (creates or updates). */
export function setButlerState(
  name: string,
  key: string,
  value: StateSetRequest["value"],
): Promise<ApiResponse<Record<string, string>>> {
  return apiFetch<ApiResponse<Record<string, string>>>(
    `/butlers/${encodeURIComponent(name)}/state/${encodeURIComponent(key)}`,
    {
      method: "PUT",
      body: JSON.stringify({ value }),
    },
  );
}

/** Delete a state entry for a butler. */
export function deleteButlerState(
  name: string,
  key: string,
): Promise<ApiResponse<Record<string, string>>> {
  return apiFetch<ApiResponse<Record<string, string>>>(
    `/butlers/${encodeURIComponent(name)}/state/${encodeURIComponent(key)}`,
    { method: "DELETE" },
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

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

/** Search across all butlers for sessions, state, and other entities. */
export function searchAll(query: string, limit?: number): Promise<ApiResponse<SearchResults>> {
  const sp = new URLSearchParams({ q: query });
  if (limit) sp.set("limit", String(limit));
  return apiFetch<ApiResponse<SearchResults>>(`/search?${sp.toString()}`);
}

// ---------------------------------------------------------------------------
// Traces
// ---------------------------------------------------------------------------

/** Fetch a paginated list of traces across all butlers. */
export function getTraces(
  params?: TraceParams,
): Promise<PaginatedResponse<TraceSummary>> {
  const sp = new URLSearchParams();
  if (params?.offset != null) sp.set("offset", String(params.offset));
  if (params?.limit != null) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  const path = qs ? `/traces?${qs}` : "/traces";
  return apiFetch<PaginatedResponse<TraceSummary>>(path);
}

/** Fetch a single trace by ID. */
export function getTrace(traceId: string): Promise<ApiResponse<TraceDetail>> {
  return apiFetch<ApiResponse<TraceDetail>>(
    `/traces/${encodeURIComponent(traceId)}`,
  );
}
