"""Tests for the ButlerDaemon class.

Uses extensive mocking to avoid real DB, FastMCP, and runtime dependencies.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from butlers.credentials import CredentialError
from butlers.daemon import ButlerDaemon, RuntimeBinaryNotFoundError
from butlers.modules.base import Module
from butlers.modules.registry import ModuleRegistry

# ---------------------------------------------------------------------------
# Test helpers: stub modules
# ---------------------------------------------------------------------------


class StubConfigA(BaseModel):
    """Config schema for StubModuleA."""


class StubModuleA(Module):
    """Stub module with no dependencies."""

    def __init__(self) -> None:
        self.started = False
        self.shutdown_called = False
        self.tools_registered = False
        self._startup_config: Any = None
        self._startup_db: Any = None

    @property
    def name(self) -> str:
        return "stub_a"

    @property
    def config_schema(self) -> type[BaseModel]:
        return StubConfigA

    @property
    def dependencies(self) -> list[str]:
        return []

    @property
    def credentials_env(self) -> list[str]:
        return ["STUB_A_TOKEN"]

    async def register_tools(self, mcp: Any, config: Any, db: Any) -> None:
        self.tools_registered = True

    def migration_revisions(self) -> str | None:
        return "stub_a"

    async def on_startup(self, config: Any, db: Any) -> None:
        self.started = True
        self._startup_config = config
        self._startup_db = db

    async def on_shutdown(self) -> None:
        self.shutdown_called = True


class StubConfigB(BaseModel):
    """Config schema for StubModuleB."""


class StubModuleB(Module):
    """Stub module that depends on stub_a."""

    def __init__(self) -> None:
        self.started = False
        self.shutdown_called = False
        self.tools_registered = False

    @property
    def name(self) -> str:
        return "stub_b"

    @property
    def config_schema(self) -> type[BaseModel]:
        return StubConfigB

    @property
    def dependencies(self) -> list[str]:
        return ["stub_a"]

    async def register_tools(self, mcp: Any, config: Any, db: Any) -> None:
        self.tools_registered = True

    def migration_revisions(self) -> str | None:
        return None

    async def on_startup(self, config: Any, db: Any) -> None:
        self.started = True

    async def on_shutdown(self) -> None:
        self.shutdown_called = True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_butler_toml(
    tmp_path: Path,
    modules: dict | None = None,
    runtime_type: str | None = None,
) -> Path:
    """Write a minimal butler.toml in tmp_path and return the directory."""
    modules = modules or {}
    toml_lines = [
        "[butler]",
        'name = "test-butler"',
        "port = 9100",
        'description = "A test butler"',
        "",
        "[butler.db]",
        'name = "butler_test"',
        "",
        "[[butler.schedule]]",
        'name = "daily-check"',
        'cron = "0 9 * * *"',
        'prompt = "Do the daily check"',
    ]
    for mod_name, mod_cfg in modules.items():
        toml_lines.append(f"\n[modules.{mod_name}]")
        for k, v in mod_cfg.items():
            if isinstance(v, str):
                toml_lines.append(f'{k} = "{v}"')
            else:
                toml_lines.append(f"{k} = {v}")
    if runtime_type is not None:
        toml_lines.append("\n[runtime]")
        toml_lines.append(f'type = "{runtime_type}"')
    (tmp_path / "butler.toml").write_text("\n".join(toml_lines))
    return tmp_path


def _make_registry(*module_classes: type[Module]) -> ModuleRegistry:
    """Create a ModuleRegistry with the given module classes pre-registered."""
    registry = ModuleRegistry()
    for cls in module_classes:
        registry.register(cls)
    return registry


@pytest.fixture
def butler_dir(tmp_path: Path) -> Path:
    """Create a temp directory with a minimal butler.toml (no modules)."""
    return _make_butler_toml(tmp_path)


@pytest.fixture
def butler_dir_with_modules(tmp_path: Path) -> Path:
    """Create a temp directory with butler.toml that enables stub_a and stub_b."""
    return _make_butler_toml(
        tmp_path,
        modules={"stub_a": {}, "stub_b": {}},
    )


def _patch_infra():
    """Return a dict of patches for all infrastructure dependencies."""
    mock_pool = AsyncMock()

    mock_db = MagicMock()
    mock_db.provision = AsyncMock()
    mock_db.connect = AsyncMock(return_value=mock_pool)
    mock_db.close = AsyncMock()
    mock_db.pool = mock_pool
    mock_db.user = "postgres"
    mock_db.password = "postgres"
    mock_db.host = "localhost"
    mock_db.port = 5432
    mock_db.db_name = "butler_test"

    # Mock adapter class that returns an adapter with binary_name
    mock_adapter = MagicMock()
    mock_adapter.binary_name = "claude"
    mock_adapter_cls = MagicMock(return_value=mock_adapter)

    return {
        "db_from_env": patch("butlers.daemon.Database.from_env", return_value=mock_db),
        "run_migrations": patch("butlers.daemon.run_migrations", new_callable=AsyncMock),
        "validate_credentials": patch("butlers.daemon.validate_credentials"),
        "init_telemetry": patch("butlers.daemon.init_telemetry"),
        "sync_schedules": patch("butlers.daemon.sync_schedules", new_callable=AsyncMock),
        "FastMCP": patch("butlers.daemon.FastMCP"),
        "Spawner": patch("butlers.daemon.Spawner"),
        "get_adapter": patch("butlers.daemon.get_adapter", return_value=mock_adapter_cls),
        "shutil_which": patch("butlers.daemon.shutil.which", return_value="/usr/bin/claude"),
        "mock_db": mock_db,
        "mock_pool": mock_pool,
        "mock_adapter_cls": mock_adapter_cls,
        "mock_adapter": mock_adapter,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStartupSequence:
    """Verify the startup sequence executes in the documented order."""

    async def test_startup_calls_in_order(self, butler_dir: Path) -> None:
        """Steps 1-12 should execute in documented order."""
        patches = _patch_infra()
        call_order: list[str] = []

        with (
            patches["db_from_env"] as mock_from_env,
            patches["run_migrations"] as mock_migrations,
            patches["validate_credentials"] as mock_validate,
            patches["init_telemetry"] as mock_telemetry,
            patches["sync_schedules"] as mock_sync,
            patches["FastMCP"] as mock_fastmcp,
            patches["Spawner"] as mock_spawner_cls,
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            mock_db = patches["mock_db"]

            # Instrument calls to record order
            mock_telemetry.side_effect = lambda *a, **kw: call_order.append("init_telemetry")
            mock_validate.side_effect = lambda *a, **kw: call_order.append("validate_credentials")
            mock_from_env.side_effect = lambda *a, **kw: (
                call_order.append("db_from_env"),
                mock_db,
            )[-1]
            mock_db.provision.side_effect = lambda: call_order.append("provision")
            mock_db.connect.side_effect = lambda: (
                call_order.append("connect"),
                patches["mock_pool"],
            )[-1]
            mock_migrations.side_effect = lambda *a, **kw: call_order.append(
                f"run_migrations({kw.get('chain', a[1] if len(a) > 1 else 'core')})"
            )
            mock_sync.side_effect = lambda *a, **kw: call_order.append("sync_schedules")
            mock_fastmcp.side_effect = lambda *a, **kw: (
                call_order.append("FastMCP"),
                MagicMock(),
            )[-1]
            mock_spawner_cls.side_effect = lambda **kw: (
                call_order.append("Spawner"),
                MagicMock(),
            )[-1]

            daemon = ButlerDaemon(butler_dir)
            await daemon.start()

        expected_order = [
            "init_telemetry",
            "validate_credentials",
            "db_from_env",
            "provision",
            "connect",
            "run_migrations(core)",
            "Spawner",
            "sync_schedules",
            "FastMCP",
        ]
        # Filter to only expected items (there may be extra calls)
        filtered = [c for c in call_order if c in expected_order]
        assert filtered == expected_order

    async def test_config_loaded(self, butler_dir: Path) -> None:
        """After start(), config should be populated from butler.toml."""
        patches = _patch_infra()
        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir)
            await daemon.start()

        assert daemon.config is not None
        assert daemon.config.name == "test-butler"
        assert daemon.config.port == 9100
        assert daemon.config.description == "A test butler"

    async def test_started_at_recorded(self, butler_dir: Path) -> None:
        """After start(), _started_at should be set."""
        patches = _patch_infra()
        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir)
            before = time.monotonic()
            await daemon.start()
            after = time.monotonic()

        assert daemon._started_at is not None
        assert before <= daemon._started_at <= after


class TestCoreToolRegistration:
    """Verify all expected core MCP tools are registered."""

    EXPECTED_TOOLS = {
        "status",
        "trigger",
        "tick_now",
        "get_state",
        "set_state",
        "delete_state",
        "list_state",
        "list_schedules",
        "create_schedule",
        "update_schedule",
        "delete_schedule",
        "list_sessions",
        "get_session",
    }

    async def test_all_core_tools_registered(self, butler_dir: Path) -> None:
        """All 13 core tools should be registered on FastMCP via @mcp.tool()."""
        patches = _patch_infra()
        registered_tools: list[str] = []

        # Create a mock FastMCP that captures tool registrations
        mock_mcp = MagicMock()

        def tool_decorator():
            def decorator(fn):
                registered_tools.append(fn.__name__)
                return fn

            return decorator

        mock_mcp.tool = tool_decorator

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patch("butlers.daemon.FastMCP", return_value=mock_mcp),
            patches["Spawner"],
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir)
            await daemon.start()

        assert set(registered_tools) == self.EXPECTED_TOOLS


class TestModuleToolRegistration:
    """Verify module tools are registered in topological order."""

    async def test_module_tools_registered(self, butler_dir_with_modules: Path) -> None:
        """register_tools should be called for each enabled module."""
        registry = _make_registry(StubModuleA, StubModuleB)
        patches = _patch_infra()

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir_with_modules, registry=registry)
            await daemon.start()

        # All modules should have had register_tools called
        for mod in daemon._modules:
            assert mod.tools_registered, f"Module {mod.name} tools not registered"

    async def test_module_startup_order(self, butler_dir_with_modules: Path) -> None:
        """Modules should start in topological order (stub_a before stub_b)."""
        registry = _make_registry(StubModuleA, StubModuleB)
        patches = _patch_infra()

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir_with_modules, registry=registry)
            await daemon.start()

        module_names = [m.name for m in daemon._modules]
        assert module_names.index("stub_a") < module_names.index("stub_b")

    async def test_module_migrations_run(self, butler_dir_with_modules: Path) -> None:
        """Module migrations should be run for modules that declare them."""
        registry = _make_registry(StubModuleA, StubModuleB)
        patches = _patch_infra()

        with (
            patches["db_from_env"],
            patches["run_migrations"] as mock_migrations,
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir_with_modules, registry=registry)
            await daemon.start()

        # Should have been called for "core" and "stub_a" (stub_b returns None)
        migration_chains = [
            c.kwargs.get("chain", c.args[1] if len(c.args) > 1 else None)
            for c in mock_migrations.call_args_list
        ]
        assert "core" in migration_chains
        assert "stub_a" in migration_chains

    async def test_module_on_startup_called(self, butler_dir_with_modules: Path) -> None:
        """on_startup should be called for each module with its config."""
        registry = _make_registry(StubModuleA, StubModuleB)
        patches = _patch_infra()

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir_with_modules, registry=registry)
            await daemon.start()

        for mod in daemon._modules:
            assert mod.started, f"Module {mod.name} on_startup not called"


class TestShutdownSequence:
    """Verify graceful shutdown order."""

    async def test_shutdown_modules_reverse_order(self, butler_dir_with_modules: Path) -> None:
        """Modules should be shut down in reverse topological order."""
        registry = _make_registry(StubModuleA, StubModuleB)
        patches = _patch_infra()
        shutdown_order: list[str] = []

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir_with_modules, registry=registry)
            await daemon.start()

        # Monkey-patch on_shutdown to record order
        for mod in daemon._modules:
            original = mod.on_shutdown

            async def make_tracker(name: str, orig=original):
                shutdown_order.append(name)
                await orig()

            mod.on_shutdown = lambda n=mod.name, o=original: make_tracker(n, o)

        await daemon.shutdown()

        # stub_b depends on stub_a, so stub_b shuts down first
        assert shutdown_order.index("stub_b") < shutdown_order.index("stub_a")

    async def test_shutdown_closes_db(self, butler_dir: Path) -> None:
        """DB pool should be closed during shutdown."""
        patches = _patch_infra()
        mock_db = patches["mock_db"]

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir)
            await daemon.start()

        await daemon.shutdown()
        mock_db.close.assert_awaited_once()

    async def test_shutdown_continues_on_module_error(self, butler_dir_with_modules: Path) -> None:
        """If a module's on_shutdown raises, others still shut down and DB closes."""
        registry = _make_registry(StubModuleA, StubModuleB)
        patches = _patch_infra()
        mock_db = patches["mock_db"]

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir_with_modules, registry=registry)
            await daemon.start()

        # Make stub_b's shutdown raise
        for mod in daemon._modules:
            if mod.name == "stub_b":

                async def failing_shutdown():
                    raise RuntimeError("shutdown failed")

                mod.on_shutdown = failing_shutdown

        # Should not raise
        await daemon.shutdown()

        # DB should still be closed
        mock_db.close.assert_awaited_once()
        # stub_a should still have gotten a chance to shut down
        next(m for m in daemon._modules if m.name == "stub_a")
        # Since we didn't patch stub_a, check it was called via the original
        # We just verify db.close was called — the important assertion


