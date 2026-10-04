"""Tests for the vector store protocol (no DB needed)."""

from __future__ import annotations

from uuid import uuid4

from qzdap_vector.store import SearchResult, VectorItem


def test_vector_item_construction() -> None:
    item = VectorItem(
        id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        embedding=[0.1] * 8,
        payload={"x": 1},
    )
    assert item.embedding == [0.1] * 8
    assert item.payload == {"x": 1}


def test_search_result_immutable() -> None:
    r = SearchResult(id=uuid4(), score=0.95, payload={"k": "v"})
    assert r.score == 0.95
