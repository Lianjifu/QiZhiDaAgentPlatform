"""use_case decorator that runs PolicyGuard.check() before delegating to the wrapped function.

Designed to be applied to ``XxxUseCase.execute()`` methods:

    class ExecuteToolUseCase:
        def __init__(self, ..., policy_guard: PolicyGuard | None = None):
            self._policy_guard = policy_guard

        @policy_check(
            action=lambda self, *a, tool_name=None, **kw: f"tool:execute:{tool_name}",
            resource=lambda self, *a, **kw: dict(kw),
        )
        async def execute(self, *, actor, tool_name, arguments):
            ...
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

from qzdap_vault.actor import ActorContext

from qzdap.modules.governance.adapter.guard.policy_guard import PolicyGuard

P = ParamSpec("P")
R = TypeVar("R")


def policy_check(
    *,
    action: Callable[..., str],
    resource: Callable[..., dict[str, Any]] | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator factory.

    The decorator expects ``self`` (or any object) to expose
    ``self._policy_guard`` (a ``PolicyGuard``) and the wrapped call to
    receive an ``actor`` keyword.  If ``_policy_guard`` is ``None`` the
    decorator is a no-op — this lets us write ``policy_guard=...`` as
    an optional kwarg and skip the check entirely in unit tests.
    """

    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(fn)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> R:
            guard: PolicyGuard | None = getattr(self, "_policy_guard", None)
            actor: ActorContext | None = kwargs.get("actor")
            if guard is not None and actor is not None:
                action_str = action(self, *args, **kwargs)
                res = resource(self, *args, **kwargs) if resource else {}
                await guard.check(actor=actor, action=action_str, resource=res)
            return await fn(self, *args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


__all__ = ["policy_check"]
