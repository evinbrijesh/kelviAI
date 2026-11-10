import functools
import inspect
from collections.abc import Callable, Mapping
from typing import Any, get_args, get_origin

from kelvi.tools.registry import ToolSpec


def _py_type_to_json_type(py_type: Any) -> str:
    origin = get_origin(py_type) or py_type
    if origin is str:
        return "string"
    if origin is int and origin is not bool:
        return "integer"
    if origin is float:
        return "number"
    if origin is bool:
        return "boolean"
    if origin in (list, tuple, set):
        return "array"
    if origin in (dict, Mapping):
        return "object"
    return "string"


def _generate_json_schema(func: Callable[..., Any]) -> dict[str, Any]:
    sig = inspect.signature(func)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue
        param_type = param.annotation
        if param_type is inspect.Parameter.empty:
            json_type = "string"
        else:
            # Handle Optional[T] / Union[T, None]
            origin = get_origin(param_type)
            args = get_args(param_type)
            if origin is not None and type(None) in args:
                non_none = [a for a in args if a is not type(None)]
                json_type = _py_type_to_json_type(non_none[0]) if non_none else "string"
            else:
                json_type = _py_type_to_json_type(param_type)

        properties[param_name] = {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def tool(
    *,
    name: str | None = None,
    description: str | None = None,
    parameters: Mapping[str, Any] | None = None,
    requires_confirmation: bool = False,
    confirmation_prompt: Mapping[str, str] | None = None,
) -> Callable[[Callable[..., Any]], Any]:
    """Decorator to declare a Python function as a Kelvi AI Tool.

    Automatically extracts JSON Schema parameters from Python type annotations.
    """

    def decorator(func: Callable[..., Any]) -> Any:
        if not inspect.iscoroutinefunction(func):
            raise TypeError(f"Tool function '{func.__name__}' must be an async coroutine function")

        tool_name = name or func.__name__
        tool_desc = description or (func.__doc__ or "").strip() or f"Execute {tool_name}"
        tool_params = parameters if parameters is not None else _generate_json_schema(func)

        # Wrap handler so it can be called either with dict payload or direct kwargs
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())

        async def handler(payload: dict[str, Any]) -> Any:
            # If function expects a single dictionary called `payload` or `arguments`
            if len(param_names) == 1 and param_names[0] in ("payload", "arguments"):
                return await func(payload)
            # Otherwise unpack kwargs matching declared params
            kwargs = {k: v for k, v in payload.items() if k in param_names}
            return await func(**kwargs)

        spec = ToolSpec(
            name=tool_name,
            description=tool_desc,
            parameters=tool_params,
            handler=handler,
            requires_confirmation=requires_confirmation,
            confirmation_prompt=confirmation_prompt or {},
        )

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if args and isinstance(args[0], dict) and not kwargs:
                return await handler(args[0])
            return await func(*args, **kwargs)

        setattr(wrapper, "__kelvi_tool_spec__", spec)
        setattr(wrapper, "spec", spec)
        return wrapper

    return decorator
