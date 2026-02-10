/**
 * TypeScript interfaces matching the backend Pydantic models
 * defined in src/butlers/api/models/__init__.py.
 */

// ---------------------------------------------------------------------------
// Base response wrappers
// ---------------------------------------------------------------------------

/** Extensible metadata bag attached to every API response. */
export interface ApiMeta {
  [key: string]: unknown;
}

/** Generic API response wrapper: { data: T, meta: {...} } */
export interface ApiResponse<T> {
  data: T;
  meta: ApiMeta;
}

/** Structured error payload. */
export interface ErrorDetail {
  code: string;
  message: string;
  butler?: string | null;
  details?: Record<string, unknown> | null;
}

/** Standard error response envelope. */
export interface ErrorResponse {
  error: ErrorDetail;
}

// ---------------------------------------------------------------------------
// Pagination
// ---------------------------------------------------------------------------

/** Pagination metadata for list endpoints. */
export interface PaginationMeta {
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
}

/** API response wrapper for paginated list endpoints. */
export interface PaginatedResponse<T> {
  data: T[];
  meta: PaginationMeta;
}

// ---------------------------------------------------------------------------
// Domain summaries
// ---------------------------------------------------------------------------

/** Lightweight butler representation for list views. */
export interface ButlerSummary {
  name: string;
  status: string;
  port: number;
}

/** Butler configuration files returned by GET /api/butlers/:name/config. */
export interface ButlerConfigResponse {
  butler_toml: Record<string, unknown>;
  claude_md: string | null;
  agents_md: string | null;
  manifesto_md: string | null;
}

/** Lightweight session representation for list views. */
export interface SessionSummary {
  id: string;
  butler?: string;
  prompt: string;
  trigger_source: string;
  success: boolean | null;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
}

/** Full session detail returned by the single-session endpoint. */
export interface SessionDetail {
  id: string;
  butler: string;
  prompt: string;
  trigger_source: string;
  result: string | null;
  tool_calls: unknown[];
  duration_ms: number | null;
  trace_id: string | null;
  cost: Record<string, unknown> | null;
  started_at: string;
  completed_at: string | null;
  success: boolean | null;
  error: string | null;
  model: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  parent_session_id: string | null;
}

/** Full session detail including result and tool usage. */
export interface SessionDetail extends SessionSummary {
  result: string | null;
  tool_calls: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  model: string | null;
  error: string | null;
}

/** Query parameters for session list endpoints. */
export interface SessionParams {
  offset?: number;
  limit?: number;
  butler?: string;
  trigger_source?: string;
  status?: string; // "all" | "success" | "failed"
  since?: string;
  until?: string;
}

/** Lightweight notification representation for list views. */
export interface NotificationSummary {
  id: string;
  source_butler: string;
  channel: string;
  recipient: string | null;
  message: string;
  metadata: Record<string, unknown> | null;
  status: string;
  error: string | null;
  session_id: string | null;
  trace_id: string | null;
  created_at: string;
}

/** Health-check response. */
export interface HealthResponse {
  status: string;
}

// ---------------------------------------------------------------------------
// Traces
// ---------------------------------------------------------------------------

/** A recursive span node in a trace tree. */
export interface SpanNode {
  id: string;
  butler: string;
  prompt: string;
  trigger_source: string;
  success: boolean | null;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  model: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  parent_session_id: string | null;
  children: SpanNode[];
}

/** Lightweight trace representation for list views. */
export interface TraceSummary {
  trace_id: string;
  root_butler: string;
  span_count: number;
  total_duration_ms: number | null;
  started_at: string;
  status: string; // "success" | "failed" | "running" | "partial"
}

/** Full trace detail including the span tree. */
export interface TraceDetail extends TraceSummary {
  spans: SpanNode[];
}

