# Dashboard Chat Stop Handoff Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make durable dashboard-chat Stop safe across route-handoff recovery by closing every pre-spawn lease gap, pinning retry and observer behavior, and reconciling the governing contracts.

**Architecture:** A route-inbox claim is fenced by an immediate renewal and heartbeat before any anchor or recovery reconciliation can block. A second synchronous ownership checkpoint immediately before `Spawner.trigger()` ensures a displaced worker cannot begin a runtime even if ownership changed during protected I/O. Dashboard turns remain message-scoped, durable, and no-replay when an already-processing predecessor cannot be proven stopped; ordinary accepted-row recovery remains available.

**Tech Stack:** Python 3.13, asyncio, asyncpg, FastAPI/SSE, React/TypeScript, Vitest, pytest, OpenSpec Markdown.

## Global Constraints

- Work only on `fix/dashboard-chat-stop-handoff`; never alter the live root checkout or push directly to `main`.
- Preserve message-scoped Stop at `POST /api/butlers/{name}/conversation-turns/{message_id}/cancel`.
- A displaced worker must not invoke or settle a runtime; all terminal writes stay claim-fenced.
- Dashboard `processing` recovery is ambiguous/no-replay when a predecessor cannot be proven stopped; do not weaken ordinary non-dashboard recovery.
- No new dependency, migration, external action, or user message is in scope.

---

### Task 1: Rebase the existing remediation branch onto the current base

**Files:**
- Modify: existing commits on `fix/dashboard-chat-stop-handoff` through a clean rebase
- Verify: `git status --short --branch`, `git merge-base --is-ancestor origin/main HEAD`

**Interfaces:**
- Consumes: current `origin/main` and the existing PR #3624 source branch.
- Produces: a clean current-base implementation candidate.

- [ ] **Step 1: Refresh and inspect the branch**

Run: `git fetch origin --prune && git status --short --branch && git rev-parse HEAD origin/main`

Expected: a clean worktree and exact source/base SHAs.

- [ ] **Step 2: Rebase safely**

Run: `git rebase origin/main`

Expected: current-main changes and durable message-turn behavior are both preserved. Resolve only demonstrated conflicts, then use `git rebase --continue`.

- [ ] **Step 3: Verify the rebased graph**

Run: `git merge-base --is-ancestor origin/main HEAD && git diff --check origin/main...HEAD`

Expected: exit status zero and no stale-base condition.

### Task 2: Fence every route-inbox pre-spawn boundary

**Files:**
- Modify: `src/butlers/core/route_inbox.py:186-285`
- Modify: `src/butlers/core_tools/_routing.py:930-1026`
- Modify: `src/butlers/switchboard_wiring.py:395-505`
- Test: `tests/core/test_route_inbox.py`
- Test: `tests/daemon/test_route_execute_conversation_anchor.py`
- Test: `tests/daemon/test_route_execute_async_dispatch.py`

**Interfaces:**
- Consumes: `route_inbox_renew_processing_claim(pool, row_id, processing_claim_id) -> bool`.
- Produces: `route_inbox_processing_lease_heartbeat(...)` that refuses an already displaced claim and `route_inbox_wait_while_claimed(pool, row_id, processing_claim_id, lease_lost, invocation_factory)` that renews synchronously immediately before it constructs the runtime coroutine.

- [ ] **Step 1: Write failing immediate-fence coverage**

Add a unit test that patches `route_inbox_renew_processing_claim` to return `False` and proves the heartbeat context body is never entered:

```python
entered = False
with pytest.raises(RouteInboxLeaseLost):
    async with route_inbox_processing_lease_heartbeat(pool, row_id, claim_id):
        entered = True
assert entered is False
```

Run: `uv run pytest tests/core/test_route_inbox.py::test_processing_lease_heartbeat_refuses_lost_claim_before_body -q`

Expected before the fix: FAIL because the old heartbeat yields before checking ownership.

- [ ] **Step 2: Write failing direct-pre-spawn checkpoint coverage**

Add a unit test that gives `route_inbox_wait_while_claimed` a clear in-memory event but patches the database renewal to return `False`. Assert it raises `RouteInboxLeaseLost` and the invocation factory is never called:

```python
with pytest.raises(RouteInboxLeaseLost):
    await route_inbox_wait_while_claimed(pool, row_id, claim_id, asyncio.Event(), invocation)
assert invoked is False
```

Run: `uv run pytest tests/core/test_route_inbox.py::test_wait_while_claimed_fences_database_ownership_before_invocation -q`

Expected before the fix: FAIL because the old helper has no database ownership checkpoint.

- [ ] **Step 3: Write failing two-worker anchor regression**

In `tests/daemon/test_route_execute_conversation_anchor.py`, use a controllable heartbeat context and slow `conversation_get_or_create_by_thread` stub. The stub models a recovery worker reclaiming the row while anchor I/O is pending. Release it only after the second worker has claimed. Assert the first worker does not start or settle a runtime:

```python
assert heartbeat_entered_before_anchor is True
first_worker_trigger.assert_not_awaited()
first_worker_mark_processed.assert_not_awaited()
first_worker_mark_errored.assert_not_awaited()
```

