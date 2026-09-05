"""sessions_friction: typed friction ledger derived at session close.

Revision ID: core_220
Revises: core_219
Create Date: 2026-09-05 00:00:00.000000

bu-8cdl1.9 S2 (friction ledger + outcome-carrying self-observation). Adds the
``sessions_friction`` table to the per-butler core chain (unqualified, so it
fans out to every butler schema via the existing search_path replay — see
``core_061_runtime_config.py`` for the same pattern).

One row per typed friction episode derived deterministically from a
completed session's ``success``/``error``/``model`` columns
(``src/butlers/core/sessions.py::_classify_friction_kind`` — no LLM
judgment). A clean session writes zero rows. ``(session_id, kind, ordinal)``
is the idempotence key: ``ordinal`` distinguishes multiple episodes of the
same kind for one session, reserved for future multi-episode derivation.
"""

from __future__ import annotations

from alembic import op

revision = "core_220"
down_revision = "core_219"
branch_labels = None
depends_on = None

_KINDS = (
    "degenerate_tool_loop",
    "guardrail_termination",
    "classification_timeout",
    "recovered_error",
    "dead_end",
)


def upgrade() -> None:
    kinds_list = ", ".join(f"'{kind}'" for kind in _KINDS)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS sessions_friction (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id  UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            kind        TEXT NOT NULL,
            ordinal     INTEGER NOT NULL DEFAULT 0,
            detail      TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT sessions_friction_kind_check CHECK (kind IN ({kinds_list})),
            CONSTRAINT sessions_friction_session_kind_ordinal_key
                UNIQUE (session_id, kind, ordinal)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sessions_friction")
