import asyncio
from typing import Any

import pytest

from app.tools.registry import (
    ToolArgumentError,
    ToolError,
    ToolRegistry,
    ToolTimeoutError,
    UnknownToolError,
)

PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "count": {"type": "integer"},
    },
    "required": ["text"],
    "additionalProperties": False,
}


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()

    @registry.tool(name="echo", description="Echo the text", parameters=PARAMETERS)
    async def echo(args: dict[str, Any]) -> str:
        return str(args["text"])

    return registry


@pytest.mark.asyncio
async def test_one_function_extension() -> None:
    registry = build_registry()
    assert registry.names() == ["echo"]
    assert len(registry) == 1
    assert await registry.invoke("echo", {"text": "namaskaram"}) == "namaskaram"
    definition = registry.definitions()[0]
    assert definition["name"] == "echo"
    assert definition["parameters"]["required"] == ["text"]


@pytest.mark.asyncio
async def test_unknown_tool_is_rejected() -> None:
    registry = build_registry()
    with pytest.raises(UnknownToolError):
        await registry.invoke("transfer_to_bank", {})


@pytest.mark.asyncio
async def test_missing_required_argument() -> None:
    registry = build_registry()
    with pytest.raises(ToolArgumentError, match="missing required"):
        await registry.invoke("echo", {"count": 2})


@pytest.mark.asyncio
async def test_wrong_argument_type() -> None:
    registry = build_registry()
    with pytest.raises(ToolArgumentError, match="must be"):
        await registry.invoke("echo", {"text": 42})


@pytest.mark.asyncio
async def test_boolean_is_not_an_integer() -> None:
    registry = build_registry()
    with pytest.raises(ToolArgumentError):
        await registry.invoke("echo", {"text": "ok", "count": True})


@pytest.mark.asyncio
async def test_undeclared_argument_rejected_when_schema_is_strict() -> None:
    registry = build_registry()
    with pytest.raises(ToolArgumentError, match="undeclared argument"):
        await registry.invoke("echo", {"text": "ok", "admin": True})


@pytest.mark.asyncio
async def test_tool_timeout() -> None:
    registry = ToolRegistry(timeout_seconds=0.01)

    @registry.tool(name="slow", description="Sleeps too long")
    async def slow(args: dict[str, Any]) -> None:
        await asyncio.sleep(0.2)

    with pytest.raises(ToolTimeoutError):
        await registry.invoke("slow", {})


@pytest.mark.asyncio
async def test_restrict_to_agent_declared_tools() -> None:
    registry = build_registry()

    @registry.tool(name="book_slot", description="Book a slot")
    async def book_slot(args: dict[str, Any]) -> str:
        return "booked"

    restricted = registry.restrict_to(["echo"])
    assert restricted.names() == ["echo"]
    with pytest.raises(UnknownToolError):
        await restricted.invoke("book_slot", {})


def test_duplicate_registration_is_rejected() -> None:
    registry = build_registry()
    with pytest.raises(ToolError, match="already registered"):

        @registry.tool(name="echo", description="Duplicate")
        async def duplicate(args: dict[str, Any]) -> None:
            return None


def test_sync_handler_is_rejected() -> None:
    registry = ToolRegistry()
    with pytest.raises(TypeError):

        @registry.tool(name="sync", description="Not async")
        def sync_tool(args: dict[str, Any]) -> None:
            return None
