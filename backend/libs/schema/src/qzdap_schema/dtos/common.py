"""Pagination contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PageRequest(BaseModel):
    """Standard pagination request (cursor-style + offset fallback)."""

    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = None
    offset: int = Field(default=0, ge=0)


class PageResponse[ItemT]:
    """Standard page response. ItemT is the runtime type of each row.

    Implementation note: we keep this as a non-Pydantic generic because
    Pydantic generics play poorly with `model_dump` in older runtimes.
    Use `to_dict(items=...)` instead.
    """

    items: list
    next_cursor: str | None
    total: int | None

    def __init__(
        self, items: list, next_cursor: str | None = None, total: int | None = None
    ) -> None:
        self.items = items
        self.next_cursor = next_cursor
        self.total = total

    def to_dict(self) -> dict:
        return {
            "items": [
                i.model_dump(mode="json") if hasattr(i, "model_dump") else i
                for i in self.items
            ],
            "next_cursor": self.next_cursor,
            "total": self.total,
        }