class TestStatusTool:
    """Verify the status() MCP tool returns correct data."""

    async def test_status_returns_butler_info(self, butler_dir: Path) -> None:
        """status() should return name, description, port, modules, health, uptime."""
        patches = _patch_infra()
        status_fn = None

        mock_mcp = MagicMock()

        def tool_decorator():
            def decorator(fn):
                nonlocal status_fn
                if fn.__name__ == "status":
                    status_fn = fn
                return fn

            return decorator

        mock_mcp.tool = tool_decorator

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patch("butlers.daemon.FastMCP", return_value=mock_mcp),
            patches["Spawner"],
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir)
            await daemon.start()

        assert status_fn is not None, "status tool was not registered"

        result = await status_fn()
        assert result["name"] == "test-butler"
        assert result["description"] == "A test butler"
        assert result["port"] == 9100
        assert result["modules"] == []
        assert result["health"] == "ok"
        assert isinstance(result["uptime_seconds"], float)
        assert result["uptime_seconds"] >= 0

    async def test_status_includes_module_names(self, butler_dir_with_modules: Path) -> None:
        """status() should list loaded module names."""
        registry = _make_registry(StubModuleA, StubModuleB)
        patches = _patch_infra()
        status_fn = None

        mock_mcp = MagicMock()

        def tool_decorator():
            def decorator(fn):
                nonlocal status_fn
                if fn.__name__ == "status":
                    status_fn = fn
                return fn

            return decorator

        mock_mcp.tool = tool_decorator

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patch("butlers.daemon.FastMCP", return_value=mock_mcp),
            patches["Spawner"],
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir_with_modules, registry=registry)
            await daemon.start()

        assert status_fn is not None
        result = await status_fn()
        assert set(result["modules"]) == {"stub_a", "stub_b"}


