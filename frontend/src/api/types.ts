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

/** Lightweight session representation for list views. */
export interface SessionSummary {
  id: string;
  prompt: string;
  trigger_source: string;
  success: boolean | null;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
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
