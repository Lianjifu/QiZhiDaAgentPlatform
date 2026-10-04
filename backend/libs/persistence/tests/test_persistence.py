"""Tests for the persistence package (lightweight, mostly structural)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from qzdap_kernel.errors import ForbiddenError

from qzdap_persistence.base import Base, make_composite_index
from qzdap_persistence.tenant_guard import (
    assert_tenant_scope,
    bind_tenant_to_session,
    current_tenant_id,
    reset_tenant_to_session,
)


def test_base_metadata_has_naming_convention() -> None:
    assert "ix" in Base.metadata.naming_convention
    ix_pattern = Base.metadata.naming_convention["ix"]
    assert isinstance(ix_pattern, str) and ix_pattern.startswith("ix_")


def test_make_composite_index_prefixes_tenant() -> None:
    idx = make_composite_index("workspace_id", "status")
    # Index name should start with ix_<table>_tenant_id_workspace_id_status
    assert idx.name is not None
    assert "tenant_id" in idx.name


def test_tenant_id_var_set_and_reset() -> None:
    assert current_tenant_id() is None
    tid = uuid4()
    token = bind_tenant_to_session(tid)
    assert current_tenant_id() == tid
    reset_tenant_to_session(token)
    assert current_tenant_id() is None


def test_assert_tenant_scope_blocks_cross() -> None:
    a, b = uuid4(), uuid4()
    token = bind_tenant_to_session(a)
    try:
        with pytest.raises(ForbiddenError) as exc:
            assert_tenant_scope(b)
        assert exc.value.code == "TENANT_DENIED"
    finally:
        reset_tenant_to_session(token)


def test_assert_tenant_scope_allows_self() -> None:
    tid = uuid4()
    token = bind_tenant_to_session(tid)
    try:
        assert_tenant_scope(tid)  # does not raise
    finally:
        reset_tenant_to_session(token)


def test_register_pgvector_is_idempotent() -> None:
    from qzdap_persistence.pgvector import register_pgvector

    register_pgvector()
    register_pgvector()  # must not raise
