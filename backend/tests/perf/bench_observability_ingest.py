"""Bench: observability_module event-bus → DB ingest latency.

Spins up an InProcessBus with the ObservabilityRecorder subscriber, fires
N synthetic events, and measures the wall-clock latency from `publish`
to the row landing in `InMemoryCostRecordRepository` / `InMemoryRunRecordRepository`.

This is a *micro-bench* of the subscriber routing path — it does NOT
exercise SQL. For SQL bench use a testcontainers PG run separately.

Usage:
    uv run python -m tests.perf.bench_observability_ingest --events 1000 --warmup 50
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from qzdap_messaging import InProcessBus

# observability_module's test in-memory doubles live in the module's own
# tests/unit tree (not under backend/tests/). Add that path so this bench
# can use the same stubs the unit tests do.
_OBS_TEST_DIR = (
    Path(__file__).resolve().parents[2] / "modules" / "observability_module" / "tests" / "unit"
)
if str(_OBS_TEST_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_OBS_TEST_DIR.parent))

from modules.observability_module.tests.unit._in_memory import (  # noqa: E402
    InMemoryCostRecordRepository,
    InMemoryRunRecordRepository,
)

from qzdap.modules.observability_module.application.pricing import (  # noqa: E402
    DEFAULT_LLM_PRICING,
    PricingCatalog,
)
from qzdap.modules.observability_module.application.recorder import (  # noqa: E402
    ObservabilityRecorder,
)


@dataclass(slots=True)
class IngestSample:
    duration_ms: float
    ok: bool
    error: str | None = None


def _envelope(event_name: str, payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        event_name=event_name,
        payload=payload,
        occurred_at_ms=int(datetime.now(UTC).timestamp() * 1000),
    )


def _build_recorder() -> ObservabilityRecorder:
    return ObservabilityRecorder(
        run_repo=InMemoryRunRecordRepository(),
        cost_repo=InMemoryCostRecordRepository(),
        pricing=PricingCatalog(
            llm_pricing=dict(DEFAULT_LLM_PRICING),
            tool_unit_cost={"echo": Decimal("0")},
            skill_unit_cost={},
            memory_write_unit_cost_usd=Decimal("0.00001"),
            knowledge_ingest_unit_cost_usd=Decimal("0.001"),
            channel_send_unit_cost_usd=Decimal("0.0005"),
        ),
    )


async def _publish_one(bus: InProcessBus, recorder: ObservabilityRecorder, i: int) -> IngestSample:
    tid = uuid4()
    wid = uuid4()
    payload = {
        "tenant_id": tid,
        "workspace_id": wid,
        "model_id": "default",
        "input_tokens": 100 + (i % 100),
        "output_tokens": 50 + (i % 50),
        "latency_ms": 10,
        "provider": "bench",
    }
    envelope = _envelope("ModelInvoked", payload)
    t0 = time.perf_counter()
    try:
        await bus.publish(envelope)
        return IngestSample(
            duration_ms=(time.perf_counter() - t0) * 1000,
            ok=True,
            error=None,
        )
    except Exception as exc:
        return IngestSample(duration_ms=0, ok=False, error=str(exc))


async def _run(args: argparse.Namespace) -> list[IngestSample]:
    bus = InProcessBus()
    recorder = _build_recorder()
    for topic in recorder.topics():
        bus.subscribe(topic, recorder.handle)

    # warmup
    for _ in range(args.warmup):
        await _publish_one(bus, recorder, 0)
    await asyncio.sleep(0)

    samples: list[IngestSample] = []
    started = time.perf_counter()
    for i in range(args.events):
        samples.append(await _publish_one(bus, recorder, i))
    wall_ms = (time.perf_counter() - started) * 1000

    total = len(samples)
    failed = sum(1 for s in samples if not s.ok)
    durs = sorted(s.duration_ms for s in samples if s.ok)
    print("--- bench_observability_ingest ---")
    print(f"  events   = {total}  failed = {failed}")
    print(f"  wall_ms  = {wall_ms:.1f}")
    print(f"  eps      = {total / (wall_ms / 1000):.1f}")
    if durs:
        p50 = durs[len(durs) // 2]
        p95 = durs[min(int(len(durs) * 0.95), len(durs) - 1)]
        p99 = durs[min(int(len(durs) * 0.99), len(durs) - 1)]
        print(f"  P50/P95/P99 ms = {p50:.2f} / {p95:.2f} / {p99:.2f}")
        print(f"  mean ms = {statistics.mean(durs):.2f}")
    return samples


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Observability recorder ingest bench.")
    p.add_argument("--events", type=int, default=1000)
    p.add_argument("--warmup", type=int, default=50)
    p.add_argument(
        "--p95-threshold-ms",
        type=float,
        default=5.0,
        help="Exit 1 if P95 exceeds this in ms (default 5.0 per SLO-1 micro-bench)",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    samples = asyncio.run(_run(args))
    durs = sorted(s.duration_ms for s in samples if s.ok)
    p95 = durs[min(int(len(durs) * 0.95), len(durs) - 1)] if durs else float("inf")
    exit_code = 0
    if p95 > args.p95_threshold_ms:
        print(f"FAIL: P95 {p95:.2f}ms > {args.p95_threshold_ms:.2f}ms")
        exit_code = 1
    if exit_code == 0:
        print("PASS")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