Run: `uv run pytest tests/daemon/test_route_execute_conversation_anchor.py::test_reclaimed_lease_during_anchor_never_invokes_original_worker -q`

Expected before the fix: FAIL because the old hot path starts its heartbeat only after anchor I/O.

- [ ] **Step 4: Write the recovery-reconciliation boundary regression**

In `tests/daemon/test_route_execute_async_dispatch.py`, block `reconcile_route_recovery` after a recovery claim and simulate ownership loss before the potential `Spawner.trigger`. Assert no runtime and no terminal write by the displaced recovery worker.

Run: `uv run pytest tests/daemon/test_route_execute_async_dispatch.py::test_recovery_reconciliation_keeps_claim_fenced_before_spawn -q`

Expected before the fix: FAIL because recovery currently awaits reconciliation before it starts the heartbeat.

- [ ] **Step 5: Implement the smallest shared fencing primitive**

At entry to `route_inbox_processing_lease_heartbeat`, synchronously renew before yielding any body work:

```python
if not await route_inbox_renew_processing_claim(pool, row_id, processing_claim_id):
    raise RouteInboxLeaseLost(
        "route inbox processing lease was lost before protected work began"
    )
```

Change `route_inbox_wait_while_claimed` to accept `pool`, `row_id`, and `processing_claim_id`, then check both the local event and the fenced database renewal before `asyncio.ensure_future(invocation_factory())`:

```python
if lease_lost.is_set() or not await route_inbox_renew_processing_claim(
    pool, row_id, processing_claim_id
):
    lease_lost.set()
    raise RouteInboxLeaseLost("route inbox processing lease was lost before invocation")
```

- [ ] **Step 6: Keep both blocking operations under the heartbeat**

Open the heartbeat immediately after each successful claim. Move the optional conversation anchor in `_routing.py` inside its scope. Move dashboard `reconcile_route_recovery` in `switchboard_wiring.py` inside its scope. Pass the pool, row ID, and claim ID to every `route_inbox_wait_while_claimed` call; preserve current best-effort anchor behavior and all existing dashboard terminal semantics.

- [ ] **Step 7: Run focused green coverage**

Run: `uv run pytest tests/core/test_route_inbox.py tests/daemon/test_route_execute_conversation_anchor.py tests/daemon/test_route_execute_async_dispatch.py -q`

Expected: PASS, including existing anchor forwarding, normal recovery, and lease-loss behavior.

### Task 3: Pin durable Stop retry, observer, and pending-state semantics

**Files:**
- Modify/Test: `tests/api/test_conversations.py`
- Modify/Test: `tests/api/test_dashboard_turn_cancellation.py`
- Modify/Test: `frontend/src/components/chat/ChatPanel.test.tsx`
- Modify/Test: `frontend/src/components/chat/FloatingChatWidget.test.tsx`
- Modify as required: `frontend/src/api/types.ts`, `frontend/src/components/chat/send-error-utils.ts`, `src/butlers/api/routers/conversations.py`

**Interfaces:**
- Consumes: durable `claim_ingress` outcomes and SSE error codes `INGEST_IN_PROGRESS`, `SESSION_CANCELLED`, and `TURN_OUTCOME_UNKNOWN`.
- Produces: no duplicate Switchboard submission on an accepted retry, a truthful remote-cancellation observer state, and a pending/cancelling classification that does not offer a generic retry.

- [ ] **Step 1: Add the accepted-ingress retry regression**

After a prior `bind_ingress`, have `claim_ingress` return `accepted` and assert a reconnecting stream polls for the reply without a second ingestion submission:

```python
submit.assert_not_awaited()
assert "SESSION_CANCELLED" not in "".join(events)
```

Run: `uv run pytest tests/api/test_conversations.py -q`

Expected: PASS if the existing durable-claim branch is already correct; otherwise change only that duplicate-submit path.

- [ ] **Step 2: Add remote observer tests for both chat surfaces**

For each widget, feed a streaming turn an SSE `SESSION_CANCELLED` error without a local Stop click. Assert accessible owner-cancel copy, re-enabled input, and no generic failure:

```tsx
expect(screen.getByText("Cancelled by owner")).toBeInTheDocument();
expect(screen.getByRole("status")).toHaveTextContent("This turn was stopped.");
expect(screen.queryByText(/failed/i)).not.toBeInTheDocument();
```

- [ ] **Step 3: Add pending-ingress classification coverage**

Add `INGEST_IN_PROGRESS` to the frontend typed error vocabulary and test that `send-error-utils` treats it as a truthful pending/cancelling state, not a normal retry. Keep `TURN_OUTCOME_UNKNOWN` separate and honest.

Run: `cd frontend && npm test -- --run src/components/chat/ChatPanel.test.tsx src/components/chat/FloatingChatWidget.test.tsx src/components/chat/send-error-utils.test.ts`

Expected: PASS. Make the smallest implementation change only if a new assertion fails.

### Task 4: Reconcile the canonical Stop, API, and recovery contracts

