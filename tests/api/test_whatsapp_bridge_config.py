"""WhatsApp bridge socket configuration contract tests."""

from pathlib import Path

import pytest
import yaml

from butlers.api.routers.whatsapp import _get_bridge_socket_path
from butlers.modules.whatsapp import WhatsAppConfig

pytestmark = pytest.mark.unit


def test_dashboard_default_matches_connector_owned_socket_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All bridge clients target the connector-owned socket without env-only masking."""
    monkeypatch.delenv("WHATSAPP_BRIDGE_SOCKET", raising=False)
    connector_owned_socket = WhatsAppConfig().bridge_socket

    assert _get_bridge_socket_path() == connector_owned_socket

    services = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))["services"]
    configured_clients = {
        "connector-whatsapp-user": ("WA_BRIDGE_SOCKET", connector_owned_socket),
        "dashboard-api": ("WHATSAPP_BRIDGE_SOCKET", connector_owned_socket),
        "dashboard-api-hotreload": ("WHATSAPP_BRIDGE_SOCKET", connector_owned_socket),
        "butlers-up": ("WHATSAPP_BRIDGE_SOCKET", connector_owned_socket),
    }

    for service_name, (env_name, expected_socket) in configured_clients.items():
        assert services[service_name]["environment"][env_name] == expected_socket
