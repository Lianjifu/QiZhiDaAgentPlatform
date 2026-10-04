"""PricingCatalog — pure-Python cost calculation.

Loaded once from settings at lifespan; cost methods are pure functions
that take token counts / entity names and return ``Decimal`` amounts.

Pricing is env-driven (per user decision for P9): a JSON blob in
settings.py.  When parsing fails we fall back to hardcoded defaults
below.

This module introduces ``decimal.Decimal`` as the project's money
type — ``NUMERIC(12, 6)`` in the SQL column, ``str()``-serialized in
HTTP DTOs, ``Decimal(...)`` reconstructed by clients.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal

_log = logging.getLogger(__name__)


# ── Pricing model ─────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class ModelPricing:
    input_usd_per_1k: Decimal
    output_usd_per_1k: Decimal


# ── Hardcoded fallback defaults ──────────────────────────────────────────


DEFAULT_LLM_PRICING: dict[str, ModelPricing] = {
    "default": ModelPricing(
        input_usd_per_1k=Decimal("0.00015"),
        output_usd_per_1k=Decimal("0.0006"),
    ),
    "gpt-4o-mini": ModelPricing(
        input_usd_per_1k=Decimal("0.00015"),
        output_usd_per_1k=Decimal("0.0006"),
    ),
    "gpt-4o": ModelPricing(
        input_usd_per_1k=Decimal("0.0025"),
        output_usd_per_1k=Decimal("0.01"),
    ),
}
DEFAULT_TOOL_UNIT_COST: dict[str, Decimal] = {
    "echo": Decimal(0),
    "reverse": Decimal(0),
    "clock": Decimal(0),
}
DEFAULT_SKILL_UNIT_COST: dict[str, Decimal] = {}
DEFAULT_MEMORY_WRITE_COST_USD: Decimal = Decimal("0.00001")
DEFAULT_KNOWLEDGE_INGEST_COST_USD: Decimal = Decimal("0.001")
DEFAULT_CHANNEL_SEND_COST_USD: Decimal = Decimal("0.0005")


# ── Pricing catalog ──────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class PricingCatalog:
    """Loaded once at lifespan; pure cost compute.

    Every cost method returns ``Decimal``.  Unknown keys fall back to
    ``default`` pricing (LLM) or ``Decimal('0')`` (tool/skill).
    """

    llm_pricing: dict[str, ModelPricing]
    tool_unit_cost: dict[str, Decimal]
    skill_unit_cost: dict[str, Decimal]
    memory_write_unit_cost_usd: Decimal
    knowledge_ingest_unit_cost_usd: Decimal
    channel_send_unit_cost_usd: Decimal
    currency: str = "USD"

    # ── LLM ─────────────────────────────────────────────────────────────

    def llm_cost(
        self, *, model_id: str, input_tokens: int, output_tokens: int
    ) -> tuple[Decimal, Decimal]:
        """Return ``(input_cost_usd, output_cost_usd)``.

        Unknown model_id falls back to ``default``.  Both tokens must
        be non-negative.
        """
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("token counts must be non-negative")
        pricing = self.llm_pricing.get(model_id) or self.llm_pricing.get("default")
        if pricing is None:
            pricing = ModelPricing(
                input_usd_per_1k=Decimal(0),
                output_usd_per_1k=Decimal(0),
            )
        in_cost = (Decimal(input_tokens) / Decimal(1000)) * pricing.input_usd_per_1k
        out_cost = (Decimal(output_tokens) / Decimal(1000)) * pricing.output_usd_per_1k
        return in_cost, out_cost

    # ── Tool / Skill / Memory / Knowledge / Channel ─────────────────────

    def tool_cost(self, *, tool_name: str) -> Decimal:
        return self.tool_unit_cost.get(tool_name, Decimal(0))

    def skill_cost(self, *, skill_name: str) -> Decimal:
        return self.skill_unit_cost.get(skill_name, Decimal(0))

    def memory_write_cost(self) -> Decimal:
        return self.memory_write_unit_cost_usd

    def knowledge_ingest_cost(self, *, chunk_count: int = 1) -> Decimal:
        if chunk_count < 0:
            raise ValueError("chunk_count must be non-negative")
        return self.knowledge_ingest_unit_cost_usd * Decimal(chunk_count)

    def channel_send_cost(self) -> Decimal:
        return self.channel_send_unit_cost_usd

    # ── Settings loader ─────────────────────────────────────────────────

    @classmethod
    def from_settings(cls, settings: object) -> PricingCatalog:
        """Parse JSON pricing from settings; fall back to defaults on error."""

        llm_raw = _getattr_str(settings, "model_pricing_json", "{}")
        tool_raw = _getattr_str(settings, "tool_unit_cost_json", "{}")
        skill_raw = _getattr_str(settings, "skill_unit_cost_json", "{}")

        llm_pricing = _parse_llm_pricing(llm_raw)
        tool_unit_cost = _parse_unit_map(tool_raw)
        skill_unit_cost = _parse_unit_map(skill_raw)
        memory_cost = Decimal(
            str(
                _getattr_float(
                    settings,
                    "memory_write_unit_cost_usd",
                    float(DEFAULT_MEMORY_WRITE_COST_USD),
                )
            )
        )
        knowledge_cost = Decimal(
            str(
                _getattr_float(
                    settings,
                    "knowledge_ingest_unit_cost_usd",
                    float(DEFAULT_KNOWLEDGE_INGEST_COST_USD),
                )
            )
        )
        channel_cost = Decimal(
            str(
                _getattr_float(
                    settings,
                    "channel_send_unit_cost_usd",
                    float(DEFAULT_CHANNEL_SEND_COST_USD),
                )
            )
        )
        currency = _getattr_str(settings, "default_currency", "USD")

        return cls(
            llm_pricing=llm_pricing,
            tool_unit_cost=tool_unit_cost,
            skill_unit_cost=skill_unit_cost,
            memory_write_unit_cost_usd=memory_cost,
            knowledge_ingest_unit_cost_usd=knowledge_cost,
            channel_send_unit_cost_usd=channel_cost,
            currency=currency,
        )


# ── Helpers ──────────────────────────────────────────────────────────────


def _getattr_str(settings: object, key: str, default: str) -> str:
    raw = getattr(settings, key, default)
    if not isinstance(raw, str):
        raw = str(raw)
    return raw


def _getattr_float(settings: object, key: str, default: float) -> float:
    raw = getattr(settings, key, default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _parse_llm_pricing(raw: str) -> dict[str, ModelPricing]:
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise TypeError("not a dict")
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        _log.warning(
            "model_pricing_json parse failed, falling back to defaults: %s", exc
        )
        return dict(DEFAULT_LLM_PRICING)
    out: dict[str, ModelPricing] = {}
    for model_id, pair in data.items():
        if not isinstance(pair, dict):
            continue
        try:
            out[model_id] = ModelPricing(
                input_usd_per_1k=Decimal(str(pair["input"])),
                output_usd_per_1k=Decimal(str(pair["output"])),
            )
        except (KeyError, TypeError, ValueError):
            _log.warning("skipping malformed llm pricing entry %s", model_id)
    out.setdefault(
        "default",
        DEFAULT_LLM_PRICING.get(
            "default",
            ModelPricing(
                input_usd_per_1k=Decimal(0),
                output_usd_per_1k=Decimal(0),
            ),
        ),
    )
    return out


def _parse_unit_map(raw: str) -> dict[str, Decimal]:
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise TypeError("not a dict")
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        _log.warning("unit cost JSON parse failed: %s", exc)
        return {}
    out: dict[str, Decimal] = {}
    for k, v in data.items():
        try:
            out[str(k)] = Decimal(str(v))
        except (TypeError, ValueError):
            _log.warning("skipping malformed unit cost entry %s", k)
    return out


__all__ = [
    "DEFAULT_CHANNEL_SEND_COST_USD",
    "DEFAULT_KNOWLEDGE_INGEST_COST_USD",
    "DEFAULT_LLM_PRICING",
    "DEFAULT_MEMORY_WRITE_COST_USD",
    "DEFAULT_SKILL_UNIT_COST",
    "DEFAULT_TOOL_UNIT_COST",
    "ModelPricing",
    "PricingCatalog",
]
