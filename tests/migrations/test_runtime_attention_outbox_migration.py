"""Real-Postgres contract tests for the inert runtime-attention outbox.

REQ-runtime-attention-outbox-001 defines durable, safe episode representation
without migration-time paging or historical backfill.  REQ-database-security-007
requires effective-role (rather than source-only) proof that producers can only
perform validated appends while Switchboard owns delivery transitions.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import unquote, urlparse

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from alembic import command
from butlers.migrations import _build_alembic_config, run_migrations
from butlers.testing.migration import (
    create_migration_db,
    init_db_sql_for_dbapi,
    migration_bootstrap_db_url,
    migration_db_name,
)

docker_available = shutil.which("docker") is not None
pytestmark = [
    pytest.mark.db,
    pytest.mark.integration,
    pytest.mark.skipif(not docker_available, reason="Docker not available"),
]

_OUTBOX = "public.runtime_attention_outbox"
_MODEL_PRODUCER = "butler_general_rw"
_SWITCHBOARD = "butler_switchboard_rw"
_CONNECTOR = "connector_writer"
_FUNCTION_MODEL_BREAKER = "public.append_runtime_attention_model_breaker(bigint)"
_FUNCTION_FLEET_HALT = "public.append_runtime_attention_fleet_halt()"


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _upgrade_to_core_197(db_url: str) -> None:
    command.upgrade(_build_alembic_config(db_url, chains=["core"]), "core_197")


def _upgrade_to_core_head(db_url: str) -> None:
    command.upgrade(_build_alembic_config(db_url, chains=["core"]), "core@head")


def _rerun_actual_init_db(bootstrap_url: str, migration_url: str) -> None:
    """Execute the checked-in bootstrap source again, as production does.

    This is intentionally not a hand-written ACL approximation: the broad
    public grants in init-db must run first so the finalizer proves it repairs
    them on every rerun.
    """
    migration_role = unquote(urlparse(migration_url).username or "")
    assert migration_role
    engine = create_engine(bootstrap_url, isolation_level="AUTOCOMMIT")
    raw_connection = engine.raw_connection()
    try:
        raw_connection.autocommit = True
        with raw_connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('butlers.connecting_user', %s, false)",
                (migration_role,),
            )
            cursor.execute(init_db_sql_for_dbapi())
    finally:
        raw_connection.close()
        engine.dispose()


async def _decode_jsonb(connection: asyncpg.Connection) -> None:
    await connection.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


def _seed_legacy_breaker_edge(db_url: str) -> tuple[uuid.UUID, int]:
    """Create an already-open edge before the representation migration runs."""
    entry_id = uuid.uuid4()
    now = datetime.now(UTC)
    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO public.model_catalog (id, alias, runtime_type, model_id)
                    VALUES (:id, 'runtime-attention-legacy', 'codex', 'legacy-model')
                    """
                ),
                {"id": entry_id},
            )
            trigger_id: int | None = None
            for offset in range(5):
                trigger_id = conn.execute(
                    text(
                        """
                        INSERT INTO public.model_dispatch_attempts (
                            catalog_entry_id, ts, butler, outcome, error_code, error_message
                        )
                        VALUES (:catalog_entry_id, :ts, 'general', 'runtime_failure',
                                'RuntimeFailure', 'provider detail must never enter the outbox')
                        RETURNING id
                        """
                    ),
                    {
                        "catalog_entry_id": entry_id,
                        "ts": now - timedelta(minutes=5 - offset),
                    },
                ).scalar_one()
    finally:
        engine.dispose()
    assert trigger_id is not None
    return entry_id, trigger_id


@pytest.fixture(scope="module")
def upgraded_db_url(postgres_container) -> str:
    """An upgraded database proves the migration does not page old incidents."""
    db_url = create_migration_db(postgres_container, migration_db_name())
    _upgrade_to_core_197(db_url)
    _seed_legacy_breaker_edge(db_url)
    _upgrade_to_core_head(db_url)
    return db_url


