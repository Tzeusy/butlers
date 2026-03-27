"""Tests for Google Drive module — tasks 6.1–6.3 and core config/metadata behavior.

Covers:
- GoogleDriveConfig validation (6.1/7.1)
- register_tools registers all 7 MCP tools (6.1)
- tool_metadata sensitivity declarations (6.2)
- migration_revisions returns "google_drive" (6.3)
- Module ABC compliance (name, dependencies, config_schema)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from butlers.modules.base import Module, ToolMeta
from butlers.modules.google_drive import GoogleDriveConfig, GoogleDriveModule

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Config validation (task 7.1)
# ---------------------------------------------------------------------------


class TestGoogleDriveConfig:
    def test_default_config(self) -> None:
        """Default config has no account, 10 MB read limit, 'butlers' folder name."""
        cfg = GoogleDriveConfig()
        assert cfg.account is None
        assert cfg.max_read_size_bytes == 10 * 1024 * 1024
        assert cfg.butler_folder_name == "butlers"

    def test_explicit_account(self) -> None:
        cfg = GoogleDriveConfig(account="work@example.com")
        assert cfg.account == "work@example.com"

    def test_account_stripped(self) -> None:
        cfg = GoogleDriveConfig(account="  user@example.com  ")
        assert cfg.account == "user@example.com"

    def test_account_whitespace_only_becomes_none(self) -> None:
        cfg = GoogleDriveConfig(account="   ")
        assert cfg.account is None

    def test_custom_max_read_size(self) -> None:
        cfg = GoogleDriveConfig(max_read_size_bytes=5_000_000)
        assert cfg.max_read_size_bytes == 5_000_000

    def test_custom_butler_folder_name(self) -> None:
        cfg = GoogleDriveConfig(butler_folder_name="my-butler-outputs")
        assert cfg.butler_folder_name == "my-butler-outputs"

    def test_extra_fields_rejected(self) -> None:
        """Extra fields raise ValidationError (extra='forbid')."""
        with pytest.raises(ValidationError):
            GoogleDriveConfig(unknown_field="oops")  # type: ignore[call-arg]

    def test_from_dict(self) -> None:
        cfg = GoogleDriveConfig(**{"account": "test@example.com", "max_read_size_bytes": 1024})
        assert cfg.account == "test@example.com"
        assert cfg.max_read_size_bytes == 1024


# ---------------------------------------------------------------------------
# Module ABC compliance
# ---------------------------------------------------------------------------


class TestGoogleDriveModuleIdentity:
    def test_name(self) -> None:
        assert GoogleDriveModule().name == "google_drive"

    def test_dependencies_empty(self) -> None:
        assert GoogleDriveModule().dependencies == []

    def test_config_schema(self) -> None:
        assert GoogleDriveModule().config_schema is GoogleDriveConfig

    def test_is_module_subclass(self) -> None:
        assert issubclass(GoogleDriveModule, Module)

    def test_instantiation_no_args(self) -> None:
        """Module can be instantiated without arguments (registry requirement)."""
        module = GoogleDriveModule()
        assert module is not None


# ---------------------------------------------------------------------------
# migration_revisions (task 6.3)
# ---------------------------------------------------------------------------


class TestMigrationRevisions:
    def test_returns_google_drive_branch_label(self) -> None:
        """migration_revisions() returns 'google_drive' for the butler folders table."""
        module = GoogleDriveModule()
        assert module.migration_revisions() == "google_drive"

    def test_not_none(self) -> None:
        """migration_revisions() is not None (unlike modules with no DB tables)."""
        module = GoogleDriveModule()
        assert module.migration_revisions() is not None


# ---------------------------------------------------------------------------
# tool_metadata (task 6.2)
# ---------------------------------------------------------------------------


class TestToolMetadata:
    def test_drive_write_file_content_sensitive(self) -> None:
        """drive_write_file.content is declared sensitive."""
        module = GoogleDriveModule()
        meta = module.tool_metadata()
        assert "drive_write_file" in meta
        write_meta = meta["drive_write_file"]
        assert isinstance(write_meta, ToolMeta)
        assert write_meta.arg_sensitivities.get("content") is True

    def test_drive_move_file_args_sensitive(self) -> None:
        """drive_move_file.file_id and .new_parent_id are declared sensitive."""
        module = GoogleDriveModule()
        meta = module.tool_metadata()
        assert "drive_move_file" in meta
        move_meta = meta["drive_move_file"]
        assert isinstance(move_meta, ToolMeta)
        assert move_meta.arg_sensitivities.get("file_id") is True
        assert move_meta.arg_sensitivities.get("new_parent_id") is True

    def test_read_tools_not_declared(self) -> None:
        """Read-only tools are not listed in tool_metadata (no explicit declarations)."""
        module = GoogleDriveModule()
        meta = module.tool_metadata()
        for read_tool in (
            "drive_list_files",
            "drive_get_file_metadata",
            "drive_read_file",
            "drive_search_files",
        ):
            assert read_tool not in meta, (
                f"{read_tool!r} should not appear in tool_metadata "
                f"(only write/move tools are declared)"
            )

    def test_returns_dict_of_tool_meta(self) -> None:
        """tool_metadata() returns a dict mapping tool names to ToolMeta instances."""
        module = GoogleDriveModule()
        meta = module.tool_metadata()
        assert isinstance(meta, dict)
        for key, val in meta.items():
            assert isinstance(key, str)
            assert isinstance(val, ToolMeta)


# ---------------------------------------------------------------------------
# register_tools (task 6.1)
# ---------------------------------------------------------------------------


class TestRegisterTools:
    """Tests that register_tools correctly registers all 7 MCP tools."""

    async def test_all_seven_tools_registered(self) -> None:
        """All 7 Drive MCP tools must be registered."""
        module = GoogleDriveModule()
        registered_tools: list[str] = []

        mock_mcp = MagicMock()

        # Capture tool names when @mcp.tool() decorator is called
        def fake_tool_decorator():
            def decorator(fn):
                registered_tools.append(fn.__name__)
                return fn

            return decorator

        mock_mcp.tool = MagicMock(side_effect=lambda: fake_tool_decorator())

        config = GoogleDriveConfig()
        await module.register_tools(mcp=mock_mcp, config=config, db=None)

        expected_tools = {
            "drive_list_files",
            "drive_get_file_metadata",
            "drive_read_file",
            "drive_write_file",
            "drive_create_folder",
            "drive_move_file",
            "drive_search_files",
        }
        assert set(registered_tools) == expected_tools, (
            f"Expected {expected_tools}, got {set(registered_tools)}"
        )

    async def test_register_tools_exactly_seven(self) -> None:
        """Exactly 7 tools are registered (no duplicates, no extras)."""
        module = GoogleDriveModule()
        registered_tools: list[str] = []

        mock_mcp = MagicMock()

        def fake_tool_decorator():
            def decorator(fn):
                registered_tools.append(fn.__name__)
                return fn

            return decorator

        mock_mcp.tool = MagicMock(side_effect=lambda: fake_tool_decorator())

        await module.register_tools(mcp=mock_mcp, config=GoogleDriveConfig(), db=None)

        assert len(registered_tools) == 7, (
            f"Expected 7 tools, got {len(registered_tools)}: {registered_tools}"
        )

    async def test_register_tools_coerces_dict_config(self) -> None:
        """register_tools accepts a raw dict config and coerces it to GoogleDriveConfig."""
        module = GoogleDriveModule()
        registered_tools: list[str] = []

        mock_mcp = MagicMock()

        def fake_tool_decorator():
            def decorator(fn):
                registered_tools.append(fn.__name__)
                return fn

            return decorator

        mock_mcp.tool = MagicMock(side_effect=lambda: fake_tool_decorator())

        # Pass raw dict instead of GoogleDriveConfig instance
        await module.register_tools(
            mcp=mock_mcp,
            config={"account": "test@example.com"},
            db=None,
        )

        assert len(registered_tools) == 7
        assert module._config.account == "test@example.com"

    async def test_register_tools_none_config_uses_defaults(self) -> None:
        """register_tools handles None config gracefully (uses defaults)."""
        module = GoogleDriveModule()
        registered_tools: list[str] = []

        mock_mcp = MagicMock()

        def fake_tool_decorator():
            def decorator(fn):
                registered_tools.append(fn.__name__)
                return fn

            return decorator

        mock_mcp.tool = MagicMock(side_effect=lambda: fake_tool_decorator())

        await module.register_tools(mcp=mock_mcp, config=None, db=None)

        assert len(registered_tools) == 7

    async def test_register_tools_extracts_butler_name_from_db(self) -> None:
        """register_tools reads butler_name from db.butler_name when available."""
        module = GoogleDriveModule()
        registered_tools: list[str] = []

        mock_mcp = MagicMock()

        def fake_tool_decorator():
            def decorator(fn):
                registered_tools.append(fn.__name__)
                return fn

            return decorator

        mock_mcp.tool = MagicMock(side_effect=lambda: fake_tool_decorator())

        mock_db = MagicMock()
        mock_db.butler_name = "finance"
        mock_db.pool = None

        await module.register_tools(mcp=mock_mcp, config=GoogleDriveConfig(), db=mock_db)

        assert module._butler_name == "finance"


# ---------------------------------------------------------------------------
# on_startup behavior
# ---------------------------------------------------------------------------


class TestOnStartup:
    async def test_startup_without_store_does_not_raise(self) -> None:
        """on_startup with no credential store logs a warning but does not raise."""
        module = GoogleDriveModule()
        # Should complete without exception (warn instead)
        await module.on_startup(config=GoogleDriveConfig(), db=None, credential_store=None)

    async def test_startup_accepts_store_alias(self) -> None:
        """on_startup accepts 'store' keyword arg as alias for credential_store."""
        from butlers.google_credentials import MissingGoogleCredentialsError

        module = GoogleDriveModule()
        mock_store = MagicMock()

        # Patch resolve to raise MissingGoogleCredentialsError (no creds set up)
        with patch(
            "butlers.modules.google_drive.resolve_google_credentials",
            new_callable=AsyncMock,
            side_effect=MissingGoogleCredentialsError("no creds"),
        ):
            with pytest.raises(MissingGoogleCredentialsError):
                await module.on_startup(
                    config=GoogleDriveConfig(),
                    store=mock_store,
                    pool=None,
                    butler_name="test-butler",
                    server=None,
                )

    async def test_startup_sets_butler_name(self) -> None:
        """on_startup captures butler_name kwarg."""
        from butlers.google_credentials import MissingGoogleCredentialsError

        module = GoogleDriveModule()

        with patch(
            "butlers.modules.google_drive.resolve_google_credentials",
            new_callable=AsyncMock,
            side_effect=MissingGoogleCredentialsError("no creds"),
        ):
            try:
                await module.on_startup(
                    config=GoogleDriveConfig(),
                    credential_store=MagicMock(),
                    butler_name="archiver",
                )
            except MissingGoogleCredentialsError:
                pass  # expected — no valid creds

        assert module._butler_name == "archiver"

    async def test_on_shutdown_closes_http_client(self) -> None:
        """on_shutdown closes the HTTP client if it was initialized."""
        module = GoogleDriveModule()
        mock_http = AsyncMock()
        module._http = mock_http

        await module.on_shutdown()

        mock_http.aclose.assert_awaited_once()
        assert module._http is None

    async def test_on_shutdown_idempotent_when_no_client(self) -> None:
        """on_shutdown is a no-op when HTTP client was never initialized."""
        module = GoogleDriveModule()
        # Should not raise
        await module.on_shutdown()
