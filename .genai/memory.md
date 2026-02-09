# Notes to self

## Core database tables per butler

_Added: 2026-02-09 by claude-opus-4-6_

Every butler DB has three core tables created by `migrations/core/001_core.sql`: `state` (KV JSONB), `scheduled_tasks` (cron-driven), `sessions` (CC invocation log). Plus a `_migrations` tracking table. Butler-specific tables go in `migrations/<butler-name>/` and are applied after core migrations on startup.

## Project has full v1 MVP specification but no implementation code yet

_Added: 2026-02-09 by claude-opus-4-6_

As of 2026-02-09, this repo has planning docs (`PROJECT_PLAN.md`) and a complete OpenSpec change at `openspec/changes/v1-mvp-spec/` with 4 artifacts: proposal, design, 15 capability specs (~500+ test scenarios), and 90+ implementation tasks across 22 groups. No implementation code exists yet.

## OpenSpec workflow for this project

_Added: 2026-02-09 by claude-opus-4-6_

This project uses OpenSpec (experimental artifact-driven workflow) for spec management. CLI: `openspec new change`, `openspec status`, `openspec instructions`. Changes live in `openspec/changes/<name>/`. The `spec-driven` schema has 4 artifacts: proposal → design + specs (parallel) → tasks. Use `/opsx:continue` to advance through artifacts, `/opsx:apply` to implement.

## Migrations are plain SQL files, not Alembic

_Added: 2026-02-09 by claude-opus-4-6_

Despite earlier notes suggesting Alembic, the design decision (D12 in `openspec/changes/v1-mvp-spec/design.md`) chose plain ordered `.sql` files in `migrations/<butler-name>/` directories, applied lexicographically on startup. A `_migrations` tracking table records which have been applied. No migration framework dependency.

## 15 capability specs cover the full v1 MVP

_Added: 2026-02-09 by claude-opus-4-6_

The v1 MVP spec has 15 capabilities: `butler-daemon`, `module-system`, `state-store`, `task-scheduler`, `cc-spawner`, `session-log`, `switchboard`, `heartbeat`, `butler-relationship`, `butler-health`, `butler-general`, `cli-and-deployment`, `telemetry`, `butler-credentials`, `butler-skills`. Each has a `spec.md` at `openspec/changes/v1-mvp-spec/specs/<name>/spec.md`.

## Key design decisions (from design.md)

_Added: 2026-02-09 by claude-opus-4-6_

FastMCP for MCP servers. asyncpg (no ORM). croniter for cron. Click for CLI. SSE transport for inter-butler MCP. Ephemeral MCP configs lock down CC instances. Plain SQL migrations (no Alembic). OTel + Jaeger for tracing. Serial CC dispatch in v1. No auth between butlers in v1.

## Moltbot/OpenClaw as a reference architecture

_Added: 2026-02-09 by claude-opus-4-6_

Moltbot (now OpenClaw) is a comparable open-source personal AI assistant. Key lessons extracted for Butlers: deterministic session keys, concurrency caps on agent spawning, context auto-compaction, config hot-reload, per-module tool policy scoping. Butlers differentiates with PostgreSQL-backed state, strict DB isolation per butler, MCP-native protocol.
