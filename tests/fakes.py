from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from fhiratwill import (
    Coding,
    ExpansionResult,
    LookupResult,
    SubsumesResult,
    SubsumptionOutcome,
    TerminologyHealth,
    TerminologyUnavailableError,
    TranslateResult,
    ValidateCodeResult,
)


@dataclass
class FakeTerminologyClient:
    membership: dict[str, bool] = field(default_factory=dict)
    expansions: dict[str, tuple[Coding, ...]] = field(default_factory=dict)
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
        del version
        if self.unavailable:
            raise TerminologyUnavailableError("terminology unavailable")
        return ValidateCodeResult(
            result=self.membership.get(code, True),
            coding=Coding(system, code, display),
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
        if self.unavailable:
            raise TerminologyUnavailableError("terminology unavailable")
        return ExpansionResult(value_set, self.expansions.get(value_set, ()))

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
