---
skill: tick-diagnostics
description: Diagnose and report on butler health from tick cycle results
version: 1.0.0
author: Heartbeat Butler
tags: [diagnostics, health, monitoring, alerting]
---

# Tick Diagnostics Skill

This skill helps you analyze tick cycle results from `tick_all_butlers` and produce actionable health reports. Use this skill when processing tick cycle outcomes to identify patterns, assess system health, and determine when escalation is needed.

## Quick Start

After running `tick_all_butlers`, pass the result dictionary to this skill's diagnostic framework:

1. Classify each butler's health status
2. Detect failure patterns across cycles
3. Apply escalation rules
4. Generate summary report

## Health Status Assessment

### Status Categories

Each butler tick result falls into one of these health states:

- **Healthy (✓)**: Tick completed successfully
  - Present in `successful` list
  - No errors or timeouts
  - Butler is responsive and operational

- **Failed (✗)**: Tick returned an error
  - Present in `failed` list with error message
  - Butler responded but encountered an internal error
  - Common causes: database issues, module crashes, invalid state

- **Timeout (⏱)**: Tick did not complete within timeout window
  - Error message contains "timeout" or "deadline exceeded"
  - Butler may be overloaded or stuck in long operation
  - Requires investigation of active operations

- **Unreachable (⚠)**: Cannot connect to butler
  - Error message contains "connection refused", "connection reset", or "network unreachable"
  - Butler process may be down or port blocked
  - Most severe state requiring immediate attention

### Classification Logic

```python
def classify_health(result: dict) -> dict[str, str]:
    """Classify each butler's health status from tick results.
    
    Args:
        result: Output from tick_all_butlers with keys:
            - total: int
            - successful: list[str]
            - failed: list[dict] with "name" and "error"
    
    Returns:
        Dict mapping butler name to status: "healthy", "failed", "timeout", "unreachable"
    """
    status = {}
    
    # Mark successful butlers as healthy
    for name in result["successful"]:
        status[name] = "healthy"
    
    # Classify failed butlers by error type
    for failure in result["failed"]:
        name = failure["name"]
        error = failure["error"].lower()
        
        if any(keyword in error for keyword in ["connection refused", "connection reset", "network unreachable"]):
            status[name] = "unreachable"
        elif any(keyword in error for keyword in ["timeout", "deadline exceeded"]):
            status[name] = "timeout"
        else:
            status[name] = "failed"
    
    return status
```

## Failure Pattern Detection

### Historical Tracking

Use the state store to track failure history across tick cycles:

```python
# Retrieve historical failures
history = await state_get("tick_failure_history")  # dict[butler_name, list[timestamp]]

# Update with current failures
for failure in result["failed"]:
    name = failure["name"]
    if name not in history:
        history[name] = []
    history[name].append(datetime.now().isoformat())
    # Keep only last 20 failures
    history[name] = history[name][-20:]

await state_set("tick_failure_history", history)
```

### Consecutive Failure Detection

Identify butlers failing repeatedly in consecutive ticks:

```python
def detect_consecutive_failures(name: str, history: list[str], current_failed: bool) -> int:
    """Count consecutive failures ending at current tick.
    
    Returns number of consecutive failures (0 if currently healthy).
    """
    if not current_failed:
        return 0
    
    # Count backwards from most recent failure
    consecutive = 1
    now = datetime.now()
    
    for i in range(len(history) - 2, -1, -1):
        timestamp = datetime.fromisoformat(history[i])
        prev_timestamp = datetime.fromisoformat(history[i + 1]) if i + 1 < len(history) else now
        
        # If gap between failures > 15 minutes, not consecutive (tick cycle is 10 min)
        if (prev_timestamp - timestamp).total_seconds() > 900:
            break
        
        consecutive += 1
    
    return consecutive
```

### Pattern Recognition Rules

- **Intermittent**: 1-2 failures in last 10 ticks, no consecutive failures
  - Usually transient network issues or brief overload
  - Log and monitor, no immediate action needed

- **Degraded**: 3-5 consecutive failures
  - Butler is struggling but may recover
  - Warn and investigate

- **Critical**: 5+ consecutive failures or unreachable state
  - Butler requires immediate intervention
  - Alert and escalate

- **Chronic**: >30% failure rate over last 20 ticks (non-consecutive)
  - Systemic issue requiring architectural review
  - Document and schedule investigation

## Escalation Rules

Apply these rules to determine appropriate response level:

### Log Only (Severity: INFO)

- Single failure after successful ticks
- Successful tick after previous failure (recovery)
- Butler in "intermittent" pattern with <10% failure rate

**Action**: Record to session log, no alerts

### Warn (Severity: WARNING)

- 3 consecutive failures
- First timeout or unreachable status
- Butler crosses into "degraded" pattern

**Action**: Log warning with context, consider notification

### Alert (Severity: ERROR)

- 5+ consecutive failures
- Unreachable status persists for 2+ ticks
- Butler in "critical" pattern
- Multiple butlers failing simultaneously (>50% of total)

**Action**: Log error, send alert, page on-call if available

