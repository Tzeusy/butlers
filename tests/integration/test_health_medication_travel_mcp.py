"""In-process proof of Travel -> Switchboard -> Health medication MCP routing."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastmcp import Client, FastMCP

from butlers.modules._roster_health import HealthModule
from butlers.modules._roster_travel import TravelModule

pytestmark = pytest.mark.integration


class _HealthPool:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def fetch(self, query: str, *_args: object) -> list[dict]:
        self.queries.append(query)
        return [
            {
                "id": uuid4(),
                "predicate": "medication",
                "content": "Metformin 500 mg twice daily",
                "valid_at": None,
                "created_at": None,
                "metadata": {
                    "name": "Metformin",
                    "dosage": "500 mg",
                    "frequency": "twice daily",
                    "schedule": ["08:00", "20:00"],
                    "active": True,
                    "notes": "private note that must stay in Health",
                },
            }
        ]


class _TravelPool:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def fetchrow(self, query: str, *_args: object) -> None:
        self.queries.append(query)
        if "health." in query.lower():
            raise AssertionError("Travel attempted a direct Health-schema query")
        return None


class _InProcessSwitchboardClient:
    def __init__(self, health_mcp: FastMCP) -> None:
        self.health_mcp = health_mcp
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, tool_name: str, args: dict) -> object:
        self.calls.append((tool_name, args))
        assert tool_name == "route"
        assert args["target_butler"] == "health"
        assert args["tool_name"] == "medication_travel_snapshot"
        assert args["source_butler"] == "travel"

        async with Client(self.health_mcp) as client:
            health_result = await client.call_tool(
                args["tool_name"], args["args"], raise_on_error=True
            )
        return SimpleNamespace(
            is_error=False,
            data={"result": health_result.data},
            content=[],
        )


async def test_travel_obtains_minimum_medication_snapshot_through_health_mcp() -> None:
    health_pool = _HealthPool()
    health_module = HealthModule()
    health_mcp = FastMCP("health")
    await health_module.register_tools(
        health_mcp,
        {},
        SimpleNamespace(pool=health_pool),
        butler_name="health",
    )

    travel_pool = _TravelPool()
    travel_module = TravelModule()
    travel_mcp = FastMCP("travel")
    await travel_module.register_tools(
        travel_mcp,
        {},
        SimpleNamespace(pool=travel_pool),
        butler_name="travel",
    )
    switchboard = _InProcessSwitchboardClient(health_mcp)
    travel_module.wire_runtime(None, "/repo", switchboard_client=switchboard)

    async with Client(travel_mcp) as client:
        result = await client.call_tool("health_medication_snapshot", {}, raise_on_error=True)

    assert result.data == {
        "schema_version": "health.medication-travel.v1",
        "status": "ok",
        "medications": [
            {
                "name": "Metformin",
                "dosage": "500 mg",
                "frequency": "twice daily",
                "schedule": ["08:00", "20:00"],
            }
        ],
        "error": None,
    }
    assert switchboard.calls
    assert health_pool.queries and "FROM facts" in health_pool.queries[0]
    assert travel_pool.queries
    assert all("health." not in query.lower() for query in travel_pool.queries)
    assert "private note" not in str(result.data)
