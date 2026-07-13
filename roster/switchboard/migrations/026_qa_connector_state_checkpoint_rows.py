"""Exclude checkpoint-only registry rows from QA connector liveness.

Revision ID: sw_026
Revises: sw_025
Create Date: 2026-07-13 00:00:00.000000

``cursor_store.save_cursor`` persists checkpoints in ``connector_registry``.
Most connectors use their canonical heartbeat identity as the cursor key, but
connectors with independently advancing streams may encode an extra dimension
in that key.  Google Health, for example, uses one key per account and resource.
Those rows carry a checkpoint but never receive a heartbeat, so the original
``v_qa_connector_state`` view exposed them as connectors that had never checked
in.  ``InfraStateSource`` consequently emitted a permanent ``ConnectorOffline``
finding once the row passed its startup grace window.

Heartbeat is the sole connector self-registration mechanism.  A registry row
that has a checkpoint but has never received a heartbeat is therefore storage
state, not a connector liveness identity.  Keep such rows in
``connector_registry`` for restart-safe cursor persistence, but exclude them
from the QA liveness view.  A canonical row becomes visible automatically as
soon as its first heartbeat sets ``last_heartbeat_at``.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "sw_026"
down_revision = "sw_025"
branch_labels = None
depends_on = None

_CONNECTOR_VIEW_FQN = "public.v_qa_connector_state"

_BASE_CONNECTOR_VIEW_SQL = """
    SELECT
        connector_type,
        endpoint_identity,
        state,
        error_message,
        last_heartbeat_at,
        first_seen_at
    FROM connector_registry
    WHERE deleted_at IS NULL
      AND archived_at IS NULL
"""

_CHECKPOINT_ONLY_PREDICATE = """
      AND NOT (
          last_heartbeat_at IS NULL
          AND checkpoint_cursor IS NOT NULL
      )
"""


def upgrade() -> None:
    op.execute(
        f"CREATE OR REPLACE VIEW {_CONNECTOR_VIEW_FQN} AS"
        f"{_BASE_CONNECTOR_VIEW_SQL}{_CHECKPOINT_ONLY_PREDICATE}"
    )


def downgrade() -> None:
    op.execute(f"CREATE OR REPLACE VIEW {_CONNECTOR_VIEW_FQN} AS{_BASE_CONNECTOR_VIEW_SQL}")