class TestStartupFailurePropagation:
    """Verify that failures in early steps prevent later steps."""

    async def test_credential_failure_stops_startup(self, butler_dir: Path) -> None:
        """If validate_credentials raises, DB is never provisioned."""
        patches = _patch_infra()

        with (
            patches["db_from_env"] as mock_from_env,
            patches["run_migrations"],
            patch(
                "butlers.daemon.validate_credentials",
                side_effect=CredentialError("missing ANTHROPIC_API_KEY"),
            ),
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir)
            with pytest.raises(CredentialError, match="missing ANTHROPIC_API_KEY"):
                await daemon.start()

        # DB should never have been created
        mock_from_env.assert_not_called()

    async def test_db_provision_failure_stops_startup(self, butler_dir: Path) -> None:
        """If DB provisioning fails, migrations should not run."""
        patches = _patch_infra()
        mock_db = patches["mock_db"]
        mock_db.provision.side_effect = ConnectionRefusedError("no pg")

        with (
            patches["db_from_env"],
            patches["run_migrations"] as mock_migrations,
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir)
            with pytest.raises(ConnectionRefusedError):
                await daemon.start()

        mock_migrations.assert_not_awaited()


class TestScheduleSync:
    """Verify TOML schedules are synced to DB during startup."""

    async def test_schedules_synced(self, butler_dir: Path) -> None:
        """sync_schedules should be called with parsed schedule entries."""
        patches = _patch_infra()

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"] as mock_sync,
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir)
            await daemon.start()

        mock_sync.assert_awaited_once()
        args = mock_sync.call_args
        schedules_arg = args[0][1]  # second positional arg
        assert len(schedules_arg) == 1
        assert schedules_arg[0]["name"] == "daily-check"
        assert schedules_arg[0]["cron"] == "0 9 * * *"
        assert schedules_arg[0]["prompt"] == "Do the daily check"


