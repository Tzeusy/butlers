"""Google Drive module — MCP tools for reading, writing, and organizing Drive files.

Provides 7 MCP tools for butler access to Google Drive:
- drive_list_files: list files in a folder or by query
- drive_get_file_metadata: fetch detailed metadata for a single file
- drive_read_file: download and return content for text/doc/sheet/slides files
- drive_write_file: create or upload a file (auto-creates butler folder hierarchy)
- drive_create_folder: create a folder (defaults to butler subfolder)
- drive_move_file: move a file to a new parent folder
- drive_search_files: full-text search across Drive

Butler outputs are organized under a root folder (default: "butlers/") with a
per-butler subfolder ("butlers/{butler_name}/"). Folder IDs are cached in the
google_drive_butler_folders table to avoid repeated API calls.

Credentials are resolved via resolve_google_credentials at startup. The full
"drive" scope is required (drive.readonly is insufficient because write tools
are registered).
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from butlers.google_credentials import (
    GoogleCredentials,
    MissingGoogleCredentialsError,
    resolve_google_credentials,
)
from butlers.modules.base import Module, ToolMeta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DRIVE_API_BASE = "https://www.googleapis.com/drive/v3/"
_DRIVE_UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3/"
_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
_TOKEN_REFRESH_URL = "https://oauth2.googleapis.com/token"

# Google workspace MIME types and their text export formats
_GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
_GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
_GOOGLE_SLIDES_MIME = "application/vnd.google-apps.presentation"
_GOOGLE_FOLDER_MIME = "application/vnd.google-apps.folder"
_GOOGLE_MIME_EXPORTS: dict[str, str] = {
    _GOOGLE_DOC_MIME: "text/plain",
    _GOOGLE_SHEET_MIME: "text/csv",
    _GOOGLE_SLIDES_MIME: "text/plain",
}

# MIME inference from extension (spec §5.4)
_EXT_MIME_MAP: dict[str, str] = {
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".md": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
}

_DEFAULT_TIMEOUT_S = 30.0
_MAX_PAGINATION_ITEMS = 1000
_DEFAULT_PAGE_SIZE = 100
_TOKEN_EXPIRY_MARGIN_S = 60

# Redaction pattern for log messages
_CREDENTIAL_REDACT_RE = re.compile(
    r"(client_secret|refresh_token|access_token)=[^\s&]+", re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class GoogleDriveConfig(BaseModel):
    """Configuration for the Google Drive module.

    Configured under ``[modules.google_drive]`` in ``butler.toml``.
    """

    account: str | None = Field(default=None, description="Google account email to use")
    max_read_size_bytes: int = Field(
        default=10 * 1024 * 1024,  # 10 MB
        description="Maximum file size in bytes for drive_read_file",
    )
    butler_folder_name: str = Field(
        default="butlers",
        description="Root folder name for butler outputs in Drive root",
    )

    model_config = ConfigDict(extra="forbid")

    def model_post_init(self, __context: Any) -> None:
        if self.account is not None:
            object.__setattr__(self, "account", self.account.strip() or None)


# ---------------------------------------------------------------------------
# Module implementation
# ---------------------------------------------------------------------------


class GoogleDriveModule(Module):
    """Google Drive module providing 7 MCP tools for Drive file management.

    Lifecycle:
    - on_startup: resolve credentials, validate drive scope, create HTTP client
    - on_shutdown: close HTTP client
    - register_tools: register all 7 tools on the FastMCP server
    - tool_metadata: declare write and move tools as sensitive
    - migration_revisions: return "google_drive" for butler folder table migration
    """

    def __init__(self) -> None:
        self._config: GoogleDriveConfig = GoogleDriveConfig()
        self._creds: GoogleCredentials | None = None
        self._http: httpx.AsyncClient | None = None
        self._pool: Any = None
        self._butler_name: str = "default"
        # Token cache: (access_token, expires_at)
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None

    # ------------------------------------------------------------------
    # Module ABC properties
    # ------------------------------------------------------------------

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
        """Return Alembic branch label for google_drive_butler_folders migration."""
        return "google_drive"

    # ------------------------------------------------------------------
    # Lifecycle: on_startup / on_shutdown
    # ------------------------------------------------------------------

    async def on_startup(
        self,
        config: Any = None,
        db: Any = None,
        credential_store: Any = None,
        blob_store: Any = None,
        *,
        # Optional keyword args used by integration tests
        store: Any = None,
        pool: Any = None,
        butler_name: str | None = None,
        server: Any = None,
    ) -> None:
        """Resolve Google credentials and initialize the HTTP client.

        Validates that the resolved account has the full ``drive`` scope —
        ``drive.readonly`` is not sufficient because this module writes files.
        """
        # Coerce config
        self._config = (
            config if isinstance(config, GoogleDriveConfig) else GoogleDriveConfig(**(config or {}))
        )

        # Accept credential_store or store (test-compat alias)
        effective_store = credential_store if credential_store is not None else store
        # Accept db or pool (test-compat alias)
        effective_pool = getattr(db, "pool", None) if db is not None else pool

        if butler_name is not None:
            self._butler_name = butler_name
        elif db is not None and hasattr(db, "butler_name"):
            self._butler_name = db.butler_name

        self._pool = effective_pool

        if effective_store is None:
            logger.warning(
                "google_drive module: no credential store provided — "
                "tools will return actionable errors."
            )
            return

        # Resolve credentials
        creds = await resolve_google_credentials(
            effective_store,
            pool=effective_pool,
            caller="google_drive",
            account=self._config.account if self._config.account else None,
        )

        # Validate scope — must include full drive scope for write access
        scope_str = creds.scope or ""
        if _DRIVE_SCOPE not in scope_str.split():
            account_hint = self._config.account or "your primary account"
            raise MissingGoogleCredentialsError(
                f"google_drive module: the connected account ({account_hint}) "
                f"does not have the required 'drive' scope (found: {scope_str!r}). "
                "Re-authorize at /api/oauth/google/start"
                f"?account_hint={account_hint}&force_consent=true "
                "and select the Drive permission."
            )

        self._creds = creds
        self._access_token = None
        self._token_expires_at = None

        # Create HTTP client (base URL set for convenience)
        self._http = httpx.AsyncClient(
            base_url=_DRIVE_API_BASE,
            timeout=_DEFAULT_TIMEOUT_S,
        )
        logger.info("google_drive module: initialized for butler %r", self._butler_name)

    async def on_shutdown(self) -> None:
        """Close the HTTP client."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # ------------------------------------------------------------------
    # Tool metadata
    # ------------------------------------------------------------------

    def tool_metadata(self) -> dict[str, ToolMeta]:
        """Declare sensitivity for write and move tools.

        - drive_write_file: content is sensitive (file data)
        - drive_move_file: file_id and new_parent_id are sensitive (file identity)
        """
        return {
            "drive_write_file": ToolMeta(arg_sensitivities={"content": True}),
            "drive_move_file": ToolMeta(arg_sensitivities={"file_id": True, "new_parent_id": True}),
        }

    # ------------------------------------------------------------------
    # register_tools — all 7 MCP tools
    # ------------------------------------------------------------------

    async def register_tools(self, mcp: Any, config: Any, db: Any) -> None:
        """Register all 7 Google Drive MCP tools on the FastMCP server."""
        self._config = (
            config if isinstance(config, GoogleDriveConfig) else GoogleDriveConfig(**(config or {}))
        )
        if db is not None:
            effective_pool = getattr(db, "pool", None)
            if effective_pool is not None:
                self._pool = effective_pool
            if hasattr(db, "butler_name"):
                self._butler_name = db.butler_name

        module = self  # capture for closures

        @mcp.tool()
        async def drive_list_files(
            folder_id: str | None = None,
            query: str | None = None,
        ) -> dict:
            """List files in a Google Drive folder or matching a query.

            If folder_id is omitted, lists files in My Drive root.
            Optional query narrows results (e.g. "name contains 'report'").
            Returns up to 1000 items with a truncated flag if there are more.
            """
            return await module.drive_list_files(folder_id=folder_id, query=query)

        @mcp.tool()
        async def drive_get_file_metadata(file_id: str) -> dict:
            """Return detailed metadata for a single Google Drive file.

            Returns file metadata dict on success, or {"status": "not_found"} if
            the file does not exist.
            """
            return await module.drive_get_file_metadata(file_id=file_id)

        @mcp.tool()
        async def drive_read_file(file_id: str) -> dict:
            """Download and return the content of a text-representable Drive file.

            Supports plain text files (downloaded as-is), Google Docs (exported as
            text/plain), Google Sheets (exported as text/csv), and Google Slides
            (exported as text/plain). Binary files are rejected with metadata.
            Files exceeding max_read_size_bytes are rejected with size info.
            """
            return await module.drive_read_file(file_id=file_id)

        @mcp.tool()
        async def drive_write_file(
            name: str,
            content: str,
            folder_id: str | None = None,
            mime_type: str | None = None,
        ) -> dict:
            """Create or upload a file to Google Drive.

            If folder_id is omitted, the file is created in the butler's subfolder
            (butlers/{butler_name}/), which is auto-created if needed.
            MIME type is inferred from the file extension when not provided.
            Returns file_id, name, folder path, and web_view_link.
            """
            return await module.drive_write_file(
                name=name, content=content, folder_id=folder_id, mime_type=mime_type
            )

        @mcp.tool()
        async def drive_create_folder(
            name: str,
            parent_id: str | None = None,
        ) -> dict:
            """Create a folder in Google Drive.

            If parent_id is omitted, the folder is created inside the butler's
            subfolder (butlers/{butler_name}/). Returns folder_id, name, and parent path.
            """
            return await module.drive_create_folder(name=name, parent_id=parent_id)

        @mcp.tool()
        async def drive_move_file(file_id: str, new_parent_id: str) -> dict:
            """Move a file from its current location to a new parent folder.

            Returns file metadata with new_parent_id on success, or
            {"status": "not_found"} if the file does not exist.
            """
            return await module.drive_move_file(file_id=file_id, new_parent_id=new_parent_id)

        @mcp.tool()
        async def drive_search_files(
            query: str,
            limit: int | None = None,
        ) -> dict:
            """Search files across Google Drive using full-text search.

            Uses Drive API's built-in fullText search. Results are sorted by
            Drive relevance. Optional limit caps the number of results.
            Returns {"files": [...], "total": N}.
            """
            return await module.drive_search_files(query=query, limit=limit)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_valid_access_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        now = datetime.now(tz=UTC)
        margin = timedelta(seconds=_TOKEN_EXPIRY_MARGIN_S)

        if (
            self._access_token is not None
            and self._token_expires_at is not None
            and now + margin < self._token_expires_at
        ):
            return self._access_token

        if self._creds is None:
            raise RuntimeError(
                "google_drive module: no credentials available — "
                "ensure on_startup completed successfully."
            )

        # Perform token refresh
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _TOKEN_REFRESH_URL,
                data={
                    "client_id": self._creds.client_id,
                    "client_secret": self._creds.client_secret,
                    "refresh_token": self._creds.refresh_token,
                    "grant_type": "refresh_token",
                },
            )

        if resp.status_code != 200:
            # Redact credentials from error message before logging
            safe_text = _CREDENTIAL_REDACT_RE.sub(r"\1=<REDACTED>", resp.text)
            raise RuntimeError(
                f"google_drive module: token refresh failed ({resp.status_code}): {safe_text}"
            )

        data = resp.json()
        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        self._token_expires_at = now + timedelta(seconds=expires_in)

        # Update last_token_refresh_at in DB if pool is available
        if self._pool is not None:
            try:
                from butlers.google_credentials import _pool_acquire  # type: ignore[attr-defined]

                async with _pool_acquire(self._pool) as conn:
                    await conn.execute(
                        """
                        UPDATE public.google_accounts
                        SET last_token_refresh_at = now()
                        WHERE email = $1
                        """,
                        self._config.account or "",
                    )
            except Exception:
                logger.debug("google_drive: could not update last_token_refresh_at", exc_info=True)

        return self._access_token

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _require_http(self) -> httpx.AsyncClient:
        if self._http is None:
            raise RuntimeError(
                "google_drive module: HTTP client not initialized. "
                "Call on_startup before using Drive tools."
            )
        return self._http

    async def _api_get(self, path: str, params: dict | None = None) -> httpx.Response:
        """GET against the Drive v3 API with auth header."""
        token = await self._get_valid_access_token()
        http = self._require_http()
        return await http.get(path, params=params, headers=self._auth_headers(token))

    async def _api_post_json(self, path: str, json: dict) -> httpx.Response:
        """POST JSON to the Drive v3 API with auth header."""
        token = await self._get_valid_access_token()
        http = self._require_http()
        return await http.post(path, json=json, headers=self._auth_headers(token))

    async def _api_patch_json(
        self, path: str, json: dict, params: dict | None = None
    ) -> httpx.Response:
        """PATCH JSON to the Drive v3 API with auth header."""
        token = await self._get_valid_access_token()
        http = self._require_http()
        return await http.patch(path, json=json, params=params, headers=self._auth_headers(token))

    # ------------------------------------------------------------------
    # Butler folder hierarchy
    # ------------------------------------------------------------------

    async def _ensure_butler_folder(self) -> tuple[str, str]:
        """Ensure butler folder hierarchy exists and return (folder_id, folder_path).

        Checks the DB cache first. If a cached entry exists, verifies the folder
        still exists via files.get. Re-creates if deleted. Creates both the root
        "butlers/" folder and the per-butler subfolder if needed.

        Creation strategy:
        - Fresh start (no cache): search for root folder (1 GET), create root if missing
          (1 POST), then always create the subfolder without searching (1 POST).
        - Stale cache (folder deleted): re-create the butler subfolder directly under
          Drive root without rebuilding the parent hierarchy (1 POST), then cache.

        Returns (folder_id, folder_path) for the butler's subfolder.
        """
        butler_name = self._butler_name
        folder_name = self._config.butler_folder_name

        # Check DB cache
        cached_id, cached_path = await self._load_folder_cache(butler_name)
        if cached_id is not None:
            # Verify folder still exists
            if await self._folder_exists(cached_id):
                return cached_id, cached_path
            # Folder was deleted — invalidate cache and re-create just the subfolder.
            await self._delete_folder_cache(butler_name)
            sub_id = await self._create_folder(butler_name, parent_id=None)
            folder_path = butler_name
            await self._save_folder_cache(butler_name, sub_id, folder_path)
            return sub_id, folder_path

        # Fresh start: find or create root "butlers/" folder (search + maybe create)
        root_id = await self._find_or_create_folder(folder_name, parent_id="root")

        # Always create the per-butler subfolder without searching.
        sub_id = await self._create_folder(butler_name, parent_id=root_id)

        folder_path = f"{folder_name}/{butler_name}"
        await self._save_folder_cache(butler_name, sub_id, folder_path)
        return sub_id, folder_path

    async def _create_folder(self, name: str, parent_id: str | None) -> str:
        """Create a folder in Drive and return its ID (no existence search)."""
        body: dict[str, Any] = {
            "name": name,
            "mimeType": _GOOGLE_FOLDER_MIME,
        }
        if parent_id and parent_id != "root":
            body["parents"] = [parent_id]
        create_resp = await self._api_post_json("files", body)
        if create_resp.status_code not in (200, 201):
            raise RuntimeError(
                f"google_drive: failed to create folder {name!r} (status {create_resp.status_code})"
            )
        return create_resp.json()["id"]

    async def _folder_exists(self, folder_id: str) -> bool:
        """Return True if the folder exists in Drive."""
        try:
            resp = await self._api_get(f"files/{folder_id}", params={"fields": "id,trashed"})
            if resp.status_code == 200:
                data = resp.json()
                return not data.get("trashed", False)
        except Exception:
            pass
        return False

    async def _find_or_create_folder(self, name: str, parent_id: str) -> str:
        """Find an existing folder by name under parent_id, or create it.

        Performs a single search GET; if no match is found, creates via POST.
        """
        parent_filter = f"'{parent_id}' in parents" if parent_id != "root" else "'root' in parents"
        q = (
            f"{parent_filter} and name = '{name}' "
            f"and mimeType = '{_GOOGLE_FOLDER_MIME}' and trashed = false"
        )
        resp = await self._api_get("files", params={"q": q, "fields": "files(id,name)"})
        if resp.status_code == 200:
            files = resp.json().get("files", [])
            if files:
                return files[0]["id"]

        return await self._create_folder(name, parent_id=parent_id)

    async def _load_folder_cache(self, butler_name: str) -> tuple[str | None, str | None]:
        """Load cached folder ID and path from DB."""
        if self._pool is None:
            return None, None
        try:
            from butlers.google_credentials import _pool_acquire  # type: ignore[attr-defined]

            async with _pool_acquire(self._pool) as conn:
                row = await conn.fetchrow(
                    """
                    SELECT folder_id, folder_path
                    FROM google_drive_butler_folders
                    WHERE butler_name = $1 AND account_email = $2
                    """,
                    butler_name,
                    self._config.account or "",
                )
            if row:
                return row["folder_id"], row["folder_path"]
        except Exception:
            logger.debug("google_drive: could not load folder cache", exc_info=True)
        return None, None

    async def _save_folder_cache(self, butler_name: str, folder_id: str, folder_path: str) -> None:
        """Upsert folder ID and path into DB cache."""
        if self._pool is None:
            return
        try:
            from butlers.google_credentials import _pool_acquire  # type: ignore[attr-defined]

            async with _pool_acquire(self._pool) as conn:
                await conn.execute(
                    """
                    INSERT INTO google_drive_butler_folders
                        (butler_name, account_email, folder_id, folder_path)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (butler_name, account_email)
                    DO UPDATE SET folder_id = EXCLUDED.folder_id,
                                  folder_path = EXCLUDED.folder_path
                    """,
                    butler_name,
                    self._config.account or "",
                    folder_id,
                    folder_path,
                )
        except Exception:
            logger.debug("google_drive: could not save folder cache", exc_info=True)

    async def _delete_folder_cache(self, butler_name: str) -> None:
        """Remove stale folder cache entry from DB."""
        if self._pool is None:
            return
        try:
            from butlers.google_credentials import _pool_acquire  # type: ignore[attr-defined]

            async with _pool_acquire(self._pool) as conn:
                await conn.execute(
                    """
                    DELETE FROM google_drive_butler_folders
                    WHERE butler_name = $1 AND account_email = $2
                    """,
                    butler_name,
                    self._config.account or "",
                )
        except Exception:
            logger.debug("google_drive: could not delete folder cache", exc_info=True)

    # ------------------------------------------------------------------
    # Tool implementations (also callable directly, e.g. in tests)
    # ------------------------------------------------------------------

    async def drive_list_files(
        self,
        folder_id: str | None = None,
        query: str | None = None,
    ) -> dict:
        """List files in a Drive folder or matching a query."""
        parent = folder_id or "root"
        base_q = f"'{parent}' in parents and trashed=false"
        if query:
            full_q = f"{base_q} and {query}"
        else:
            full_q = base_q

        fields = "nextPageToken,files(id,name,mimeType,modifiedTime,size,parents,shared,owners)"
        all_files: list[dict] = []
        page_token: str | None = None
        truncated = False

        while True:
            params: dict[str, Any] = {
                "q": full_q,
                "fields": fields,
                "pageSize": _DEFAULT_PAGE_SIZE,
            }
            if page_token:
                params["pageToken"] = page_token

            resp = await self._api_get("files", params=params)
            if resp.status_code != 200:
                return {"error": f"Drive API error {resp.status_code}", "files": []}

            data = resp.json()
            all_files.extend(data.get("files", []))

            if len(all_files) >= _MAX_PAGINATION_ITEMS:
                truncated = bool(data.get("nextPageToken"))
                all_files = all_files[:_MAX_PAGINATION_ITEMS]
                break

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return {"files": all_files, "total": len(all_files), "truncated": truncated}

    async def drive_get_file_metadata(self, file_id: str) -> dict:
        """Return detailed metadata for a single file."""
        fields = (
            "id,name,mimeType,modifiedTime,createdTime,size,parents,"
            "shared,sharingUser,owners,webViewLink,description"
        )
        resp = await self._api_get(f"files/{file_id}", params={"fields": fields})
        if resp.status_code == 404:
            return {"status": "not_found", "file": None}
        if resp.status_code != 200:
            return {"error": f"Drive API error {resp.status_code}", "file": None}
        return resp.json()

    async def drive_read_file(self, file_id: str) -> dict:
        """Download and return file content for text-representable files."""
        # First get metadata to check MIME type and size
        meta_fields = "id,name,mimeType,size,webViewLink"
        meta_resp = await self._api_get(f"files/{file_id}", params={"fields": meta_fields})
        if meta_resp.status_code == 404:
            return {"status": "not_found", "file": None}
        if meta_resp.status_code != 200:
            return {"error": f"Drive API error {meta_resp.status_code}"}

        meta = meta_resp.json()
        mime_type = meta.get("mimeType", "")
        name = meta.get("name", "")
        size_bytes = int(meta.get("size", 0)) if meta.get("size") else 0
        web_view_link = meta.get("webViewLink", "")

        # Check if this is a Google Workspace type (no size limit for exports)
        is_google_workspace = mime_type in _GOOGLE_MIME_EXPORTS

        if not is_google_workspace:
            # Size check for regular files
            if size_bytes > self._config.max_read_size_bytes:
                return {
                    "status": "too_large",
                    "size_bytes": size_bytes,
                    "max_bytes": self._config.max_read_size_bytes,
                    "name": name,
                }

            # Reject binary files
            if not (mime_type.startswith("text/") or mime_type in ("application/json",)):
                return {
                    "status": "binary_file",
                    "mime_type": mime_type,
                    "name": name,
                    "size_bytes": size_bytes,
                    "web_view_link": web_view_link,
                }

            # Download text file content via alt=media
            token = await self._get_valid_access_token()
            http = self._require_http()
            content_resp = await http.get(
                f"files/{file_id}",
                params={"alt": "media"},
                headers=self._auth_headers(token),
            )
            if content_resp.status_code != 200:
                return {"error": f"Drive API error {content_resp.status_code}"}
            return {
                "content": content_resp.text,
                "mime_type": mime_type,
                "name": name,
                "size_bytes": size_bytes,
                "file_id": file_id,
            }
        else:
            # Export Google Workspace document
            export_mime = _GOOGLE_MIME_EXPORTS[mime_type]
            token = await self._get_valid_access_token()
            http = self._require_http()
            export_resp = await http.get(
                f"files/{file_id}/export",
                params={"mimeType": export_mime},
                headers=self._auth_headers(token),
            )
            if export_resp.status_code != 200:
                return {"error": f"Drive export error {export_resp.status_code}"}
            return {
                "content": export_resp.text,
                "mime_type": export_mime,
                "name": name,
                "file_id": file_id,
            }

    async def drive_write_file(
        self,
        name: str,
        content: str,
        folder_id: str | None = None,
        mime_type: str | None = None,
    ) -> dict:
        """Create or upload a file to Google Drive.

        If folder_id is omitted, uses the butler's subfolder (auto-created).
        MIME type is inferred from the file extension when not provided.
        """
        # Resolve target folder
        folder_path: str
        if folder_id is None:
            folder_id, folder_path = await self._ensure_butler_folder()
        else:
            folder_path = folder_id  # caller-provided, path unknown

        # Infer MIME type from extension if not provided
        if mime_type is None:
            suffix = ""
            dot_idx = name.rfind(".")
            if dot_idx >= 0:
                suffix = name[dot_idx:].lower()
            mime_type = _EXT_MIME_MAP.get(suffix, "application/octet-stream")

        # Multipart upload: metadata + media
        token = await self._get_valid_access_token()
        http = self._require_http()

        metadata: dict[str, Any] = {
            "name": name,
            "parents": [folder_id],
        }

        import json as _json

        boundary = "butler_drive_boundary"
        body = (
            f"--{boundary}\r\n"
            f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{_json.dumps(metadata)}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: {mime_type}\r\n\r\n"
            f"{content}\r\n"
            f"--{boundary}--"
        )

        upload_resp = await http.post(
            "https://www.googleapis.com/upload/drive/v3/files",
            params={"uploadType": "multipart"},
            content=body.encode("utf-8"),
            headers={
                **self._auth_headers(token),
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
        )

        if upload_resp.status_code not in (200, 201):
            return {"error": f"Drive upload error {upload_resp.status_code}"}

        file_data = upload_resp.json()
        return {
            "file_id": file_data.get("id"),
            "name": file_data.get("name", name),
            "folder": folder_path,
            "web_view_link": file_data.get("webViewLink", ""),
        }

    async def drive_create_folder(
        self,
        name: str,
        parent_id: str | None = None,
    ) -> dict:
        """Create a folder in Google Drive."""
        parent_path: str
        if parent_id is None:
            parent_id, parent_path = await self._ensure_butler_folder()
        else:
            parent_path = parent_id

        body: dict[str, Any] = {
            "name": name,
            "mimeType": _GOOGLE_FOLDER_MIME,
            "parents": [parent_id],
        }
        resp = await self._api_post_json("files", body)
        if resp.status_code not in (200, 201):
            return {"error": f"Drive API error {resp.status_code}"}

        folder_data = resp.json()
        return {
            "folder_id": folder_data.get("id"),
            "name": folder_data.get("name", name),
            "parent_path": parent_path,
        }

    async def drive_move_file(self, file_id: str, new_parent_id: str) -> dict:
        """Move a file from its current location to a new parent folder."""
        # Get current parents first
        meta_resp = await self._api_get(f"files/{file_id}", params={"fields": "id,name,parents"})
        if meta_resp.status_code == 404:
            return {"status": "not_found", "error": "File not found"}
        if meta_resp.status_code != 200:
            return {"error": f"Drive API error {meta_resp.status_code}"}

        meta = meta_resp.json()
        current_parents = ",".join(meta.get("parents", []))

        # Move file: add new parent, remove current parents
        token = await self._get_valid_access_token()
        http = self._require_http()
        update_resp = await http.patch(
            f"files/{file_id}",
            params={
                "addParents": new_parent_id,
                "removeParents": current_parents,
                "fields": "id,name,parents",
            },
            json={},
            headers=self._auth_headers(token),
        )
        if update_resp.status_code == 404:
            return {"status": "not_found", "error": "File not found"}
        if update_resp.status_code != 200:
            return {"error": f"Drive API error {update_resp.status_code}"}

        updated = update_resp.json()
        return {
            "file_id": updated.get("id"),
            "name": updated.get("name"),
            "new_parent_id": new_parent_id,
        }

    async def drive_search_files(
        self,
        query: str,
        limit: int | None = None,
    ) -> dict:
        """Search files across Drive using full-text search."""
        q = f"fullText contains '{query}' and trashed=false"
        fields = (
            "nextPageToken,files(id,name,mimeType,modifiedTime,size,"
            "parents,shared,owners,webViewLink)"
        )

        page_size = min(limit or _DEFAULT_PAGE_SIZE, _DEFAULT_PAGE_SIZE)
        params: dict[str, Any] = {"q": q, "fields": fields, "pageSize": page_size}

        resp = await self._api_get("files", params=params)
        if resp.status_code != 200:
            return {"files": [], "total": 0, "error": f"Drive API error {resp.status_code}"}

        data = resp.json()
        files = data.get("files", [])
        if limit is not None:
            files = files[:limit]

        return {"files": files, "total": len(files)}
