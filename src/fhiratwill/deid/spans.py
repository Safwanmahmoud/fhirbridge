"""Detected identifier spans and deterministic overlap resolution."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from fhiratwill.deid.models import IdentifierClass


@dataclass(frozen=True, slots=True)
class Span:
    start: int
    end: int
    identifier_class: IdentifierClass
    detector: str

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("a span must have non-negative, increasing offsets")

    @property
    def length(self) -> int:
        return self.end - self.start


def resolve_overlaps(spans: Iterable[Span]) -> list[Span]:
    selected: list[Span] = []
    ordered = sorted(
        spans,
        key=lambda item: (-item.length, item.start, item.end, str(item.identifier_class)),
    )
    for candidate in ordered:
        if any(candidate.start < item.end and item.start < candidate.end for item in selected):
            continue
        selected.append(candidate)
    return sorted(selected, key=lambda item: item.start)


__all__ = ["Span", "resolve_overlaps"]
