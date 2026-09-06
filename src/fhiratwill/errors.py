"""PHI-safe exception hierarchy for fail-closed library operations."""

from __future__ import annotations

from types import MappingProxyType
from typing import ClassVar, TypeAlias

SafeContext: TypeAlias = dict[str, str | int | float | bool]


class FhiratwillError(Exception):
    """Base error whose message and context must never contain clinical values."""

    code: ClassVar[str] = "internal-error"

    def __init__(
        self,
        message: str = "",
        *,
        safe_context: SafeContext | None = None,
        retry_after_s: int | None = None,
    ) -> None:
        super().__init__(message)
        self.safe_context = MappingProxyType(dict(safe_context or {}))
        self.retry_after_s = retry_after_s


class TerminologyError(FhiratwillError):
    code = "terminology-error"


class TerminologyUnavailableError(TerminologyError):
    code = "terminology-unavailable"


class UnknownValueSetError(TerminologyError):
    code = "unknown-value-set"


class TargetUnavailableError(FhiratwillError):
    code = "target-unavailable"


class ValidatorUnavailableError(FhiratwillError):
    code = "validator-unavailable"


class IgNotLoadedError(FhiratwillError):
    code = "ig-not-loaded"


class InvalidInputError(FhiratwillError):
    code = "invalid-input"


class DeidError(FhiratwillError):
    code = "deidentification-error"


class PhiMinimizationRequiredError(DeidError):
    code = "phi-minimization-required"


class PhiMinimizationFailedError(DeidError):
    code = "phi-minimization-failed"


class PhiMinimizationUnavailableError(DeidError):
    code = "phi-minimization-unavailable"


class AudioEgressNotPermittedError(DeidError):
    code = "audio-egress-not-permitted"


class LlmError(FhiratwillError):
    code = "llm-error"


class LlmAuthFailedError(LlmError):
    code = "llm-auth-failed"


class LlmQuotaExhaustedError(LlmError):
    code = "llm-quota-exhausted"


class LlmRateLimitedError(LlmError):
    code = "llm-rate-limited"


class LlmContextExceededError(LlmError):
    code = "llm-context-exceeded"


class LlmSchemaViolationError(LlmError):
    code = "llm-schema-violation"


class LlmContentFilteredError(LlmError):
    code = "llm-content-filtered"


class BudgetExceededError(LlmError):
    code = "budget-exceeded"


class EgressBlockedError(LlmError):
    code = "egress-blocked"


class PhiEgressNotAcknowledgedError(LlmError):
    code = "phi-egress-not-acknowledged"


__all__ = [
    "AudioEgressNotPermittedError",
    "BudgetExceededError",
    "DeidError",
    "EgressBlockedError",
    "FhiratwillError",
    "IgNotLoadedError",
    "InvalidInputError",
    "LlmAuthFailedError",
    "LlmContentFilteredError",
    "LlmContextExceededError",
    "LlmError",
    "LlmQuotaExhaustedError",
    "LlmRateLimitedError",
    "LlmSchemaViolationError",
    "PhiEgressNotAcknowledgedError",
    "PhiMinimizationFailedError",
    "PhiMinimizationRequiredError",
    "PhiMinimizationUnavailableError",
    "SafeContext",
    "TargetUnavailableError",
    "TerminologyError",
    "TerminologyUnavailableError",
    "UnknownValueSetError",
    "ValidatorUnavailableError",
]
