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
