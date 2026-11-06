#!/usr/bin/env python3
"""把**开发目录**写进开发库 —— 显式一次性脚本 ✓。

⚠️ **开发环境不种内容数据** ✓ —— 应用启动**不会**跑这个脚本 ✓；
目录页开箱仍是空态 ✓。需要这三个智能体时手动跑一次 ✓：

    cd backend && .venv/bin/python dev/seed_dev_catalog.py

幂等 ✓ —— 资产 id 由 ``uuid5`` 派生 ✓，重复跑不会产生第二份 ✓
（评测套件按名字去重 ✓）。
"""

from __future__ import annotations

import argparse
import os
from typing import Any

import httpx

from qzdap.composition.dev_catalog import build_assets

DEFAULT_BASE = os.environ.get("QZDAP_DEV_API", "http://127.0.0.1:9151")
DEFAULT_EMAIL = os.environ.get("QZDAP_DEV_EMAIL", "admin@dev.qzdap.dev")
DEFAULT_PASSWORD = os.environ.get("QZDAP_DEV_PASSWORD", "dev-admin-password-change-me")

LIST_PATHS: dict[str, str] = {
    "skill": "/api/admin/skills",
    "kb": "/api/admin/knowledge/kbs",
    "doc": "/api/admin/knowledge/docs",
    "workflow": "/api/admin/workflows",
    "agent": "/api/admin/agents",
    "evalSuite": "/api/admin/evaluations/suites",
}


class SeedError(RuntimeError):
    """落库失败 ✓ —— 带上资产 key ✓."""


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for field in ("items", "data", "results"):
            value = payload.get(field)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def login(client: httpx.Client, email: str, password: str) -> tuple[str, str, str]:
    """登录拿 token + 租户 / 工作区 ✓ —— 目录内容按工作区落 ✓."""
    resp = client.post(
        "/v1/identity/login", json={"email": email, "password": password}, timeout=15.0
    )
    resp.raise_for_status()
    body = resp.json()
    user = body["user"]
    return str(body["access_token"]), str(user["tenant_id"]), str(user["workspace_id"])


def main() -> int:
    parser = argparse.ArgumentParser(description="把开发目录写进开发库(幂等)")
    parser.add_argument("--base", default=DEFAULT_BASE, help="后端地址")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="管理员邮箱")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="管理员口令")
    parser.add_argument("--dry-run", action="store_true", help="只列将要落库的资产")
    args = parser.parse_args()

    assets = build_assets()

    with httpx.Client(base_url=args.base, timeout=30.0) as client:
        token, tenant_id, workspace_id = login(client, args.email, args.password)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": tenant_id,
            "X-Workspace-Id": workspace_id,
        }

        existing: dict[str, list[dict[str, Any]]] = {}
        for kind, path in LIST_PATHS.items():
            resp = client.get(path, headers=headers, timeout=30.0)
            resp.raise_for_status()
            existing[kind] = _items(resp.json())

        created = 0
        skipped = 0
        for asset in assets:
            known = existing.get(asset.kind, [])
            if asset.kind == "evalSuite":
                hit = any(item.get("name") == asset.body.get("name") for item in known)
            else:
                hit = any(str(item.get("id")) == asset.id for item in known)
            if hit:
                skipped += 1
                print(f"  · 跳过 {asset.kind:<10} {asset.key}")
                continue
            if args.dry_run:
                print(f"  - 将写入 {asset.kind:<10} {asset.key}  id={asset.id}")
                continue
            resp = client.post(asset.path, json=asset.payload, headers=headers, timeout=60.0)
            if resp.status_code >= 400:
                raise SeedError(
                    f"{asset.kind}/{asset.key} 落库失败 HTTP {resp.status_code}: {resp.text[:300]}"
                )
            created += 1
            print(f"  ✓ 写入 {asset.kind:<10} {asset.key}  id={asset.id}")

    verb = "将要写入" if args.dry_run else "写入"
    print(f"\n{verb} {created} 条,跳过 {skipped} 条 —— 共 {len(assets)} 条资产")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