### Escalate (Severity: CRITICAL)

- Core infrastructure butler unreachable (switchboard)
- All butlers failing (cascade failure)
- Heartbeat butler itself unable to complete tick cycle

**Action**: Emergency escalation, investigate infrastructure

## Diagnostic Checklist

When investigating failures, check these potential causes in order:

### 1. Database Connectivity

- **Symptom**: Error contains "connection", "database", "pool", or "psycopg"
- **Check**: Can butler connect to PostgreSQL?
- **Commands**: 
  ```bash
  docker ps | grep postgres
  docker logs butler_postgres
  psql -h localhost -p 5432 -U butler -d butler_<name> -c "SELECT 1;"
  ```

### 2. Port Availability

- **Symptom**: "connection refused" or "port already in use"
- **Check**: Is butler process running? Is port blocked?
- **Commands**:
  ```bash
  docker ps | grep butler-<name>
  docker logs butler-<name>
  netstat -an | grep <port>
  ```

### 3. Resource Exhaustion

- **Symptom**: Timeouts, "out of memory", slow responses
- **Check**: Memory usage, CPU load, disk space
- **Commands**:
  ```bash
  docker stats butler-<name>
  df -h
  free -h
  ```

### 4. Process Crash

- **Symptom**: Unreachable after previously healthy
- **Check**: Container status, exit codes, crash logs
- **Commands**:
  ```bash
  docker ps -a | grep butler-<name>
  docker inspect butler-<name> | grep ExitCode
  docker logs --tail 50 butler-<name>
  ```

### 5. Module or Tool Error

- **Symptom**: Error mentions specific module or tool name
- **Check**: Module initialization logs, tool handler exceptions
- **Action**: Review butler's module configuration and recent changes

### 6. Configuration Issue

- **Symptom**: Error during startup or initialization
- **Check**: butler.toml syntax, missing environment variables
- **Action**: Validate config file and check `butlers list` output

## Summary Report Template

Generate a structured summary after each tick cycle:

```markdown
# Tick Cycle Report — {timestamp}

## Overview
- **Total Butlers**: {total}
- **Healthy**: {healthy_count} ({healthy_pct}%)
- **Failed**: {failed_count} ({failed_pct}%)
- **Overall Status**: {OK | DEGRADED | CRITICAL}

## Health Breakdown

### ✓ Healthy ({healthy_count})
{list of healthy butler names}

### ✗ Failed ({failed_count})
{for each failed butler:}
- **{butler_name}** ({status_category})
  - Error: {error_message}
  - Consecutive failures: {count}
  - Pattern: {intermittent | degraded | critical | chronic}
  - Action: {log | warn | alert | escalate}

## Patterns Detected

{if any patterns found:}
- **Degraded butlers**: {names} (3-4 consecutive failures)
- **Critical butlers**: {names} (5+ consecutive failures)
- **Chronic issues**: {names} (>30% failure rate)
- **Multi-butler failure**: {count} butlers affected (possible infrastructure issue)

{if no patterns:}
No concerning patterns detected.

## Recommended Actions

{based on escalation rules:}
1. {action item}
2. {action item}

{if all healthy:}
No action required. All butlers operating normally.

## Historical Context

- Previous tick: {timestamp}
- Failures in last 10 ticks: {count}
- Recovery rate: {pct}% (butlers recovered after failure)
```

## Usage Example

```python
# After running tick_all_butlers
result = await tick_all_butlers(pool, list_butlers_fn, tick_fn)

# 1. Classify health status
status = classify_health(result)

# 2. Load and update failure history
history = await state_get("tick_failure_history") or {}
for failure in result["failed"]:
    name = failure["name"]
    if name not in history:
        history[name] = []
    history[name].append(datetime.now().isoformat())
    history[name] = history[name][-20:]
await state_set("tick_failure_history", history)

# 3. Detect patterns and apply escalation rules
alerts = []
for name, state in status.items():
    if state == "healthy":
        continue
    
    consecutive = detect_consecutive_failures(
        name, history.get(name, []), True
    )
    
    if consecutive >= 5 or state == "unreachable":
        alerts.append({"name": name, "severity": "ERROR", "consecutive": consecutive})
    elif consecutive >= 3:
        alerts.append({"name": name, "severity": "WARNING", "consecutive": consecutive})

# 4. Generate report
report = generate_summary_report(result, status, history, alerts)

# 5. Log to session
await sessions_create({
    "type": "tick_cycle",
    "result": result,
    "status": status,
    "alerts": alerts,
    "report": report
})
```

## Progressive Disclosure

This skill is organized for quick reference during tick cycles:

1. **Quick Start** (above) — immediate guidance for common case
2. **Health Status Assessment** — classification logic and status definitions
3. **Failure Pattern Detection** — historical tracking and pattern recognition
4. **Escalation Rules** — when to log, warn, alert, or escalate
5. **Diagnostic Checklist** — systematic troubleshooting steps
6. **Summary Report Template** — structured output format

Start with Quick Start, drill down as needed based on tick results.