/** Query parameters for trace list endpoints. */
export interface TraceParams {
  offset?: number;
  limit?: number;
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

/** Aggregate notification statistics. */
export interface NotificationStats {
  total: number;
  sent: number;
  failed: number;
  by_channel: Record<string, number>;
  by_butler: Record<string, number>;
}

/** Query parameters for notification list endpoints. */
export interface NotificationParams {
  offset?: number;
  limit?: number;
  butler?: string;
  channel?: string;
  status?: string;
  since?: string;
  until?: string;
}

// ---------------------------------------------------------------------------
// Issues
// ---------------------------------------------------------------------------

/** Active issue detected across butler infrastructure. */
export interface Issue {
  severity: string;
  type: string;
  butler: string;
  description: string;
  link: string | null;
}

// ---------------------------------------------------------------------------
// Activity / Timeline
// ---------------------------------------------------------------------------

/** A timeline event from the activity feed. */
export interface ActivityEvent {
  id: string;
  butler: string;
  type: string; // "session", "schedule", "notification", "startup", etc.
  summary: string;
  timestamp: string; // ISO 8601
  task_name?: string;
}

/** A unified timeline event from GET /api/timeline. */
export interface TimelineEvent {
  id: string;
  type: string; // "session", "error", "notification", etc.
  butler: string;
  timestamp: string; // ISO 8601
  summary: string;
  data: Record<string, unknown>;
}

/** Cursor-based pagination metadata for the timeline endpoint. */
export interface TimelineMeta {
  cursor: string | null;
  has_more: boolean;
}

/** Response shape from GET /api/timeline. */
export interface TimelineResponse {
  data: TimelineEvent[];
  meta: TimelineMeta;
}

/** Query parameters for the timeline endpoint. */
export interface TimelineParams {
  limit?: number;
  butler?: string[];
  event_type?: string[];
  before?: string;
}

// ---------------------------------------------------------------------------
// Costs
// ---------------------------------------------------------------------------

/** Aggregate cost summary across all butlers. */
export interface CostSummary {
  total_cost_usd: number;
  total_sessions: number;
  total_input_tokens: number;
  total_output_tokens: number;
  by_butler: Record<string, number>;
  by_model: Record<string, number>;
}

/** Cost data for a single day. */
export interface DailyCost {
  date: string;
  cost_usd: number;
  sessions: number;
  input_tokens: number;
  output_tokens: number;
}

/** A session ranked by cost. */
export interface TopSession {
  session_id: string;
  butler: string;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  model: string;
  started_at: string;
}

// ---------------------------------------------------------------------------
// Schedules
// ---------------------------------------------------------------------------

/** A scheduled task belonging to a butler. */
export interface Schedule {
  id: string;
  name: string;
  cron: string;
  prompt: string;
  source: string;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Payload for creating a new schedule. */
export interface ScheduleCreate {
  name: string;
  cron: string;
  prompt: string;
}

/** Payload for updating an existing schedule (all fields optional). */
export interface ScheduleUpdate {
  name?: string;
  cron?: string;
  prompt?: string;
  enabled?: boolean;
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

/** A key-value state entry from a butler's state store. */
export interface StateEntry {
  key: string;
  value: Record<string, unknown>;
  updated_at: string; // ISO 8601
}

/** Request body for setting a state value. */
export interface StateSetRequest {
  value: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

/** A single search result from the global search endpoint. */
export interface SearchResult {
  id: string;
  butler: string;
  type: string;
  title: string;
  snippet: string;
  url: string;
}

/** Grouped search results keyed by category. */
export interface SearchResults {
  sessions: SearchResult[];
  state: SearchResult[];
  [key: string]: SearchResult[];
}

/** Query parameters for the search endpoint. */
export interface SearchParams {
  q: string;
  limit?: number;
}

// ---------------------------------------------------------------------------
// Audit Log
// ---------------------------------------------------------------------------

/** A single audit log entry. */
export interface AuditEntry {
  id: string;
  butler: string;
  operation: string;
  request_summary: Record<string, unknown>;
  result: string; // "success" | "error"
  error: string | null;
  user_context: Record<string, unknown>;
  created_at: string; // ISO 8601
}

/** Query parameters for the audit log endpoint. */
export interface AuditLogParams {
  offset?: number;
  limit?: number;
  butler?: string;
  operation?: string;
  since?: string;
  until?: string;
}

// ---------------------------------------------------------------------------
// Skills
// ---------------------------------------------------------------------------

/** A skill available to a butler. */
export interface ButlerSkill {
  name: string;
  content: string;
}

// ---------------------------------------------------------------------------
// Trigger
// ---------------------------------------------------------------------------

/** Response from triggering a butler CC session. */
export interface TriggerResponse {
  session_id: string;
  success: boolean;
  output: string;
}
