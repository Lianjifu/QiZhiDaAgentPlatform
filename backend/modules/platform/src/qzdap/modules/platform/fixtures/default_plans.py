"""Default Plan catalog — 3 plans: free / pro / enterprise.

Loaded at lifespan start and seeded idempotently.  Each plan has:

- ``code`` — short stable identifier used in API + UI
- ``display_name`` — human-readable label
- ``limits`` — JSON dict (max_turns_per_day, max_tokens_per_min, …)
- ``features`` — ordered tuple of feature strings
- ``price_monthly_usd`` — Decimal for money
- ``sort_order`` — for stable catalog ordering
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from qzdap.modules.platform.domain.entities import Plan
from qzdap.modules.platform.domain.value_objects import PlanStatus


@dataclass(slots=True, frozen=True)
class _PlanSpec:
    code: str
    display_name: str
    description: str
    limits: dict[str, object]
    features: tuple[str, ...]
    price_monthly_usd: Decimal
    sort_order: int


DEFAULT_PLANS: tuple[_PlanSpec, ...] = (
    _PlanSpec(
        code="free",
        display_name="Free",
        description="Get started — 100 turns/day, 1 workspace.",
        limits={
            "max_turns_per_day": 100,
            "max_workspaces": 1,
            "max_team_members": 4,
            "data_retention_days": 7,
        },
        features=(
            "1 workspace",
            "100 turns / day",
            "community knowledge packs",
            "single-tenant observability (24h retention)",
        ),
        price_monthly_usd=Decimal("0.00"),
        sort_order=10,
    ),
    _PlanSpec(
        code="pro",
        display_name="Pro",
        description="For small teams — 10 workspaces, 5K turns/day, 90-day retention.",
        limits={
            "max_turns_per_day": 5_000,
            "max_workspaces": 10,
            "max_team_members": 25,
            "data_retention_days": 90,
        },
        features=(
            "10 workspaces",
            "5,000 turns / day",
            "premium knowledge packs",
            "eval gate enabled",
            "per-tenant observability (90-day retention)",
            "private skill + tool registries",
        ),
        price_monthly_usd=Decimal("99.00"),
        sort_order=20,
    ),
    _PlanSpec(
        code="enterprise",
        display_name="Enterprise",
        description="Custom limits — contact sales for SSO, audit retention, and SLAs.",
        limits={
            "max_turns_per_day": 100_000,
            "max_workspaces": 1_000,
            "max_team_members": 10_000,
            "data_retention_days": 730,
        },
        features=(
            "1,000 workspaces",
            "100,000 turns / day",
            "all knowledge packs",
            "SSO + SCIM",
            "audit retention 2 years",
            "24×7 SLA",
            "dedicated tenant routing",
        ),
        price_monthly_usd=Decimal("0.00"),
        sort_order=30,
    ),
)


def build_default_plan(spec: _PlanSpec) -> Plan:
    """Materialize a :class:`Plan` from a spec; used by the lifespan seed."""
    return Plan.create(
        code=spec.code,
        display_name=spec.display_name,
        description=spec.description,
        limits=dict(spec.limits),
        features=spec.features,
        price_monthly_usd=spec.price_monthly_usd,
        status=PlanStatus.ACTIVE,
        sort_order=spec.sort_order,
    )


__all__ = ["DEFAULT_PLANS", "build_default_plan"]