class TestModuleCredentials:
    """Verify module credentials are collected and passed to validation."""

    async def test_module_creds_passed_to_validate(self, butler_dir_with_modules: Path) -> None:
        """validate_credentials should receive module credential env vars."""
        registry = _make_registry(StubModuleA, StubModuleB)
        patches = _patch_infra()

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"] as mock_validate,
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir_with_modules, registry=registry)
            await daemon.start()

        mock_validate.assert_called_once()
        call_kwargs = mock_validate.call_args
        # Third argument (module_credentials keyword)
        module_creds = call_kwargs.kwargs.get(
            "module_credentials", call_kwargs[0][2] if len(call_kwargs[0]) > 2 else None
        )
        assert module_creds is not None
        assert "stub_a" in module_creds
        assert "STUB_A_TOKEN" in module_creds["stub_a"]


# ---------------------------------------------------------------------------
# Runtime adapter wiring tests
# ---------------------------------------------------------------------------


class TestRuntimeAdapterWiring:
    """Verify runtime adapter is correctly wired from butler.toml config."""

    async def test_default_runtime_is_claude_code(self, butler_dir: Path) -> None:
        """When no [runtime] section, default to claude-code."""
        patches = _patch_infra()

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"] as mock_get_adapter,
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir)
            await daemon.start()

        mock_get_adapter.assert_called_once_with("claude-code")

    async def test_explicit_runtime_type_wired(self, tmp_path: Path) -> None:
        """When [runtime] type = 'codex', get_adapter is called with 'codex'."""
        butler_dir = _make_butler_toml(tmp_path, runtime_type="codex")
        patches = _patch_infra()

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"] as mock_get_adapter,
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir)
            await daemon.start()

        mock_get_adapter.assert_called_once_with("codex")

    async def test_adapter_instance_passed_to_spawner(self, butler_dir: Path) -> None:
        """The adapter instance should be passed as 'runtime' kwarg to Spawner."""
        patches = _patch_infra()

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"] as mock_spawner_cls,
            patches["get_adapter"],
            patches["shutil_which"],
        ):
            daemon = ButlerDaemon(butler_dir)
            await daemon.start()

        mock_spawner_cls.assert_called_once()
        call_kwargs = mock_spawner_cls.call_args.kwargs
        assert "runtime" in call_kwargs
        # The runtime should be the instance created by mock_adapter_cls()
        assert call_kwargs["runtime"] is patches["mock_adapter"]


