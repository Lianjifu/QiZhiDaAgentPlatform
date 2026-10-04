"""In-process tool registry: tool name → async callable.

Used for the `custom` protocol and for built-in tools registered at
lifespan startup (echo / reverse / clock). Wraps the registry as a
`CustomInvokerPort` for the use-case layer.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from qzdap.modules.tool.domain.errors import ToolNotFound


class CustomInvokerRegistry:
    def __init__(self) -> None:
        self._fns: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = {}

    def register(
        self,
        name: str,
        fn: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> None:
        if name in self._fns:
            raise ValueError(f"tool {name!r} already registered")
        self._fns[name] = fn

    def unregister(self, name: str) -> None:
        self._fns.pop(name, None)

    def has(self, name: str) -> bool:
        return name in self._fns

    def names(self) -> list[str]:
        return list(self._fns.keys())

    async def invoke(self, *, name: str, arguments: dict) -> dict:
        fn = self._fns.get(name)
        if fn is None:
            raise ToolNotFound(f"custom tool {name!r} not registered")
        return dict(await fn(arguments))


# ── Built-in tools (registered at lifespan startup) ─────────────────


async def built_in_invoke_echo(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"echo": dict(arguments)}


async def built_in_invoke_reverse(arguments: dict[str, Any]) -> dict[str, Any]:
    text = arguments.get("text", "")
    if not isinstance(text, str):
        return {"reversed": "", "error": "text must be a string"}
    return {"reversed": text[::-1]}


async def built_in_invoke_clock(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"now": datetime.now(UTC).isoformat()}
