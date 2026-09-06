"""Transport-neutral terminology protocol and immutable result values."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class BindingStrength(StrEnum):
    REQUIRED = "required"
    EXTENSIBLE = "extensible"
    PREFERRED = "preferred"
    EXAMPLE = "example"

    @property
    def is_blocking(self) -> bool:
        return self is BindingStrength.REQUIRED


@dataclass(frozen=True, slots=True)
class Coding:
    system: str | None
    code: str | None
    display: str | None = None
    version: str | None = None


@dataclass(frozen=True, slots=True)
class ValidateCodeResult:
    result: bool
    coding: Coding
    value_set: str | None = None
    display: str | None = None
    message: str | None = None
    code_system_version: str | None = None
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LookupResult:
    coding: Coding
    display: str | None = None
    code_system_version: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExpansionResult:
    value_set: str
    contains: tuple[Coding, ...]
    total: int | None = None
    offset: int | None = None
    incomplete: bool = False


class SubsumptionOutcome(StrEnum):
    EQUIVALENT = "equivalent"
    SUBSUMES = "subsumes"
    SUBSUMED_BY = "subsumed-by"
    NOT_SUBSUMED = "not-subsumed"


@dataclass(frozen=True, slots=True)
class SubsumesResult:
    outcome: SubsumptionOutcome
    left: Coding
    right: Coding


@dataclass(frozen=True, slots=True)
class TranslateMatch:
    equivalence: str
    concept: Coding


@dataclass(frozen=True, slots=True)
class TranslateResult:
    result: bool
    matches: tuple[TranslateMatch, ...] = ()
    message: str | None = None


@dataclass(frozen=True, slots=True)
class CodeSystemVersion:
    system: str
    version: str | None


@dataclass(frozen=True, slots=True)
class TerminologyHealth:
    reachable: bool
    software: str | None = None
    fhir_version: str | None = None
    code_systems: tuple[CodeSystemVersion, ...] = ()
    detail: str | None = None


@runtime_checkable
class TerminologyClient(Protocol):
    """Async adapter contract. Unavailable answers must raise, never return invalid."""

    async def validate_code(
        self,
        *,
        system: str | None,
        code: str,
        display: str | None = None,
        version: str | None = None,
        value_set: str | None = None,
    ) -> ValidateCodeResult: ...

    async def lookup(
        self, *, system: str, code: str, version: str | None = None
    ) -> LookupResult: ...

    async def expand(
        self,
        *,
        value_set: str,
        filter_text: str | None = None,
        count: int | None = None,
        offset: int | None = None,
    ) -> ExpansionResult: ...

    async def subsumes(
        self,
        *,
        system: str,
        code_a: str,
        code_b: str,
        version: str | None = None,
    ) -> SubsumesResult: ...

    async def translate(
        self,
        *,
        system: str,
        code: str,
        target_system: str | None = None,
        concept_map: str | None = None,
    ) -> TranslateResult: ...

    async def health(self, *, code_systems: Sequence[str] = ()) -> TerminologyHealth: ...

    async def aclose(self) -> None: ...


__all__ = [
    "BindingStrength",
    "CodeSystemVersion",
    "Coding",
    "ExpansionResult",
    "LookupResult",
    "SubsumesResult",
    "SubsumptionOutcome",
    "TerminologyClient",
    "TerminologyHealth",
    "TranslateMatch",
    "TranslateResult",
    "ValidateCodeResult",
]