@pytest.fixture(scope="module")
def core_only_db_url(postgres_container) -> str:
    """A fresh core-only database has no specialist-schema prerequisites."""
    db_url = create_migration_db(postgres_container, migration_db_name())
    asyncio.run(run_migrations(db_url, chain="core"))
    return db_url


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def upgraded_pool(upgraded_db_url: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(upgraded_db_url, min_size=1, max_size=3, init=_decode_jsonb)
    yield pool
    await pool.close()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def core_only_pool(core_only_db_url: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(core_only_db_url, min_size=1, max_size=2, init=_decode_jsonb)
    yield pool
    await pool.close()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def core_only_admin_pool(postgres_container, core_only_db_url: str) -> asyncpg.Pool:
    db_name = urlparse(core_only_db_url).path.lstrip("/")
    bootstrap_url = migration_bootstrap_db_url(postgres_container, db_name).replace(
        "postgresql+psycopg2://", "postgresql://", 1
    )
    pool = await asyncpg.create_pool(bootstrap_url, min_size=1, max_size=2, init=_decode_jsonb)
    yield pool
    await pool.close()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def upgraded_admin_pool(postgres_container, upgraded_db_url: str) -> asyncpg.Pool:
    db_name = urlparse(upgraded_db_url).path.lstrip("/")
    bootstrap_url = migration_bootstrap_db_url(postgres_container, db_name).replace(
        "postgresql+psycopg2://", "postgresql://", 1
    )
    pool = await asyncpg.create_pool(
        bootstrap_url,
        min_size=1,
        max_size=2,
        init=_decode_jsonb,
    )
    yield pool
    await pool.close()


async def _call_as_role(
    pool: asyncpg.Pool,
    role: str,
    statement: str,
    *args: object,
) -> object:
    async with pool.acquire() as conn:
        await conn.execute(f"SET ROLE {_quote_ident(role)}")
        try:
            return await conn.fetchval(statement, *args)
        finally:
            await conn.execute("RESET ROLE")


async def _execute_as_role(
    pool: asyncpg.Pool,
    role: str,
    statement: str,
    *args: object,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(f"SET ROLE {_quote_ident(role)}")
        try:
            await conn.execute(statement, *args)
        finally:
            await conn.execute("RESET ROLE")


async def _fetchrow_as_role(
    pool: asyncpg.Pool,
    role: str,
    statement: str,
    *args: object,
) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        await conn.execute(f"SET ROLE {_quote_ident(role)}")
        try:
            return await conn.fetchrow(statement, *args)
        finally:
            await conn.execute("RESET ROLE")


async def _seed_breaker_edge(pool: asyncpg.Pool, alias: str) -> tuple[uuid.UUID, int]:
    entry_id = uuid.uuid4()
    now = datetime.now(UTC)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO public.model_catalog (id, alias, runtime_type, model_id)
            VALUES ($1, $2, 'codex', 'runtime-attention-test-model')
            """,
            entry_id,
            alias,
        )
        trigger_id: int | None = None
        for offset in range(5):
            trigger_id = await conn.fetchval(
                """
                INSERT INTO public.model_dispatch_attempts (
                    catalog_entry_id, ts, butler, outcome, error_code, error_message
                )
                VALUES ($1, $2, 'general', 'runtime_failure', 'RuntimeFailure',
                        'unsafe provider detail must not be copied')
                RETURNING id
                """,
                entry_id,
                now - timedelta(minutes=5 - offset),
            )
    assert isinstance(trigger_id, int)
    return entry_id, trigger_id


async def _seed_fleet_halt_evidence(pool: asyncpg.Pool) -> None:
    entry_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO public.model_catalog (id, alias, runtime_type, model_id)
            VALUES ($1, 'runtime-attention-fleet-halt', 'codex', 'fleet-halt-model')
            """,
            entry_id,
        )
        await conn.execute(
            """
            INSERT INTO public.model_dispatch_attempts (
                catalog_entry_id, ts, butler, outcome, failure_reason
            )
            VALUES ($1, now(), 'general', 'quota_skip',
                    'Monthly spend ceiling reached: test evidence')
            """,
            entry_id,
        )


@pytest.mark.asyncio(loop_scope="module")
async def test_upgraded_database_creates_no_historical_runtime_attention_episode(
    upgraded_pool: asyncpg.Pool,
    upgraded_admin_pool: asyncpg.Pool,
) -> None:
    """REQ-runtime-attention-outbox-001: migration itself never backfills/pages."""
    assert (
        await upgraded_pool.fetchval(f"SELECT to_regclass('{_OUTBOX}')")
        == "runtime_attention_outbox"
    )
    assert await upgraded_admin_pool.fetchval(f"SELECT count(*) FROM {_OUTBOX}") == 0


@pytest.mark.asyncio(loop_scope="module")
async def test_core_only_database_has_guarded_outbox_without_specialist_schema(
    core_only_pool: asyncpg.Pool,
    core_only_admin_pool: asyncpg.Pool,
) -> None:
    """REQ-runtime-attention-outbox-001: core-only deployment remains migratable."""
    assert (
        await core_only_pool.fetchval(f"SELECT to_regclass('{_OUTBOX}')")
        == "runtime_attention_outbox"
    )
    assert await core_only_pool.fetchval("SELECT to_regclass('relationship.entity_facts')") is None
    assert await core_only_pool.fetchval("SELECT to_regclass('switchboard.notifications')") is None
    assert await core_only_pool.fetchval(
        """
        SELECT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = 'idx_model_dispatch_attempts_catalog_ts_id'
        )
        """
    )
    assert await core_only_pool.fetchval(
        """
        SELECT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = 'idx_model_dispatch_attempts_outcome_ts_id'
        )
        """
    )
    acl_shape = await core_only_admin_pool.fetchrow(
        """
        SELECT
            owner_role.rolcanlogin = false
                AND owner_role.rolinherit = false
                AND owner_role.rolsuper = false
                AND owner_role.rolbypassrls = false AS constrained_owner,
            model_breaker.prosecdef
                AND model_breaker.proconfig = ARRAY[
                    'search_path=pg_catalog, public, pg_temp'
                ]::text[] AS fixed_definer_path,
            fleet_halt.prosecdef
                AND fleet_halt.proconfig = ARRAY[
                    'search_path=pg_catalog, public, pg_temp'
                ]::text[] AS fixed_fleet_path,
            lease_guard.prosecdef
                AND lease_guard.proconfig = ARRAY[
                    'search_path=pg_catalog, public, pg_temp'
                ]::text[] AS fixed_lease_guard_path,
            has_table_privilege(owner_role.oid, 'public.model_catalog'::regclass, 'SELECT')
                AND has_table_privilege(
                    owner_role.oid, 'public.model_dispatch_attempts'::regclass, 'SELECT'
                )
                AND NOT has_table_privilege(
                    owner_role.oid, 'public.model_catalog'::regclass, 'INSERT'
                )
                AND NOT has_table_privilege(
                    owner_role.oid, 'public.model_dispatch_attempts'::regclass, 'UPDATE'
                )
                AND NOT has_table_privilege(
                    owner_role.oid, 'public.model_catalog'::regclass, 'DELETE'
                )
                AND NOT has_table_privilege(
                    owner_role.oid, 'public.model_dispatch_attempts'::regclass, 'DELETE'
                ) AS source_read_only,
            NOT EXISTS (
                SELECT 1
                FROM aclexplode(COALESCE(model_breaker.proacl, acldefault('f', model_breaker.proowner)))
                    AS acl
                WHERE acl.grantee = 0 AND acl.privilege_type = 'EXECUTE'
            )
                AND NOT has_function_privilege(
                    'connector_writer'::regrole,
                    'public.append_runtime_attention_model_breaker(bigint)'::regprocedure,
                    'EXECUTE'
                )
                AND NOT has_function_privilege(
                    'connector_writer'::regrole,
                    'public.append_runtime_attention_fleet_halt()'::regprocedure,
                    'EXECUTE'
                ) AS no_public_or_connector_execute,
            NOT EXISTS (
                SELECT 1
                FROM aclexplode(
                    COALESCE(admin_schema.nspacl, acldefault('n', admin_schema.nspowner))
                ) AS acl
                WHERE acl.grantee <> bootstrap_owner.oid
            )
                AND NOT EXISTS (
                    SELECT 1
                    FROM aclexplode(
                        COALESCE(
                            bootstrap_configuration.relacl,
                            acldefault('r', bootstrap_configuration.relowner)
                        )
                    ) AS acl
                    WHERE acl.grantee <> bootstrap_owner.oid
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_proc AS admin_function
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(
                            admin_function.proacl,
                            acldefault('f', admin_function.proowner)
                        )
                    ) AS acl
                    WHERE admin_function.oid IN (
                        'runtime_attention_admin.install_interface()'::regprocedure,
                        'runtime_attention_admin.finalize_interface()'::regprocedure,
                        'runtime_attention_admin.rollback_interface()'::regprocedure
                    )
                      AND acl.privilege_type = 'EXECUTE'
                      AND acl.grantee <> bootstrap_owner.oid
                ) AS bootstrap_interface_private
        FROM pg_roles AS owner_role
        JOIN pg_proc AS model_breaker
          ON model_breaker.oid = 'public.append_runtime_attention_model_breaker(bigint)'::regprocedure
        JOIN pg_proc AS fleet_halt
          ON fleet_halt.oid = 'public.append_runtime_attention_fleet_halt()'::regprocedure
        JOIN pg_proc AS lease_guard
          ON lease_guard.oid = 'public.runtime_attention_delivery_lease_guard()'::regprocedure
        JOIN pg_namespace AS admin_schema
          ON admin_schema.nspname = 'runtime_attention_admin'
        JOIN pg_roles AS bootstrap_owner ON bootstrap_owner.oid = admin_schema.nspowner
        JOIN pg_class AS bootstrap_configuration
          ON bootstrap_configuration.relnamespace = admin_schema.oid
         AND bootstrap_configuration.relname = 'bootstrap_configuration'
        WHERE owner_role.rolname = 'runtime_attention_outbox_owner'
        """
    )
    assert acl_shape is not None
    assert all(dict(acl_shape).values())


@pytest.mark.asyncio(loop_scope="module")
async def test_validated_producers_append_only_safe_server_derived_episodes(
    upgraded_pool: asyncpg.Pool,
    upgraded_admin_pool: asyncpg.Pool,
) -> None:
    """REQ-runtime-attention-outbox-001 and REQ-database-security-007."""
    entry_id, trigger_id = await _seed_breaker_edge(upgraded_pool, "runtime-attention-safe")

    episode_id = await _call_as_role(
        upgraded_pool,
        _MODEL_PRODUCER,
        "SELECT public.append_runtime_attention_model_breaker($1)",
        trigger_id,
    )
    assert isinstance(episode_id, uuid.UUID)
    # The triggering-edge uniqueness also makes a recorder retry idempotent.
    assert (
        await _call_as_role(
            upgraded_pool,
            _MODEL_PRODUCER,
            "SELECT public.append_runtime_attention_model_breaker($1)",
            trigger_id,
        )
        == episode_id
    )

    row = await upgraded_admin_pool.fetchrow(
        f"""
        SELECT source, lifecycle_state, triggering_attempt_id, source_snapshot, payload,
               claim_epoch, claim_token, manual_reissue_of
        FROM {_OUTBOX}
        WHERE id = $1
        """,
        episode_id,
    )
    assert row is not None
    assert dict(row) == {
        "source": "model_breaker",
        "lifecycle_state": "pending",
        "triggering_attempt_id": trigger_id,
        "source_snapshot": {
            "catalog_entry_id": str(entry_id),
            "alias": "runtime-attention-safe",
            "model_id": "runtime-attention-test-model",
            "triggering_attempt_id": trigger_id,
            "consecutive_failures": 5,
        },
        "payload": {
            "classification": "model_breaker_open",
            "consecutive_failures": 5,
            "door": f"/settings/models?highlight={entry_id}",
        },
        "claim_epoch": 0,
        "claim_token": None,
        "manual_reissue_of": None,
    }
    assert "unsafe provider detail" not in json.dumps(dict(row))

    await _seed_fleet_halt_evidence(upgraded_pool)
    fleet_episode_id = await _call_as_role(
        upgraded_pool,
        _MODEL_PRODUCER,
        "SELECT public.append_runtime_attention_fleet_halt()",
    )
    assert isinstance(fleet_episode_id, uuid.UUID)
    fleet_row = await upgraded_admin_pool.fetchrow(
        f"SELECT source, source_snapshot, payload FROM {_OUTBOX} WHERE id = $1",
        fleet_episode_id,
    )
    assert fleet_row is not None
    assert fleet_row["source"] == "fleet_halt"
    assert fleet_row["source_snapshot"]["denied_count"] >= 1
    assert fleet_row["payload"]["classification"] == "monthly_spend_ceiling"


@pytest.mark.asyncio(loop_scope="module")
async def test_constraints_reject_non_edge_forgery_keep_source_snapshot_and_fence_reissues(
    upgraded_pool: asyncpg.Pool,
    upgraded_admin_pool: asyncpg.Pool,
) -> None:
    """REQ-runtime-attention-outbox-001: constraints preserve durable truth."""
    entry_id = uuid.uuid4()
    async with upgraded_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO public.model_catalog (id, alias, runtime_type, model_id)
            VALUES ($1, 'runtime-attention-non-edge', 'codex', 'non-edge-model')
            """,
            entry_id,
        )
        non_edge_attempt_id = await conn.fetchval(
            """
            INSERT INTO public.model_dispatch_attempts (catalog_entry_id, butler, outcome)
            VALUES ($1, 'general', 'runtime_failure')
            RETURNING id
            """,
            entry_id,
        )
    assert isinstance(non_edge_attempt_id, int)
    with pytest.raises(asyncpg.CheckViolationError, match="breaker edge"):
        await _call_as_role(
            upgraded_pool,
            _MODEL_PRODUCER,
            "SELECT public.append_runtime_attention_model_breaker($1)",
            non_edge_attempt_id,
        )

    # Even a privileged fixture cannot create an outbox row carrying a raw
    # provider/error sentinel: the durable JSON projection is allowlisted.
    with pytest.raises(asyncpg.CheckViolationError, match="snapshot_allowlist"):
        await upgraded_admin_pool.execute(
            f"""
            INSERT INTO {_OUTBOX} (
                source, triggering_attempt_id, source_snapshot, payload
            )
            VALUES (
                'model_breaker', 999999999,
                $1::jsonb,
                $2::jsonb
            )
            """,
            {
                "catalog_entry_id": "forged",
                "alias": "forged",
                "model_id": "forged",
                "triggering_attempt_id": 999999999,
                "consecutive_failures": 5,
                "error_message": "provider secret sentinel",
            },
            {
                "classification": "model_breaker_open",
                "consecutive_failures": 5,
                "door": "/settings/models?highlight=forged",
            },
        )

    retained_entry_id, retained_trigger_id = await _seed_breaker_edge(
        upgraded_pool, "runtime-attention-retained"
    )
    retained_episode_id = await _call_as_role(
        upgraded_pool,
        _MODEL_PRODUCER,
        "SELECT public.append_runtime_attention_model_breaker($1)",
        retained_trigger_id,
    )
    assert isinstance(retained_episode_id, uuid.UUID)
    await upgraded_admin_pool.execute(
        "DELETE FROM public.model_catalog WHERE id = $1", retained_entry_id
    )
    retained = await upgraded_admin_pool.fetchrow(
        f"SELECT triggering_attempt_id, source_snapshot FROM {_OUTBOX} WHERE id = $1",
        retained_episode_id,
    )
    assert retained is not None
    assert retained["triggering_attempt_id"] == retained_trigger_id
    assert retained["source_snapshot"]["catalog_entry_id"] == str(retained_entry_id)
    with pytest.raises(asyncpg.CheckViolationError, match="snapshots and retention are immutable"):
        await upgraded_admin_pool.execute(
            f"UPDATE {_OUTBOX} SET source_snapshot = '{{}}'::jsonb WHERE id = $1",
            retained_episode_id,
        )
    with pytest.raises(asyncpg.CheckViolationError, match="snapshots and retention are immutable"):
        await upgraded_admin_pool.execute(
            f"UPDATE {_OUTBOX} SET payload = '{{}}'::jsonb WHERE id = $1",
            retained_episode_id,
        )
    with pytest.raises(asyncpg.CheckViolationError, match="snapshots and retention are immutable"):
        await upgraded_admin_pool.execute(
            f"UPDATE {_OUTBOX} "
            "SET retention_until = retention_until + interval '1 day' WHERE id = $1",
            retained_episode_id,
        )
    assert (
        await upgraded_admin_pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM public.model_dispatch_attempts WHERE id = $1)",
            retained_trigger_id,
        )
        is False
    )

    reissue_snapshot = {"reissue_of": str(retained_episode_id)}
    reissue_payload = {"classification": "manual_reissue"}
    await upgraded_admin_pool.execute(
        f"""
        INSERT INTO {_OUTBOX} (
            source, lifecycle_state, source_snapshot, payload, manual_reissue_of
        )
        VALUES ('model_breaker', 'pending', $1::jsonb, $2::jsonb, $3)
        """,
        reissue_snapshot,
        reissue_payload,
        retained_episode_id,
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await upgraded_admin_pool.execute(
            f"""
            INSERT INTO {_OUTBOX} (
                source, lifecycle_state, source_snapshot, payload, manual_reissue_of
            )
            VALUES ('model_breaker', 'pending', $1::jsonb, $2::jsonb, $3)
            """,
            reissue_snapshot,
            reissue_payload,
            retained_episode_id,
        )


@pytest.mark.asyncio(loop_scope="module")
async def test_effective_role_boundary_allows_only_validated_producers_and_switchboard_claims(
    upgraded_pool: asyncpg.Pool,
) -> None:
    """REQ-database-security-007: exercise effective PostgreSQL permissions."""
    entry_id, trigger_id = await _seed_breaker_edge(upgraded_pool, "runtime-attention-acl")
    episode_id = await _call_as_role(
        upgraded_pool,
        _MODEL_PRODUCER,
        "SELECT public.append_runtime_attention_model_breaker($1)",
        trigger_id,
    )
    assert isinstance(episode_id, uuid.UUID)

    for role in (_MODEL_PRODUCER, _CONNECTOR):
        for statement in (
            f"SELECT count(*) FROM {_OUTBOX}",
            (
                f"INSERT INTO {_OUTBOX} (source, lifecycle_state, source_snapshot, payload) "
                "VALUES ('model_breaker', 'pending', '{}'::jsonb, '{}'::jsonb)"
            ),
            f"UPDATE {_OUTBOX} SET lifecycle_state = 'failed' WHERE id = '{episode_id}'::uuid",
            f"DELETE FROM {_OUTBOX} WHERE id = '{episode_id}'::uuid",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await _execute_as_role(upgraded_pool, role, statement)

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await _call_as_role(
            upgraded_pool,
            _CONNECTOR,
            "SELECT public.append_runtime_attention_model_breaker($1)",
            trigger_id,
        )

    direct_attempt_id = await upgraded_pool.fetchval(
        "SELECT id FROM public.model_dispatch_attempts WHERE catalog_entry_id = $1 ORDER BY id DESC LIMIT 1",
        entry_id,
    )
    assert isinstance(direct_attempt_id, int)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await _call_as_role(
            upgraded_pool,
            _CONNECTOR,
            "SELECT public.append_runtime_attention_model_breaker($1)",
            direct_attempt_id,
        )

    await _execute_as_role(
        upgraded_pool,
        _SWITCHBOARD,
        f"""
        UPDATE {_OUTBOX}
        SET lifecycle_state = 'sending',
            claim_token = gen_random_uuid(),
            claim_epoch = claim_epoch + 1,
            delivery_lease_epoch = 1,
            claimed_by_instance = 'switchboard-test',
            claimed_at = now(),
            claim_expires_at = now() + interval '30 seconds'
        WHERE id = '{episode_id}'::uuid
        """,
    )
    switchboard_state = await _call_as_role(
        upgraded_pool,
        _SWITCHBOARD,
        f"SELECT lifecycle_state FROM {_OUTBOX} WHERE id = '{episode_id}'::uuid",
    )
    assert switchboard_state == "sending"
    with pytest.raises(asyncpg.CheckViolationError, match="fenced claim identity"):
        await _execute_as_role(
            upgraded_pool,
            _SWITCHBOARD,
            f"""
            UPDATE {_OUTBOX}
            SET claim_token = gen_random_uuid(), claim_epoch = claim_epoch + 1
            WHERE id = '{episode_id}'::uuid
            """,
        )


@pytest.mark.asyncio(loop_scope="module")
async def test_switchboard_cannot_skip_claim_fencing_or_regress_delivery_lease_epoch(
    upgraded_pool: asyncpg.Pool,
) -> None:
    """REQ-runtime-attention-outbox-001 fences state and singleton-lease changes."""
    entry_id, trigger_id = await _seed_breaker_edge(upgraded_pool, "runtime-attention-fences")
    episode_id = await _call_as_role(
        upgraded_pool,
        _MODEL_PRODUCER,
        "SELECT public.append_runtime_attention_model_breaker($1)",
        trigger_id,
    )
    assert isinstance(episode_id, uuid.UUID)
    assert isinstance(entry_id, uuid.UUID)

    # A terminal state cannot be written straight from pending: it must retain
    # a fresh fenced sending claim first.
    with pytest.raises(asyncpg.CheckViolationError, match="requires a fenced sending claim"):
        await _execute_as_role(
            upgraded_pool,
            _SWITCHBOARD,
            f"""
            UPDATE {_OUTBOX}
            SET lifecycle_state = 'sent', delivered_at = now()
            WHERE id = '{episode_id}'::uuid
            """,
        )

    # A new singleton lease starts at epoch one; a stale holder cannot choose
    # an arbitrary epoch or move a live fence backwards.
    with pytest.raises(asyncpg.CheckViolationError, match="lease acquisition must advance"):
        await _execute_as_role(
            upgraded_pool,
            _SWITCHBOARD,
            """
            INSERT INTO public.runtime_attention_delivery_lease (
                lease_token, lease_epoch, holder_instance, acquired_at, expires_at
            )
            VALUES (gen_random_uuid(), 9, 'switchboard-test', now(), now() + interval '30 seconds')
            """,
        )

    await _execute_as_role(
        upgraded_pool,
        _SWITCHBOARD,
        """
        INSERT INTO public.runtime_attention_delivery_lease (
            lease_token, lease_epoch, holder_instance, acquired_at, expires_at
        )
        VALUES (gen_random_uuid(), 1, 'switchboard-test', now(), now() + interval '30 seconds')
        """,
    )
    with pytest.raises(asyncpg.CheckViolationError, match="lease epoch may not move backwards"):
        await _execute_as_role(
            upgraded_pool,
            _SWITCHBOARD,
            """
            UPDATE public.runtime_attention_delivery_lease
            SET lease_epoch = 0
            WHERE lease_name = 'runtime_attention_delivery'
            """,
        )


@pytest.mark.asyncio(loop_scope="module")
async def test_concurrent_half_open_failures_emit_one_deterministic_edge(
    upgraded_pool: asyncpg.Pool,
    upgraded_admin_pool: asyncpg.Pool,
) -> None:
    """A stale breaker reopens once even when same-timestamp failures race.

    The lower id is the first ordered new failure after the stale window, so
    it is the only valid closed-to-open transition.  Concurrent calls for the
    later equal-timestamp failure must not create a duplicate episode.
    """
    entry_id = uuid.uuid4()
    stale_ts = datetime.now(UTC) - timedelta(minutes=16)
    tied_ts = datetime.now(UTC)
    async with upgraded_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO public.model_catalog (id, alias, runtime_type, model_id)
            VALUES ($1, 'runtime-attention-half-open', 'codex', 'half-open-model')
            """,
            entry_id,
        )
        for _ in range(5):
            await conn.execute(
                """
                INSERT INTO public.model_dispatch_attempts (catalog_entry_id, ts, butler, outcome)
                VALUES ($1, $2, 'general', 'runtime_failure')
                """,
                entry_id,
                stale_ts,
            )
        trigger_ids = [
            await conn.fetchval(
                """
                INSERT INTO public.model_dispatch_attempts (catalog_entry_id, ts, butler, outcome)
                VALUES ($1, $2, 'general', 'runtime_failure')
                RETURNING id
                """,
                entry_id,
                tied_ts,
            )
            for _ in range(2)
        ]
    assert all(isinstance(trigger_id, int) for trigger_id in trigger_ids)

    results = await asyncio.gather(
        *[
            _call_as_role(
                upgraded_pool,
                _MODEL_PRODUCER,
                "SELECT public.append_runtime_attention_model_breaker($1)",
                trigger_id,
            )
            for trigger_id in trigger_ids
        ],
        return_exceptions=True,
    )
    episode_ids = [result for result in results if isinstance(result, uuid.UUID)]
    assert len(episode_ids) == 1
    assert any(
        isinstance(result, asyncpg.CheckViolationError) and "already open" in str(result)
        for result in results
    )
    row = await upgraded_admin_pool.fetchrow(
        f"SELECT triggering_attempt_id FROM {_OUTBOX} WHERE id = $1", episode_ids[0]
    )
    assert row is not None
    assert row["triggering_attempt_id"] == min(trigger_ids)


def test_core_chain_is_idempotent_for_two_target_schemas_without_switchboard_dependency(
    postgres_container,
) -> None:
    """The database-global outbox installs once across two core-chain targets."""
    db_name = migration_db_name()
    db_url = create_migration_db(postgres_container, db_name)
    asyncio.run(run_migrations(db_url, chain="core", schema="general"))
    asyncio.run(run_migrations(db_url, chain="core", schema="switchboard"))

    engine = create_engine(migration_bootstrap_db_url(postgres_container, db_name))
    try:
        with engine.connect() as conn:
            assert (
                conn.execute(
                    text(
                        "SELECT count(*) FROM pg_class WHERE oid = 'public.runtime_attention_outbox'::regclass"
                    )
                ).scalar_one()
                == 1
            )
            assert (
                conn.execute(
                    text(
                        "SELECT count(*) FROM pg_constraint "
                        "WHERE conrelid = 'public.runtime_attention_outbox'::regclass AND contype = 'f'"
                    )
                ).scalar_one()
                == 0
            )
            assert (
                conn.execute(text("SELECT version_num FROM general.alembic_version")).scalar_one()
                == "core_198"
            )
            assert (
                conn.execute(
                    text("SELECT version_num FROM switchboard.alembic_version")
                ).scalar_one()
                == "core_198"
            )
    finally:
        engine.dispose()


def test_actual_init_db_rerun_repairs_function_only_acl_and_effective_roles(
    postgres_container,
) -> None:
    """Rerunning bootstrap cannot restore broad producer/connector public DML."""
    db_name = migration_db_name()
    db_url = create_migration_db(postgres_container, db_name)
    bootstrap_url = migration_bootstrap_db_url(postgres_container, db_name)
    _upgrade_to_core_head(db_url)
    _rerun_actual_init_db(bootstrap_url, db_url)
    _entry_id, trigger_id = _seed_legacy_breaker_edge(db_url)

    def execute_as(role: str | None, statement: str):
        engine = create_engine(db_url, isolation_level="AUTOCOMMIT")
        try:
            with engine.connect() as conn:
                if role is not None:
                    conn.execute(text(f"SET ROLE {_quote_ident(role)}"))
                try:
                    return conn.execute(
                        text(statement), {"trigger_id": trigger_id}
                    ).scalar_one_or_none()
                finally:
                    if role is not None:
                        conn.execute(text("RESET ROLE"))
        finally:
            engine.dispose()

    # The shared login inherits ordinary runtime memberships, but no active
    # role is not a producer identity.  ACL inheritance alone must not pass.
    with pytest.raises(DBAPIError, match="active canonical SET ROLE"):
        execute_as(None, "SELECT public.append_runtime_attention_model_breaker(:trigger_id)")

    episode_id = execute_as(
        _MODEL_PRODUCER, "SELECT public.append_runtime_attention_model_breaker(:trigger_id)"
    )
    assert isinstance(episode_id, uuid.UUID)

    for role, statement in (
        (
            _MODEL_PRODUCER,
            f"INSERT INTO {_OUTBOX} (source, source_snapshot, payload) "
            "VALUES ('model_breaker', '{}'::jsonb, '{}'::jsonb)",
        ),
        (_CONNECTOR, "SELECT public.append_runtime_attention_model_breaker(:trigger_id)"),
    ):
        with pytest.raises(DBAPIError):
            execute_as(role, statement)

    # A role with only PUBLIC grants and a deliberately nonproducer role both
    # lack the narrowly granted function interface.
    migration_role = unquote(urlparse(db_url).username or "")
    nonproducer_role = f"runtime_attention_nonproducer_{db_name}"
    public_only_role = f"runtime_attention_public_only_{db_name}"
    admin = create_engine(bootstrap_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f"CREATE ROLE {_quote_ident(nonproducer_role)} NOLOGIN"))
            conn.execute(text(f"CREATE ROLE {_quote_ident(public_only_role)} NOLOGIN"))
            conn.execute(
                text(
                    f"GRANT {_quote_ident(nonproducer_role)} TO {_quote_ident(migration_role)} WITH INHERIT TRUE"
                )
            )
            conn.execute(
                text(
                    f"GRANT {_quote_ident(nonproducer_role)} TO {_quote_ident(migration_role)} WITH SET TRUE"
                )
            )
            # Deliberately simulate an accidental direct EXECUTE grant.  The
            # function must still reject an active role outside the canonical
            # producer allowlist; ACL membership alone is not a producer
            # identity in this shared-login topology.
            conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {_quote_ident(nonproducer_role)}"))
            conn.execute(
                text(
                    "GRANT EXECUTE ON FUNCTION "
                    "public.append_runtime_attention_model_breaker(bigint) "
                    f"TO {_quote_ident(nonproducer_role)}"
                )
            )
            conn.execute(text(f"SET ROLE {_quote_ident(public_only_role)}"))
            try:
                with pytest.raises(DBAPIError):
                    conn.execute(
                        text("SELECT public.append_runtime_attention_model_breaker(:trigger_id)"),
                        {"trigger_id": trigger_id},
                    )
            finally:
                conn.execute(text("RESET ROLE"))
    finally:
        admin.dispose()
    with pytest.raises(DBAPIError, match="active canonical SET ROLE"):
        execute_as(
            nonproducer_role, "SELECT public.append_runtime_attention_model_breaker(:trigger_id)"
        )

    # Switchboard alone gets direct read/claim access, and its RLS policy also
    # requires the active role (the un-set shared-login read fails below).
    assert execute_as(_SWITCHBOARD, f"SELECT count(*) FROM {_OUTBOX}") == 1
    with pytest.raises(DBAPIError, match="SET ROLE butler_switchboard_rw"):
        execute_as(None, f"SELECT count(*) FROM {_OUTBOX}")


