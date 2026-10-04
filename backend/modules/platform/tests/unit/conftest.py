"""Shared fixtures for platform unit tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from qzdap.modules.platform.application.services import PlatformService
from qzdap.modules.platform.fixtures.default_plans import (
    DEFAULT_PLANS,
    build_default_plan,
)

from ._in_memory import (
    InMemoryPlanRepository,
    InMemorySubscriptionRepository,
    InMemoryTenantSettingRepository,
    RecordingPlatformEventPublisher,
)


@pytest.fixture
def tenant_id() -> object:
    from qzdap_schema.ids import TenantId

    return TenantId(uuid4())


@pytest.fixture
def other_tenant_id() -> object:
    from qzdap_schema.ids import TenantId

    return TenantId(uuid4())


@pytest.fixture
def plan_repo() -> InMemoryPlanRepository:
    return InMemoryPlanRepository()


@pytest.fixture
def sub_repo() -> InMemorySubscriptionRepository:
    return InMemorySubscriptionRepository()


@pytest.fixture
def setting_repo() -> InMemoryTenantSettingRepository:
    return InMemoryTenantSettingRepository()


@pytest.fixture
def publisher() -> RecordingPlatformEventPublisher:
    return RecordingPlatformEventPublisher()


@pytest.fixture
def service(
    plan_repo: InMemoryPlanRepository,
    sub_repo: InMemorySubscriptionRepository,
    setting_repo: InMemoryTenantSettingRepository,
    publisher: RecordingPlatformEventPublisher,
) -> PlatformService:
    return PlatformService.from_parts(
        plan_repo=plan_repo,
        subscription_repo=sub_repo,
        setting_repo=setting_repo,
        publisher=publisher,
    )


@pytest.fixture
def seeded_plan_repo() -> InMemoryPlanRepository:
    """A plan repo pre-populated with the 3 default plans."""
    repo = InMemoryPlanRepository()
    import asyncio

    async def _seed() -> None:
        for spec in DEFAULT_PLANS:
            await repo.add(build_default_plan(spec))

    asyncio.run(_seed())
    return repo


__all__ = [
    "InMemoryPlanRepository",
    "InMemorySubscriptionRepository",
    "InMemoryTenantSettingRepository",
    "PlatformService",
    "RecordingPlatformEventPublisher",
    "seeded_plan_repo",
]
