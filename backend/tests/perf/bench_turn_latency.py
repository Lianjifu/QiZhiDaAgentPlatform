"""Bench: turn latency under concurrent load.

Usage:
    # 1. start app + point to it
    export QZDAP_BENCH_URL=http://127.0.0.1:8102
    # token minted by libs.auth.mint_admin_token
    export QZDAP_BENCH_TOKEN=$(
        uv run python -c "from libs.auth import mint_admin_token; print(mint_admin_token())"
    )
    export QZDAP_BENCH_TENANT=<uuid>
    export QZDAP_BENCH_WORKSPACE=<uuid>

    # 2. run bench (10 concurrent x 5 turns = 50 requests)
    uv run python -m tests.perf.bench_turn_latency --concurrency 10 --turns 5

    # 3. read report
    # P50=… P95=… P99=… QPS=…  failure_rate=…
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time
from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class Sample:
    duration_ms: float
    status: int
    ok: bool
    error: str | None = None


def _env(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if val is None:
        print(f"missing env: {name}", file=sys.stderr)
        sys.exit(2)
    return val


async def _create_session(
    client: httpx.AsyncClient,
    base: str,
    token: str,
    tenant: str,
    workspace: str,
    agent_id: str,
) -> str:
    resp = await client.post(
        f"{base}/v1/agents/{agent_id}/sessions",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": tenant,
            "X-Workspace-Id": workspace,
        },
        json={"agent_version": "1.0.0"},
    )
    resp.raise_for_status()
    return resp.json()["id"]


async def _one_turn(
    client: httpx.AsyncClient,
    base: str,
    token: str,
    tenant: str,
    workspace: str,
    session_id: str,
    content: str,
    ring: str | None = None,
) -> Sample:
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": tenant,
        "X-Workspace-Id": workspace,
        "Accept": "text/event-stream",
    }
    if ring:
        headers["X-QZDAP-Ring"] = ring
    t0 = time.perf_counter()
    try:
        async with client.stream(
            "POST",
            f"{base}/v1/sessions/{session_id}/turn/stream",
            headers=headers,
            json={"content": content},
            timeout=30.0,
        ) as r:
            await r.aread()
            elapsed = (time.perf_counter() - t0) * 1000
            return Sample(
                duration_ms=elapsed,
                status=r.status_code,
                ok=200 <= r.status_code < 300,
                error=None if r.status_code < 400 else f"status={r.status_code}",
            )
    except Exception as exc:
        return Sample(
            duration_ms=(time.perf_counter() - t0) * 1000,
            status=0,
            ok=False,
            error=str(exc),
        )


async def _run(args: argparse.Namespace) -> list[Sample]:
    base = _env("QZDAP_BENCH_URL")
    token = _env("QZDAP_BENCH_TOKEN")
    tenant = _env("QZDAP_BENCH_TENANT")
    workspace = _env("QZDAP_BENCH_WORKSPACE")
    agent_id = _env("QZDAP_BENCH_AGENT_ID")
    ring = os.environ.get("QZDAP_BENCH_RING")

    limits = httpx.Limits(max_keepalive_connections=args.concurrency * 2)
    async with httpx.AsyncClient(limits=limits) as client:
        session_id = await _create_session(client, base, token, tenant, workspace, agent_id)
        sem = asyncio.Semaphore(args.concurrency)

        async def worker() -> list[Sample]:
            out: list[Sample] = []
            for _ in range(args.turns):
                async with sem:
                    out.append(
                        await _one_turn(
                            client,
                            base,
                            token,
                            tenant,
                            workspace,
                            session_id,
                            args.content,
                            ring=ring,
                        )
                    )
            return out

        started = time.perf_counter()
        workers = [worker() for _ in range(args.concurrency)]
        results = await asyncio.gather(*workers)
        wall_ms = (time.perf_counter() - started) * 1000

    samples = [s for batch in results for s in batch]
    total = len(samples)
    failed = sum(1 for s in samples if not s.ok)
    durs = sorted(s.duration_ms for s in samples if s.ok)

    print("--- bench_turn_latency ---")
    print(f"  url       = {base}")
    print(f"  ring      = {ring or 'stable'}")
    print(f"  concurrency = {args.concurrency}")
    print(f"  turns/worker = {args.turns}")
    print(f"  total    = {total}  failed = {failed}  failure_rate = {failed / total:.1%}")
    print(f"  wall_ms  = {wall_ms:.1f}")
    print(f"  qps      = {total / (wall_ms / 1000):.2f}")
    if durs:
        p50 = durs[int(len(durs) * 0.50)]
        p95 = durs[min(int(len(durs) * 0.95), len(durs) - 1)]
        p99 = durs[min(int(len(durs) * 0.99), len(durs) - 1)]
        print(f"  P50      = {p50:.1f} ms")
        print(f"  P95      = {p95:.1f} ms")
        print(f"  P99      = {p99:.1f} ms")
        print(f"  min/max  = {durs[0]:.1f} / {durs[-1]:.1f} ms")
        print(f"  mean     = {statistics.mean(durs):.1f} ms")
    return samples


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Turn latency bench.")
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--turns", type=int, default=5)
    p.add_argument(
        "--content",
        type=str,
        default="bencher hello",
        help="Prompt content for each turn",
    )
    p.add_argument(
        "--fail-threshold",
        type=float,
        default=0.01,
        help="Exit 1 if failure_rate exceeds this (default 0.01 = 1 percent)",
    )
    p.add_argument(
        "--p95-threshold-ms",
        type=float,
        default=10_000.0,
        help="Exit 1 if P95 exceeds this in ms (default 10000 = 10s, matches SLO-1)",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    samples = asyncio.run(_run(args))
    total = len(samples)
    failed = sum(1 for s in samples if not s.ok)
    durs = sorted(s.duration_ms for s in samples if s.ok)
    failure_rate = failed / total if total else 0.0
    p95 = durs[min(int(len(durs) * 0.95), len(durs) - 1)] if durs else float("inf")
    exit_code = 0
    if failure_rate > args.fail_threshold:
        print(f"FAIL: failure_rate {failure_rate:.1%} > {args.fail_threshold:.1%}")
        exit_code = 1
    if p95 > args.p95_threshold_ms:
        print(f"FAIL: P95 {p95:.1f}ms > {args.p95_threshold_ms:.1f}ms (SLO-1)")
        exit_code = 1
    if exit_code == 0:
        print("PASS")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
