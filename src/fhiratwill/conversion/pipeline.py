"""Framework-neutral text and voice conversion pipelines."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final
from urllib.parse import urlparse

from fhiratwill.assembly import assemble_bundle
from fhiratwill.binding import bind_bundle
from fhiratwill.conversion.errors import EgressPolicyError, InvalidAudioError
from fhiratwill.conversion.extraction import parse_entities
from fhiratwill.conversion.models import (
    LlmClient,
    LlmInvocation,
    SpeechClient,
    SpeechInvocation,
    Text2FhirResult,
    Voice2FhirResult,
)
from fhiratwill.conversion.prompts import NARRATIVE_TO_ENTITIES, PROMPT_FINGERPRINT
from fhiratwill.deid import (
    NOOP_DEID_OBSERVER,
    DeclaredIdentifier,
    DeidObserver,
    DeidPolicy,
)
from fhiratwill.deid.core import minimize
from fhiratwill.terminology import TerminologyClient
from fhiratwill.validation import ValidationConfig, ValidationSpec, ValidatorClient, validate

DEFAULT_MAX_AUDIO_BYTES: Final = 20 * 1024 * 1024
_LOOPBACK: Final = frozenset({"localhost", "127.0.0.1", "::1"})


async def text2fhir(
    text: str,
    *,
    llm: LlmClient,
    invocation: LlmInvocation,
    seed: str,
    terminology: TerminologyClient | None = None,
    validator: ValidatorClient | None = None,
    validation_config: ValidationConfig | None = None,
    validation_spec: ValidationSpec | None = None,
    deid_policy: DeidPolicy | None = None,
    known_identifiers: Sequence[DeclaredIdentifier] = (),
    deid_observer: DeidObserver = NOOP_DEID_OBSERVER,
) -> Text2FhirResult:
    """Minimize, extract, restore, assemble, optionally bind, then validate."""
    minimization = minimize(
        text,
        policy=deid_policy or DeidPolicy(),
        known_identifiers=known_identifiers,
        observer=deid_observer,
    )
    try:
        user_prompt = NARRATIVE_TO_ENTITIES.render_user(narrative=minimization.safe_text)
        minimization.assert_safe_payload(
            {"system": NARRATIVE_TO_ENTITIES.system, "user": user_prompt}
        )
        extraction = await llm.complete_json(
            invocation,
            system_prompt=NARRATIVE_TO_ENTITIES.system,
            user_prompt=user_prompt,
        )
        minimization.assert_safe_payload(extraction.resource)
        entities = minimization.restore_entities(parse_entities(extraction.resource))
        assembled = assemble_bundle(entities, seed=seed)
        binding = (
            await bind_bundle(assembled.bundle, client=terminology)
            if terminology is not None
            else None
        )
        bundle = binding.bundle if binding is not None else assembled.bundle
        validation = await validate(
            bundle,
            validator=validator,
            terminology=terminology,
            config=validation_config,
            spec=validation_spec,
        )
        return Text2FhirResult(
            bundle=bundle,
            assembled=assembled,
            extraction=extraction,
            deidentification=minimization.result(),
            prompt_fingerprint=PROMPT_FINGERPRINT,
            entities=tuple(entities),
            binding=binding,
            validation=validation,
            notes=("terminology binding skipped",) if terminology is None else (),
        )
    finally:
        minimization.close()


async def voice2fhir(
    audio: bytes,
    *,
    media_type: str,
    speech: SpeechClient,
    speech_invocation: SpeechInvocation,
    llm: LlmClient,
    llm_invocation: LlmInvocation,
    seed: str,
    terminology: TerminologyClient | None = None,
    validator: ValidatorClient | None = None,
    validation_config: ValidationConfig | None = None,
    validation_spec: ValidationSpec | None = None,
    deid_policy: DeidPolicy | None = None,
    known_identifiers: Sequence[DeclaredIdentifier] = (),
    deid_observer: DeidObserver = NOOP_DEID_OBSERVER,
    allow_audio_egress: bool = False,
    max_audio_bytes: int = DEFAULT_MAX_AUDIO_BYTES,
) -> Voice2FhirResult:
    """Transcribe once, then run the transcript through the identical text pipeline."""
    if not audio:
        raise InvalidAudioError("audio must not be empty")
    if max_audio_bytes <= 0 or len(audio) > max_audio_bytes:
        raise InvalidAudioError("audio exceeds the configured byte limit")
    if not allow_audio_egress and not _is_loopback(speech_invocation.base_url):
        raise EgressPolicyError("raw audio egress requires explicit permission or loopback")
    dictation = await speech.transcribe(
        speech_invocation,
        audio=audio,
        media_type=media_type,
    )
    if not dictation.text.strip():
        raise InvalidAudioError("dictation contained no discernible speech")
    conversion = await text2fhir(
        dictation.text,
        llm=llm,
        invocation=llm_invocation,
        seed=seed,
        terminology=terminology,
        validator=validator,
        validation_config=validation_config,
        validation_spec=validation_spec,
        deid_policy=deid_policy,
        known_identifiers=known_identifiers,
        deid_observer=deid_observer,
    )
    return Voice2FhirResult(
        transcript=dictation.text,
        dictation=dictation,
        conversion=conversion,
    )


def _is_loopback(base_url: str | None) -> bool:
    return bool(base_url and (urlparse(base_url).hostname or "").lower() in _LOOPBACK)


__all__ = ["DEFAULT_MAX_AUDIO_BYTES", "text2fhir", "voice2fhir"]
