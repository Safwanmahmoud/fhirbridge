"""Transport-neutral validator adapter values and protocol."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from fhiratwill.errors import IgNotLoadedError, ValidatorUnavailableError


@dataclass(frozen=True, slots=True)
class ValidatorIssue:
    severity: str
    code: str
    message: str
    expression: str | None = None
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True, slots=True)
class ValidatorOutcome:
    issues: tuple[ValidatorIssue, ...] = ()
    profiles: tuple[str, ...] = ()
    duration_ms: int = 0


@dataclass(frozen=True, slots=True)
class FhirPathOutcome:
    expression: str
    values: tuple[Any, ...] = ()

    @property
    def is_true(self) -> bool:
        if len(self.values) != 1:
            return False
        value = self.values[0]
        return value if isinstance(value, bool) else str(value).lower() == "true"


@runtime_checkable
class ValidatorClient(Protocol):
    async def validate_resource(
        self, resource: dict[str, Any], *, profiles: Sequence[str] = ()
    ) -> ValidatorOutcome: ...

    async def evaluate_fhirpath(
        self, resource: dict[str, Any], expression: str
    ) -> FhirPathOutcome: ...


__all__ = [
    "FhirPathOutcome",
    "IgNotLoadedError",
    "ValidatorClient",
    "ValidatorIssue",
    "ValidatorOutcome",
    "ValidatorUnavailableError",
]
