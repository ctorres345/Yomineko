"""Split a long list into pages for a table."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
PAGE_SIZE = 50


@dataclass(frozen=True)
class Page(Generic[T]):
    items: list[T]
    number: int  # 1-based
    pages: int
    total: int

    @property
    def has_previous(self) -> bool:
        return self.number > 1

    @property
    def has_next(self) -> bool:
        return self.number < self.pages


def paginate(items: list[T], number: int, size: int = PAGE_SIZE) -> Page[T]:
    """The ``number``-th page (clamped to the pages that exist)."""
    pages = max(1, -(-len(items) // size))
    number = min(max(number, 1), pages)
    start = (number - 1) * size
    return Page(items[start : start + size], number, pages, len(items))
