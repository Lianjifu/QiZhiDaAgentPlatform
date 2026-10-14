"""Governance 协议层：PolicyGuard 进程内实现（§5.7）。"""

from __future__ import annotations

from .policy import InMemoryPolicyGuard

__all__ = ["InMemoryPolicyGuard"]