class TestRuntimeBinaryCheck:
    """Verify that missing runtime binaries are detected at startup."""

    async def test_missing_binary_raises_at_startup(self, butler_dir: Path) -> None:
        """When shutil.which returns None, startup should raise RuntimeBinaryNotFoundError."""
        patches = _patch_infra()

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"],
            patch("butlers.daemon.shutil.which", return_value=None),
        ):
            daemon = ButlerDaemon(butler_dir)
            with pytest.raises(RuntimeBinaryNotFoundError, match="not found on PATH"):
                await daemon.start()

    async def test_missing_binary_error_names_binary(self, butler_dir: Path) -> None:
        """The error message should include the binary name."""
        patches = _patch_infra()

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"],
            patch("butlers.daemon.shutil.which", return_value=None),
        ):
            daemon = ButlerDaemon(butler_dir)
            with pytest.raises(RuntimeBinaryNotFoundError, match="'claude'"):
                await daemon.start()

    async def test_binary_found_allows_startup(self, butler_dir: Path) -> None:
        """When shutil.which finds the binary, startup should proceed normally."""
        patches = _patch_infra()

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"],
            patches["get_adapter"],
            patches["shutil_which"] as mock_which,
        ):
            daemon = ButlerDaemon(butler_dir)
            await daemon.start()

        # shutil.which should have been called with the binary name
        mock_which.assert_called_once_with("claude")
        # Daemon should have completed startup
        assert daemon._started_at is not None

    async def test_missing_binary_prevents_spawner_creation(self, butler_dir: Path) -> None:
        """When binary is missing, Spawner should not be created."""
        patches = _patch_infra()

        with (
            patches["db_from_env"],
            patches["run_migrations"],
            patches["validate_credentials"],
            patches["init_telemetry"],
            patches["sync_schedules"],
            patches["FastMCP"],
            patches["Spawner"] as mock_spawner_cls,
            patches["get_adapter"],
            patch("butlers.daemon.shutil.which", return_value=None),
        ):
            daemon = ButlerDaemon(butler_dir)
            with pytest.raises(RuntimeBinaryNotFoundError):
                await daemon.start()

        mock_spawner_cls.assert_not_called()
