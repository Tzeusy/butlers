"""Tests for the Google Drive module — schema, config, and registry.

Covers:
- GoogleDriveConfig validation (task 7.1)
- Module name, dependencies, migration_revisions (task 2.3 registry integration)
- tool_metadata sensitivity declarations
- Module is discoverable via default_registry()
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from butlers.modules.google_drive import (
    DEFAULT_BUTLER_FOLDER_NAME,
    DEFAULT_MAX_READ_SIZE_BYTES,
    GoogleDriveConfig,
    GoogleDriveModule,
)
from butlers.modules.registry import default_registry

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# GoogleDriveConfig validation (task 7.1)
# ---------------------------------------------------------------------------


class TestGoogleDriveConfig:
    """Validate GoogleDriveConfig Pydantic model behaviour."""

    def test_defaults(self) -> None:
        """Config with no arguments uses all defaults."""
        config = GoogleDriveConfig()
        assert config.account is None
        assert config.max_read_size_bytes == DEFAULT_MAX_READ_SIZE_BYTES
        assert config.butler_folder_name == DEFAULT_BUTLER_FOLDER_NAME

    def test_default_max_read_size(self) -> None:
        """Default max_read_size_bytes is 10 MiB."""
        assert DEFAULT_MAX_READ_SIZE_BYTES == 10 * 1024 * 1024

    def test_default_butler_folder_name(self) -> None:
        """Default butler_folder_name is 'butlers'."""
        assert DEFAULT_BUTLER_FOLDER_NAME == "butlers"

    def test_explicit_account(self) -> None:
        """Account field accepts a string email."""
        config = GoogleDriveConfig(account="user@example.com")
        assert config.account == "user@example.com"

    def test_account_none_explicit(self) -> None:
        """Account field accepts explicit None."""
        config = GoogleDriveConfig(account=None)
        assert config.account is None

    def test_custom_max_read_size(self) -> None:
        """max_read_size_bytes accepts a custom positive integer."""
        config = GoogleDriveConfig(max_read_size_bytes=5 * 1024 * 1024)
        assert config.max_read_size_bytes == 5 * 1024 * 1024

    def test_custom_butler_folder_name(self) -> None:
        """butler_folder_name accepts a custom non-empty string."""
        config = GoogleDriveConfig(butler_folder_name="my-butlers")
        assert config.butler_folder_name == "my-butlers"

    def test_extra_fields_rejected(self) -> None:
        """Extra fields are forbidden (extra='forbid')."""
        with pytest.raises(ValidationError) as exc_info:
            GoogleDriveConfig(unknown_field="oops")  # type: ignore[call-arg]
        assert "unknown_field" in str(exc_info.value)

    def test_max_read_size_zero_rejected(self) -> None:
        """max_read_size_bytes must be positive (gt=0)."""
        with pytest.raises(ValidationError) as exc_info:
            GoogleDriveConfig(max_read_size_bytes=0)
        assert "max_read_size_bytes" in str(exc_info.value)

    def test_max_read_size_negative_rejected(self) -> None:
        """max_read_size_bytes must be positive (gt=0)."""
        with pytest.raises(ValidationError) as exc_info:
            GoogleDriveConfig(max_read_size_bytes=-1)
        assert "max_read_size_bytes" in str(exc_info.value)

    def test_butler_folder_name_empty_rejected(self) -> None:
        """butler_folder_name must be non-empty (min_length=1)."""
        with pytest.raises(ValidationError) as exc_info:
            GoogleDriveConfig(butler_folder_name="")
        assert "butler_folder_name" in str(exc_info.value)


# ---------------------------------------------------------------------------
# GoogleDriveModule contract (task 2.3 — registry)
# ---------------------------------------------------------------------------


class TestGoogleDriveModule:
    """Verify module contract properties."""

    def setup_method(self) -> None:
        self.module = GoogleDriveModule()

    def test_name(self) -> None:
        """Module name is 'google_drive'."""
        assert self.module.name == "google_drive"

    def test_config_schema(self) -> None:
        """config_schema returns GoogleDriveConfig."""
        assert self.module.config_schema is GoogleDriveConfig

    def test_dependencies_empty(self) -> None:
        """Module has no dependencies."""
        assert self.module.dependencies == []

    def test_migration_revisions(self) -> None:
        """migration_revisions returns 'google_drive' branch label."""
        assert self.module.migration_revisions() == "google_drive"

    def test_tool_metadata_write_file_sensitive(self) -> None:
        """drive_write_file content arg is marked sensitive."""
        metadata = self.module.tool_metadata()
        assert "drive_write_file" in metadata
        assert metadata["drive_write_file"].arg_sensitivities.get("content") is True

    def test_tool_metadata_move_file_sensitive(self) -> None:
        """drive_move_file file_id and new_parent_id args are marked sensitive."""
        metadata = self.module.tool_metadata()
        assert "drive_move_file" in metadata
        move_meta = metadata["drive_move_file"]
        assert move_meta.arg_sensitivities.get("file_id") is True
        assert move_meta.arg_sensitivities.get("new_parent_id") is True


# ---------------------------------------------------------------------------
# Registry auto-discovery
# ---------------------------------------------------------------------------


class TestGoogleDriveModuleRegistration:
    """Verify that the google_drive module is auto-discovered by default_registry()."""

    def test_registry_contains_google_drive(self) -> None:
        """default_registry() discovers the google_drive module."""
        registry = default_registry()
        assert "google_drive" in registry.available_modules

    def test_registry_instantiation(self) -> None:
        """Registry can instantiate GoogleDriveModule via load_from_config."""
        registry = default_registry()
        modules = registry.load_from_config({"google_drive": {}})
        names = [m.name for m in modules]
        assert "google_drive" in names

    def test_registry_instantiation_with_config(self) -> None:
        """Registry passes config dict through to the module."""
        registry = default_registry()
        modules = registry.load_from_config(
            {"google_drive": {"account": "test@example.com", "max_read_size_bytes": 1024}}
        )
        gdrive = next(m for m in modules if m.name == "google_drive")
        assert isinstance(gdrive, GoogleDriveModule)


# ---------------------------------------------------------------------------
# on_startup config coercion
# ---------------------------------------------------------------------------


class TestGoogleDriveModuleStartup:
    """Verify on_startup correctly coerces raw dicts to GoogleDriveConfig."""

    @pytest.mark.asyncio
    async def test_startup_with_empty_dict(self) -> None:
        """on_startup accepts an empty dict and uses defaults."""
        module = GoogleDriveModule()
        await module.on_startup({}, db=None)
        assert module._config.account is None
        assert module._config.max_read_size_bytes == DEFAULT_MAX_READ_SIZE_BYTES

    @pytest.mark.asyncio
    async def test_startup_with_config_object(self) -> None:
        """on_startup accepts a GoogleDriveConfig instance directly."""
        module = GoogleDriveModule()
        config = GoogleDriveConfig(account="user@example.com")
        await module.on_startup(config, db=None)
        assert module._config.account == "user@example.com"

    @pytest.mark.asyncio
    async def test_startup_with_dict_fields(self) -> None:
        """on_startup coerces a dict with known fields."""
        module = GoogleDriveModule()
        await module.on_startup(
            {"account": "a@b.com", "butler_folder_name": "ai-files"},
            db=None,
        )
        assert module._config.account == "a@b.com"
        assert module._config.butler_folder_name == "ai-files"

    @pytest.mark.asyncio
    async def test_shutdown_is_noop(self) -> None:
        """on_shutdown completes without error (no resources to release yet)."""
        module = GoogleDriveModule()
        await module.on_shutdown()  # should not raise
