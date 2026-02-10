/**
 * Public API surface — re-exports from client and types.
 */

export { ApiError, apiFetch, getButler, getButlers, getHealth, getSession, getSessions } from "./client.ts";

export type {
  ApiMeta,
  ApiResponse,
  ButlerSummary,
  ErrorDetail,
  ErrorResponse,
  HealthResponse,
  PaginatedResponse,
  PaginationMeta,
  SessionSummary,
} from "./types.ts";
