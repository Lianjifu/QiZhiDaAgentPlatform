"""Smoke test runner — boot the app + hit /healthz + create a tenant + workspace.

Run via `make smoke` (or `uv run python tests/e2e/smoke.py`).
"""

from __future__ import annotations

import os
import sys
from uuid import uuid4

import httpx

BASE = os.environ.get("QZDAP_SMOKE_BASE_URL", "http://127.0.0.1:8100")


def main() -> int:
    print(f"[smoke] BASE = {BASE}", flush=True)

    with httpx.Client(timeout=10.0) as c:
        # 1. healthz
        r = c.get(f"{BASE}/healthz")
        assert r.status_code == 200, r.text
        assert r.json() == {"status": "ok"}
        print("[smoke] /healthz OK")

        # 2. create tenant
        slug = f"smoke-{uuid4().hex[:8]}"
        r = c.post(f"{BASE}/v1/identity/tenants", json={"slug": slug, "display_name": "Smoke Test"})
        assert r.status_code == 201, r.text
        tenant_id = r.json()["id"]
        print(f"[smoke] tenant created: {tenant_id}")

        # 3. create workspace
        r = c.post(
            f"{BASE}/v1/identity/workspaces",
            json={"slug": "smoke", "display_name": "Smoke"},
            headers={"X-Tenant-Id": tenant_id},
        )
        assert r.status_code == 201, r.text
        print(f"[smoke] workspace created: {r.json()['id']}")

        # 4. list workspaces (cross-tenant attempt fails)
        r = c.get(
            f"{BASE}/v1/identity/workspaces",
            headers={"X-Tenant-Id": uuid4().hex},  # wrong tenant
        )
        # Should 200 with empty list OR 403; here we just confirm no 500.
        assert r.status_code < 500, r.text
        print("[smoke] cross-tenant attempt handled without 500")

        # 5. metrics
        r = c.get(f"{BASE}/metrics")
        assert r.status_code == 200, r.text
        assert b"qzdap_http_requests_total" in r.content
        print("[smoke] /metrics OK")

    print("[smoke] all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
