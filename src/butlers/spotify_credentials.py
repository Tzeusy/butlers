"""Canonical Spotify credential authority identifiers.

The application client id is Tier 1 system configuration. OAuth tokens are
Tier 2 owner credentials and must only be resolved from ``entity_info``.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# butler_secrets key names for Spotify OAuth credentials
# ---------------------------------------------------------------------------

SPOTIFY_CLIENT_ID = "SPOTIFY_CLIENT_ID"
"""Spotify application client ID (32-character hex string)."""

SPOTIFY_OAUTH_ACCESS = "spotify_oauth_access"
SPOTIFY_OAUTH_REFRESH = "spotify_oauth_refresh"
SPOTIFY_OAUTH_EXPIRES_AT = "spotify_oauth_expires_at"

SPOTIFY_MANAGED_ENTITY_INFO_TYPES: frozenset[str] = frozenset(
    {SPOTIFY_OAUTH_ACCESS, SPOTIFY_OAUTH_REFRESH, SPOTIFY_OAUTH_EXPIRES_AT}
)

# Compatibility names retained until the separately-owned generic OAuth
# Spotify provider is removed. Connector and module code must not use these.
SPOTIFY_ACCESS_TOKEN = "SPOTIFY_ACCESS_TOKEN"
SPOTIFY_REFRESH_TOKEN = "SPOTIFY_REFRESH_TOKEN"
SPOTIFY_TOKEN_EXPIRES_AT = "SPOTIFY_TOKEN_EXPIRES_AT"

SPOTIFY_CATEGORY = "spotify"
"""Category label used when storing Spotify credentials in butler_secrets."""
