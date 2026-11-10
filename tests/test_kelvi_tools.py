import pytest

from kelvi import (
    ToolArgumentError,
    ToolConfirmationRequired,
    ToolRegistry,
    tool,
)


@pytest.mark.asyncio
async def test_tool_decorator_extracts_schema():
    @tool(
        name="calculate_fare",
        description="Calculate delivery fare between two points",
        requires_confirmation=False,
    )
    async def calculate_fare(distance_km: float, priority: bool = False) -> dict:
        rate = 15.0 if priority else 10.0
        return {"fare": distance_km * rate}

    spec = calculate_fare.spec
    assert spec.name == "calculate_fare"
    assert spec.description == "Calculate delivery fare between two points"
    assert spec.parameters["type"] == "object"
    assert spec.parameters["properties"]["distance_km"]["type"] == "number"
    assert spec.parameters["properties"]["priority"]["type"] == "boolean"
    assert "distance_km" in spec.parameters["required"]
    assert "priority" not in spec.parameters["required"]


@pytest.mark.asyncio
async def test_tool_registry_registration_and_invoke():
    registry = ToolRegistry()

    @tool(name="ping", description="Ping health check")
    async def ping_tool() -> dict:
        return {"status": "pong"}

    registry.register(ping_tool)
    assert "ping" in registry

    result = await registry.invoke("ping")
    assert result == {"status": "pong"}


@pytest.mark.asyncio
async def test_tool_confirmation_guardrail():
    registry = ToolRegistry()

    @tool(
        name="delete_account",
        description="Delete user account",
        requires_confirmation=True,
    )
    async def delete_account(user_id: str) -> dict:
        return {"deleted": user_id}

    registry.register(delete_account)

    # Calling without confirmed=True must raise ToolConfirmationRequired
    with pytest.raises(ToolConfirmationRequired):
        await registry.invoke("delete_account", {"user_id": "U-123"}, confirmed=False)

    # Calling with confirmed=True executes successfully
    res = await registry.invoke("delete_account", {"user_id": "U-123"}, confirmed=True)
    assert res == {"deleted": "U-123"}


@pytest.mark.asyncio
async def test_tool_argument_validation():
    registry = ToolRegistry()

    @tool(name="greet")
    async def greet(name: str) -> str:
        return f"Hello, {name}!"

    registry.register(greet)

    with pytest.raises(ToolArgumentError) as exc_info:
        await registry.invoke("greet", {})
    assert "missing required argument" in str(exc_info.value)
