import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]


class ToolError(RuntimeError):
    """Base class for tool contract violations."""


class UnknownToolError(ToolError):
    """The agent asked for a tool that is not registered or not declared."""


class ToolArgumentError(ToolError):
    """Arguments did not satisfy the tool's declared JSON schema."""


class ToolTimeoutError(ToolError):
    """The tool exceeded its execution budget."""


class ToolConfirmationRequiredError(ToolError):
    """The tool cannot be executed without explicit user confirmation."""


# Alias for backward compatibility
ToolConfirmationRequired = ToolConfirmationRequiredError


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: Mapping[str, Any]
    handler: ToolHandler
    requires_confirmation: bool = False
    confirmation_prompt: Mapping[str, str] = field(default_factory=dict)

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": dict(self.parameters),
            "requires_confirmation": self.requires_confirmation,
        }


def _matches_type(value: Any, expected: str) -> bool:
    match expected:
        case "string":
            return isinstance(value, str)
        case "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        case "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        case "boolean":
            return isinstance(value, bool)
        case "array":
            return isinstance(value, list)
        case "object":
            return isinstance(value, dict)
        case "null":
            return value is None
        case _:
            return True


class ToolRegistry:
    """Declared tools only. Anything not registered here cannot be invoked."""

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self.timeout_seconds = timeout_seconds

    def register(self, tool_or_spec: Any) -> ToolSpec:
        """Register a ToolSpec or a function decorated with @tool."""
        if hasattr(tool_or_spec, "__kelvi_tool_spec__"):
            spec: ToolSpec = tool_or_spec.__kelvi_tool_spec__
        elif isinstance(tool_or_spec, ToolSpec):
            spec = tool_or_spec
        else:
            cls_name = type(tool_or_spec).__name__
            raise TypeError(
                f"Cannot register {cls_name}. Expected ToolSpec or @tool function."
            )

        if spec.name in self._tools:
            raise ToolError(f"Tool '{spec.name}' is already registered")
        self._tools[spec.name] = spec
        return spec

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def get(self, name: str) -> ToolSpec:
        spec = self._tools.get(name)
        if spec is None:
            raise UnknownToolError(f"Tool '{name}' is not available to this agent")
        return spec

    def restrict_to(self, allowed: Iterable[str]) -> "ToolRegistry":
        """Return a registry containing only tools the current agent is allowed to call."""
        allowed_names = set(allowed)
        restricted = ToolRegistry(timeout_seconds=self.timeout_seconds)
        for name, spec in self._tools.items():
            if name in allowed_names:
                restricted.register(spec)
        return restricted

    def definitions(self) -> list[dict[str, Any]]:
        return [self._tools[name].definition() for name in self.names()]

    async def invoke(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        confirmed: bool = False,
    ) -> Any:
        spec = self.get(name)
        if spec.requires_confirmation and not confirmed:
            raise ToolConfirmationRequiredError(
                f"Tool '{name}' requires explicit caller confirmation before execution"
            )

        payload = dict(arguments or {})
        self._validate_arguments(spec, payload)
        try:
            return await asyncio.wait_for(spec.handler(payload), timeout=self.timeout_seconds)
        except TimeoutError as exc:
            raise ToolTimeoutError(f"Tool '{name}' timed out") from exc

    def _validate_arguments(self, spec: ToolSpec, arguments: dict[str, Any]) -> None:
        schema = spec.parameters or {}
        required = schema.get("required") or []
        missing = sorted(key for key in required if key not in arguments)
        if missing:
            missing_list = ", ".join(missing)
            raise ToolArgumentError(
                f"Tool '{spec.name}' missing required argument(s): {missing_list}"
            )

        properties = schema.get("properties") or {}
        if schema.get("additionalProperties") is False:
            unexpected = sorted(key for key in arguments if key not in properties)
            if unexpected:
                unexpected_list = ", ".join(unexpected)
                raise ToolArgumentError(
                    f"Tool '{spec.name}' received undeclared argument(s): {unexpected_list}"
                )

        for key, value in arguments.items():
            declared = properties.get(key)
            if not isinstance(declared, dict):
                continue
            expected = declared.get("type")
            if expected is None:
                continue
            expected_types = expected if isinstance(expected, list) else [expected]
            if value is not None and not any(_matches_type(value, t) for t in expected_types):
                raise ToolArgumentError(
                    f"Tool '{spec.name}' argument '{key}' must be {expected}, "
                    f"got {type(value).__name__}"
                )
