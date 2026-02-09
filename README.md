# Butlers

A personal AI agent framework where each **butler** is a long-running MCP server daemon that you interact with day-to-day. Butlers handle recurring tasks, manage integrations, and act on your behalf — powered by Claude Code under the hood.

## How It Works

Each butler runs as a persistent daemon with built-in infrastructure:

- **State store** — remembers things between sessions (key-value JSONB)
- **Task scheduler** — runs prompts on cron schedules (e.g., morning briefings, inbox triage)
- **Claude Code spawner** — spins up ephemeral Claude Code instances to reason and act
- **Session log** — tracks what happened and when

On top of that, butlers gain capabilities through **modules** — pluggable integrations like email, Telegram, calendar, Slack, and GitHub. Mix and match modules to build the butler you need.

## Example

A personal assistant butler configured in `butler.toml`:

```toml
[butler]
name = "assistant"
description = "Personal assistant with email and calendar"
port = 8101

[[butler.schedule]]
name = "morning-briefing"
cron = "0 8 * * *"
prompt = "Check my calendar for today, summarize meetings, and email me a briefing."

[[butler.schedule]]
name = "inbox-triage"
cron = "*/30 * * * *"
prompt = "Check for new emails. Flag anything urgent and draft replies for routine items."

[modules.email]
provider = "gmail"
address = "me@example.com"

[modules.calendar]
provider = "google"
calendar_id = "primary"
```

## Architecture

```
External Clients (MCP-compatible)
        │
        ▼
  Switchboard Butler ──── routes requests to the right butler
        │
   ┌────┼────┐
   ▼    ▼    ▼
Butler Butler Butler ──── each a persistent MCP server daemon
   │    │    │
   ▼    ▼    ▼
Claude Code instances ── ephemeral, locked-down, reason + act
```

- Each butler owns a **dedicated PostgreSQL database** (strict isolation)
- Butlers communicate only via MCP tools through the Switchboard
- A **Heartbeat Butler** calls `tick()` on every butler every 10 minutes, triggering scheduled tasks
- Butler configs are **git-based directories** with personality (`CLAUDE.md`), skills, and config (`butler.toml`)

## Tech Stack

Python 3.12+ · FastMCP · Claude Code SDK · PostgreSQL · Docker · asyncio

## Development

```bash
uv sync --dev       # Install dependencies
make check           # Lint + test
make test            # Run tests
make lint            # Lint
make format          # Format
```

## Status

Early development. See `PROJECT_PLAN.md` for the full implementation roadmap.
