# Notes to self

## Core database tables per butler

_Updated: 2026-02-09 by claude-opus-4-6_

Every butler DB has three core tables: `state` (KV JSONB), `scheduled_tasks` (cron-driven), `sessions` (CC invocation log). Migrations use Alembic with multiple version chains in `alembic/versions/` — a `core` chain (applied to every butler) and per-butler chains (e.g., `relationship`, `health`). Modules contribute their own Alembic branch via `migration_revisions()`. The runtime runs `alembic.command.upgrade` programmatically at startup.

## Project has full v1 MVP specification but no implementation code yet

_Added: 2026-02-09 by claude-opus-4-6_

As of 2026-02-09, this repo has planning docs (`PROJECT_PLAN.md`) and a complete OpenSpec change at `openspec/changes/v1-mvp-spec/` with 4 artifacts: proposal, design, 15 capability specs (~500+ test scenarios), and 90+ implementation tasks across 22 groups. No implementation code exists yet.

## OpenSpec workflow for this project

_Added: 2026-02-09 by claude-opus-4-6_

This project uses OpenSpec (experimental artifact-driven workflow) for spec management. CLI: `openspec new change`, `openspec status`, `openspec instructions`. Changes live in `openspec/changes/<name>/`. The `spec-driven` schema has 4 artifacts: proposal → design + specs (parallel) → tasks. Use `/opsx:continue` to advance through artifacts, `/opsx:apply` to implement.

## Migrations use Alembic (not plain SQL files)

_Updated: 2026-02-09 by claude-opus-4-6_

Design decision D12 uses Alembic for all database migrations. Structure: `alembic/` at project root with `alembic.ini`, `env.py`, and `versions/` subdirectories per chain (`core/`, `switchboard/`, `relationship/`, `health/`, `general/`). Migrations use raw SQL via `op.execute()` — Alembic/SQLAlchemy is only used at migration time, asyncpg for all runtime queries (D3 unchanged). Module ABC uses `migration_revisions()` returning a branch label (`str | None`) instead of the old `migrations()` returning SQL statements.

## 15 capability specs cover the full v1 MVP

_Added: 2026-02-09 by claude-opus-4-6_

The v1 MVP spec has 15 capabilities: `butler-daemon`, `module-system`, `state-store`, `task-scheduler`, `cc-spawner`, `session-log`, `switchboard`, `heartbeat`, `butler-relationship`, `butler-health`, `butler-general`, `cli-and-deployment`, `telemetry`, `butler-credentials`, `butler-skills`. Each has a `spec.md` at `openspec/changes/v1-mvp-spec/specs/<name>/spec.md`.

## Key design decisions (from design.md)

_Added: 2026-02-09 by claude-opus-4-6_

FastMCP for MCP servers. asyncpg (no ORM). croniter for cron. Click for CLI. SSE transport for inter-butler MCP. Ephemeral MCP configs lock down CC instances. Alembic for migrations (raw SQL via op.execute, multi-chain). OTel + LGTM stack (Alloy/Tempo/Grafana) for observability. Serial CC dispatch in v1. No auth between butlers in v1.

## Beads backlog covers full v1 MVP (122 issues)

_Added: 2026-02-09 by claude-opus-4-6_

The v1 MVP spec has been converted to 122 beads issues under root epic `butlers-0qp`. Structure: 1 root epic → 22 milestone epics → 99 child tasks. Cross-milestone dependencies are wired (25 total). Run `bd ready` to find unblocked work. Milestones 1-4 (skeleton, config, modules, DB) are the starting point — they unblock everything downstream.

## Beads CLI: use `bd create --silent` for scripting, not `bd q`

_Added: 2026-02-09 by claude-opus-4-6_

`bd q` (quick capture) only supports `-t`, `-p`, `-l` flags. It does NOT support `--parent`, `--description`, `--acceptance`, `--design`, `--notes`, `--deps`, or `--estimate`. For scripting that needs full fields, use `bd create --silent` which outputs only the ID but accepts all flags. `bd create --silent` is the correct replacement for the `bd q` pattern shown in beads-writer skill examples.

## Moltbot/OpenClaw as a reference architecture

_Added: 2026-02-09 by claude-opus-4-6_

Moltbot (now OpenClaw) is a comparable open-source personal AI assistant. Key lessons extracted for Butlers: deterministic session keys, concurrency caps on agent spawning, context auto-compaction, config hot-reload, per-module tool policy scoping. Butlers differentiates with PostgreSQL-backed state, strict DB isolation per butler, MCP-native protocol.
