"""验收样本的**纯逻辑** ✓（H1 / P-09 ✓）。

⚠️ **不碰数据库** ✓ —— 这里只验「样本是可复现的 ✓ / 脱敏的 ✓ / 不该种的环境
拦得住 ✓」✓（真正种库在 ``scripts/seed_acceptance_samples.py`` ✓）。
"""

from __future__ import annotations

import pytest

from qzdap.composition.acceptance_samples import (
    FORBIDDEN_ENVS,
    QA_PASSWORD,
    acceptance_profiles,
    assert_seedable_env,
    qa_id,
)


def test_the_ids_are_reproducible() -> None:
    """**同一个名字 → 同一个 id** ✓（可复现 ✓ —— 跑两次不重复 ✓）。"""
    assert qa_id("tenant-a") == qa_id("tenant-a")
    assert qa_id("tenant-a") != qa_id("tenant-b")


def test_the_emails_cannot_be_delivered_to() -> None:
    """**邮箱用 ``.invalid``** ✓（RFC 2606 ✓ —— 保证不可投递 ✓ —— 脱敏 ✓）。"""
    for profile in acceptance_profiles():
        for email, _display, _role in profile.accounts:
            assert email.endswith("@example.invalid")


def test_two_tenants_with_two_users_each() -> None:
    """**两个租户 × 两个用户** ✓（验隔离 ✓ —— 样本得够分得开 ✓）。"""
    profiles = acceptance_profiles()
    assert len(profiles) == 2
    assert {profile.tenant_slug for profile in profiles} == {"qa-tenant-a", "qa-tenant-b"}
    for profile in profiles:
        assert len(profile.accounts) == 2
        assert profile.tenant_id != qa_id("nope")


def test_the_demo_and_production_envs_are_refused() -> None:
    """**demo / production 不许种** ✓（这两个 env 已退役 ✓ —— 留着当兜底 ✓）。"""
    assert {"demo", "production"} == FORBIDDEN_ENVS
    for env in FORBIDDEN_ENVS:
        with pytest.raises(ValueError):
            assert_seedable_env(env)


def test_the_dev_envs_are_allowed() -> None:
    """**开发 / 测试可以种** ✓（只剩这三个 env ✓）。"""
    for env in ("development", "test", "ci"):
        assert_seedable_env(env)


def test_the_password_is_a_local_constant() -> None:
    """**样本口令是本地固定值** ✓（不是生产口令 ✓）。"""
    assert QA_PASSWORD == "qa-local-samples-only"