def test_empty_outbox_can_downgrade_and_reupgrade_through_bootstrap(
    postgres_container,
) -> None:
    """An empty inert representation is the only reversible core_198 state."""
    db_name = migration_db_name()
    db_url = create_migration_db(postgres_container, db_name)
    bootstrap_url = migration_bootstrap_db_url(postgres_container, db_name)
    _upgrade_to_core_head(db_url)
    config = _build_alembic_config(bootstrap_url, chains=["core"])
    command.downgrade(config, "core_197")
    engine = create_engine(bootstrap_url)
    try:
        with engine.connect() as conn:
            assert conn.execute(text(f"SELECT to_regclass('{_OUTBOX}') IS NULL")).scalar_one()
    finally:
        engine.dispose()
    _upgrade_to_core_head(db_url)
    engine = create_engine(bootstrap_url)
    try:
        with engine.connect() as conn:
            assert conn.execute(text(f"SELECT to_regclass('{_OUTBOX}') IS NOT NULL")).scalar_one()
    finally:
        engine.dispose()


def test_nonempty_outbox_rejects_downgrade_and_requires_forward_remediation(
    postgres_container,
) -> None:
    """REQ-runtime-attention-outbox-001: rollback never deletes durable evidence."""
    db_name = migration_db_name()
    db_url = create_migration_db(postgres_container, db_name)
    bootstrap_url = migration_bootstrap_db_url(postgres_container, db_name)
    _upgrade_to_core_head(db_url)
    engine = create_engine(bootstrap_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                        INSERT INTO {_OUTBOX} (source, fleet_halt_month, lifecycle_state, source_snapshot, payload)
                    VALUES (
                        'fleet_halt',
                        date '2026-08-01',
                        'pending',
                        jsonb_build_object(
                            'month', '2026-08', 'denied_count', 1, 'first_denied_at', NULL
                        ),
                        jsonb_build_object(
                            'classification', 'monthly_spend_ceiling',
                            'door', '/spend?outcome=quota_skip'
                        )
                    )
                    """
                )
            )
    finally:
        engine.dispose()

    config = _build_alembic_config(bootstrap_url, chains=["core"])
    with pytest.raises(DBAPIError, match="forward remediation"):
        command.downgrade(config, "core_197")

    _upgrade_to_core_head(db_url)
    engine = create_engine(bootstrap_url)
    try:
        with engine.connect() as conn:
            assert conn.execute(text(f"SELECT count(*) FROM {_OUTBOX}")).scalar_one() == 1
    finally:
        engine.dispose()