**Files:**
- Modify: `openspec/specs/dashboard-chat-ui/spec.md`
- Modify: `openspec/specs/dashboard-conversations/spec.md`
- Modify: `openspec/specs/dashboard-api/spec.md`
- Modify: `about/legends-and-lore/rfcs/0001-daemon-lifecycle-and-triggers.md`
- Modify: `about/legends-and-lore/rfcs/0003-switchboard-routing-and-ingestion.md`
- Modify: `about/legends-and-lore/rfcs/0007-dashboard-and-api-surface.md`
- Modify: `docs/plans/2026-07-17-chat-send-retry-semantics.md`
- Create: `openspec/changes/harden-dashboard-chat-stop-handoff/{proposal.md,design.md,tasks.md,specs/dashboard-chat-ui/spec.md}`
- Archive: `openspec/changes/chat-stop-button-server-cancel/` after canonical reconciliation

**Interfaces:**
- Consumes: current durable message-turn implementation, endpoint response shape, and route-inbox claim state machine.
- Produces: a narrow OpenSpec remediation record plus canonical contracts that distinguish legacy conversation cancellation, message-scoped Stop, pending ingress, cancellation, unknown outcomes, and dashboard-specific recovery.

- [ ] **Step 1: Create the focused OpenSpec change**

Create `harden-dashboard-chat-stop-handoff` with proposal, design, dashboard-chat delta, and checkable tasks covering Tasks 2–4. State the exact new fence: heartbeat before any blocking claim-adjacent I/O plus a database ownership check before invocation.

- [ ] **Step 2: Make canonical specs authoritative**

Keep the message-scoped dashboard-chat scenario. Add the endpoint, immutable client message identifier, response outcomes, legacy conversation-scoped endpoint status, and all three SSE code semantics to `dashboard-conversations`. Add the conversation endpoint family to `dashboard-api` and explicitly list raw typed `ConversationCancelResponse` as an exception to the normal response envelope rather than silently contradicting it.

- [ ] **Step 3: Amend RFCs without over-scoping recovery**

RFC 0001 and RFC 0003 must describe claim fencing, pre-invocation renewal, and terminal-write fencing. They must retain ordinary accepted recovery but state that a dashboard `processing` predecessor whose runtime cannot be proven stopped is `ambiguous` and is not automatically replayed. RFC 0007 must inventory the endpoint and SSE outcomes, including the raw typed response exception.

- [ ] **Step 4: Supersede obsolete planning language and archive history**

Update the current retry plan to point to the durable Stop contract instead of describing cancellation as future work. Validate then archive the completed, obsolete conversation-scoped `chat-stop-button-server-cancel` change; never use it as normative authority.

- [ ] **Step 5: Validate documentation**

Run: `openspec validate harden-dashboard-chat-stop-handoff --strict && rg -n "/conversations/\\{conversation_id\\}/cancel" openspec about docs`

Expected: strict validation passes; any remaining old endpoint reference is clearly legacy or archival.

### Task 5: Verify, publish, and request exact-head review

**Files:**
- Verify: all files changed by Tasks 1–4

**Interfaces:**
- Consumes: a clean current-base branch and focused passing regressions.
- Produces: a pushed #3624 remediation head with exact-head CI and independent review; it does not merge the PR.

- [ ] **Step 1: Run focused and broad quality gates**

Run:

```bash
uv run pytest tests/core/test_route_inbox.py tests/daemon/test_route_execute_async_dispatch.py tests/daemon/test_route_execute_conversation_anchor.py tests/api/test_conversations.py tests/api/test_dashboard_turn_cancellation.py -q
cd frontend && npm run lint && npm run build && npm test -- --run src/components/chat/ChatPanel.test.tsx src/components/chat/FloatingChatWidget.test.tsx src/components/chat/send-error-utils.test.ts
make lint
make check-for-update-joins
git diff --check origin/main...HEAD
```

Expected: every command exits zero.

- [ ] **Step 2: Commit and update the existing PR**

Run:

```bash
git add src tests frontend openspec about docs
git commit -m "fix(dashboard): fence Stop handoff lease"
git push --force-with-lease origin fix/dashboard-chat-stop-handoff
```

Expected: the existing PR #3624 advances without a direct-main mutation.

- [ ] **Step 3: Prove exact-head readiness**

Run: `gh pr checks 3624 --watch --fail-fast`

Expected: every required check is terminal success on the same `headRefOid` returned by `gh pr view 3624 --json headRefOid,baseRefOid`. Then obtain independent exact-head review, address actionable comments, and repeat this step after any head change.

## Plan Self-Review

- Spec coverage: pre-anchor and pre-invoke fencing, recovery reconciliation, accepted retry, remote cancellation observers, pending/unknown SSE semantics, API shape, RFC drift, archival, current-base rebasing, and exact-head verification each have a concrete task.
- Placeholder scan: no TODO/TBD marker remains; every task names exact paths, interfaces, and commands.
- Type consistency: the plan keeps the existing `RouteInboxLeaseLost`, renewal primitive, message ID, and SSE vocabulary rather than adding a parallel Stop state machine.
