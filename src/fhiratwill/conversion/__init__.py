"""Framework-neutral narrative and voice conversion."""

from fhiratwill.conversion.errors import (
    ConversionError,
    CostLimitError,
    EgressPolicyError,
    ExtractionSchemaError,
    InvalidAudioError,
    ProviderUnavailableError,
)
from fhiratwill.conversion.extraction import (
    MAX_EXTRACTED_ENTITIES,
    RESOURCE_CATALOG,
    ExtractedEntity,
    parse_entities,
)
from fhiratwill.conversion.models import (
    DictationResult,
    LlmClient,
    LlmInvocation,
    LlmResult,
    SpeechClient,
    SpeechInvocation,
    Text2FhirResult,
    Voice2FhirResult,
)
from fhiratwill.conversion.pipeline import DEFAULT_MAX_AUDIO_BYTES, text2fhir, voice2fhir
from fhiratwill.conversion.prompts import (
    PROMPT_FINGERPRINT,
    REVIEWED_PROMPT_FINGERPRINT,
    prompt_set_fingerprint,
)

__all__ = [
    "DEFAULT_MAX_AUDIO_BYTES",
    "MAX_EXTRACTED_ENTITIES",
    "PROMPT_FINGERPRINT",
    "RESOURCE_CATALOG",
    "REVIEWED_PROMPT_FINGERPRINT",
    "ConversionError",
    "CostLimitError",
    "DictationResult",
    "EgressPolicyError",
    "ExtractedEntity",
    "ExtractionSchemaError",
    "InvalidAudioError",
    "LlmClient",
    "LlmInvocation",
    "LlmResult",
    "ProviderUnavailableError",
    "SpeechClient",
    "SpeechInvocation",
    "Text2FhirResult",
    "Voice2FhirResult",
    "parse_entities",
    "prompt_set_fingerprint",
    "text2fhir",
    "voice2fhir",
]
