"""Google Drive module — MCP tools for reading, writing, and organizing Drive files.

Provides seven MCP tools for interacting with the authenticated user's Google Drive:
- drive_list_files: List files in a folder with optional query filter
- drive_get_file_metadata: Retrieve detailed file metadata
- drive_read_file: Download text file content (with size and MIME type checks)
- drive_write_file: Create/upload a file to Drive
- drive_create_folder: Create a new folder
- drive_move_file: Move a file to a different folder
- drive_search_files: Full-text search using Drive's built-in search

Butler-produced files are organized under a ``butlers/{butler_name}/`` folder
hierarchy auto-created on first write. Folder IDs are cached in the
``google_drive_butler_folders`` table to avoid redundant API calls.

Configured via ``[modules.google_drive]`` in ``butler.toml``.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from butlers.modules.base import Module, ToolMeta

logger = logging.getLogger(__name__)

# Default maximum file size in bytes for drive_read_file (10 MiB).
DEFAULT_MAX_READ_SIZE_BYTES = 10 * 1024 * 1024  # 10485760

# Default name for the root butler folder in Drive.
DEFAULT_BUTLER_FOLDER_NAME = "butlers"


class GoogleDriveConfig(BaseModel):
    """Configuration for the Google Drive module.

    Attributes:
        account: Optional Google account email to use. When ``None``, the
            module resolves credentials from the default account linked via
            the Google OAuth flow.
        max_read_size_bytes: Maximum file size in bytes that
            ``drive_read_file`` will download. Files larger than this
            limit are rejected with an actionable error.
        butler_folder_name: Name of the root folder created at the Drive
            root to organize butler-produced files. Each butler gets a
            subfolder ``{butler_folder_name}/{butler_name}/``.
    """

    account: str | None = None
    max_read_size_bytes: int = Field(default=DEFAULT_MAX_READ_SIZE_BYTES, gt=0)
    butler_folder_name: str = Field(default=DEFAULT_BUTLER_FOLDER_NAME, min_length=1)

    model_config = ConfigDict(extra="forbid")


class GoogleDriveModule(Module):
    """Google Drive module providing MCP tools for file management.

    This module shell satisfies tasks 2.1–2.3 (config, migration, registry).
    Full MCP tool registration is implemented in tasks 3–6.
    """

    def __init__(self) -> None:
        self._config: GoogleDriveConfig = GoogleDriveConfig()

    @property
    def name(self) -> str:
        return "google_drive"

    @property
    def config_schema(self) -> type[BaseModel]:
        return GoogleDriveConfig

    @property
    def dependencies(self) -> list[str]:
        return []

    def migration_revisions(self) -> str | None:
        return "google_drive"

    def tool_metadata(self) -> dict[str, ToolMeta]:
        return {
            "drive_write_file": ToolMeta(arg_sensitivities={"content": True}),
            "drive_move_file": ToolMeta(arg_sensitivities={"file_id": True, "new_parent_id": True}),
        }

    async def on_startup(
        self,
        config: Any,
        db: Any,
        credential_store: Any = None,
        blob_store: Any = None,
    ) -> None:
        """Validate config and store for later use by tools.

        Full credential resolution and Drive API client initialization
        are implemented in task 3.2.
        """
        self._config = (
            config if isinstance(config, GoogleDriveConfig) else GoogleDriveConfig(**(config or {}))
        )

    async def on_shutdown(self) -> None:
        """Release resources held by the module.

        HTTP client teardown is implemented in task 3.3.
        """

    async def register_tools(self, mcp: Any, config: Any, db: Any) -> None:
        """Register all seven Google Drive MCP tools.

        Full tool registration is implemented in task 6.1.
        """
