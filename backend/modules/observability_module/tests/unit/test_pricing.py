"""Tests for PricingCatalog — LLM cost math + Settings fallback."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from qzdap.modules.observability_module.application.pricing import (
    DEFAULT_LLM_PRICING,
    DEFAULT_TOOL_UNIT_COST,
    ModelPricing,
    PricingCatalog,
)


@pytest.fixture
def catalog() -> PricingCatalog:
    return PricingCatalog(
        llm_pricing={
            "default": ModelPricing(Decimal("0.00015"), Decimal("0.0006")),
            "gpt-4o": ModelPricing(Decimal("0.0025"), Decimal("0.01")),
        },
        tool_unit_cost={"echo": Decimal(0), "premium_tool": Decimal("0.01")},
        skill_unit_cost={"echo_skill": Decimal("0.005")},
        memory_write_unit_cost_usd=Decimal("0.00001"),
        knowledge_ingest_unit_cost_usd=Decimal("0.001"),
        channel_send_unit_cost_usd=Decimal("0.0005"),
        currency="USD",
    )


# ── llm_cost ──────────────────────────────────────────────────────────────


def test_llm_cost_known(catalog: PricingCatalog) -> None:
    in_c, out_c = catalog.llm_cost(
        model_id="gpt-4o", input_tokens=1000, output_tokens=500
    )
    assert in_c == Decimal("0.0025")
    assert out_c == Decimal("0.01") * Decimal("0.5")


def test_llm_cost_falls_back_to_default(catalog: PricingCatalog) -> None:
    in_c, out_c = catalog.llm_cost(
        model_id="unknown-model", input_tokens=2000, output_tokens=1000
    )
    assert in_c == Decimal("0.00015") * Decimal(2)
    assert out_c == Decimal("0.0006")


def test_llm_cost_rejects_negative_tokens(catalog: PricingCatalog) -> None:
    with pytest.raises(ValueError):
        catalog.llm_cost(model_id="default", input_tokens=-1, output_tokens=0)
    with pytest.raises(ValueError):
        catalog.llm_cost(model_id="default", input_tokens=0, output_tokens=-1)


def test_llm_cost_zero_tokens() -> None:
    cat = PricingCatalog(
        llm_pricing={"default": ModelPricing(Decimal(1), Decimal(1))},
        tool_unit_cost={},
        skill_unit_cost={},
        memory_write_unit_cost_usd=Decimal(0),
        knowledge_ingest_unit_cost_usd=Decimal(0),
        channel_send_unit_cost_usd=Decimal(0),
    )
    in_c, out_c = cat.llm_cost(model_id="default", input_tokens=0, output_tokens=0)
    assert in_c == Decimal(0)
    assert out_c == Decimal(0)


# ── tool / skill / memory / knowledge / channel ───────────────────────────


def test_tool_cost_known(catalog: PricingCatalog) -> None:
    assert catalog.tool_cost(tool_name="premium_tool") == Decimal("0.01")


def test_tool_cost_unknown(catalog: PricingCatalog) -> None:
    assert catalog.tool_cost(tool_name="nope") == Decimal(0)


def test_skill_cost_known(catalog: PricingCatalog) -> None:
    assert catalog.skill_cost(skill_name="echo_skill") == Decimal("0.005")


def test_skill_cost_unknown(catalog: PricingCatalog) -> None:
    assert catalog.skill_cost(skill_name="whatever") == Decimal(0)


def test_memory_cost(catalog: PricingCatalog) -> None:
    assert catalog.memory_write_cost() == Decimal("0.00001")


def test_knowledge_ingest_cost_per_chunk(catalog: PricingCatalog) -> None:
    assert catalog.knowledge_ingest_cost(chunk_count=1) == Decimal("0.001")
    assert catalog.knowledge_ingest_cost(chunk_count=5) == Decimal("0.005")


def test_knowledge_ingest_cost_rejects_negative(catalog: PricingCatalog) -> None:
    with pytest.raises(ValueError):
        catalog.knowledge_ingest_cost(chunk_count=-1)


def test_channel_send_cost(catalog: PricingCatalog) -> None:
    assert catalog.channel_send_cost() == Decimal("0.0005")


# ── from_settings ─────────────────────────────────────────────────────────


def test_from_settings_parses_json() -> None:
    settings = SimpleNamespace(
        model_pricing_json='{"default":{"input":"0.01","output":"0.03"},"custom":{"input":"1.0","output":"2.0"}}',
        tool_unit_cost_json='{"t1":"0.05","t2":"0.1"}',
        skill_unit_cost_json='{"s1":"0.02"}',
        memory_write_unit_cost_usd=0.0001,
        knowledge_ingest_unit_cost_usd=0.002,
        channel_send_unit_cost_usd=0.001,
        default_currency="EUR",
    )
    cat = PricingCatalog.from_settings(settings)
    assert cat.currency == "EUR"
    in_c, out_c = cat.llm_cost(model_id="custom", input_tokens=1000, output_tokens=1000)
    assert in_c == Decimal("1.0")
    assert out_c == Decimal("2.0")
    assert cat.tool_cost(tool_name="t1") == Decimal("0.05")
    assert cat.skill_cost(skill_name="s1") == Decimal("0.02")


def test_from_settings_bad_json_falls_back() -> None:
    settings = SimpleNamespace(
        model_pricing_json="not-json",
        tool_unit_cost_json="also-not-json",
        skill_unit_cost_json="{}",
        memory_write_unit_cost_usd=0.0,
        knowledge_ingest_unit_cost_usd=0.0,
        channel_send_unit_cost_usd=0.0,
        default_currency="USD",
    )
    cat = PricingCatalog.from_settings(settings)
    # Fallback to DEFAULT_LLM_PRICING's "default" key.
    in_c, _ = cat.llm_cost(model_id="x", input_tokens=1000, output_tokens=0)
    assert in_c == DEFAULT_LLM_PRICING["default"].input_usd_per_1k
    # tool empty fallback when JSON malformed
    assert cat.tool_cost(tool_name="anything") == Decimal(0)


def test_from_settings_skips_malformed_entries() -> None:
    settings = SimpleNamespace(
        model_pricing_json='{"default":{"input":"0.01","output":"0.03"},"bad":"not-a-dict","also_bad":{"wrong":"shape"}}',
        tool_unit_cost_json="{}",
        skill_unit_cost_json="{}",
        memory_write_unit_cost_usd=0.0,
        knowledge_ingest_unit_cost_usd=0.0,
        channel_send_unit_cost_usd=0.0,
        default_currency="USD",
    )
    cat = PricingCatalog.from_settings(settings)
    assert "default" in cat.llm_pricing
    # bad/also_bad entries silently dropped
    assert "bad" not in cat.llm_pricing
    assert "also_bad" not in cat.llm_pricing


def test_default_tool_unit_cost_shipped() -> None:
    assert "echo" in DEFAULT_TOOL_UNIT_COST
    assert DEFAULT_TOOL_UNIT_COST["echo"] == Decimal(0)
