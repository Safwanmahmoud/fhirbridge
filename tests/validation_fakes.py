from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from fhiratwill import (
    Coding,
    ExpansionResult,
    LookupResult,
    SubsumesResult,
    SubsumptionOutcome,
    TerminologyHealth,
    TranslateResult,
    ValidateCodeResult,
)
from fhiratwill.errors import TerminologyUnavailableError
from fhiratwill.validation import (
    FhirPathOutcome,
    ValidatorIssue,
    ValidatorOutcome,
    ValidatorUnavailableError,
)


@dataclass
class FakeValidator:
    issues: tuple[ValidatorIssue, ...] = ()
    unavailable: bool = False

    async def validate_resource(
        self, resource: dict[str, Any], *, profiles: Sequence[str] = ()
    ) -> ValidatorOutcome:
        del resource
        if self.unavailable:
            raise ValidatorUnavailableError("validator unavailable")
        return ValidatorOutcome(self.issues, tuple(profiles))

    async def evaluate_fhirpath(self, resource: dict[str, Any], expression: str) -> FhirPathOutcome:
        del resource
        if self.unavailable:
            raise ValidatorUnavailableError("validator unavailable")
        return FhirPathOutcome(expression, (True,))


@dataclass
class FakeTerminology:
    unavailable: bool = False

    async def validate_code(
        self,
        *,
        system: str | None,
        code: str,
        display: str | None = None,
        version: str | None = None,
        value_set: str | None = None,
    ) -> ValidateCodeResult:
        if self.unavailable:
            raise TerminologyUnavailableError("terminology unavailable")
        return ValidateCodeResult(
            True,
            Coding(system, code, display, version),
            value_set=value_set,
        )

    async def lookup(self, *, system: str, code: str, version: str | None = None) -> LookupResult:
        return LookupResult(Coding(system, code, version=version))

    async def expand(
        self,
        *,
        value_set: str,
        filter_text: str | None = None,
        count: int | None = None,
        offset: int | None = None,
    ) -> ExpansionResult:
        del filter_text, count, offset
        return ExpansionResult(value_set, ())

    async def subsumes(
        self,
        *,
        system: str,
        code_a: str,
        code_b: str,
        version: str | None = None,
    ) -> SubsumesResult:
        return SubsumesResult(
            SubsumptionOutcome.NOT_SUBSUMED,
            Coding(system, code_a, version=version),
            Coding(system, code_b, version=version),
        )

    async def translate(
        self,
        *,
        system: str,
        code: str,
        target_system: str | None = None,
        concept_map: str | None = None,
    ) -> TranslateResult:
        del system, code, target_system, concept_map
        return TranslateResult(False)

    async def health(self, *, code_systems: Sequence[str] = ()) -> TerminologyHealth:
        del code_systems
        return TerminologyHealth(not self.unavailable)

    async def aclose(self) -> None:
        return None
