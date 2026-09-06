"""Typed transport-neutral conversion contracts and results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from pydantic import SecretStr

from fhiratwill.assembly import AssembledBundle
from fhiratwill.binding import BoundBundle
from fhiratwill.deid import DeidentifyResult
from fhiratwill.validation.models import ValidationReport


@dataclass(frozen=True, slots=True)
class LlmInvocation:
    provider: str
    model: str
    api_key: SecretStr
    base_url: str | None = None
    phi_egress_acknowledged: bool = False
    max_cost_usd: Decimal | None = None


@dataclass(frozen=True, slots=True)
class SpeechInvocation:
    provider: str
    model: str
    api_key: SecretStr
    base_url: str | None = None
    phi_egress_acknowledged: bool = False
    language: str | None = None
    max_cost_usd: Decimal | None = None


@dataclass(frozen=True, slots=True)
class LlmResult:
    resource: dict[str, Any]
    model: str
    usage: Mapping[str, int] = field(default_factory=dict)
    cost_usd: Decimal | None = None
    latency_ms: int = 0
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class DictationResult:
    """Text may contain PHI; provider errors must not."""

    text: str
    model: str
    usage: Mapping[str, int] = field(default_factory=dict)
    cost_usd: Decimal | None = None
    latency_ms: int = 0


@runtime_checkable
class LlmClient(Protocol):
    async def complete_json(
        self,
        invocation: LlmInvocation,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> LlmResult: ...


@runtime_checkable
class SpeechClient(Protocol):
    async def transcribe(
        self,
        invocation: SpeechInvocation,
        *,
        audio: bytes,
        media_type: str,
    ) -> DictationResult: ...


@dataclass(frozen=True, slots=True)
class Text2FhirResult:
    bundle: dict[str, Any]
    assembled: AssembledBundle
    extraction: LlmResult
    deidentification: DeidentifyResult
    prompt_fingerprint: str
    entities: Sequence[Mapping[str, str]]
    validation: ValidationReport
    binding: BoundBundle | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Voice2FhirResult:
    transcript: str
    dictation: DictationResult
    conversion: Text2FhirResult
    notes: tuple[str, ...] = ()

    @property
    def bundle(self) -> dict[str, Any]:
        return self.conversion.bundle


__all__ = [
    "DictationResult",
    "LlmClient",
    "LlmInvocation",
    "LlmResult",
    "SpeechClient",
    "SpeechInvocation",
    "Text2FhirResult",
    "Voice2FhirResult",
]
