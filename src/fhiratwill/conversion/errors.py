"""PHI-safe conversion exceptions."""

from fhiratwill.errors import FhiratwillError


class ConversionError(FhiratwillError):
    """Base conversion failure; messages must contain no clinical content."""

    code = "conversion-error"


class ExtractionSchemaError(ConversionError):
    """The model output did not satisfy the strict extraction contract."""

    code = "extraction-schema-invalid"


class InvalidAudioError(ConversionError):
    """Audio was empty or exceeded the configured bound."""

    code = "invalid-audio"


class ProviderUnavailableError(ConversionError):
    """A provider failed without exposing its unsafe response."""

    code = "provider-unavailable"


class EgressPolicyError(ConversionError):
    """A provider call was refused before network access."""

    code = "egress-blocked"


class CostLimitError(EgressPolicyError):
    """A configured worst-case cost bound would be exceeded."""

    code = "cost-limit-exceeded"


__all__ = [
    "ConversionError",
    "CostLimitError",
    "EgressPolicyError",
    "ExtractionSchemaError",
    "InvalidAudioError",
    "ProviderUnavailableError",
]
